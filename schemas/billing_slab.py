from pydantic import BaseModel, Field, model_validator
from typing import Optional
from datetime import datetime


ALLOWED_CATEGORIES = (
    "auction_marketplace",
    "marketplace",
    "marketing",
    "logistics",
    "referral",
    "referral_purchase",
    "spin_win",
)


class BillingSlabBase(BaseModel):
    category_key: str = Field(..., description="Category key: auction_marketplace, marketplace, marketing, logistics, referral, referral_purchase, spin_win")
    min_price: float = Field(0.0, ge=0.0, description="Minimum price threshold (inclusive)")
    max_price: Optional[float] = Field(None, description="Maximum price threshold (inclusive), None for open-ended range")
    dealer_percentage: Optional[float] = Field(None, ge=0.0, le=1.0, description="Dealer percentage as decimal e.g. 0.02 for 2%")
    customer_percentage: Optional[float] = Field(None, ge=0.0, le=1.0, description="Customer percentage as decimal e.g. 0.005 for 0.5%")
    dealer_amount: Optional[float] = Field(None, ge=0.0, description="Fixed Dealer amount e.g. 100.0")
    customer_amount: Optional[float] = Field(None, ge=0.0, description="Fixed Customer amount e.g. 5.0")
    gst_type: Optional[str] = Field(None, description="GST type description or code e.g. STANDARD_18")
    sac_hsn_code: Optional[str] = Field(None, description="SAC or HSN code e.g. 998314")
    calculation_basis: Optional[str] = Field(None, description="Calculation basis description e.g. Net Selling Price")
    notes: Optional[str] = Field(None, description="Additional rule notes or description")
    is_active: bool = True

    @model_validator(mode="after")
    def validate_price_range(self):
        if self.category_key not in ALLOWED_CATEGORIES:
            raise ValueError(f"category_key must be one of: {ALLOWED_CATEGORIES}")
        if self.max_price is not None:
            if self.max_price < self.min_price:
                raise ValueError("max_price cannot be less than min_price")
        return self


class BillingSlabCreate(BillingSlabBase):
    pass


class BillingSlabUpdate(BaseModel):
    min_price: Optional[float] = Field(None, ge=0.0)
    max_price: Optional[float] = Field(None)
    dealer_percentage: Optional[float] = Field(None, ge=0.0, le=1.0)
    customer_percentage: Optional[float] = Field(None, ge=0.0, le=1.0)
    dealer_amount: Optional[float] = Field(None, ge=0.0)
    customer_amount: Optional[float] = Field(None, ge=0.0)
    gst_type: Optional[str] = None
    sac_hsn_code: Optional[str] = None
    calculation_basis: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def validate_price_range(self):
        if self.min_price is not None and self.max_price is not None:
            if self.max_price < self.min_price:
                raise ValueError("max_price cannot be less than min_price")
        return self


class BillingSlabOut(BillingSlabBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
