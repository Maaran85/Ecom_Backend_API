from datetime import date, datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID
from services.financial_year_service import IST_TZ

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.permissions import (
    require_admin, require_dealer_or_admin, get_current_active_user,
)
from core.enums import SettlementStatus, AdjustmentType
from models import User, Dealer, OrderItem
from models.settlement import Settlement, SettlementItem
from schemas.settlement import (
    GenerateSettlementRequest, SettlementPreviewOut,
    SettlementOut, SettlementSummaryOut,
    SettlementApproveRequest, SettlementPaidRequest, SettlementCancelRequest,
    SettlementAdjustmentCreate,
)
from services.settlement_eligibility_service import get_eligible_order_items
from services.settlement_workflow import (
    preview_settlement,
    generate_settlement,
    approve_settlement,
    mark_settlement_paid,
    cancel_settlement,
    queue_post_settlement_adjustment,
)
from services.audit import log_audit

router = APIRouter()


async def _load_settlement(db: AsyncSession, settlement_id: int) -> Settlement:
    result = await db.execute(
        select(Settlement)
        .options(
            selectinload(Settlement.items).selectinload(SettlementItem.order_item).selectinload(OrderItem.product),
            selectinload(Settlement.items).selectinload(SettlementItem.order),
            selectinload(Settlement.adjustments),
        )
        .where(Settlement.id == settlement_id)
    )
    return result.scalar_one_or_none()


async def _dealer_ids_with_eligible_items(db: AsyncSession, as_of: Optional[datetime] = None) -> List[UUID]:
    """Dealers who currently have eligible (matured) order items."""
    from services.settlement_eligibility_service import get_eligible_order_items
    items = await get_eligible_order_items(db, as_of=as_of)
    dealers = {dealer.id for _, _, _, dealer in items}
    return list(dealers)


# ---------------------------------------------------------------------------
# Admin: generate / list / detail / approve / pay / cancel
# ---------------------------------------------------------------------------

@router.post(
    "/admin/settlements/generate",
    response_model=None,  # handled manually: dry_run → dict, real → List[SettlementSummaryOut]
)
async def generate_settlements(
    req: GenerateSettlementRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Generates settlements for one (or all) dealer(s). Eligible order items are
    those delivered whose return window has matured and which aren't already
    settled. dry_run=true returns a preview without persisting anything.
    """
    current_ist = datetime.now(timezone.utc).astimezone(IST_TZ)
    settlement_date = req.period_end or (current_ist.date() - timedelta(days=1))

    naive_eod = datetime.combine(settlement_date, datetime.max.time())
    localized_eod = naive_eod.replace(tzinfo=IST_TZ)
    as_of = localized_eod.astimezone(timezone.utc)

    dealer_ids: List[UUID]
    if req.dealer_id:
        dealer_ids = [req.dealer_id]
    else:
        dealer_ids = await _dealer_ids_with_eligible_items(db, as_of=as_of)

    if not dealer_ids:
        # dry_run with zero eligible items is a normal / expected state (all items are
        # already settled, in-progress, or returned).  Return 200 with an empty preview
        # list so the frontend can display a friendly "nothing to settle" message.
        # For actual generation (dry_run=false) we still raise 400 to prevent an
        # accidental no-op confirmation.
        if req.dry_run:
            return {"dry_run": True, "previews": []}
        raise HTTPException(status_code=400, detail="No eligible order items found")

    results = []
    generated_settlements: List[Settlement] = []  # collect ORM objects for real generation
    dealer_map: dict = {}  # dealer_id → Dealer, reused for response building

    for dealer_id in dealer_ids:
        dealer = await db.get(Dealer, dealer_id)
        if not dealer:
            continue
        dealer_map[dealer_id] = dealer

        eligible = await get_eligible_order_items(
            db, dealer_id=dealer_id, as_of=as_of, for_update=not req.dry_run
        )
        if not eligible:
            if req.dealer_id and not req.dry_run:
                raise HTTPException(
                    status_code=400,
                    detail=f"No eligible order items found for dealer {dealer_id}."
                )
            continue

        if req.dry_run:
            preview = await preview_settlement(db, dealer, eligible, settlement_date)
            results.append(SettlementPreviewOut(**preview))
            continue

        settlement = await generate_settlement(
            db,
            dealer,
            eligible,
            settlement_date=settlement_date,
            period_start=req.period_start,
            period_end=req.period_end,
        )
        await log_audit(
            db, admin, "GENERATE", "settlement",
            resource_id=str(settlement.id),
            new_values={"dealer_id": str(dealer.id), "net_payable": settlement.net_payable},
        )
        await db.flush()
        generated_settlements.append((settlement, dealer))

    await db.commit()

    if req.dry_run:
        return {"dry_run": True, "previews": [r.model_dump() for r in results]}

    # Build SettlementSummaryOut for each generated settlement.
    # Refresh each settlement after commit so item counts reflect persisted rows.
    summary_results = []
    for settlement, dealer in generated_settlements:
        await db.refresh(settlement)
        # Load items count via fresh query (settlement.items may be unloaded after flush/commit)
        items_res = await db.execute(
            select(SettlementItem).where(SettlementItem.settlement_id == settlement.id)
        )
        items = items_res.scalars().all()
        summary_results.append(SettlementSummaryOut(
            id=settlement.id,
            settlement_number=settlement.settlement_number,
            dealer_id=settlement.dealer_id,
            dealer_name=dealer.business_name,
            status=settlement.status,
            financial_year=settlement.financial_year,
            period_start=settlement.period_start,
            period_end=settlement.period_end,
            gross_sale_amount=settlement.gross_sale_amount,
            total_tds=settlement.total_tds,
            net_payable=settlement.net_payable,
            item_count=len(items),
            generated_at=settlement.generated_at,
            paid_at=settlement.paid_at,
            created_at=settlement.created_at,
        ))

    return [s.model_dump() for s in summary_results]



@router.get("/admin/settlements", response_model=List[SettlementSummaryOut])
async def list_admin_settlements(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    dealer_id: Optional[UUID] = None,
    financial_year: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    query = select(Settlement).options(selectinload(Settlement.items))
    if status_filter:
        try:
            query = query.where(Settlement.status == SettlementStatus(status_filter))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")
    if dealer_id:
        query = query.where(Settlement.dealer_id == dealer_id)
    if financial_year:
        query = query.where(Settlement.financial_year == financial_year)

    query = query.order_by(Settlement.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    settlements = result.scalars().all()

    dealer_ids = {s.dealer_id for s in settlements}
    dealers = {}
    if dealer_ids:
        dealer_rows = await db.execute(select(Dealer).where(Dealer.id.in_(dealer_ids)))
        dealers = {d.id: d for d in dealer_rows.scalars().all()}

    return [
        SettlementSummaryOut(
            id=s.id,
            settlement_number=s.settlement_number,
            dealer_id=s.dealer_id,
            dealer_name=dealers[s.dealer_id].business_name if s.dealer_id in dealers else None,
            status=s.status,
            financial_year=s.financial_year,
            period_start=s.period_start,
            period_end=s.period_end,
            gross_sale_amount=s.gross_sale_amount,
            total_tds=s.total_tds,
            net_payable=s.net_payable,
            item_count=len(s.items) if s.items else 0,
            generated_at=s.generated_at,
            paid_at=s.paid_at,
            created_at=s.created_at,
        )
        for s in settlements
    ]


@router.get("/admin/settlements/{settlement_id}", response_model=SettlementOut)
async def get_admin_settlement(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    settlement = await _load_settlement(db, settlement_id)
    if not settlement:
        raise HTTPException(status_code=404, detail="Settlement not found")
    return settlement


@router.post("/admin/settlements/{settlement_id}/approve", response_model=SettlementOut)
async def approve_settlement_endpoint(
    settlement_id: int,
    req: SettlementApproveRequest = SettlementApproveRequest(),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    settlement = await _load_settlement(db, settlement_id)
    if not settlement:
        raise HTTPException(status_code=404, detail="Settlement not found")
    settlement = await approve_settlement(db, settlement, admin, notes=req.notes)
    await log_audit(
        db, admin, "APPROVE", "settlement",
        resource_id=str(settlement.id),
        new_values={"net_payable": settlement.net_payable, "remittance_id": settlement.remittance_id},
    )
    await db.commit()
    await db.refresh(settlement)
    return settlement


@router.post("/admin/settlements/{settlement_id}/paid", response_model=SettlementOut)
async def mark_settlement_paid_endpoint(
    settlement_id: int,
    req: SettlementPaidRequest = SettlementPaidRequest(),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    settlement = await _load_settlement(db, settlement_id)
    if not settlement:
        raise HTTPException(status_code=404, detail="Settlement not found")
    settlement = await mark_settlement_paid(
        db, settlement, admin,
        reference_no=req.reference_no,
        payment_method=req.payment_method,
        payment_date=req.payment_date,
        notes=req.notes,
    )
    await log_audit(
        db, admin, "PAID", "settlement",
        resource_id=str(settlement.id),
        new_values={"net_payable": settlement.net_payable, "reference_no": req.reference_no},
    )
    await db.commit()
    await db.refresh(settlement)
    return settlement


@router.post("/admin/settlements/{settlement_id}/cancel", response_model=SettlementOut)
async def cancel_settlement_endpoint(
    settlement_id: int,
    req: SettlementCancelRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    settlement = await _load_settlement(db, settlement_id)
    if not settlement:
        raise HTTPException(status_code=404, detail="Settlement not found")
    settlement = await cancel_settlement(db, settlement, admin, reason=req.reason)
    await log_audit(
        db, admin, "CANCEL", "settlement",
        resource_id=str(settlement.id),
        new_values={"reason": req.reason},
    )
    await db.commit()
    await db.refresh(settlement)
    return settlement


@router.post("/admin/settlements/{settlement_id}/adjustments", response_model=SettlementOut)
async def add_adjustment_to_settlement(
    settlement_id: int,
    req: SettlementAdjustmentCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Manually attach a credit/debit adjustment to a DRAFT settlement."""
    settlement = await _load_settlement(db, settlement_id)
    if not settlement:
        raise HTTPException(status_code=404, detail="Settlement not found")
    if settlement.status != SettlementStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Adjustments can only be added to DRAFT settlements")

    from models.settlement import SettlementAdjustment
    settlement.adjustments.append(
        SettlementAdjustment(
            order_id=req.order_id,
            order_item_id=req.order_item_id,
            source_settlement_id=req.source_settlement_id,
            type=req.type,
            reason=req.reason,
            amount=req.amount,
            reference=req.reference,
        )
    )
    settlement.total_adjustments += (
        req.amount if req.type == AdjustmentType.CREDIT else -req.amount
    )
    await db.commit()
    await db.refresh(settlement)
    return settlement


@router.post("/admin/pending-adjustments")
async def create_pending_adjustment(
    req: SettlementAdjustmentCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Queue a credit/debit that flows into the dealer's NEXT settlement
    (used for returns approved after a settlement was already PAID).
    """
    if not req.source_settlement_id:
        raise HTTPException(status_code=400, detail="source_settlement_id is required for post-payment adjustments")

    source = await db.get(Settlement, req.source_settlement_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source settlement not found")

    pending = await queue_post_settlement_adjustment(
        db,
        dealer_id=source.dealer_id,
        type=req.type,
        reason=req.reason,
        amount=req.amount,
        order_id=req.order_id,
        order_item_id=req.order_item_id,
        source_settlement_id=req.source_settlement_id,
        reference=req.reference,
        created_by=admin.id,
    )
    await db.commit()
    return {
        "id": pending.id,
        "dealer_id": pending.dealer_id,
        "type": pending.type.value,
        "reason": pending.reason,
        "amount": pending.amount,
        "applied_to_settlement_id": pending.applied_to_settlement_id,
    }


# ---------------------------------------------------------------------------
# Dealer: list / detail own settlements
# ---------------------------------------------------------------------------

@router.get("/dealers/settlements", response_model=List[SettlementSummaryOut])
async def list_my_settlements(
    financial_year: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    if not user.dealer_id:
        raise HTTPException(status_code=403, detail="User is not associated with a dealer")
    query = select(Settlement).options(selectinload(Settlement.items)).where(Settlement.dealer_id == user.dealer_id)
    if financial_year:
        query = query.where(Settlement.financial_year == financial_year)
    query = query.order_by(Settlement.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    settlements = result.scalars().all()
    return [
        SettlementSummaryOut(
            id=s.id,
            settlement_number=s.settlement_number,
            dealer_id=s.dealer_id,
            status=s.status,
            financial_year=s.financial_year,
            period_start=s.period_start,
            period_end=s.period_end,
            gross_sale_amount=s.gross_sale_amount,
            total_tds=s.total_tds,
            net_payable=s.net_payable,
            item_count=len(s.items) if s.items else 0,
            generated_at=s.generated_at,
            paid_at=s.paid_at,
            created_at=s.created_at,
        )
        for s in settlements
    ]


@router.get("/dealers/settlements/{settlement_id}", response_model=SettlementOut)
async def get_my_settlement(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    if not user.dealer_id:
        raise HTTPException(status_code=403, detail="User is not associated with a dealer")
    settlement = await _load_settlement(db, settlement_id)
    if not settlement:
        raise HTTPException(status_code=404, detail="Settlement not found")
    if settlement.dealer_id != user.dealer_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return settlement


@router.get("/dealers/settlements/{settlement_id}/pdf")
async def download_dealer_settlement_pdf(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    from fastapi.responses import StreamingResponse
    from services.invoice_pdf import generate_dealer_settlement_pdf

    if not user.dealer_id and user.role.value not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="User is not associated with a dealer")
    
    settlement = await _load_settlement(db, settlement_id)
    if not settlement:
        raise HTTPException(status_code=404, detail="Settlement not found")
    if user.role.value not in ["admin", "super_admin"] and settlement.dealer_id != user.dealer_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    dealer = await db.get(Dealer, settlement.dealer_id)
    pdf_buffer = generate_dealer_settlement_pdf(settlement, dealer, settlement.items)
    
    filename = f"Dealer_Settlement_{settlement.settlement_number or settlement.id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )


@router.get("/admin/settlements/{settlement_id}/pdf")
async def download_admin_settlement_pdf(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from fastapi.responses import StreamingResponse
    from services.invoice_pdf import generate_dealer_settlement_pdf

    settlement = await _load_settlement(db, settlement_id)
    if not settlement:
        raise HTTPException(status_code=404, detail="Settlement not found")
    
    dealer = await db.get(Dealer, settlement.dealer_id)
    pdf_buffer = generate_dealer_settlement_pdf(settlement, dealer, settlement.items)
    
    filename = f"Dealer_Settlement_{settlement.settlement_number or settlement.id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )


