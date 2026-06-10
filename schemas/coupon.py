from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.coupon import DiscountType

# Coupon Schemas
class CouponBase(BaseModel):
    code: str
    description: Optional[str] = None
    discount_type: DiscountType
    discount_value: float = Field(..., gt=0)
    dealer_id: Optional[int] = None
    min_order_value: float = 0.0
    max_discount_amount: Optional[float] = None
    usage_limit: Optional[int] = None
    usage_per_user: int = 1
    valid_from: datetime
    valid_until: datetime
    applicable_categories: Optional[List[int]] = None
    applicable_products: Optional[List[int]] = None
    first_order_only: bool = False

class CouponCreate(CouponBase):
    is_active: bool = True

class CouponUpdate(BaseModel):
    code: Optional[str] = None
    description: Optional[str] = None
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[float] = Field(None, gt=0)
    min_order_value: Optional[float] = None
    max_discount_amount: Optional[float] = None
    usage_limit: Optional[int] = None
    usage_per_user: Optional[int] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    is_active: Optional[bool] = None
    applicable_categories: Optional[List[int]] = None
    applicable_products: Optional[List[int]] = None
    first_order_only: Optional[bool] = None

class Coupon(CouponBase):
    id: int
    current_usage: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Coupon Validation
class CouponValidationRequest(BaseModel):
    code: str
    cart_total: float
    cart_items: List[dict]  # [{"product_id": 1, "category_id": 2, "quantity": 1}]

class CouponValidationResponse(BaseModel):
    valid: bool
    message: str
    discount_amount: float = 0.0
    final_amount: float = 0.0
    coupon: Optional[Coupon] = None

# Coupon Usage
class CouponUsageStats(BaseModel):
    coupon_id: int
    coupon_code: str
    total_usage: int
    total_discount_given: float
    unique_users: int
