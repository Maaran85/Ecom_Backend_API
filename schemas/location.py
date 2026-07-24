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
    delivery_type: Optional[str] = None # "local_hub" or "courier"
    message: str
    estimated_days: Optional[int] = None
