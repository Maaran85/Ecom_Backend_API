from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Dealer, User, OrderItem, Order, Product, DealerRemittance
from models.settlement import Settlement, SettlementAdjustment
from models.pending_settlement_adjustment import PendingSettlementAdjustment
from core.enums import SettlementStatus, AdjustmentType
from core.money import money, money_2dp
from services.settlement_status_service import assert_transition
from services.settlement_calculator import calculate_settlement, SettlementCalculationResult
from services.settlement_builder import build_and_persist_settlement
from services.financial_year_service import (
    financial_year_for,
    as_date,
    get_or_create_fy_summary,
    apply_to_fy_summary,
    revert_from_fy_summary,
)
from services.configuration_service import get_active_tds_config_required, ConfigurationError


async def preview_settlement(
    db: AsyncSession,
    dealer: Dealer,
    eligible_items: List[Tuple[OrderItem, Order, Product, Dealer]],
    settlement_date: date,
) -> dict:
    """
    Non-persisting preview of a settlement (dry-run). Returns data shaped for
    SettlementPreviewOut.
    """
    fy_label, fy_start, fy_end = await _resolve_period_and_fy(settlement_date)
    fy_summary = await get_or_create_fy_summary(db, dealer.id, fy_label, fy_start, fy_end)

    pending = await _collect_pending_adjustments(db, dealer.id)
    adjustment_total = money(sum(p.amount for p in pending))

    calc: SettlementCalculationResult = await calculate_settlement(
        db,
        dealer,
        eligible_items,
        fy_summary=fy_summary,
        adjustment_total=adjustment_total,
    )

    items = [
        {
            "order_item_id": line.item.id,
            "order_id": line.order.id,
            "order_number": line.order.order_number,
            "gross_sale_amount": float(money_2dp(line.gross_sale)),
            "marketplace_fee": float(money_2dp(line.marketplace_fee)),
            "marketing_fee": float(money_2dp(line.marketing_fee)),
            "shipping_received": float(money_2dp(line.shipping_received)),
            "logistics_charge": float(money_2dp(line.logistics_charge)),
            "tds_base": float(money_2dp(line.tds_base)),
            "tds_rate": float(line.tds_rate),
            "tds_amount": float(money_2dp(line.tds_amount)),
            "tds_exempt_portion": float(money_2dp(line.tds_exempt_portion)),
            "net_payable": float(line.net_payable),
        }
        for line in calc.lines
    ]

    return {
        "dealer_id": dealer.id,
        "financial_year": fy_label,
        "item_count": len(calc.lines),
        "gross_sale_amount": float(money_2dp(calc.gross_sale_total)),
        "total_marketplace_fee": float(money_2dp(calc.marketplace_fee_total)),
        "total_marketing_fee": float(money_2dp(calc.marketing_fee_total)),
        "total_shipping_received": float(money_2dp(calc.shipping_received_total)),
        "total_logistics_charge": float(money_2dp(calc.logistics_charge_total)),
        "total_gst_on_fees": float(money_2dp(calc.gst_on_fees_total)),
        "gross_tds_base": float(money_2dp(calc.tds_base_total)),
        "tds_exempt_portion": float(money_2dp(calc.tds_exempt_total)),
        "total_tds": float(money_2dp(calc.tds_total)),
        "tds_rate_applied": float(calc.tds_rate),
        "net_payable": float(calc.net_payable),
        "items": items,
    }


async def _resolve_period_and_fy(settlement_date: date):
    fy_label, fy_start, fy_end = financial_year_for(settlement_date)
    return fy_label, fy_start, fy_end


async def _collect_pending_adjustments(db: AsyncSession, dealer_id) -> List[PendingSettlementAdjustment]:
    result = await db.execute(
        select(PendingSettlementAdjustment)
        .where(
            PendingSettlementAdjustment.dealer_id == dealer_id,
            PendingSettlementAdjustment.applied_to_settlement_id.is_(None),
        )
        .order_by(PendingSettlementAdjustment.created_at.asc())
    )
    return result.scalars().all()


async def generate_settlement(
    db: AsyncSession,
    dealer: Dealer,
    eligible_items: List[Tuple[OrderItem, Order, Product, Dealer]],
    *,
    settlement_date: date,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    notes: Optional[str] = None,
) -> Settlement:
    """
    Computes and persists a GENERATED settlement for one dealer.

    Pending adjustments (returns after a previous PAYMENT) are absorbed into
    this settlement's net as an adjustment line.
    """
    if not eligible_items:
        raise ValueError("No eligible order items to settle")

    fy_label, fy_start, fy_end = await _resolve_period_and_fy(settlement_date)

    # Absorb pending post-payment adjustments into this settlement
    pending = await _collect_pending_adjustments(db, dealer.id)
    adjustment_total = money(sum(p.amount for p in pending))

    fy_summary = await get_or_create_fy_summary(db, dealer.id, fy_label, fy_start, fy_end)

    calc: SettlementCalculationResult = await calculate_settlement(
        db,
        dealer,
        eligible_items,
        fy_summary=fy_summary,
        adjustment_total=adjustment_total,
    )

    period_start = period_start or min(as_date(o.created_at) for _, o, _, _ in eligible_items)
    period_end = period_end or max(as_date(o.created_at) for _, o, _, _ in eligible_items)

    adjustment_rows: List[Tuple[SettlementAdjustment, str]] = []
    for p in pending:
        adj = SettlementAdjustment(
            order_id=p.order_id,
            order_item_id=p.order_item_id,
            source_settlement_id=p.source_settlement_id,
            type=p.type,
            reason=p.reason,
            amount=p.amount,
            reference=p.reference,
        )
        adjustment_rows.append((adj, p.reason))

    settlement = await build_and_persist_settlement(
        db,
        calc,
        period_start=period_start,
        period_end=period_end,
        fy_label=fy_label,
        fy_start=fy_start,
        fy_end=fy_end,
        settlement_date=settlement_date,
        adjustment_rows=adjustment_rows,
        notes=notes,
    )

    # Mark pending adjustments as applied
    if pending:
        for p in pending:
            p.applied_to_settlement_id = settlement.id

    # Transition DRAFT -> GENERATED
    assert_transition(settlement.status, SettlementStatus.GENERATED)
    settlement.status = SettlementStatus.GENERATED
    settlement.generated_at = datetime.now(timezone.utc)

    # FY summary update (official at generation so subsequent generated settlements read updated cumulative sales)
    apply_to_fy_summary(
        fy_summary,
        gross_sale=settlement.gross_sale_amount,
        tds_exempt=settlement.tds_exempt_portion,
        tds_applied=settlement.gross_tds_base,
        tds_amount=settlement.total_tds,
    )
    await db.flush()

    return settlement


async def _notify_dealer_users(db: AsyncSession, dealer_id, status: str, settlement_number: str, data: dict = None) -> None:
    """Notify the dealer's user accounts about a settlement status change."""
    try:
        from sqlalchemy import select
        from models.user import User
        result = await db.execute(
            select(User.id).where(User.dealer_id == dealer_id, User.is_active.is_(True))
        )
        user_ids = [r[0] for r in result.all()]
        if not user_ids:
            return
        from services.notification import AppNotificationService
        await AppNotificationService.notify_settlement(
            db,
            dealer_user_ids=user_ids,
            status=status,
            settlement_number=settlement_number or f"STL-{settlement_number}",
            data=data or {"settlement_number": settlement_number},
        )
    except Exception as e:  # notifications must never block the settlement flow
        import logging
        logging.getLogger(__name__).warning(f"Failed to notify dealer {dealer_id}: {e}")


async def approve_settlement(
    db: AsyncSession,
    settlement: Settlement,
    admin: User,
    notes: Optional[str] = None,
) -> Settlement:
    """
    GENERATED -> APPROVED. Creates the payout remittance record and commits the
    numbers to the dealer's FY summary (exemption threshold tracking).
    """
    assert_transition(settlement.status, SettlementStatus.APPROVED)
    if not settlement.items:
        raise ValueError("Cannot approve an empty settlement")

    if settlement.remittance_id is None:
        remittance = DealerRemittance(
            dealer_id=settlement.dealer_id,
            amount=settlement.net_payable,
            status="pending",
            type="payout",
            notes=notes,
        )
        db.add(remittance)
        await db.flush()
        settlement.remittance_id = remittance.id

    settlement.status = SettlementStatus.APPROVED
    settlement.approved_at = datetime.now(timezone.utc)
    settlement.approved_by = admin.id
    if notes:
        settlement.notes = notes

    # Note: FY summary update occurs during generate_settlement() so subsequent
    # generated batches read updated cumulative FY sales. Do NOT update here to avoid double counting.

    await _notify_dealer_users(
        db, settlement.dealer_id, "approved",
        settlement.settlement_number,
        data={"settlement_id": settlement.id, "net_payable": settlement.net_payable},
    )

    return settlement


async def mark_settlement_paid(
    db: AsyncSession,
    settlement: Settlement,
    admin: User,
    reference_no: Optional[str] = None,
    payment_method: Optional[str] = None,
    payment_date: Optional[date] = None,
    notes: Optional[str] = None,
) -> Settlement:
    """APPROVED -> PAID. Records the actual payment against the remittance."""
    assert_transition(settlement.status, SettlementStatus.PAID)
    if settlement.remittance_id is None:
        raise ValueError("Settlement has no remittance record; approve it first")

    remittance = await db.get(DealerRemittance, settlement.remittance_id)
    if remittance is None:
        raise ValueError("Settlement remittance record not found")

    remittance.status = "completed"
    remittance.reference_no = reference_no or remittance.reference_no
    remittance.payment_method = payment_method or remittance.payment_method
    remittance.payment_date = payment_date
    remittance.confirmed_at = datetime.now(timezone.utc)
    remittance.confirmed_by_admin_id = admin.id
    if notes:
        remittance.notes = notes

    settlement.status = SettlementStatus.PAID
    settlement.paid_at = datetime.now(timezone.utc)
    settlement.paid_by = admin.id

    await _notify_dealer_users(
        db, settlement.dealer_id, "paid",
        settlement.settlement_number,
        data={"settlement_id": settlement.id, "reference_no": reference_no},
    )

    return settlement


async def cancel_settlement(
    db: AsyncSession,
    settlement: Settlement,
    admin: User,
    reason: str,
) -> Settlement:
    """DRAFT/GENERATED -> CANCELLED. Remittance is never created for a cancelled settlement."""
    assert_transition(settlement.status, SettlementStatus.CANCELLED)
    if settlement.status in (SettlementStatus.GENERATED, SettlementStatus.APPROVED):
        fy_summary = await get_or_create_fy_summary(
            db,
            settlement.dealer_id,
            settlement.financial_year,
            settlement.fy_start_date,
            settlement.fy_end_date,
        )
        revert_from_fy_summary(
            fy_summary,
            gross_sale=settlement.gross_sale_amount,
            tds_exempt=settlement.tds_exempt_portion,
            tds_applied=settlement.gross_tds_base,
            tds_amount=settlement.total_tds,
        )
        await db.flush()

    settlement.status = SettlementStatus.CANCELLED
    settlement.cancelled_at = datetime.now(timezone.utc)
    settlement.cancelled_by = admin.id
    settlement.cancel_reason = reason
    return settlement


async def queue_post_settlement_adjustment(
    db: AsyncSession,
    dealer_id,
    *,
    type: AdjustmentType,
    reason: str,
    amount: float,
    order_id: Optional[int] = None,
    order_item_id: Optional[int] = None,
    source_settlement_id: Optional[int] = None,
    reference: Optional[str] = None,
    created_by: Optional[int] = None,
) -> PendingSettlementAdjustment:
    """Queue a credit/debit to be absorbed by the dealer's next settlement."""
    pending = PendingSettlementAdjustment(
        dealer_id=dealer_id,
        order_id=order_id,
        order_item_id=order_item_id,
        source_settlement_id=source_settlement_id,
        type=type,
        reason=reason,
        amount=amount,
        reference=reference,
        created_by=created_by,
    )
    db.add(pending)
    await db.flush()
    return pending
