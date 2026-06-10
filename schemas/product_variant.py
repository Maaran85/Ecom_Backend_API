from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# Product Variant Schemas
class ProductVariantBase(BaseModel):
    size: Optional[str] = None
    color: Optional[str] = None
    material: Optional[str] = None
    price_adjustment: float = 0.0
    stock: int = 0
    images: Optional[List[str]] = None
    is_active: bool = True

class ProductVariantCreate(ProductVariantBase):
    product_id: int
    sku: str

class ProductVariantUpdate(BaseModel):
    size: Optional[str] = None
    color: Optional[str] = None
    material: Optional[str] = None
    price_adjustment: Optional[float] = None
    stock: Optional[int] = None
    images: Optional[List[str]] = None
    is_active: Optional[bool] = None

class ProductVariant(ProductVariantBase):
    id: int
    product_id: int
    sku: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
