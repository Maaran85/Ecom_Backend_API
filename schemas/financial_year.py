from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from datetime import date, datetime


class DealerFinancialYearSummaryOut(BaseModel):
    id: int
    dealer_id: UUID
    financial_year: str
    fy_start_date: date
    fy_end_date: date
    cumulative_gross_sale: float
    cumulative_tds_exempt: float
    cumulative_tds_applied: float
    cumulative_tds_amount: float
    total_settlements: int

    class Config:
        from_attributes = True


class FinancialYearPeriodOut(BaseModel):
    """Resolved FY for a given date."""
    financial_year: str
    start_date: date
    end_date: date
