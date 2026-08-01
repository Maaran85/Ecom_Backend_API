from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.permissions import require_admin, get_current_active_user
from models import User
from schemas.reports import (
    TDSStatementOut, SettlementReportOut, TDSLedgerOut,
)
from services.report_service import (
    dealer_tds_statement,
    settlement_report,
    tds_ledger,
)

router = APIRouter()


@router.get("/admin/reports/tds-statement", response_model=TDSStatementOut)
async def get_tds_statement(
    dealer_id: UUID = Query(...),
    financial_year: str = Query(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    try:
        return await dealer_tds_statement(db, dealer_id, financial_year)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/admin/reports/settlements", response_model=SettlementReportOut)
async def get_settlements_report(
    period_start: date = Query(...),
    period_end: date = Query(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if period_start > period_end:
        raise HTTPException(status_code=400, detail="period_start must be <= period_end")
    return await settlement_report(db, period_start, period_end)


@router.get("/admin/reports/tds-ledger", response_model=TDSLedgerOut)
async def get_tds_ledger(
    financial_year: str = Query(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return await tds_ledger(db, financial_year)


@router.get("/dealers/reports/tds-statement", response_model=TDSStatementOut)
async def get_my_tds_statement(
    financial_year: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    if not user.dealer_id:
        raise HTTPException(status_code=403, detail="User is not associated with a dealer")
    try:
        return await dealer_tds_statement(db, user.dealer_id, financial_year)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
