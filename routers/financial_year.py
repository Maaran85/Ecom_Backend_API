from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.permissions import require_admin, get_current_active_user
from models import User
from models.financial_year_summary import DealerFinancialYearSummary
from schemas.financial_year import (
    DealerFinancialYearSummaryOut,
    FinancialYearPeriodOut,
)
from services.financial_year_service import financial_year_for

router = APIRouter()


@router.get("/financial-year/period", response_model=FinancialYearPeriodOut)
async def get_financial_year_period(
    for_date: Optional[str] = Query(default=None, description="ISO date (YYYY-MM-DD); defaults to today"),
):
    from datetime import date
    dt = date.fromisoformat(for_date) if for_date else date.today()
    fy_label, start, end = financial_year_for(dt)
    return FinancialYearPeriodOut(financial_year=fy_label, start_date=start, end_date=end)


@router.get("/admin/dealers/{dealer_id}/financial-year/{financial_year}/summary", response_model=DealerFinancialYearSummaryOut)
async def get_dealer_fy_summary(
    dealer_id: UUID,
    financial_year: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(
        select(DealerFinancialYearSummary).where(
            DealerFinancialYearSummary.dealer_id == dealer_id,
            DealerFinancialYearSummary.financial_year == financial_year,
        )
    )
    summary = result.scalar_one_or_none()
    if not summary:
        raise HTTPException(status_code=404, detail="No FY summary found for this dealer/financial year")
    return summary


@router.get("/dealers/financial-year/summary", response_model=DealerFinancialYearSummaryOut)
async def get_my_fy_summary(
    financial_year: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    if not user.dealer_id:
        raise HTTPException(status_code=403, detail="User is not associated with a dealer")
    result = await db.execute(
        select(DealerFinancialYearSummary).where(
            DealerFinancialYearSummary.dealer_id == user.dealer_id,
            DealerFinancialYearSummary.financial_year == financial_year,
        )
    )
    summary = result.scalar_one_or_none()
    if not summary:
        raise HTTPException(status_code=404, detail="No FY summary found for this financial year")
    return summary
