from pydantic import BaseModel, EmailStr
from typing import Optional, Any
from datetime import datetime
from models.user import UserRole
from schemas.dealer import Dealer as DealerSchema

class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserUpdate(UserBase):
    password: Optional[str] = None

class UserInDBBase(UserBase):
    id: int
    role: UserRole
    is_active: bool
    dealer_id: Optional[int] = None
    hub_id: Optional[int] = None
    logistics_partner_id: Optional[int] = None
    dob: Optional[str] = None
    address: Optional[str] = None
    aadhaar_number: Optional[str] = None
    emergency_contact: Optional[str] = None
    photo_url: Optional[str] = None
    aadhaar_image: Optional[str] = None
    employee_id: Optional[str] = None
    shift_type: Optional[str] = None
    created_at: datetime
    dealer: Optional[DealerSchema] = None

    class Config:
        from_attributes = True

class User(UserInDBBase):
    pass

class AdminUserCreate(UserBase):
    password: str
    role: str
    dealer_id: Optional[int] = None
    hub_id: Optional[int] = None
    logistics_partner_id: Optional[int] = None
    employee_id: Optional[str] = None
    shift_type: Optional[str] = None
    dob: Optional[str] = None
    address: Optional[str] = None
    aadhaar_number: Optional[str] = None
    emergency_contact: Optional[str] = None
    photo_url: Optional[str] = None
    aadhaar_image: Optional[str] = None
    is_active: Optional[bool] = True

class AdminUserUpdate(UserBase):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[str] = None
    dealer_id: Optional[int] = None
    hub_id: Optional[int] = None
    logistics_partner_id: Optional[int] = None
    employee_id: Optional[str] = None
    shift_type: Optional[str] = None
    dob: Optional[str] = None
    address: Optional[str] = None
    aadhaar_number: Optional[str] = None
    emergency_contact: Optional[str] = None
    photo_url: Optional[str] = None
    aadhaar_image: Optional[str] = None
    is_active: Optional[bool] = None
