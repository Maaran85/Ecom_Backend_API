from uuid import UUID
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime
from schemas.dealer import Hub

class ShowroomCreate(BaseModel):
    name: str
    address: str
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    phone: Optional[str] = None
    contact_person: Optional[str] = None
    is_active: bool = True

class ShowroomUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    phone: Optional[str] = None
    contact_person: Optional[str] = None
    is_active: Optional[bool] = None

class ProductInventoryBase(BaseModel):
    product_id: UUID
    hub_id: int
    quantity: int

class ProductInventoryResponse(ProductInventoryBase):
    id: int
    product_name: Optional[str] = None
    product_price: Optional[float] = None
    product_image: Optional[Any] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    main_category_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class StockAddRequest(BaseModel):
    product_id: UUID
    quantity: int
    notes: Optional[str] = None

class ShowroomSaleItem(BaseModel):
    product_id: UUID
    quantity: int
    price: float
    variant_attributes: Optional[dict] = None

class ShowroomSaleRequest(BaseModel):
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    items: List[ShowroomSaleItem]
    payment_method: str = "CASH"  # CASH, CARD, UPI
    discount_amount: float = 0.0
    notes: Optional[str] = None
class ShowroomSaleHistory(BaseModel):
    id: int
    order_number: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    subtotal: Optional[float] = None          # Pre-discount total
    discount_amount: Optional[float] = None   # Discount applied
    total_amount: float                       # Final paid amount
    payment_method: str
    created_at: datetime
    items_count: int
    showroom_name: Optional[str] = None

    class Config:
        from_attributes = True

class ShowroomSalesResponse(BaseModel):
    items: List[ShowroomSaleHistory]
    total: int
    page: int
    limit: int
