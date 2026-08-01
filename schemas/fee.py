from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime
from core.enums import FeeType


class FeeConfigurationBase(BaseModel):
    key: str = Field(..., description="e.g. marketplace_fee, marketing_fee, partner_logistics_fee")
    name: Optional[str] = None
    description: Optional[str] = None
    fee_type: FeeType = FeeType.FLAT
    value: float = Field(default=0.0, description="flat amount per item or decimal rate for percentage")
    is_gst_applicable: bool = False
    gst_rate: float = Field(default=0.0, ge=0, le=1)
    is_active: bool = True


class FeeConfigurationCreate(FeeConfigurationBase):
    pass


class FeeConfigurationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    fee_type: Optional[FeeType] = None
    value: Optional[float] = None
    is_gst_applicable: Optional[bool] = None
    gst_rate: Optional[float] = Field(default=None, ge=0, le=1)
    is_active: Optional[bool] = None


class FeeConfigurationOut(FeeConfigurationBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
