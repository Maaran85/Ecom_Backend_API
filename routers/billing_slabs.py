from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.database import get_db
from core.permissions import require_admin, require_super_admin
from models.user import User
from models.billing_slab import BillingSlab
from schemas.billing_slab import BillingSlabCreate, BillingSlabUpdate, BillingSlabOut
from services.fee_service import validate_no_overlap
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


@router.post("", response_model=BillingSlabOut, status_code=status.HTTP_201_CREATED)
async def create_billing_slab(
    data: BillingSlabCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    # Validate no overlapping active slab range
    if data.is_active:
        try:
            await validate_no_overlap(db, data.category_key, data.min_price, data.max_price)
        except ValueError as val_err:
            raise HTTPException(status_code=400, detail=str(val_err))

    slab = BillingSlab(**data.model_dump())
    db.add(slab)
    await db.flush()

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

    if target_active:
        try:
            await validate_no_overlap(db, slab.category_key, target_min, target_max, exclude_id=slab.id)
        except ValueError as val_err:
            raise HTTPException(status_code=400, detail=str(val_err))

    old_dict = {c.name: getattr(slab, c.name).isoformat() if hasattr(getattr(slab, c.name), "isoformat") else getattr(slab, c.name) for c in slab.__table__.columns}
    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(slab, field, val)
    new_dict = {c.name: getattr(slab, c.name).isoformat() if hasattr(getattr(slab, c.name), "isoformat") else getattr(slab, c.name) for c in slab.__table__.columns}

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

    old_dict = {c.name: getattr(slab, c.name).isoformat() if hasattr(getattr(slab, c.name), "isoformat") else getattr(slab, c.name) for c in slab.__table__.columns}
    slab.is_active = not slab.is_active
    new_dict = {c.name: getattr(slab, c.name).isoformat() if hasattr(getattr(slab, c.name), "isoformat") else getattr(slab, c.name) for c in slab.__table__.columns}

    action_label = "ACTIVATE" if slab.is_active else "DEACTIVATE"
    await db.flush()
    await log_audit(db, admin, action_label, "billing_slab", resource_id=str(slab.id), old_values=old_dict, new_values=new_dict)
    await db.commit()
    await db.refresh(slab)
    return slab
