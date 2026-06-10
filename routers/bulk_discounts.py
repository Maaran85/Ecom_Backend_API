"""
Bulk discounts management router
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from core.permissions import require_admin
from models import BulkDiscount
from schemas.bulk_discount import BulkDiscountCreate, BulkDiscountUpdate, BulkDiscount as BulkDiscountSchema

router = APIRouter()

@router.post("", response_model=BulkDiscountSchema, status_code=status.HTTP_201_CREATED)
async def create_bulk_discount(
    discount_data: BulkDiscountCreate,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create bulk discount rule (admin only)"""
    
    # Validate that either product_id or category_id is set
    if not discount_data.product_id and not discount_data.category_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either product_id or category_id must be specified"
        )
    
    bulk_discount = BulkDiscount(**discount_data.model_dump())
    
    db.add(bulk_discount)
    await db.commit()
    await db.refresh(bulk_discount)
    
    return bulk_discount

@router.get("", response_model=list[BulkDiscountSchema])
async def list_bulk_discounts(
    skip: int = 0,
    limit: int = 50,
    active_only: bool = False,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all bulk discount rules (admin only)"""
    query = select(BulkDiscount).offset(skip).limit(limit)
    
    if active_only:
        query = query.where(BulkDiscount.is_active == True)
    
    result = await db.execute(query)
    discounts = result.scalars().all()
    
    return discounts

@router.get("/product/{product_id}", response_model=list[BulkDiscountSchema])
async def get_product_bulk_discounts(
    product_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get bulk discounts for a specific product"""
    result = await db.execute(
        select(BulkDiscount).where(
            BulkDiscount.product_id == product_id,
            BulkDiscount.is_active == True
        )
    )
    discounts = result.scalars().all()
    
    return discounts

@router.get("/{discount_id}", response_model=BulkDiscountSchema)
async def get_bulk_discount(
    discount_id: int,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get bulk discount details (admin only)"""
    result = await db.execute(select(BulkDiscount).where(BulkDiscount.id == discount_id))
    discount = result.scalar_one_or_none()
    
    if not discount:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bulk discount not found"
        )
    
    return discount

@router.put("/{discount_id}", response_model=BulkDiscountSchema)
async def update_bulk_discount(
    discount_id: int,
    discount_data: BulkDiscountUpdate,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update bulk discount rule (admin only)"""
    result = await db.execute(select(BulkDiscount).where(BulkDiscount.id == discount_id))
    discount = result.scalar_one_or_none()
    
    if not discount:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bulk discount not found"
        )
    
    for field, value in discount_data.model_dump(exclude_unset=True).items():
        setattr(discount, field, value)
    
    await db.commit()
    await db.refresh(discount)
    
    return discount

@router.delete("/{discount_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bulk_discount(
    discount_id: int,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete bulk discount rule (admin only)"""
    result = await db.execute(select(BulkDiscount).where(BulkDiscount.id == discount_id))
    discount = result.scalar_one_or_none()
    
    if not discount:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bulk discount not found"
        )
    
    await db.delete(discount)
    await db.commit()
    
    return None
