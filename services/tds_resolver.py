from decimal import Decimal
from typing import List, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.money import money
from core.enums import TDSThresholdStrategy
from models.tds_configuration import TDSConfiguration
from services.configuration_service import get_active_tds_config_required, ConfigurationError


def _has_pan(dealer) -> bool:
    return bool(getattr(dealer, "pan_number", None))


async def resolve_tds_rate(db: AsyncSession, dealer) -> Decimal:
    """Applicable TDS rate (decimal) for a dealer based on its active rule + PAN."""
    config = await get_active_tds_config_required(db, getattr(dealer, "organization_type", None))
    rate, _ = applicable_rate_and_exemption(config, _has_pan(dealer))
    return rate


def applicable_rate_and_exemption(config: TDSConfiguration, has_pan: bool):
    if has_pan:
        return money(config.tds_rate_with_pan), config.exemption_limit_with_pan
    return money(config.tds_rate_without_pan), config.exemption_limit_without_pan


def resolve_tds_line(
    config: TDSConfiguration,
    has_pan: bool,
    cumulative_before: Decimal,
    gross_sale: Decimal,
) -> Dict[str, Any]:
    """
    Resolves TDS for a single gross-sale line given the FY cumulative gross
    recognized so far.

    PROSPECTIVE (default): the exemption limit shields the first `limit` rupees
    of FY gross sale; TDS applies only on the excess (excess-only).

    Returns:
      rate, exemption_limit (original or None), tds_exempt_portion,
      tds_base (amount actually taxed), tds_amount
    """
    if config.threshold_strategy != TDSThresholdStrategy.PROSPECTIVE:
        raise ConfigurationError(
            f"TDS threshold strategy '{config.threshold_strategy.value}' is not implemented. "
            "Only 'prospective' is currently supported; leave threshold_strategy=prospective."
        )

    rate, exemption_raw = applicable_rate_and_exemption(config, has_pan)
    exemption_limit = Decimal(str(exemption_raw)) if exemption_raw is not None else Decimal("0")

    gross = money(gross_sale)
    cumulative = money(cumulative_before)

    if exemption_limit <= 0:
        exempt_this = Decimal("0")
    else:
        covered_before = min(cumulative, exemption_limit)
        exempt_this = min(gross, max(Decimal("0"), exemption_limit - covered_before))

    tds_base = money(gross - exempt_this)
    tds_amount = money(tds_base * rate)

    return {
        "rate": rate,
        "exemption_limit": exemption_raw,
        "tds_exempt_portion": exempt_this,
        "tds_base": tds_base,
        "tds_amount": tds_amount,
    }


def resolve_tds_batch(
    config: TDSConfiguration,
    has_pan: bool,
    cumulative_before: Decimal,
    gross_sales: List[Decimal],
) -> Dict[str, Any]:
    """
    Resolves TDS across a list of per-item gross sales, tracking the exemption
    limit consumption cumulatively.

    Returns:
      items: [per-line resolve_tds_line result]
      cumulative_after, total_exempt, total_base, total_tds
    """
    cumulative = money(cumulative_before)
    results = []
    for gross in gross_sales:
        line = resolve_tds_line(config, has_pan, cumulative, gross)
        cumulative = money(cumulative + gross)
        results.append(line)

    return {
        "items": results,
        "cumulative_after": cumulative,
        "total_exempt": money(sum(r["tds_exempt_portion"] for r in results)),
        "total_base": money(sum(r["tds_base"] for r in results)),
        "total_tds": money(sum(r["tds_amount"] for r in results)),
        "has_pan": has_pan,
    }
