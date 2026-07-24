from uuid import UUID
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from models.cart import OrderStatus
from schemas.product import Product
import schemas.order_management
from schemas.dealer import Hub

# Cart Schemas
class CartItemBase(BaseModel):
    product_id: UUID
    quantity: int = 1
    variant_id: Optional[UUID] = None
    size: Optional[str] = None
    variant_attributes: Optional[dict] = None

class CartItemCreate(CartItemBase):
    pass

class CartItemUpdate(BaseModel):
    quantity: int

class CartItem(CartItemBase):
    id: int
    customer_id: int
    created_at: datetime
    product: Optional[Product] = None

    class Config:
        from_attributes = True

# Order Schemas
class OrderItemBase(BaseModel):
    product_id: UUID
    variant_id: Optional[UUID] = None
    quantity: int
    price: float
    size: Optional[str] = None
    variant_attributes: Optional[dict] = None

class OrderItem(OrderItemBase):
    id: int
    order_id: int
    item_order_id: Optional[str] = None
    order_number: Optional[str] = None
    product: Optional[Product] = None
    variant: Optional[Product] = None
    status: str = "pending"
    payment_status: str = "pending"
    reject_reason: Optional[str] = None
    courier_company: Optional[str] = None
    tracking_number: Optional[str] = None
    tracking_url: Optional[str] = None
    dispatch_date: Optional[datetime] = None
    estimated_delivery: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    rider_id: Optional[int] = None
    hub_id: Optional[int] = None
    hub: Optional[Hub] = None
    hub_arrived_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class OrderBase(BaseModel):
    total_amount: float

class OrderCreate(BaseModel):
    pass  # Will create from cart items

class Order(OrderBase):
    id: int
    order_number: Optional[str] = None
    customer_id: int
    subtotal: float
    discount_amount: float = 0.0
    delivery_charge: float = 0.0
    platform_fee_amount: float = 0.0
    payment_status: str = "pending"
    payment_method: str = "COD"
    status: OrderStatus
    tracking_number: Optional[str] = None
    estimated_delivery: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    tax_invoice_no: Optional[str] = None
    tax_amount: float = 0.0
    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0
    is_auction_order: bool = False
    created_at: datetime
    items: List[OrderItem] = []
    returns: List["schemas.order_management.OrderReturn"] = []

    class Config:
        from_attributes = True
