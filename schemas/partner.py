from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PartnerBase(BaseModel):
    partner_name: str
    support_email: Optional[str] = None
    support_phone: Optional[str] = None
    address: Optional[str] = None
    pincode: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    tax_id: Optional[str] = None
    logo_url: Optional[str] = None
    
    license_key: Optional[str] = None
    plan_type: Optional[str] = "Basic"
    valid_until: Optional[datetime] = None
    max_dealers: Optional[int] = 10
    
    default_currency: Optional[str] = "INR"
    timezone: Optional[str] = "Asia/Kolkata"
    is_active: Optional[bool] = True

class PartnerCreate(PartnerBase):
    pass

class PartnerUpdate(BaseModel):
    partner_name: Optional[str] = None
    support_email: Optional[str] = None
    support_phone: Optional[str] = None
    address: Optional[str] = None
    pincode: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    tax_id: Optional[str] = None
    logo_url: Optional[str] = None
    
    license_key: Optional[str] = None
    plan_type: Optional[str] = None
    valid_until: Optional[datetime] = None
    max_dealers: Optional[int] = None
    
    default_currency: Optional[str] = None
    timezone: Optional[str] = None
    is_active: Optional[bool] = None

class PartnerResponse(PartnerBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
