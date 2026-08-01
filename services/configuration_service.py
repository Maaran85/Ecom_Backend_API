from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.tds_configuration import TDSConfiguration
from models.fee_configuration import FeeConfiguration
from models.settlement_configuration import SettlementConfiguration
from core.enums import TDSThresholdStrategy, FeeType, OrganizationType


# ---------------------------------------------------------------------------
# Default seed data (source: ecommerce-taxation structure.xlsx)
# ---------------------------------------------------------------------------

# Sec 194-O. Exemption limits: Individual/HUF = 5,00,000; Company/LLP/Pvt Ltd = None.
# Without PAN the rate is 5% and the exemption is Nill for every org type.
SEED_TDS_CONFIGS: list[Dict[str, Any]] = [
    {
        "organization_type": OrganizationType.INDIVIDUAL.value,
        "tds_rate_with_pan": 0.001,
        "exemption_limit_with_pan": 500000.0,
        "tds_rate_without_pan": 0.05,
        "exemption_limit_without_pan": None,
        "threshold_strategy": TDSThresholdStrategy.PROSPECTIVE,
    },
    {
        "organization_type": OrganizationType.HUF.value,
        "tds_rate_with_pan": 0.001,
        "exemption_limit_with_pan": 500000.0,
        "tds_rate_without_pan": 0.05,
        "exemption_limit_without_pan": None,
        "threshold_strategy": TDSThresholdStrategy.PROSPECTIVE,
    },
    {
        "organization_type": OrganizationType.COMPANY.value,
        "tds_rate_with_pan": 0.001,
        "exemption_limit_with_pan": None,  # blank in Excel -> no exemption
        "tds_rate_without_pan": 0.05,
        "exemption_limit_without_pan": None,
        "threshold_strategy": TDSThresholdStrategy.PROSPECTIVE,
    },
    {
        "organization_type": OrganizationType.LLP.value,
        "tds_rate_with_pan": 0.001,
        "exemption_limit_with_pan": None,
        "tds_rate_without_pan": 0.05,
        "exemption_limit_without_pan": None,
        "threshold_strategy": TDSThresholdStrategy.PROSPECTIVE,
    },
    {
        "organization_type": OrganizationType.PRIVATE_LIMITED.value,
        "tds_rate_with_pan": 0.001,
        "exemption_limit_with_pan": None,
        "tds_rate_without_pan": 0.05,
        "exemption_limit_without_pan": None,
        "threshold_strategy": TDSThresholdStrategy.PROSPECTIVE,
    },
    # Fallback for any unlisted org type: no exemption (safe default)
    {
        "organization_type": OrganizationType.OTHER.value,
        "tds_rate_with_pan": 0.001,
        "exemption_limit_with_pan": None,
        "tds_rate_without_pan": 0.05,
        "exemption_limit_without_pan": None,
        "threshold_strategy": TDSThresholdStrategy.PROSPECTIVE,
    },
]

# marketplace_fee is intentionally NOT seeded with a fixed value: when value is 0
# the settlement engine falls back to the per-order snapshot already collected at
# checkout (OrderItem.platform_fee). The Excel billing sheet (25 + 18% GST) can be
# reproduced by enabling the flat value + GST on the config.
SEED_FEE_CONFIGS: list[Dict[str, Any]] = [
    {
        "key": "marketplace_fee",
        "name": "Marketplace Fee",
        "description": "Platform commission per order item. When value = 0, uses the amount collected at checkout (OrderItem.platform_fee).",
        "fee_type": FeeType.FLAT,
        "value": 0.0,
        "is_gst_applicable": False,
        "gst_rate": 0.18,
    },
    {
        "key": "marketing_fee",
        "name": "Marketing Fee",
        "description": "Marketing contribution per order item (Excel: 10 + 18% GST).",
        "fee_type": FeeType.FLAT,
        "value": 0.0,
        "is_gst_applicable": False,
        "gst_rate": 0.18,
    },
    {
        "key": "partner_logistics_fee",
        "name": "Partner Logistics Fee",
        "description": "Deducted from the dealer payout when an order ships via a partner logistics provider (Excel: 15 + 18% GST).",
        "fee_type": FeeType.FLAT,
        "value": 0.0,
        "is_gst_applicable": False,
        "gst_rate": 0.18,
    },
    {
        "key": "customer_shipping_gst_rate",
        "name": "Customer Shipping GST Rate",
        "description": "GST applied on top of the customer shipping charge passed to the dealer (Excel: 18% on 18 = 21.24). 0 = none.",
        "fee_type": FeeType.PERCENTAGE,
        "value": 0.0,
        "is_gst_applicable": False,
        "gst_rate": 0.0,
    },
]


class ConfigurationError(Exception):
    """Raised when required configuration is missing or inconsistent."""


async def ensure_default_configurations(db: AsyncSession) -> None:
    """Idempotently seed TDS, fee and settlement configuration. Safe to call on startup."""
    for seed in SEED_TDS_CONFIGS:
        existing = await db.execute(
            select(TDSConfiguration).where(TDSConfiguration.organization_type == seed["organization_type"])
        )
        if not existing.scalar_one_or_none():
            db.add(TDSConfiguration(section="194-O", is_active=True, **seed))

    for seed in SEED_FEE_CONFIGS:
        existing = await db.execute(
            select(FeeConfiguration).where(FeeConfiguration.key == seed["key"])
        )
        if not existing.scalar_one_or_none():
            db.add(FeeConfiguration(is_active=True, **seed))

    existing_settlement_config = await db.get(SettlementConfiguration, 1)
    if not existing_settlement_config:
        db.add(SettlementConfiguration(id=1))

    await db.flush()


async def get_settlement_configuration(db: AsyncSession) -> SettlementConfiguration:
    config = await db.get(SettlementConfiguration, 1)
    if config is None:
        config = SettlementConfiguration(id=1)
        db.add(config)
        await db.flush()
    return config


# ---------------------------------------------------------------------------
# TDS configuration accessors
# ---------------------------------------------------------------------------

async def get_tds_config(db: AsyncSession, organization_type: Optional[str]) -> Optional[TDSConfiguration]:
    """Resolve the active TDS rule for an org type, falling back to 'other'."""
    org_type = (organization_type or OrganizationType.OTHER.value).strip().lower()

    result = await db.execute(
        select(TDSConfiguration).where(
            TDSConfiguration.organization_type == org_type,
            TDSConfiguration.is_active.is_(True),
        )
    )
    config = result.scalar_one_or_none()
    if config:
        return config

    if org_type != OrganizationType.OTHER.value:
        result = await db.execute(
            select(TDSConfiguration).where(
                TDSConfiguration.organization_type == OrganizationType.OTHER.value,
                TDSConfiguration.is_active.is_(True),
            )
        )
        config = result.scalar_one_or_none()

    return config


async def get_active_tds_config_required(db: AsyncSession, organization_type: Optional[str]) -> TDSConfiguration:
    """Like get_tds_config but raises if nothing is configured (fail loud, never silent)."""
    config = await get_tds_config(db, organization_type)
    if config is None:
        raise ConfigurationError(
            f"No active TDS configuration found for organization_type={organization_type or 'unknown'}"
        )
    return config


async def get_fee_config(db: AsyncSession, key: str) -> Optional[FeeConfiguration]:
    result = await db.execute(
        select(FeeConfiguration).where(
            FeeConfiguration.key == key,
            FeeConfiguration.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def get_fee_config_required(db: AsyncSession, key: str) -> FeeConfiguration:
    config = await get_fee_config(db, key)
    if config is None:
        raise ConfigurationError(f"No active fee configuration found for key={key}")
    return config
