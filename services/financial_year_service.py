from datetime import date, datetime, timezone
from typing import Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.financial_year_summary import DealerFinancialYearSummary
from core.money import money


def financial_year_for(dt: date) -> Tuple[str, date, date]:
    """Indian financial year: 1 April - 31 March. Label like '2026-2027'."""
    if dt.month >= 4:
        start_year = dt.year
    else:
        start_year = dt.year - 1
    fy_label = f"{start_year}-{start_year + 1}"
    start = date(start_year, 4, 1)
    end = date(start_year + 1, 3, 31)
    return fy_label, start, end


def as_date(dt: datetime) -> date:
    if dt.tzinfo is not None and hasattr(dt, "astimezone"):
        return dt.astimezone(timezone.utc).date()
    return dt.date() if hasattr(dt, "date") else dt


async def get_or_create_fy_summary(
    db: AsyncSession,
    dealer_id: UUID,
    fy_label: str,
    fy_start: date,
    fy_end: date,
) -> DealerFinancialYearSummary:
    result = await db.execute(
        select(DealerFinancialYearSummary).where(
            DealerFinancialYearSummary.dealer_id == dealer_id,
            DealerFinancialYearSummary.financial_year == fy_label,
        )
    )
    summary = result.scalar_one_or_none()
    if summary is None:
        summary = DealerFinancialYearSummary(
            dealer_id=dealer_id,
            financial_year=fy_label,
            fy_start_date=fy_start,
            fy_end_date=fy_end,
        )
        db.add(summary)
        await db.flush()
    return summary


def apply_to_fy_summary(
    summary: DealerFinancialYearSummary,
    gross_sale,
    tds_exempt,
    tds_applied,
    tds_amount,
) -> None:
    """Accumulate one settlement's numbers into the FY summary (in-memory; caller commits)."""
    summary.cumulative_gross_sale = float(
        money(summary.cumulative_gross_sale) + money(gross_sale)
    )
    summary.cumulative_tds_exempt = float(
        money(summary.cumulative_tds_exempt) + money(tds_exempt)
    )
    summary.cumulative_tds_applied = float(
        money(summary.cumulative_tds_applied) + money(tds_applied)
    )
    summary.cumulative_tds_amount = float(
        money(summary.cumulative_tds_amount) + money(tds_amount)
    )
    summary.total_settlements += 1


def revert_from_fy_summary(
    summary: DealerFinancialYearSummary,
    gross_sale,
    tds_exempt,
    tds_applied,
    tds_amount,
) -> None:
    """Reverse one settlement's numbers from the FY summary (e.g. upon cancellation)."""
    summary.cumulative_gross_sale = max(0.0, float(
        money(summary.cumulative_gross_sale) - money(gross_sale)
    ))
    summary.cumulative_tds_exempt = max(0.0, float(
        money(summary.cumulative_tds_exempt) - money(tds_exempt)
    ))
    summary.cumulative_tds_applied = max(0.0, float(
        money(summary.cumulative_tds_applied) - money(tds_applied)
    ))
    summary.cumulative_tds_amount = max(0.0, float(
        money(summary.cumulative_tds_amount) - money(tds_amount)
    ))
    summary.total_settlements = max(0, summary.total_settlements - 1)
