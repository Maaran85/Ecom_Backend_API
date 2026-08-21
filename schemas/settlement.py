from uuid import UUID
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field
from datetime import date, datetime
from core.enums import SettlementStatus, AdjustmentType


# --- Settlement Item ---

class SettlementItemOut(BaseModel):
    id: int
    settlement_id: int
    order_item_id: Optional[int]
    order_id: Optional[int]
    order_number: Optional[str]
    order_date: Optional[date]
    settlement_date: date
    item_price: float
    quantity: int
    gross_sale_amount: float
    marketplace_fee: float
    marketing_fee: float
    shipping_received: float
    logistics_charge: float
    tds_base: float
    tds_rate: float
    tds_amount: float
    tds_exempt_portion: float
    net_payable: float
    delivery_type: Optional[str]

    class Config:
        from_attributes = True


# --- Settlement Adjustment ---

class SettlementAdjustmentOut(BaseModel):
    id: int
    settlement_id: int
    order_id: Optional[int]
    order_item_id: Optional[int]
    source_settlement_id: Optional[int]
    type: AdjustmentType
    reason: str
    amount: float
    reference: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class SettlementAdjustmentCreate(BaseModel):
    order_id: Optional[int] = None
    order_item_id: Optional[int] = None
    source_settlement_id: Optional[int] = None
    type: AdjustmentType
    reason: str = Field(..., description="return, refund, cancellation, correction")
    amount: float = Field(..., gt=0)
    reference: Optional[str] = None


# --- Settlement ---

class SettlementOut(BaseModel):
    id: int
    settlement_number: Optional[str]
    dealer_id: UUID
    status: SettlementStatus
    financial_year: str
    fy_start_date: date
    fy_end_date: date
    period_start: date
    period_end: date
    gross_sale_amount: float
    total_marketplace_fee: float
    total_marketing_fee: float
    total_shipping_received: float
    total_logistics_charge: float
    total_gst_on_fees: float
    total_adjustments: float
    gross_tds_base: float
    tds_exempt_portion: float
    total_tds: float
    tds_rate_applied: float
    net_payable: float
    settlement_version: str
    notes: Optional[str]
    cancel_reason: Optional[str]
    generated_at: Optional[datetime]
    approved_at: Optional[datetime]
    approved_by: Optional[int]
    paid_at: Optional[datetime]
    paid_by: Optional[int]
    cancelled_at: Optional[datetime]
    remittance_id: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    items: List[SettlementItemOut] = []
    adjustments: List[SettlementAdjustmentOut] = []

    class Config:
        from_attributes = True


class SettlementSummaryOut(BaseModel):
    """Lightweight list view (no items)."""
    id: int
    settlement_number: Optional[str]
    dealer_id: UUID
    dealer_name: Optional[str] = None
    status: SettlementStatus
    financial_year: str
    period_start: date
    period_end: date
    gross_sale_amount: float
    total_tds: float
    net_payable: float
    item_count: int = 0
    generated_at: Optional[datetime]
    paid_at: Optional[datetime]
    created_at: Optional[datetime]


# --- Requests / Actions ---

class GenerateSettlementRequest(BaseModel):
    dealer_id: Optional[UUID] = None  # None = run for all eligible dealers
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    dry_run: bool = False              # preview without persisting


class SettlementPreviewItem(BaseModel):
    order_item_id: int
    order_id: int
    order_number: Optional[str]
    gross_sale_amount: float
    marketplace_fee: float
    marketing_fee: float
    shipping_received: float
    logistics_charge: float
    tds_base: float
    tds_rate: float
    tds_amount: float
    tds_exempt_portion: float
    net_payable: float
    delivery_type: Optional[str] = None


class SettlementPreviewOut(BaseModel):
    dealer_id: UUID
    financial_year: str
    item_count: int
    gross_sale_amount: float
    total_marketplace_fee: float
    total_marketing_fee: float
    total_shipping_received: float
    total_logistics_charge: float
    total_gst_on_fees: float
    gross_tds_base: float
    tds_exempt_portion: float
    total_tds: float
    tds_rate_applied: float
    net_payable: float
    items: List[SettlementPreviewItem] = []


class SettlementApproveRequest(BaseModel):
    notes: Optional[str] = None


class SettlementPaidRequest(BaseModel):
    reference_no: Optional[str] = None
    payment_method: Optional[str] = None
    payment_date: Optional[date] = None
    notes: Optional[str] = None


class SettlementCancelRequest(BaseModel):
    reason: str = Field(..., min_length=1)
