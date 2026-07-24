from uuid import UUID
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date

# --- Tax Category Schemas ---

class TaxCategoryBase(BaseModel):
    name: str = Field(..., description="Name of the tax slab, e.g., GST 12%")
    description: Optional[str] = None
    tax_type: str = Field(default="CGST_SGST", description="CGST_SGST, IGST, VAT, CUSTOM")
    cgst_rate: float = Field(default=0.0)
    sgst_rate: float = Field(default=0.0)
    igst_rate: float = Field(default=0.0)
    vat_rate: float = Field(default=0.0)
    custom_rate: float = Field(default=0.0)
    is_active: bool = Field(default=True)

class TaxCategoryCreate(TaxCategoryBase):
    pass

class TaxCategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tax_type: Optional[str] = None
    cgst_rate: Optional[float] = None
    sgst_rate: Optional[float] = None
    igst_rate: Optional[float] = None
    vat_rate: Optional[float] = None
    custom_rate: Optional[float] = None
    is_active: Optional[bool] = None

class TaxCategoryOut(TaxCategoryBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# --- Tax Rule Schemas ---

class TaxRuleBase(BaseModel):
    name: str
    category_id: Optional[int] = None
    product_id: Optional[UUID] = None
    tax_category_id: int
    priority: int = 0
    state_code: Optional[str] = None
    is_active: bool = True

class TaxRuleCreate(TaxRuleBase):
    pass

class TaxRuleUpdate(BaseModel):
    name: Optional[str] = None
    category_id: Optional[int] = None
    product_id: Optional[UUID] = None
    tax_category_id: Optional[int] = None
    priority: Optional[int] = None
    state_code: Optional[str] = None
    is_active: Optional[bool] = None

class TaxRuleOut(TaxRuleBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime]
    tax_category: Optional[TaxCategoryOut] = None

    class Config:
        from_attributes = True


# --- Financial Report Schemas ---

class PLReportOut(BaseModel):
    """Profit and Loss Statement details for the platform"""
    period_start: str
    period_end: str
    gross_merchandise_value: float = Field(description="Total value of all delivered orders (inclusive of tax)")
    total_refunds: float = Field(description="Total value refunded to customers")
    total_tax_collected: float = Field(description="Total tax collected on behalf of dealers (to be remitted by dealers)")
    net_merchandise_value: float = Field(description="GMV - Refunds - Tax")
    
    # Platform true revenue
    platform_fee_revenue: float = Field(description="Total commission earned by the platform")
    
class GST1SummaryRow(BaseModel):
    hsn_code: str
    description: str
    total_quantity: int
    total_taxable_value: float
    total_cgst: float
    total_sgst: float
    total_igst: float
    total_tax: float

class GST1SummaryOut(BaseModel):
    period: str
    total_b2c_sales: float
    total_b2b_sales: float
    total_cgst_collected: float
    total_sgst_collected: float
    total_igst_collected: float
    hsn_summary: List[GST1SummaryRow]

class DealerPayoutRow(BaseModel):
    dealer_id: UUID
    dealer_name: str
    gross_order_value: float
    refunds: float
    platform_commission: float
    tcs_deduction: float  # Tax Collected at Source (GST) - 1%
    tds_deduction: float  # Tax Deducted at Source (Income Tax) - 0.1% or 1%
    net_payout: float
    status: str

class TDSReportOut(BaseModel):
    period: str
    total_gross_value: float
    total_platform_commission: float
    total_tcs_withheld: float
    total_tds_withheld: float
    total_net_payout: float
    payouts: List[DealerPayoutRow]

# --- Tax Calculator Schema ---
class TaxCalculatorRequest(BaseModel):
    product_id: UUID
    inclusive_price: float
    quantity: int = 1
    buyer_state: Optional[str] = None
    seller_state: Optional[str] = None


# --- Dealer Remittance Schemas ---

class DealerRemittanceBase(BaseModel):
    amount: float
    reference_no: Optional[str] = None
    payment_method: Optional[str] = None
    payment_date: Optional[date] = None   # Actual payment transfer date
    notes: Optional[str] = None
    type: str = Field(default="payout", description="payout or collection")

class DealerRemittanceCreate(DealerRemittanceBase):
    dealer_id: UUID
    order_item_ids: List[int] = []

class DealerRemittanceSubmit(DealerRemittanceBase):
    order_item_ids: List[int] = []

class DealerRemittanceStatusUpdate(BaseModel):
    status: str

class DealerRemittanceOut(DealerRemittanceBase):
    id: int
    dealer_id: UUID
    status: str
    created_at: datetime
    updated_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    confirmed_by_admin_id: Optional[int]
    order_numbers: List[str] = []

    class Config:
        from_attributes = True
