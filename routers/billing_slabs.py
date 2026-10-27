from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.database import get_db
from core.permissions import require_admin, require_super_admin
from models.user import User
from models.billing_slab import BillingSlab
from schemas.billing_slab import BillingSlabCreate, BillingSlabUpdate, BillingSlabOut
from services.fee_service import validate_no_overlap, resolve_slab_gst_rate, SettlementFeeError, get_all_active_tax_categories
from services.configuration_service import get_fee_config
from services.audit import log_audit

router = APIRouter(prefix="/api/v1/admin/billing-slabs", tags=["Billing Slabs"])


@router.get("", response_model=List[BillingSlabOut])
async def list_billing_slabs(
    category_key: Optional[str] = Query(None, description="Filter by category: auction_marketplace, marketplace, marketing, logistics, referral, referral_purchase, spin_win"),
    active_only: bool = Query(False, description="Filter only active slabs"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    stmt = select(BillingSlab).order_by(BillingSlab.category_key, BillingSlab.min_price)
    if category_key:
        stmt = stmt.where(BillingSlab.category_key == category_key)
    if active_only:
        stmt = stmt.where(BillingSlab.is_active == True)
    
    res = await db.execute(stmt)
    return res.scalars().all()




async def _sync_category_fee_configurations(db: AsyncSession, category_key: str, gst_type: Optional[str]) -> None:
    """Synchronizes FeeConfiguration with BillingSlab gst_type so slab and engine remain in lockstep."""
    if not gst_type:
        return
    try:
        cats = await get_all_active_tax_categories(db)
        disp_rate, factor, is_app = resolve_slab_gst_rate(gst_type, category_key, tax_categories=cats)
    except SettlementFeeError:
        return
    
    fee_keys = []
    if category_key in ("marketplace", "auction_marketplace"):
        fee_keys = ["marketplace_fee"]
    elif category_key == "marketing":
        fee_keys = ["marketing_fee"]
    elif category_key == "logistics":
        fee_keys = ["partner_logistics_fee", "customer_shipping_gst_rate"]
    
    for f_key in fee_keys:
        f_cfg = await get_fee_config(db, f_key)
        if f_cfg:
            f_cfg.gst_rate = float(factor)
            f_cfg.is_gst_applicable = is_app
            if f_key == "customer_shipping_gst_rate":
                f_cfg.value = float(factor)
            db.add(f_cfg)

@router.post("", response_model=BillingSlabOut, status_code=status.HTTP_201_CREATED)
async def create_billing_slab(
    data: BillingSlabCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    if data.category_key == "logistics" and data.is_active:
        if data.customer_percentage is None and getattr(data, "customer_amount", None) is None:
            raise HTTPException(
                status_code=400,
                detail="Active Logistics billing slab requires 'customer_percentage' or 'customer_amount' to prevent unserviceable or missing delivery fee calculations."
            )

    # Validate no overlapping active slab range
    if data.is_active:
        try:
            await validate_no_overlap(db, data.category_key, data.min_price, data.max_price)
        except ValueError as val_err:
            raise HTTPException(status_code=400, detail=str(val_err))

    if data.gst_type:
        try:
            cats = await get_all_active_tax_categories(db)
            resolve_slab_gst_rate(data.gst_type, data.category_key, tax_categories=cats)
        except SettlementFeeError as sfe:
            raise HTTPException(status_code=400, detail=str(sfe))

    slab = BillingSlab(**data.model_dump())
    db.add(slab)
    await db.flush()

    if data.gst_type and data.is_active:
        await _sync_category_fee_configurations(db, data.category_key, data.gst_type)

    new_dict = {c.name: getattr(slab, c.name).isoformat() if hasattr(getattr(slab, c.name), "isoformat") else getattr(slab, c.name) for c in slab.__table__.columns}
    await log_audit(db, admin, "CREATE", "billing_slab", resource_id=str(slab.id), new_values=new_dict)
    await db.commit()
    await db.refresh(slab)
    return slab


@router.put("/{slab_id}", response_model=BillingSlabOut)
async def update_billing_slab(
    slab_id: int,
    data: BillingSlabUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    slab = await db.get(BillingSlab, slab_id)
    if not slab:
        raise HTTPException(status_code=404, detail="Billing slab not found")

    target_min = data.min_price if data.min_price is not None else slab.min_price
    target_max = data.max_price if data.max_price is not None else slab.max_price
    target_active = data.is_active if data.is_active is not None else slab.is_active
    target_cust_pct = data.customer_percentage if data.customer_percentage is not None else slab.customer_percentage
    target_cust_amt = data.customer_amount if hasattr(data, "customer_amount") and data.customer_amount is not None else getattr(slab, "customer_amount", None)

    if slab.category_key == "logistics" and target_active:
        if target_cust_pct is None and target_cust_amt is None:
            raise HTTPException(
                status_code=400,
                detail=f"Active Logistics billing slab ID {slab.id} requires 'customer_percentage' or 'customer_amount' to prevent unserviceable or missing delivery fee calculations."
            )

    if target_active:
        try:
            await validate_no_overlap(db, slab.category_key, target_min, target_max, exclude_id=slab.id)
        except ValueError as val_err:
            raise HTTPException(status_code=400, detail=str(val_err))

    target_gst_type = data.gst_type if data.gst_type is not None else slab.gst_type
    if data.gst_type is not None and data.gst_type:
        try:
            cats = await get_all_active_tax_categories(db)
            resolve_slab_gst_rate(data.gst_type, slab.category_key, tax_categories=cats)
        except SettlementFeeError as sfe:
            raise HTTPException(status_code=400, detail=str(sfe))

    old_dict = {c.name: getattr(slab, c.name).isoformat() if hasattr(getattr(slab, c.name), "isoformat") else getattr(slab, c.name) for c in slab.__table__.columns}
    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(slab, field, val)
    new_dict = {c.name: getattr(slab, c.name).isoformat() if hasattr(getattr(slab, c.name), "isoformat") else getattr(slab, c.name) for c in slab.__table__.columns}

    if target_gst_type and target_active:
        await _sync_category_fee_configurations(db, slab.category_key, target_gst_type)

    await db.flush()
    await log_audit(db, admin, "UPDATE", "billing_slab", resource_id=str(slab.id), old_values=old_dict, new_values=new_dict)
    await db.commit()
    await db.refresh(slab)
    return slab


@router.delete("/{slab_id}", response_model=BillingSlabOut)
async def deactivate_billing_slab(
    slab_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    slab = await db.get(BillingSlab, slab_id)
    if not slab:
        raise HTTPException(status_code=404, detail="Billing slab not found")

    new_active = not slab.is_active
    if slab.category_key == "logistics" and new_active:
        if slab.customer_percentage is None and getattr(slab, "customer_amount", None) is None:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot activate Logistics billing slab ID {slab.id} without a configured 'customer_percentage' or 'customer_amount'."
            )

    if new_active:
        try:
            await validate_no_overlap(db, slab.category_key, slab.min_price, slab.max_price, exclude_id=slab.id)
        except ValueError as val_err:
            raise HTTPException(status_code=400, detail=str(val_err))

    old_dict = {c.name: getattr(slab, c.name).isoformat() if hasattr(getattr(slab, c.name), "isoformat") else getattr(slab, c.name) for c in slab.__table__.columns}
    slab.is_active = new_active
    new_dict = {c.name: getattr(slab, c.name).isoformat() if hasattr(getattr(slab, c.name), "isoformat") else getattr(slab, c.name) for c in slab.__table__.columns}

    action_label = "ACTIVATE" if slab.is_active else "DEACTIVATE"
    await db.flush()
    await log_audit(db, admin, action_label, "billing_slab", resource_id=str(slab.id), old_values=old_dict, new_values=new_dict)
    await db.commit()
    await db.refresh(slab)
    return slab
