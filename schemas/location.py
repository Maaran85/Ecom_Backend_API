from uuid import UUID
from pydantic import BaseModel
from typing import Optional, List

class StateBase(BaseModel):
    name: str
    country_id: int
    state_code: Optional[str] = None
    type: Optional[str] = None
    is_active: bool = True

class State(StateBase):
    id: int

    class Config:
        from_attributes = True

class CountryBase(BaseModel):
    name: str
    iso_code: Optional[str] = None
    phone_code: Optional[str] = None
    is_active: bool = True

class Country(CountryBase):
    id: int

    class Config:
        from_attributes = True

class CountryWithStates(Country):
    states: List[State] = []

class PincodeResponse(BaseModel):
    pincode: str
    city: Optional[str] = None
    state: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None

    class Config:
        from_attributes = True

class ServiceabilityCheckResponse(BaseModel):
    is_serviceable: bool
    serviceable: Optional[bool] = None
    delivery_type: Optional[str] = None # "warehouse_direct", "local_hub", or "courier"
    serviceability_source: Optional[str] = None # "same_pincode_warehouse", "local_hub_radius", or "courier_whitelist"
    message: str
    estimated_days: Optional[int] = None
    estimated_delivery_date: Optional[str] = None
    pincode: Optional[str] = None
    product_id: Optional[UUID] = None
    variant_id: Optional[UUID] = None
    reason_code: Optional[str] = None
    delivery_fee: Optional[float] = None
    warehouse_id: Optional[int] = None
    locality: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    is_interstate: Optional[bool] = False
    origin_state: Optional[str] = None
    destination_state: Optional[str] = None

