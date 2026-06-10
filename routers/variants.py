"""
Product variants router
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from core.permissions import get_current_active_user, require_admin
from models import User, Product, ProductVariant, UserRole
from schemas.product_variant import ProductVariantCreate, ProductVariantUpdate, ProductVariant as ProductVariantSchema

router = APIRouter()

@router.post("", response_model=ProductVariantSchema, status_code=status.HTTP_201_CREATED)
async def create_variant(
    variant_data: ProductVariantCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create product variant (dealer/admin only)"""
    
    # Check if product exists
    result = await db.execute(select(Product).where(Product.id == variant_data.product_id))
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Check permissions: dealer can add to own products, admin can add to any
    if current_user.role == UserRole.DEALER:
        if product.dealer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only add variants to your own products"
            )
    elif current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only dealers and admins can create product variants"
        )
    
    # Check if SKU already exists
    result = await db.execute(select(ProductVariant).where(ProductVariant.sku == variant_data.sku))
    existing_sku = result.scalar_one_or_none()
    
    if existing_sku:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SKU already exists"
        )
    
    variant = ProductVariant(**variant_data.model_dump())
    
    db.add(variant)
    await db.commit()
    await db.refresh(variant)
    
    return variant

@router.get("/product/{product_id}", response_model=list[ProductVariantSchema])
async def get_product_variants(
    product_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get all variants for a product"""
    result = await db.execute(
        select(ProductVariant).where(
            ProductVariant.product_id == product_id,
            ProductVariant.is_active == True
        )
    )
    variants = list(result.scalars().all())
    
    # If no variants found, provide the base product as a "Virtual Variant" 
    # so customers can still request an exchange for products with no options.
    if not variants:
        product_res = await db.execute(select(Product).where(Product.id == product_id))
        product = product_res.scalar_one_or_none()
        if product:
            # Create a transient/virtual variant (not in DB)
            base_variant = ProductVariant(
                id=-product_id, # Use negative product_id as a unique virtual ID marker
                product_id=product_id,
                sku=f"BASE-{product_id}",
                size="Standard",
                color=product.color or "Default",
                price_adjustment=0.0,
                stock=product.stock,
                is_active=True,
                created_at=product.created_at
            )
            variants.append(base_variant)
    
    return variants

@router.get("/{variant_id}", response_model=ProductVariantSchema)
async def get_variant(
    variant_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get specific variant"""
    result = await db.execute(select(ProductVariant).where(ProductVariant.id == variant_id))
    variant = result.scalar_one_or_none()
    
    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found"
        )
    
    return variant

@router.put("/{variant_id}", response_model=ProductVariantSchema)
async def update_variant(
    variant_id: int,
    variant_data: ProductVariantUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update product variant (dealer/admin only)"""
    result = await db.execute(select(ProductVariant).where(ProductVariant.id == variant_id))
    variant = result.scalar_one_or_none()
    
    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found"
        )
    
    # Get product to check permissions
    product_result = await db.execute(select(Product).where(Product.id == variant.product_id))
    product = product_result.scalar_one_or_none()
    
    # Check permissions
    if current_user.role == UserRole.DEALER:
        if product.dealer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update variants of your own products"
            )
    elif current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only dealers and admins can update product variants"
        )
    
    for field, value in variant_data.model_dump(exclude_unset=True).items():
        setattr(variant, field, value)
    
    await db.commit()
    await db.refresh(variant)
    
    return variant

@router.delete("/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_variant(
    variant_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete product variant (dealer/admin only)"""
    result = await db.execute(select(ProductVariant).where(ProductVariant.id == variant_id))
    variant = result.scalar_one_or_none()
    
    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found"
        )
    
    # Get product to check permissions
    product_result = await db.execute(select(Product).where(Product.id == variant.product_id))
    product = product_result.scalar_one_or_none()
    
    # Check permissions
    if current_user.role == UserRole.DEALER:
        if product.dealer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete variants of your own products"
            )
    elif current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only dealers and admins can delete product variants"
        )
    
    await db.delete(variant)
    await db.commit()
    
    return None
