from typing import Optional, List
from pydantic import BaseModel, EmailStr
from datetime import datetime, date

class LogisticsPartnerBase(BaseModel):
    name: str
    contact_person: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    is_internal: bool = True
    is_active: bool = True
    tracking_api_url: Optional[str] = None

class LogisticsPartnerCreate(LogisticsPartnerBase):
    api_key: Optional[str] = None

class LogisticsPartnerUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    is_internal: Optional[bool] = None
    is_active: Optional[bool] = None
    tracking_api_url: Optional[str] = None
    api_key: Optional[str] = None

class LogisticsPartner(LogisticsPartnerBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class LogisticsStats(BaseModel):
    total_partners: int
    active_partners: int
    total_assigned_orders: int
    pending_assignments: int

class OrderAssignmentCreate(BaseModel):
    order_item_ids: List[int]
    logistics_partner_id: Optional[int] = None
    rider_id: Optional[int] = None

class LogisticsUserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: str
    logistics_partner_id: Optional[int] = None
    phone: Optional[str] = None
    dob: Optional[str] = None
    address: Optional[str] = None
    aadhaar_number: Optional[str] = None
    photo_url: Optional[str] = None
    aadhaar_image: Optional[str] = None
    employee_id: Optional[str] = None
    shift_type: Optional[str] = None
    emergency_contact: Optional[str] = None
    is_active: bool = True

class LogisticsUserCreate(LogisticsUserBase):
    password: str

class LogisticsUserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    phone: Optional[str] = None
    dob: Optional[str] = None
    address: Optional[str] = None
    aadhaar_number: Optional[str] = None
    photo_url: Optional[str] = None
    aadhaar_image: Optional[str] = None
    employee_id: Optional[str] = None
    shift_type: Optional[str] = None
    emergency_contact: Optional[str] = None

class RemittanceCreate(BaseModel):
    amount: float
    reference_no: Optional[str] = None
    payment_method: Optional[str] = None
    payment_date: Optional[date] = None
    notes: Optional[str] = None
    order_item_ids: List[int] = []

class RemittanceStatusUpdate(BaseModel):
    status: str

class RemittanceResponse(BaseModel):
    id: int
    logistics_partner_id: int
    amount: float
    status: str
    reference_no: Optional[str]
    payment_method: Optional[str]
    payment_date: Optional[date] = None
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    confirmed_by_admin_id: Optional[int]
    order_numbers: List[str] = []

    class Config:
        from_attributes = True
