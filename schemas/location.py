from pydantic import BaseModel
from typing import Optional, List

class StateBase(BaseModel):
    name: str
    country_id: int
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
