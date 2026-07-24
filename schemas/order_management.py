from uuid import UUID
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.order_return import ReturnStatus
import schemas.product

# Order Cancellation
class OrderCancelRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)

class OrderCancelResponse(BaseModel):
    order_id: int
    status: str
    message: str
    refund_initiated: bool = False

class ReturnRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    order_item_id: int
    description: Optional[str] = Field(None, max_length=1000)
    images: Optional[List[str]] = None  # Image URLs
    is_exchange: bool = False
    exchange_variant_id: Optional[UUID] = None
    pickup_date: Optional[datetime] = None

class ReturnResponse(BaseModel):
    id: int
    order_id: int
    order_item_id: Optional[int] = None
    reason: str
    status: ReturnStatus
    requested_at: datetime
    message: str

class ReturnApprovalRequest(BaseModel):
    admin_notes: Optional[str] = None
    refund_amount: Optional[float] = None      # Override if different from order total
    refund_mode: Optional[str] = None          # upi, bank_transfer, original_method, wallet, none
    refund_reference: Optional[str] = None     # UTR / transaction ID

class ReturnRejectionRequest(BaseModel):
    admin_notes: str = Field(..., min_length=10)

class ProcessRefundRequest(BaseModel):
    """Payload to record refund details after the return is approved/completed."""
    refund_mode: Optional[str] = Field(None, description="upi | bank_transfer | original_method | wallet | none")
    refund_reference: Optional[str] = Field(None, description="UTR / transaction reference ID")
    refund_amount: Optional[float] = None      # Optional override

class OrderReturn(BaseModel):
    id: int
    order_id: int
    order_item_id: Optional[int] = None
    customer_id: int
    reason: str
    description: Optional[str] = None
    images: Optional[List[str]] = None
    is_exchange: bool = False
    exchange_variant_id: Optional[UUID] = None
    exchange_product: Optional["schemas.product.Product"] = None
    replacement_order_id: Optional[int] = None
    status: ReturnStatus
    admin_notes: Optional[str] = None
    approved_by: Optional[int] = None
    refund_amount: Optional[float] = None
    refund_initiated: bool
    refund_mode: Optional[str] = None
    refund_reference: Optional[str] = None
    requested_at: datetime
    approved_at: Optional[datetime] = None
    pickup_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    rider_id: Optional[int] = None
    hub_id: Optional[int] = None

    class Config:
        from_attributes = True

class AdminReturnDetail(BaseModel):
    """Enriched return record for admin list view."""
    id: int
    order_id: int
    order_number: Optional[str] = None
    order_item_id: Optional[int] = None
    customer_id: int
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    product_name: Optional[str] = None
    reason: str
    description: Optional[str] = None
    images: Optional[List[str]] = None
    is_exchange: bool = False
    exchange_variant_id: Optional[UUID] = None
    replacement_order_id: Optional[int] = None
    status: ReturnStatus
    admin_notes: Optional[str] = None
    approved_by: Optional[int] = None
    refund_amount: Optional[float] = None
    refund_initiated: bool
    refund_mode: Optional[str] = None
    refund_reference: Optional[str] = None
    payment_method: Optional[str] = None   # COD, upi, card, net_banking, wallet
    requested_at: datetime
    approved_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Tracking Update
class TrackingUpdateRequest(BaseModel):
    tracking_number: Optional[str] = None
    status: Optional[str] = None  # Order status
    estimated_delivery: Optional[datetime] = None

class TrackingUpdateResponse(BaseModel):
    order_id: int
    tracking_number: Optional[str] = None
    status: str
    estimated_delivery: Optional[datetime] = None
    message: str

