from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from models.address import AddressType

# Address Schemas
class AddressBase(BaseModel):
    full_name: str
    phone: str
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state_id: int
    pincode: str
    country: str = "India"
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    address_type: AddressType = AddressType.HOME

class AddressCreate(AddressBase):
    is_default: bool = False

class AddressUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state_id: Optional[int] = None
    pincode: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    address_type: Optional[AddressType] = None
    is_default: Optional[bool] = None

class Address(AddressBase):
    id: int
    customer_id: int
    is_default: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    state_name: Optional[str] = None
    state_code: Optional[str] = None

    class Config:
        from_attributes = True
