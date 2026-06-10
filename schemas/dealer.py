from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from models.cart import OrderStatus

class HubBase(BaseModel):
    name: str
    address: str
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    state_id: Optional[int] = None
    country_id: Optional[int] = None
    phone: Optional[str] = None
    contact_person: Optional[str] = None
    is_active: bool = True
    is_showroom: bool = False

class HubCreate(HubBase):
    pass

class Hub(HubBase):
    id: int
    dealer_id: int
    created_at: datetime
    is_showroom: bool
    
    class Config:
        from_attributes = True

class DealerBase(BaseModel):
    business_name: str
    business_address: Optional[str] = None
    gst_number: Optional[str] = None

class DealerCreate(DealerBase):
    pass

class DealerSelfRegistration(DealerBase):
    owner_name: str
    phone: str
    email_id: str
    password: str
    pan_number: Optional[str] = None

class DealerProfileComplete(BaseModel):
    # Company Details
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    lat_long: Optional[str] = None
    business_phone: Optional[str] = None
    
    # Documents
    company_photo_url: Optional[str] = None
    gst_certificate_url: Optional[str] = None
    incorporation_certificate_url: Optional[str] = None
    pan_number: str
    pan_photo_url: Optional[str] = None
    cin_number: Optional[str] = None
    cin_certificate_url: Optional[str] = None
    company_logo_url: Optional[str] = None
    
    # Bank Details
    bank_name: str
    bank_address: str
    bank_branch: str
    ifsc_code: str
    account_holder_name: str
    account_number: str

class DealerUpdate(BaseModel):
    business_name: Optional[str] = None
    business_address: Optional[str] = None
    gst_number: Optional[str] = None
    delivery_charge: Optional[float] = None
    free_delivery_above: Optional[float] = None
    estimated_delivery_days: Optional[int] = None

class Dealer(DealerBase):
    id: int
    user_id: int
    is_approved: bool
    profile_status: str
    access_status: str
    reject_reason: Optional[str] = None
    delivery_charge: float
    free_delivery_above: float
    estimated_delivery_days: int
    platform_fee_percent: float
    created_at: datetime

    class Config:
        from_attributes = True

class DealerWithUser(Dealer):
    """Dealer with user information"""
    user_email: Optional[str] = None
    user_name: Optional[str] = None

    class Config:
        from_attributes = True

class OrderItemDealer(BaseModel):
    id: int
    item_order_id: Optional[str] = None
    product_id: int
    product_name: str
    quantity: int
    price: float
    size: Optional[str] = None
    product_image: Optional[str] = None
    status: str
    reject_reason: Optional[str] = None
    courier_company: Optional[str] = None
    tracking_number: Optional[str] = None
    tracking_url: Optional[str] = None
    dispatch_date: Optional[datetime] = None
    estimated_delivery: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    return_status: Optional[str] = None
    return_reason: Optional[str] = None
    return_id: Optional[int] = None
    return_pickup_date: Optional[datetime] = None
    payment_status: str = "pending"
    rider_id: Optional[int] = None
    rider_name: Optional[str] = None
    rider_phone: Optional[str] = None
    delivery_attempts: Optional[int] = 0
    is_exchange: bool = False
    exchange_variant_id: Optional[int] = None
    exchange_variant: Optional[dict] = None
    hub_id: Optional[int] = None
    hub: Optional[Hub] = None
    hub_arrived_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    tax_amount: Optional[float] = 0.0
    cgst_rate: Optional[float] = 0.0
    sgst_rate: Optional[float] = 0.0
    igst_rate: Optional[float] = 0.0
    hsn_code: Optional[str] = None
    platform_fee: Optional[float] = 0.0
    logistics_partner_id: Optional[int] = None
    order_notes: Optional[str] = None
    payment_method: Optional[str] = None
    dealer_name: Optional[str] = None

class DealerOrderResponse(BaseModel):
    id: int
    order_number: Optional[str] = None
    created_at: datetime
    subtotal: Optional[float] = None          # Pre-discount total
    discount_amount: Optional[float] = None   # Discount applied
    total_amount: float                       # Final amount paid
    status: OrderStatus
    payment_method: str = "COD"
    shipping_address: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    showroom_name: Optional[str] = None
    notes: Optional[str] = None
    items: List[OrderItemDealer]
    return_status: Optional[str] = None
    return_reason: Optional[str] = None
    refund_amount: Optional[float] = None
    cancellation_reason: Optional[str] = None

    class Config:
        from_attributes = True

class DealerRefundItem(BaseModel):
    return_id: int
    order_id: int
    order_item_id: Optional[int]
    item_order_id: str
    product_name: str
    product_image: Optional[str]
    quantity: int
    price: float
    total_refund: float
    reason: str
    admin_notes: Optional[str] = None
    return_status: str
    refund_initiated: bool
    requested_at: datetime
    customer_name: str
    is_exchange: Optional[bool] = False
    exchange_variant_id: Optional[int] = None


