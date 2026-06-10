"""
Coupon management router
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from datetime import datetime, timezone
from core.database import get_db
from core.permissions import get_current_active_user, require_admin
from models import User, Coupon, CouponUsage, Order, DiscountType, Dealer, Product
from schemas.coupon import (
    CouponCreate,
    CouponUpdate,
    Coupon as CouponSchema,
    CouponValidationRequest,
    CouponValidationResponse,
    CouponUsageStats
)

router = APIRouter()

@router.post("", response_model=CouponSchema, status_code=status.HTTP_201_CREATED)
async def create_coupon(
    coupon_data: CouponCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create new coupon (admin only)"""
    
    # Check if code already exists
    result = await db.execute(select(Coupon).where(Coupon.code == coupon_data.code.upper()))
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Coupon code already exists"
        )
    
    coupon = Coupon(
        **coupon_data.model_dump(),
        code=coupon_data.code.upper()  # Store in uppercase
    )
    
    db.add(coupon)
    await db.commit()
    await db.refresh(coupon)
    
    return coupon

@router.get("", response_model=list[CouponSchema])
async def list_coupons(
    skip: int = 0,
    limit: int = 50,
    active_only: bool = False,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all coupons (admin only)"""
    query = select(Coupon).offset(skip).limit(limit)
    
    if active_only:
        query = query.where(Coupon.is_active == True)
    
    result = await db.execute(query)
    coupons = result.scalars().all()
    
    return coupons

@router.get("/available", response_model=list[CouponSchema])
async def get_available_coupons(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get available coupons for current user"""
    now = datetime.now(timezone.utc)
    
    # Get active coupons within validity period
    result = await db.execute(
        select(Coupon).where(
            Coupon.is_active == True,
            Coupon.valid_from <= now,
            Coupon.valid_until >= now
        )
    )
    coupons = result.scalars().all()
    
    # Filter by usage limits
    available_coupons = []
    for coupon in coupons:
        # Check total usage limit
        if coupon.usage_limit and coupon.current_usage >= coupon.usage_limit:
            continue
        
        # Check per-user usage limit
        user_usage_result = await db.execute(
            select(func.count(CouponUsage.id)).where(
                CouponUsage.coupon_id == coupon.id,
                CouponUsage.user_id == current_user.id
            )
        )
        user_usage = user_usage_result.scalar()
        
        if user_usage >= coupon.usage_per_user:
            continue
        
        # Check first order only
        if coupon.first_order_only:
            order_count_result = await db.execute(
                select(func.count(Order.id)).where(Order.user_id == current_user.id)
            )
            order_count = order_count_result.scalar()
            if order_count > 0:
                continue
        
        available_coupons.append(coupon)
    
    return available_coupons

@router.post("/validate", response_model=CouponValidationResponse)
async def validate_coupon(
    validation_data: CouponValidationRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Validate coupon code and calculate discount"""
    
    # Get coupon
    result = await db.execute(
        select(Coupon).where(Coupon.code == validation_data.code.upper())
    )
    coupon = result.scalar_one_or_none()
    
    if not coupon:
        return CouponValidationResponse(
            valid=False,
            message="Invalid coupon code",
            discount_amount=0,
            final_amount=validation_data.cart_total
        )
    
    # Check if active
    if not coupon.is_active:
        return CouponValidationResponse(
            valid=False,
            message="Coupon is not active",
            discount_amount=0,
            final_amount=validation_data.cart_total
        )
    
    # Check validity period
    now = datetime.now(timezone.utc)
    if now < coupon.valid_from:
        return CouponValidationResponse(
            valid=False,
            message=f"Coupon not yet valid. Valid from {coupon.valid_from}",
            discount_amount=0,
            final_amount=validation_data.cart_total
        )
    
    if now > coupon.valid_until:
        return CouponValidationResponse(
            valid=False,
            message="Coupon has expired",
            discount_amount=0,
            final_amount=validation_data.cart_total
        )
    
    # Check total usage limit
    if coupon.usage_limit and coupon.current_usage >= coupon.usage_limit:
        return CouponValidationResponse(
            valid=False,
            message="Coupon usage limit reached",
            discount_amount=0,
            final_amount=validation_data.cart_total
        )
    
    # Check per-user usage limit
    user_usage_result = await db.execute(
        select(func.count(CouponUsage.id)).where(
            CouponUsage.coupon_id == coupon.id,
            CouponUsage.user_id == current_user.id
        )
    )
    user_usage = user_usage_result.scalar()
    
    if user_usage >= coupon.usage_per_user:
        return CouponValidationResponse(
            valid=False,
            message=f"You have already used this coupon {coupon.usage_per_user} time(s)",
            discount_amount=0,
            final_amount=validation_data.cart_total
        )
    
    # Check minimum order value
    if validation_data.cart_total < coupon.min_order_value:
        return CouponValidationResponse(
            valid=False,
            message=f"Minimum order value of ₹{coupon.min_order_value} required",
            discount_amount=0,
            final_amount=validation_data.cart_total
        )
    
    # Check first order only
    if coupon.first_order_only:
        order_count_result = await db.execute(
            select(func.count(Order.id)).where(Order.user_id == current_user.id)
        )
        order_count = order_count_result.scalar()
        if order_count > 0:
            return CouponValidationResponse(
                valid=False,
                message="This coupon is only valid for first orders",
                discount_amount=0,
                final_amount=validation_data.cart_total
            )
    
    # Check applicable products/categories
    if coupon.applicable_products or coupon.applicable_categories or coupon.dealer_id:
        cart_product_ids = [item["product_id"] for item in validation_data.cart_items]
        cart_category_ids = [item["category_id"] for item in validation_data.cart_items]
        
        # Resolve all product owners for dealer-specific checking
        product_dealer_map = {}
        if coupon.dealer_id:
            res = await db.execute(select(Product.id, Product.dealer_id).where(Product.id.in_(cart_product_ids)))
            product_dealer_map = {row.id: row.dealer_id for row in res.fetchall()}

        applicable = False
        
        # If it's a dealer coupon, it ONLY applies to that dealer's products
        if coupon.dealer_id:
            if any(product_dealer_map.get(pid) == coupon.dealer_id for pid in cart_product_ids):
                applicable = True
        else:
            # Global Coupon checks
            if coupon.applicable_products:
                if any(pid in coupon.applicable_products for pid in cart_product_ids):
                    applicable = True
            
            if not applicable and coupon.applicable_categories:
                if any(cid in coupon.applicable_categories for cid in cart_category_ids):
                    applicable = True
                    
            # If no specific products/categories but is a global coupon, it applies everywhere
            if not coupon.applicable_products and not coupon.applicable_categories:
                applicable = True
        
        if not applicable:
            return CouponValidationResponse(
                valid=False,
                message="Coupon not applicable to items in cart",
                discount_amount=0,
                final_amount=validation_data.cart_total
            )
    
    # Calculate discount (Weighted if dealer specific?)
    # For now, it calculates on whole cart total if ANY item is applicable.
    # TODO: Refine to only discount ONLY the applicable items.
    
    discount_amount = 0.0
    
    if coupon.discount_type == DiscountType.PERCENTAGE:
        discount_amount = validation_data.cart_total * (coupon.discount_value / 100)
        if coupon.max_discount_amount:
            discount_amount = min(discount_amount, coupon.max_discount_amount)
    elif coupon.discount_type == DiscountType.FIXED:
        discount_amount = coupon.discount_value
    elif coupon.discount_type == DiscountType.FREE_SHIPPING:
        # Shipping discount would be handled separately
        discount_amount = 0.0
    
    final_amount = max(0, validation_data.cart_total - discount_amount)
    
    return CouponValidationResponse(
        valid=True,
        message="Coupon applied successfully",
        discount_amount=discount_amount,
        final_amount=final_amount,
        coupon=coupon
    )

# ─────────────────────────────────────────────────────────────────────────────
# Dealer Coupon Management Endpoints
# (IMPORTANT: These MUST be defined BEFORE the /{coupon_id} parameterized routes
#  so FastAPI doesn't try to match "dealer" as an integer coupon ID)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dealer/all", response_model=list[CouponSchema])
async def get_my_coupons(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dealers: List all coupons owned by this dealer"""
    # Resolve dealer
    res = await db.execute(select(Dealer).where(Dealer.user_id == current_user.id))
    dealer = res.scalar_one_or_none()
    if not dealer:
        raise HTTPException(status_code=403, detail="Dealer access required")
        
    result = await db.execute(
        select(Coupon).where(Coupon.dealer_id == dealer.id).order_by(Coupon.created_at.desc())
    )
    return result.scalars().all()

@router.post("/dealer/create", response_model=CouponSchema)
async def dealer_create_coupon(
    payload: CouponCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dealers: Create a discount coupon"""
    res = await db.execute(select(Dealer).where(Dealer.user_id == current_user.id))
    dealer = res.scalar_one_or_none()
    if not dealer:
        raise HTTPException(status_code=403, detail="Dealer access required")

    # Check clash
    code = payload.code.upper()
    existing = await db.execute(select(Coupon).where(Coupon.code == code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Coupon code already in use")

    coupon = Coupon(
        **payload.model_dump(exclude={"dealer_id", "code"}),
        code=code,
        dealer_id=dealer.id
    )
    db.add(coupon)
    await db.commit()
    await db.refresh(coupon)
    return coupon

@router.delete("/dealer/{coupon_id}", status_code=204)
async def dealer_delete_coupon(
    coupon_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dealers: Delete their own coupon"""
    res = await db.execute(select(Dealer).where(Dealer.user_id == current_user.id))
    dealer = res.scalar_one_or_none()
    if not dealer:
        raise HTTPException(status_code=403, detail="Dealer access required")

    result = await db.execute(
        select(Coupon).where(Coupon.id == coupon_id, Coupon.dealer_id == dealer.id)
    )
    coupon = result.scalar_one_or_none()
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found or access denied")

    # Step 1: Nullify coupon_id on any Orders referencing this coupon
    # (preserves order history — coupon_code string column still records what was used)
    await db.execute(
        update(Order)
        .where(Order.coupon_id == coupon_id)
        .values(coupon_id=None)
        .execution_options(synchronize_session=False)
    )

    # Step 2: Bulk delete all CouponUsage rows for this coupon
    from sqlalchemy import delete as sql_delete
    await db.execute(
        sql_delete(CouponUsage)
        .where(CouponUsage.coupon_id == coupon_id)
        .execution_options(synchronize_session=False)
    )

    # Step 3: Delete the coupon itself
    await db.delete(coupon)
    await db.commit()
    return None



# ─────────────────────────────────────────────────────────────────────────────
# Admin Coupon CRUD Endpoints (parameterized — must come AFTER /dealer/* routes)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{coupon_id}", response_model=CouponSchema)
async def get_coupon(
    coupon_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get coupon details (admin only)"""
    result = await db.execute(select(Coupon).where(Coupon.id == coupon_id))
    coupon = result.scalar_one_or_none()
    
    if not coupon:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Coupon not found"
        )
    
    return coupon

@router.put("/{coupon_id}", response_model=CouponSchema)
async def update_coupon(
    coupon_id: int,
    coupon_data: CouponUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update coupon (admin only)"""
    result = await db.execute(select(Coupon).where(Coupon.id == coupon_id))
    coupon = result.scalar_one_or_none()
    
    if not coupon:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Coupon not found"
        )
    
    for field, value in coupon_data.model_dump(exclude_unset=True).items():
        if field == "code" and value:
            value = value.upper()
        setattr(coupon, field, value)
    
    await db.commit()
    await db.refresh(coupon)
    
    return coupon

@router.delete("/{coupon_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_coupon(
    coupon_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete coupon (admin only)"""
    result = await db.execute(select(Coupon).where(Coupon.id == coupon_id))
    coupon = result.scalar_one_or_none()
    
    if not coupon:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Coupon not found"
        )
    
    await db.delete(coupon)
    await db.commit()
    
    return None

@router.get("/{coupon_id}/stats", response_model=CouponUsageStats)
async def get_coupon_stats(
    coupon_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get coupon usage statistics (admin only)"""
    result = await db.execute(select(Coupon).where(Coupon.id == coupon_id))
    coupon = result.scalar_one_or_none()
    
    if not coupon:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Coupon not found"
        )
    
    # Get total discount given
    discount_result = await db.execute(
        select(func.sum(CouponUsage.discount_amount)).where(
            CouponUsage.coupon_id == coupon_id
        )
    )
    total_discount = discount_result.scalar() or 0.0
    
    # Get unique users
    users_result = await db.execute(
        select(func.count(func.distinct(CouponUsage.user_id))).where(
            CouponUsage.coupon_id == coupon_id
        )
    )
    unique_users = users_result.scalar() or 0
    
    return CouponUsageStats(
        coupon_id=coupon.id,
        coupon_code=coupon.code,
        total_usage=coupon.current_usage,
        total_discount_given=total_discount,
        unique_users=unique_users
    )
