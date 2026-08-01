from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime
from core.enums import TDSThresholdStrategy


class TDSConfigurationBase(BaseModel):
    section: str = Field(default="194-O", description="Income Tax Act section")
    organization_type: str = Field(..., description="individual, huf, company, llp, private_limited, ...")
    tds_rate_with_pan: float = Field(default=0.001, ge=0, le=1, description="TDS rate as decimal (0.001 = 0.1%)")
    exemption_limit_with_pan: Optional[float] = Field(default=None, ge=0, description="NULL = no exemption")
    tds_rate_without_pan: float = Field(default=0.05, ge=0, le=1, description="TDS rate without PAN (0.05 = 5%)")
    exemption_limit_without_pan: Optional[float] = Field(default=None, ge=0)
    threshold_strategy: TDSThresholdStrategy = TDSThresholdStrategy.PROSPECTIVE
    is_active: bool = True


class TDSConfigurationCreate(TDSConfigurationBase):
    pass


class TDSConfigurationUpdate(BaseModel):
    section: Optional[str] = None
    tds_rate_with_pan: Optional[float] = Field(default=None, ge=0, le=1)
    exemption_limit_with_pan: Optional[float] = Field(default=None, ge=0)
    tds_rate_without_pan: Optional[float] = Field(default=None, ge=0, le=1)
    exemption_limit_without_pan: Optional[float] = Field(default=None, ge=0)
    threshold_strategy: Optional[TDSThresholdStrategy] = None
    is_active: Optional[bool] = None


class TDSConfigurationOut(TDSConfigurationBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
