"""
Flash sales management router
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from core.database import get_db
from core.permissions import require_admin
from models import FlashSale, Product
from schemas.flash_sale import FlashSaleCreate, FlashSaleUpdate, FlashSale as FlashSaleSchema, FlashSaleWithProducts

router = APIRouter()

@router.post("", response_model=FlashSaleSchema, status_code=status.HTTP_201_CREATED)
async def create_flash_sale(
    sale_data: FlashSaleCreate,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create flash sale (admin only)"""
    flash_sale = FlashSale(**sale_data.model_dump())
    
    db.add(flash_sale)
    await db.commit()
    await db.refresh(flash_sale)
    
    return flash_sale

@router.get("", response_model=list[FlashSaleSchema])
async def list_flash_sales(
    skip: int = 0,
    limit: int = 50,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all flash sales (admin only)"""
    result = await db.execute(select(FlashSale).offset(skip).limit(limit))
    sales = result.scalars().all()
    
    return sales

@router.get("/active", response_model=list[FlashSaleWithProducts])
async def get_active_flash_sales(
    db: AsyncSession = Depends(get_db)
):
    """Get currently active flash sales"""
    now = datetime.now(timezone.utc)
    
    result = await db.execute(
        select(FlashSale).where(
            FlashSale.is_active == True,
            FlashSale.start_time <= now,
            FlashSale.end_time >= now
        )
    )
    sales = result.scalars().all()
    
    # Enrich with product details
    enriched_sales = []
    for sale in sales:
        # Get products if product_ids specified
        products_data = []
        if sale.product_ids:
            # Note: We need to use the Product model from the correct module
            from models import Product as ProductModel
            products_result = await db.execute(
                select(ProductModel).where(ProductModel.id.in_(sale.product_ids))
            )
            db_products = products_result.scalars().all()
            
            for p in db_products:
                products_data.append({
                    "id": p.id,
                    "name": p.name,
                    "price": p.price,
                    "images": p.images if p.images else [],
                    "discount_percentage": sale.discount_percentage,
                    "flash_sale_price": float(p.price) * (1 - sale.discount_percentage / 100)
                })
        
        # Use Pydantic to validate and return
        sale_dict = {
            "id": sale.id,
            "name": sale.name,
            "description": sale.description,
            "discount_percentage": sale.discount_percentage,
            "start_time": sale.start_time,
            "end_time": sale.end_time,
            "is_active": sale.is_active,
            "created_at": sale.created_at,
            "updated_at": sale.updated_at,
            "product_ids": sale.product_ids,
            "category_ids": sale.category_ids,
            "products": products_data
        }
        enriched_sales.append(sale_dict)
    
    return enriched_sales

@router.get("/{sale_id}", response_model=FlashSaleSchema)
async def get_flash_sale(
    sale_id: int,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get flash sale details (admin only)"""
    result = await db.execute(select(FlashSale).where(FlashSale.id == sale_id))
    sale = result.scalar_one_or_none()
    
    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flash sale not found"
        )
    
    return sale

@router.put("/{sale_id}", response_model=FlashSaleSchema)
async def update_flash_sale(
    sale_id: int,
    sale_data: FlashSaleUpdate,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update flash sale (admin only)"""
    result = await db.execute(select(FlashSale).where(FlashSale.id == sale_id))
    sale = result.scalar_one_or_none()
    
    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flash sale not found"
        )
    
    for field, value in sale_data.model_dump(exclude_unset=True).items():
        setattr(sale, field, value)
    
    await db.commit()
    await db.refresh(sale)
    
    return sale

@router.delete("/{sale_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flash_sale(
    sale_id: int,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete flash sale (admin only)"""
    result = await db.execute(select(FlashSale).where(FlashSale.id == sale_id))
    sale = result.scalar_one_or_none()
    
    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flash sale not found"
        )
    
    await db.delete(sale)
    await db.commit()
    
    return None
