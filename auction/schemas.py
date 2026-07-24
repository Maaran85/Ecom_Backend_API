from pydantic import BaseModel, ConfigDict, computed_field, field_validator, model_validator
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum
from uuid import UUID

class AuctionStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class RegistrationType(str, Enum):
    FREE = "FREE"
    PAID = "PAID"

class AuctionBidBase(BaseModel):
    bid_amount: float
    bid_qty: int

class AuctionBidCreate(AuctionBidBase):
    pass

class AuctionBidResponse(AuctionBidBase):
    id: UUID
    auction_id: UUID
    user_id: int
    is_winning: bool
    allocated_qty: int = 0
    order_id: Optional[int] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class AuctionItemBase(BaseModel):
    title: str
    description: Optional[str] = None
    product_id: UUID
    base_price: float
    start_time: datetime
    end_time: datetime
    qty: int = 1
    min_bid_qty: int = 1
    min_bid_amount: float = 0.0
    max_bidders: int = 100
    hub_id: int
    registration_type: RegistrationType = RegistrationType.FREE
    deposit_amount: Optional[float] = None

    @model_validator(mode='after')
    def validate_deposit(self) -> 'AuctionItemBase':
        if self.registration_type == RegistrationType.PAID:
            if not self.deposit_amount or self.deposit_amount <= 0:
                raise ValueError("deposit_amount must be greater than 0 for PAID registration auctions")
        return self

class AuctionItemCreate(AuctionItemBase):
    pass

class AuctionItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    base_price: Optional[float] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[AuctionStatus] = None
    registration_type: Optional[RegistrationType] = None
    deposit_amount: Optional[float] = None
    max_bidders: Optional[int] = None

class SimpleProductResponse(BaseModel):
    id: UUID
    name: str
    images: Optional[List[Any]] = []
    
    @computed_field  # type: ignore[misc]
    @property
    def image_url(self) -> Optional[str]:
        if self.images and len(self.images) > 0:
            first = self.images[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return first.get('url') or first.get('image_url') or first.get('src')
        return None
    
    model_config = ConfigDict(from_attributes=True)

class AuctionItemResponse(AuctionItemBase):
    id: UUID
    dealer_id: Optional[UUID] = None
    current_highest_bid: float
    min_bid_qty: int
    status: AuctionStatus
    registration_type: RegistrationType
    deposit_amount: Optional[float] = None
    bid_count: Optional[int] = 0
    registration_count: Optional[int] = 0
    max_bidders: int = 100
    created_at: datetime
    updated_at: datetime
    product: Optional[SimpleProductResponse] = None
    is_registered: Optional[bool] = False
    is_winner: Optional[bool] = False
    
    model_config = ConfigDict(from_attributes=True)

class AuctionItemDetailResponse(AuctionItemResponse):
    bids: List[AuctionBidResponse] = []

# --- Registration Schemas ---

class AuctionRegistrationResponse(BaseModel):
    id: UUID
    auction_id: UUID
    user_id: int
    deposit_paid: float
    registered_at: datetime
    model_config = ConfigDict(from_attributes=True)

class RegistrationStatusResponse(BaseModel):
    is_registered: bool
    registration: Optional[AuctionRegistrationResponse] = None
    auction_registration_type: RegistrationType
    deposit_amount: Optional[float] = None
