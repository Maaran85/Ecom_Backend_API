from pydantic import BaseModel, ConfigDict, computed_field, field_validator, model_validator
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID
from .models import B2BAuctionStatus, B2BRegistrationType, B2BOrderStatus

class B2BProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    images: Optional[str] = None # JSON string or comma separated
    brand: Optional[str] = None
    specification: Optional[str] = None
    warranty: Optional[str] = None
    support: Optional[str] = None
    is_returnable: bool = False
    is_exchangeable: bool = False
    base_price: float
    is_active: bool = True
    is_deleted: bool = False

class B2BProductCreate(B2BProductBase):
    pass

class B2BProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    images: Optional[str] = None
    brand: Optional[str] = None
    specification: Optional[str] = None
    warranty: Optional[str] = None
    support: Optional[str] = None
    is_returnable: Optional[bool] = None
    is_exchangeable: Optional[bool] = None
    base_price: Optional[float] = None
    is_active: Optional[bool] = None

class B2BProductResponse(B2BProductBase):
    id: UUID
    partner_id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class B2BAuctionBidBase(BaseModel):
    bid_amount: float

class B2BAuctionBidCreate(B2BAuctionBidBase):
    pass

class B2BAuctionBidResponse(B2BAuctionBidBase):
    id: UUID
    auction_id: UUID
    dealer_id: UUID
    bid_qty: int
    is_winning: bool
    is_active: bool
    allocated_qty: int = 0
    order_id: Optional[int] = None
    created_at: datetime
    dealer_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class B2BAuctionItemBase(BaseModel):
    title: str
    description: Optional[str] = None
    b2b_product_id: UUID
    base_price: float
    start_time: datetime
    end_time: datetime
    qty: int = 1
    min_bid_qty: int = 1
    min_bid_amount: float = 0.0
    registration_type: B2BRegistrationType = B2BRegistrationType.FREE
    deposit_amount: Optional[float] = None

    @model_validator(mode='after')
    def validate_deposit(self) -> 'B2BAuctionItemBase':
        if self.registration_type == B2BRegistrationType.PAID:
            if not self.deposit_amount or self.deposit_amount <= 0:
                raise ValueError("deposit_amount must be greater than 0 for PAID registration auctions")
        return self

class B2BAuctionItemCreate(B2BAuctionItemBase):
    pass

class B2BAuctionItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    b2b_product_id: Optional[UUID] = None
    qty: Optional[int] = None
    min_bid_qty: Optional[int] = None
    min_bid_amount: Optional[float] = None
    base_price: Optional[float] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[B2BAuctionStatus] = None
    registration_type: Optional[B2BRegistrationType] = None
    deposit_amount: Optional[float] = None

class B2BAuctionItemBasicResponse(B2BAuctionItemBase):
    id: UUID
    partner_id: int
    current_highest_bid: float
    min_bid_qty: int
    status: B2BAuctionStatus
    registration_type: B2BRegistrationType
    deposit_amount: Optional[float] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class B2BAuctionItemResponse(B2BAuctionItemBase):
    id: UUID
    partner_id: int
    current_highest_bid: float
    min_bid_qty: int
    status: B2BAuctionStatus
    registration_type: B2BRegistrationType
    deposit_amount: Optional[float] = None
    bid_count: Optional[int] = 0
    registration_count: Optional[int] = 0
    is_registered: Optional[bool] = False
    is_winner: Optional[bool] = False
    my_last_bid: Optional[float] = None
    created_at: datetime
    
    bids: Optional[List[B2BAuctionBidResponse]] = []
    b2b_product: Optional[B2BProductResponse] = None
    product: Optional[B2BProductResponse] = None
    
    model_config = ConfigDict(from_attributes=True)

class B2BAuctionRegistrationBase(BaseModel):
    registered_qty: int

class B2BAuctionRegistrationCreate(B2BAuctionRegistrationBase):
    pass

class B2BAuctionRegistrationResponse(B2BAuctionRegistrationBase):
    id: UUID
    auction_id: UUID
    dealer_id: UUID
    deposit_paid: float
    registered_at: datetime
    model_config = ConfigDict(from_attributes=True)

class B2BOrderItemResponse(BaseModel):
    id: UUID
    order_id: UUID
    bid_id: UUID
    qty: int
    unit_price: float
    subtotal: float
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class B2BOrderUpdate(BaseModel):
    courier_company: Optional[str] = None
    tracking_number: Optional[str] = None
    order_status: Optional[B2BOrderStatus] = None
    payment_status: Optional[str] = None

class DealerBasicResponse(BaseModel):
    id: UUID
    business_name: Optional[str] = None
    gst_number: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class PartnerBasicResponse(BaseModel):
    id: int
    company_name: Optional[str] = None
    name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class B2BOrderResponse(BaseModel):
    id: UUID
    order_number: str
    auction_id: UUID
    partner_id: int
    dealer_id: UUID
    b2b_product_id: UUID
    total_qty: int
    total_amount: float
    deposit_applied: float
    balance_due: float
    payment_status: str
    order_status: B2BOrderStatus
    shipping_address: Optional[str] = None
    courier_company: Optional[str] = None
    tracking_number: Optional[str] = None
    dispatched_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    items: List[B2BOrderItemResponse] = []
    b2b_product: Optional[B2BProductResponse] = None
    auction: Optional['B2BAuctionItemBasicResponse'] = None
    dealer: Optional[DealerBasicResponse] = None
    partner: Optional[PartnerBasicResponse] = None
    model_config = ConfigDict(from_attributes=True)

