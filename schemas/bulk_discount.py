from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# Bulk Discount Schemas
class BulkDiscountBase(BaseModel):
    name: str
    description: Optional[str] = None
    min_quantity: int = Field(..., gt=0)
    discount_percentage: float = Field(..., gt=0, le=100)
    product_id: Optional[int] = None
    category_id: Optional[int] = None

class BulkDiscountCreate(BulkDiscountBase):
    is_active: bool = True

class BulkDiscountUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    min_quantity: Optional[int] = Field(None, gt=0)
    discount_percentage: Optional[float] = Field(None, gt=0, le=100)
    product_id: Optional[int] = None
    category_id: Optional[int] = None
    is_active: Optional[bool] = None

class BulkDiscount(BulkDiscountBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
