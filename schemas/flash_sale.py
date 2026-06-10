from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# Flash Sale Schemas
class FlashSaleBase(BaseModel):
    name: str
    description: Optional[str] = None
    discount_percentage: float = Field(..., gt=0, le=100)
    start_time: datetime
    end_time: datetime
    product_ids: Optional[List[int]] = None
    category_ids: Optional[List[int]] = None
    dealer_id: Optional[int] = None

class FlashSaleCreate(FlashSaleBase):
    is_active: bool = True

class FlashSaleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    discount_percentage: Optional[float] = Field(None, gt=0, le=100)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    product_ids: Optional[List[int]] = None
    category_ids: Optional[List[int]] = None
    is_active: Optional[bool] = None

class FlashSale(FlashSaleBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class FlashSaleWithProducts(FlashSale):
    """Flash sale with product details"""
    products: Optional[List[dict]] = None  # Will be populated with product info
