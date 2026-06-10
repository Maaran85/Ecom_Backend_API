"""
Wishlist management router
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from core.permissions import get_current_active_user
from models import User, WishlistItem, Product, ProductVariant, CustomerUser
from schemas.wishlist import WishlistItemCreate, WishlistItem as WishlistItemSchema, WishlistItemWithProduct

router = APIRouter()

@router.post("", response_model=WishlistItemSchema, status_code=status.HTTP_201_CREATED)
async def add_to_wishlist(
    item_data: WishlistItemCreate,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Add product to wishlist"""
    
    # Check if product exists
    result = await db.execute(select(Product).where(Product.id == item_data.product_id))
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Check if already in wishlist
    result = await db.execute(
        select(WishlistItem).where(
            WishlistItem.customer_id == current_user.id,
            WishlistItem.product_id == item_data.product_id,
            WishlistItem.variant_id == item_data.variant_id
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product already in wishlist"
        )
    
    # Add to wishlist
    wishlist_item = WishlistItem(
        customer_id=current_user.id,
        product_id=item_data.product_id,
        variant_id=item_data.variant_id
    )
    
    db.add(wishlist_item)
    await db.commit()
    await db.refresh(wishlist_item)
    
    return wishlist_item

@router.get("", response_model=list[WishlistItemWithProduct])
async def get_wishlist(
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's wishlist with product details"""
    result = await db.execute(
        select(WishlistItem).where(WishlistItem.customer_id == current_user.id)
    )
    wishlist_items = result.scalars().all()
    
    # Enrich with product details
    enriched_items = []
    for item in wishlist_items:
        product_result = await db.execute(select(Product).where(Product.id == item.product_id))
        product = product_result.scalar_one_or_none()
        
        variant = None
        if item.variant_id:
            variant_result = await db.execute(select(ProductVariant).where(ProductVariant.id == item.variant_id))
            variant = variant_result.scalar_one_or_none()
        
        enriched_item = {
            **item.__dict__,
            "product_name": product.name if product else None,
            "product_price": product.price if product else None,
            "product_discount_price": product.discount_price if product else None,
            "product_images": product.images if product else None,
            "variant_size": variant.size if variant else None,
            "variant_color": variant.color if variant else None,
        }
        enriched_items.append(enriched_item)
    
    return enriched_items

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_wishlist(
    item_id: int,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove product from wishlist"""
    result = await db.execute(
        select(WishlistItem).where(
            WishlistItem.id == item_id,
            WishlistItem.customer_id == current_user.id
        )
    )
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wishlist item not found"
        )
    
    await db.delete(item)
    await db.commit()
    
    return None

@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_wishlist(
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Clear entire wishlist"""
    result = await db.execute(
        select(WishlistItem).where(WishlistItem.customer_id == current_user.id)
    )
    items = result.scalars().all()
    
    for item in items:
        await db.delete(item)
    
    await db.commit()
    
    return None
