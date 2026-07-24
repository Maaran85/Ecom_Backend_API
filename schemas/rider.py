from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime

class RiderBase(BaseModel):
    business_name: Optional[str] = None
    vehicle_type: Optional[str] = None
    vehicle_number: Optional[str] = None
    vehicle_model: Optional[str] = None
    insurance_expiry: Optional[str] = None
    dob: Optional[str] = None
    phone_number: Optional[str] = None
    service_zones: Optional[str] = None
    license_number: Optional[str] = None
    aadhaar_number: Optional[str] = None
    emergency_contact: Optional[str] = None
    hub_id: Optional[int] = None
    partner_id: Optional[int] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None
    aadhaar_image: Optional[str] = None
    license_image: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    upi_id: Optional[str] = None

class RiderAdminCreate(RiderBase):
    full_name: str
    email: EmailStr
    password: str
    phone_number: str
    managed_by: str = "admin"
    is_approved: bool = True

class RiderCreate(RiderBase):
    user_id: int
    managed_by: str = "admin"
    dealer_id: Optional[UUID] = None

class RiderSelfRegistration(BaseModel):
    full_name: str
    email: str
    password: str
    phone_number: str
    business_name: Optional[str] = None
    vehicle_type: str
    vehicle_number: str
    service_zones: str
    license_number: Optional[str] = None
    aadhaar_number: Optional[str] = None
    hub_id: Optional[int] = None

class RiderUpdate(RiderBase):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    is_approved: Optional[bool] = None
    is_available: Optional[bool] = None
    current_status: Optional[str] = None
    current_lat: Optional[float] = None
    current_long: Optional[float] = None

class Rider(RiderBase):
    id: int
    user_id: int
    managed_by: str
    dealer_id: Optional[UUID] = None
    partner_id: Optional[int] = None
    is_available: bool
    current_status: str
    is_approved: bool
    full_name: Optional[str] = None
    user_email: Optional[str] = None
    created_at: datetime
    total_deliveries: int = 0
    pending_deliveries: int = 0
    average_rating: float = 0.0
    total_reviews: int = 0
    current_balance: float = 0.0
    total_earnings: float = 0.0
    created_by: Optional[int] = None
    updated_by: Optional[int] = None

    @field_validator('aadhaar_number', mode='before')
    @classmethod
    def mask_aadhaar(cls, v: Optional[str]) -> Optional[str]:
        if v and len(str(v)) >= 12:
            return f"********{str(v)[-4:]}"
        return v
        
    @field_validator('license_number', mode='before')
    @classmethod
    def mask_license(cls, v: Optional[str]) -> Optional[str]:
        if v and len(str(v)) >= 6:
            return f"******{str(v)[-4:]}"
        return v

    @field_validator('account_number', mode='before')
    @classmethod
    def mask_account(cls, v: Optional[str]) -> Optional[str]:
        if v and len(str(v)) >= 4:
            return f"******{str(v)[-4:]}"
        return v

    @field_validator('upi_id', mode='before')
    @classmethod
    def mask_upi(cls, v: Optional[str]) -> Optional[str]:
        if v and '@' in str(v):
            parts = str(v).split('@')
            if len(parts[0]) > 2:
                return f"{parts[0][:2]}***@{parts[1]}"
        return v

    class Config:
        from_attributes = True

class OrderItemForRider(BaseModel):
    id: int
    order_number: str
    product_name: str
    product_id: UUID
    quantity: int
    price: float
    variant_attributes: Optional[dict] = None
    shipping_address: Optional[str]
    customer_name: Optional[str]
    customer_phone: Optional[str]
    status: str
    payment_status: str
    payment_method: str = "COD"
    total_amount: float = 0.0
    delivery_attempts: int = 0
    product_image: Optional[str] = None
    rider_payment_method: Optional[str] = None  # online, cash, upi — set by rider at delivery
    is_exchange: bool = False
    replacement_for_return_id: Optional[int] = None

    class Config:
        from_attributes = True

class RiderReturnTask(BaseModel):
    id: int
    return_id: int
    order_number: str
    product_name: str
    product_id: UUID
    quantity: int
    variant_attributes: Optional[dict] = None
    product_image: Optional[str] = None
    pickup_address: str
    customer_name: Optional[str]
    customer_phone: Optional[str]
    status: str
    reason: str
    is_exchange: bool = False
    exchange_variant_attributes: Optional[dict] = None
    pickup_attempts: int = 0
    pickup_date: Optional[datetime] = None
    created_at: datetime
    payment_method: str = "COD"
    refund_amount: float = 0.0
    extra_amount_to_collect: float = 0.0
    logistics_partner_id: Optional[int] = None

    class Config:
        from_attributes = True

class RiderEarningSchema(BaseModel):
    id: int
    amount: float
    type: str
    status: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
