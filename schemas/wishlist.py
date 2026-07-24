from uuid import UUID
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Wishlist Schemas
class WishlistItemBase(BaseModel):
    product_id: UUID

class WishlistItemCreate(WishlistItemBase):
    pass

class WishlistItem(WishlistItemBase):
    id: int
    customer_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class WishlistItemWithProduct(WishlistItem):
    """Wishlist item with product details"""
    product_name: Optional[str] = None
    product_price: Optional[float] = None
    product_discount_price: Optional[float] = None
    product_images: Optional[list] = None
    class Config:
        from_attributes = True
