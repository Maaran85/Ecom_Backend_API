from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models import OrderItem, Order, Dealer
from models.settlement import Settlement, SettlementItem, SettlementAdjustment
from core.money import money, money_2dp
from core.enums import SettlementStatus, AdjustmentType
from services.settlement_calculator import SettlementCalculationResult
from services.settlement_snapshot_service import (
    build_config_snapshot,
    build_rule_snapshot,
    build_calculation_snapshot,
)


async def next_settlement_number(db: AsyncSession, fy_label: str) -> str:
    """STL-2026-0001 style sequential number per financial year."""
    count = (
        await db.execute(
            select(func.count(Settlement.id)).where(Settlement.financial_year == fy_label)
        )
    ).scalar() or 0
    return f"STL-{fy_label[:4]}-{count + 1:04d}"


async def build_and_persist_settlement(
    db: AsyncSession,
    calc: SettlementCalculationResult,
    *,
    period_start: date,
    period_end: date,
    fy_label: str,
    fy_start: date,
    fy_end: date,
    settlement_date: date,
    adjustment_rows: Optional[List[Tuple[SettlementAdjustment, str]]] = None,
    notes: Optional[str] = None,
) -> Settlement:
    """
    Persists a DRAFT settlement (items + snapshots). The caller is responsible
    for committing and for calling the workflow service to GENERATE it.
    """
    config_snapshot = await build_config_snapshot(db, calc.dealer)
    rule_snapshot = build_rule_snapshot(
        calc.dealer,
        has_pan=calc.has_pan,
        tds_rate=str(calc.tds_rate),
        exemption_limit=config_snapshot["tds"]["exemption_limit_with_pan"],
    )
    calculation_snapshot = build_calculation_snapshot(calc)

    settlement = Settlement(
        dealer_id=calc.dealer.id,
        status=SettlementStatus.DRAFT,
        financial_year=fy_label,
        fy_start_date=fy_start,
        fy_end_date=fy_end,
        period_start=period_start,
        period_end=period_end,
        gross_sale_amount=float(money_2dp(calc.gross_sale_total)),
        total_marketplace_fee=float(money_2dp(calc.marketplace_fee_total)),
        total_marketing_fee=float(money_2dp(calc.marketing_fee_total)),
        total_shipping_received=float(money_2dp(calc.shipping_received_total)),
        total_logistics_charge=float(money_2dp(calc.logistics_charge_total)),
        total_gst_on_fees=float(money_2dp(calc.gst_on_fees_total)),
        total_adjustments=float(money_2dp(calc.adjustment_total)),
        gross_tds_base=float(money_2dp(calc.tds_base_total)),
        tds_exempt_portion=float(money_2dp(calc.tds_exempt_total)),
        total_tds=float(money_2dp(calc.tds_total)),
        tds_rate_applied=float(calc.tds_rate),
        net_payable=float(calc.net_payable),
        precise_values=calc.precise,
        settlement_version=config_snapshot["settlement"]["settlement_version"],
        config_snapshot=config_snapshot,
        rule_snapshot=rule_snapshot,
        calculation_snapshot=calculation_snapshot,
        notes=notes,
        items=[],
    )
    db.add(settlement)
    await db.flush()

    settlement.settlement_number = await next_settlement_number(db, fy_label)

    for line in calc.lines:
        settlement.items.append(
            SettlementItem(
                order_item_id=line.item.id,
                order_id=line.order.id,
                order_number=line.order.order_number,
                order_date=_to_date(line.order.created_at),
                settlement_date=settlement_date,
                item_price=float(line.item.price),
                quantity=line.item.quantity,
                gross_sale_amount=float(money_2dp(line.gross_sale)),
                marketplace_fee=float(money_2dp(line.marketplace_fee)),
                marketing_fee=float(money_2dp(line.marketing_fee)),
                shipping_received=float(money_2dp(line.shipping_received)),
                logistics_charge=float(money_2dp(line.logistics_charge)),
                tds_base=float(money_2dp(line.tds_base)),
                tds_rate=float(line.tds_rate),
                tds_amount=float(money_2dp(line.tds_amount)),
                tds_exempt_portion=float(money_2dp(line.tds_exempt_portion)),
                net_payable=float(line.net_payable),
                precise_values=line.precise,
                delivery_type=line.delivery_type,
            )
        )

    if adjustment_rows:
        for adjustment, reason in adjustment_rows:
            settlement.adjustments.append(
                SettlementAdjustment(
                    order_id=adjustment.order_id,
                    order_item_id=adjustment.order_item_id,
                    source_settlement_id=adjustment.source_settlement_id,
                    type=adjustment.type,
                    reason=reason or adjustment.reason,
                    amount=adjustment.amount,
                    reference=adjustment.reference,
                )
            )

    await db.flush()
    return settlement


def _to_date(dt) -> date:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).date()
        return dt.date()
    return dt
