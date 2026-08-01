from datetime import date
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models import Dealer
from models.settlement import Settlement, SettlementItem
from models.financial_year_summary import DealerFinancialYearSummary
from core.enums import SettlementStatus


async def dealer_tds_statement(
    db: AsyncSession,
    dealer_id: UUID,
    financial_year: str,
) -> dict:
    """Form 26AS style TDS deduction statement for one dealer + FY."""
    dealer = await db.get(Dealer, dealer_id)
    if not dealer:
        raise ValueError("dealer not found")

    settlements = (
        await db.execute(
            select(Settlement)
            .where(
                Settlement.dealer_id == dealer_id,
                Settlement.financial_year == financial_year,
                Settlement.status.in_([SettlementStatus.APPROVED, SettlementStatus.PAID]),
            )
            .order_by(Settlement.period_start.asc())
        )
    ).scalars().all()

    settlement_ids = [s.id for s in settlements]
    deduction_rows = []
    if settlement_ids:
        item_rows = (
            await db.execute(
                select(SettlementItem).where(SettlementItem.settlement_id.in_(settlement_ids))
            )
        ).scalars().all()
        settlement_by_id = {s.id: s for s in settlements}
        for it in item_rows:
            deduction_rows.append(
                {
                    "settlement_number": settlement_by_id.get(it.settlement_id).settlement_number if it.settlement_id in settlement_by_id else None,
                    "order_number": it.order_number,
                    "order_date": it.order_date,
                    "settlement_date": it.settlement_date,
                    "gross_sale_amount": it.gross_sale_amount,
                    "tds_base": it.tds_base,
                    "tds_rate": it.tds_rate,
                    "tds_amount": it.tds_amount,
                    "pan_available": bool(dealer.pan_number),
                    "organization_type": dealer.organization_type,
                }
            )

    return {
        "dealer_id": dealer.id,
        "dealer_name": dealer.business_name,
        "financial_year": financial_year,
        "organization_type": dealer.organization_type,
        "pan_available": bool(dealer.pan_number),
        "total_gross_sale": round(sum(s.gross_sale_amount for s in settlements), 2),
        "total_tds_base": round(sum(s.gross_tds_base for s in settlements), 2),
        "total_tds_exempt": round(sum(s.tds_exempt_portion for s in settlements), 2),
        "total_tds": round(sum(s.total_tds for s in settlements), 2),
        "deductions": deduction_rows,
    }


async def settlement_report(
    db: AsyncSession,
    period_start: date,
    period_end: date,
) -> dict:
    """Aggregate settlement/TDS report over a date range (admin)."""
    settlements = (
        await db.execute(
            select(Settlement)
            .where(
                Settlement.period_start >= period_start,
                Settlement.period_end <= period_end,
            )
            .order_by(Settlement.period_start.asc())
        )
    ).scalars().all()

    return {
        "period_start": period_start,
        "period_end": period_end,
        "total_gross_sale": round(sum(s.gross_sale_amount for s in settlements), 2),
        "total_marketplace_fee": round(sum(s.total_marketplace_fee for s in settlements), 2),
        "total_marketing_fee": round(sum(s.total_marketing_fee for s in settlements), 2),
        "total_tds": round(sum(s.total_tds for s in settlements), 2),
        "total_net_payable": round(sum(s.net_payable for s in settlements), 2),
        "settlement_count": len(settlements),
        "rows": [
            {
                "settlement_number": s.settlement_number,
                "status": s.status,
                "period_start": s.period_start,
                "period_end": s.period_end,
                "financial_year": s.financial_year,
                "gross_sale_amount": s.gross_sale_amount,
                "total_fees": round(s.total_marketplace_fee + s.total_marketing_fee + s.total_logistics_charge, 2),
                "total_tds": s.total_tds,
                "net_payable": s.net_payable,
                "paid_at": s.paid_at,
            }
            for s in settlements
        ],
    }


async def tds_ledger(db: AsyncSession, financial_year: str) -> dict:
    """Per-dealer cumulative TDS position for a FY."""
    rows = (
        await db.execute(
            select(DealerFinancialYearSummary)
            .where(DealerFinancialYearSummary.financial_year == financial_year)
            .order_by(DealerFinancialYearSummary.cumulative_tds_amount.desc())
        )
    ).scalars().all()

    dealer_ids = {r.dealer_id for r in rows}
    dealers = {}
    if dealer_ids:
        dealer_rows = await db.execute(select(Dealer).where(Dealer.id.in_(dealer_ids)))
        dealers = {d.id: d for d in dealer_rows.scalars().all()}

    return {
        "rows": [
            {
                "dealer_id": r.dealer_id,
                "dealer_name": dealers[r.dealer_id].business_name if r.dealer_id in dealers else None,
                "financial_year": r.financial_year,
                "cumulative_gross_sale": r.cumulative_gross_sale,
                "cumulative_tds_exempt": r.cumulative_tds_exempt,
                "cumulative_tds_applied": r.cumulative_tds_applied,
                "cumulative_tds_amount": r.cumulative_tds_amount,
            }
            for r in rows
        ]
    }
