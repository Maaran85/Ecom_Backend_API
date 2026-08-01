from uuid import UUID
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import date, datetime
from core.enums import SettlementStatus


class TDSDeductionRow(BaseModel):
    settlement_number: Optional[str]
    order_number: Optional[str]
    order_date: Optional[date]
    settlement_date: date
    gross_sale_amount: float
    tds_base: float
    tds_rate: float
    tds_amount: float
    pan_available: bool
    organization_type: str


class TDSStatementOut(BaseModel):
    """Form 26AS style TDS deduction statement for a dealer + FY."""
    dealer_id: UUID
    dealer_name: str
    financial_year: str
    organization_type: Optional[str]
    pan_available: bool
    total_gross_sale: float
    total_tds_base: float
    total_tds_exempt: float
    total_tds: float
    deductions: List[TDSDeductionRow] = []


class SettlementReportRow(BaseModel):
    settlement_number: Optional[str]
    status: SettlementStatus
    period_start: date
    period_end: date
    financial_year: str
    gross_sale_amount: float
    total_fees: float
    total_tds: float
    net_payable: float
    paid_at: Optional[datetime]


class SettlementReportOut(BaseModel):
    """Aggregate settlement/TDS report for admins over a range."""
    period_start: date
    period_end: date
    total_gross_sale: float
    total_marketplace_fee: float
    total_marketing_fee: float
    total_tds: float
    total_net_payable: float
    settlement_count: int
    rows: List[SettlementReportRow] = []


class TDSLedgerRow(BaseModel):
    dealer_id: UUID
    dealer_name: str
    financial_year: str
    cumulative_gross_sale: float
    cumulative_tds_exempt: float
    cumulative_tds_applied: float
    cumulative_tds_amount: float


class TDSLedgerOut(BaseModel):
    rows: List[TDSLedgerRow] = []
