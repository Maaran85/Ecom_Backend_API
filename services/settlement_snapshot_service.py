from typing import Dict, Any, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Dealer
from models.tds_configuration import TDSConfiguration
from models.fee_configuration import FeeConfiguration
from services.configuration_service import get_active_tds_config_required, get_settlement_configuration


async def build_config_snapshot(db: AsyncSession, dealer: Dealer) -> Dict[str, Any]:
    """
    Snapshot of the exact configuration used to produce a settlement:
      - active TDS rule for the dealer's org type
      - all active fee configurations
      - settlement engine config (return window, version)
    """
    tds_config = await get_active_tds_config_required(db, dealer.organization_type)
    settlement_config = await get_settlement_configuration(db)

    fee_result = await db.execute(
        select(FeeConfiguration).where(FeeConfiguration.is_active.is_(True))
    )
    fees = fee_result.scalars().all()

    return {
        "tds": {
            "organization_type": dealer.organization_type,
            "section": tds_config.section,
            "tds_rate_with_pan": tds_config.tds_rate_with_pan,
            "exemption_limit_with_pan": tds_config.exemption_limit_with_pan,
            "tds_rate_without_pan": tds_config.tds_rate_without_pan,
            "exemption_limit_without_pan": tds_config.exemption_limit_without_pan,
            "threshold_strategy": tds_config.threshold_strategy.value,
        },
        "fees": {
            f.key: {
                "fee_type": f.fee_type.value,
                "value": f.value,
                "is_gst_applicable": f.is_gst_applicable,
                "gst_rate": f.gst_rate,
            }
            for f in fees
        },
        "settlement": {
            "return_window_days": settlement_config.return_window_days,
            "settlement_version": settlement_config.settlement_version,
        },
    }


def build_rule_snapshot(dealer: Dealer, has_pan: bool, tds_rate, exemption_limit) -> Dict[str, Any]:
    """Dealer-specific facts applied during settlement (auditable)."""
    return {
        "dealer_id": str(dealer.id),
        "organization_type": dealer.organization_type,
        "has_pan": has_pan,
        "tds_rate": tds_rate,
        "exemption_limit_with_pan": exemption_limit,
        "pan_masked": _mask_pan(dealer.pan_number),
    }


def build_calculation_snapshot(calc_result) -> Dict[str, Any]:
    """Per-line calculation detail used to reproduce a settlement exactly."""
    lines = []
    for line in calc_result.lines:
        lines.append(
            {
                "order_item_id": line.item.id,
                "order_id": line.order.id,
                "order_number": line.order.order_number,
                "gross_sale": str(line.gross_sale),
                "marketplace_fee": str(line.marketplace_fee),
                "marketing_fee": str(line.marketing_fee),
                "shipping_received": str(line.shipping_received),
                "logistics_charge": str(line.logistics_charge),
                "gst_on_fees": str(line.gst_on_fees),
                "tds_rate": str(line.tds_rate),
                "tds_exempt_portion": str(line.tds_exempt_portion),
                "tds_base": str(line.tds_base),
                "tds_amount": str(line.tds_amount),
                "net_payable": str(line.net_payable),
                "delivery_type": line.delivery_type,
                "precise": line.precise,
            }
        )
    return {
        "lines": lines,
        "totals": {
            "gross_sale_total": str(calc_result.gross_sale_total),
            "marketplace_fee_total": str(calc_result.marketplace_fee_total),
            "marketing_fee_total": str(calc_result.marketing_fee_total),
            "shipping_received_total": str(calc_result.shipping_received_total),
            "logistics_charge_total": str(calc_result.logistics_charge_total),
            "gst_on_fees_total": str(calc_result.gst_on_fees_total),
            "tds_exempt_total": str(calc_result.tds_exempt_total),
            "tds_base_total": str(calc_result.tds_base_total),
            "tds_total": str(calc_result.tds_total),
            "net_payable": str(calc_result.net_payable),
        },
        "precise": calc_result.precise,
    }


def _mask_pan(pan: str) -> str:
    if not pan:
        return None
    if len(pan) < 4:
        return "***"
    return pan[:2] + "********" + pan[-2:]
