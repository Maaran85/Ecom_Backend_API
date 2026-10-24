"""
Centralized Delivery Pricing Service

Provides authoritative calculation of customer-facing delivery charges
across the order lifecycle (preview, checkout, invoicing).

Rules:
1. Platform logistics / Dealer delivery (dealer.is_delivery_self_logistics is False):
   - Super Admin controls customer-facing pricing via Logistics Billing Slabs (category_key='logistics'):
       * percentage slabs (customer_percentage) or flat amount (customer_amount)
       * applied to shipment subtotal (net basic selling price after discounts)
   - Free delivery is governed by Super Admin FeeConfiguration:
       * 'platform_free_delivery_threshold' (threshold, e.g. 500.0; at or above threshold, delivery is ₹0.00)
   - If below threshold and customer percentage/amount is missing on an active slab,
     raises DeliveryPricingConfigurationError (fails loud, never silent fallback).

2. Dealer-managed delivery / External courier (dealer.is_delivery_self_logistics is True):
   - Preserves dealer.delivery_charge and dealer.free_delivery_above.

3. Extensibility:
   - Supports optional weight_kg and distance_km parameters for future dimensional/distance models.
   - All monetary calculations use Decimal and 2-decimal-place half-up rounding.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from models.dealer import Dealer
from models.billing_slab import BillingSlab
from models.fee_configuration import FeeConfiguration
from core.money import money, money_2dp
from services.configuration_service import get_fee_config


class DeliveryPricingConfigurationError(Exception):
    """Raised when required Super Admin delivery pricing configuration is missing or invalid."""
    pass


@dataclass
class ShipmentDeliveryResult:
    dealer_id: Any
    dealer_name: str
    items_subtotal: Decimal
    delivery_charge: Decimal
    is_free: bool
    free_above: Decimal
    remaining_for_free: Decimal
    is_self_logistics: bool
    estimated_delivery_days: int = 7
    formatted_delivery_date: str = ""


@dataclass
class CartDeliveryPricingResult:
    shipments: Dict[Any, ShipmentDeliveryResult]
    total_delivery_charge: Decimal
    platform_eligible_subtotal: Decimal
    platform_free_delivery_threshold: Decimal
    platform_qualifies_for_free: bool
    platform_remaining_for_free: Decimal


async def calculate_shipment_delivery_fee(
    db: AsyncSession,
    dealer: Dealer,
    subtotal: Decimal,
    weight_kg: Optional[Decimal] = None,
    distance_km: Optional[Decimal] = None,
    active_slabs: Optional[List[BillingSlab]] = None,
    platform_eligible_subtotal: Optional[Decimal] = None,
) -> ShipmentDeliveryResult:
    """
    Calculates the authoritative customer delivery fee for a single shipment (dealer).

    Args:
        db: Async database session
        dealer: Dealer model instance for the shipment origin
        subtotal: Net or gross item subtotal for this dealer shipment (Decimal)
        weight_kg: Optional package weight in kg (for future weight-based pricing)
        distance_km: Optional delivery distance in km (for future distance-based pricing)
        active_slabs: Optional pre-fetched list of active BillingSlab records
        platform_eligible_subtotal: Optional combined eligible subtotal across all platform dealers in cart

    Returns:
        ShipmentDeliveryResult containing calculated fee, threshold, and status.

    Raises:
        DeliveryPricingConfigurationError if logistics slab configuration is missing, ambiguous,
        or lacks a required customer fee percentage/amount below threshold.
    """
    dealer_id = dealer.id
    dealer_name = str(dealer.business_name or f"Dealer #{dealer_id}")
    subtotal_2dp = money_2dp(subtotal)
    is_self = bool(getattr(dealer, "is_delivery_self_logistics", False))

    if is_self:
        # Dealer-managed delivery: preserve existing dealer delivery settings
        fee = money_2dp(dealer.delivery_charge or Decimal("0.00"))
        threshold = money_2dp(dealer.free_delivery_above or Decimal("0.00"))
        is_free = (fee == Decimal("0.00")) or (threshold > Decimal("0.00") and subtotal_2dp >= threshold)
        charge = Decimal("0.00") if is_free else fee
        remaining = money_2dp(max(Decimal("0.00"), threshold - subtotal_2dp)) if (threshold > Decimal("0.00") and not is_free) else Decimal("0.00")

        return ShipmentDeliveryResult(
            dealer_id=dealer_id,
            dealer_name=dealer_name,
            items_subtotal=subtotal_2dp,
            delivery_charge=charge,
            is_free=is_free,
            free_above=threshold,
            remaining_for_free=remaining,
            is_self_logistics=True,
        )

    # Platform-managed delivery: Super Admin free delivery threshold + logistics percentage slabs.
    threshold_cfg = await get_fee_config(db, "platform_free_delivery_threshold")
    threshold = (
        money_2dp(threshold_cfg.value)
        if (threshold_cfg and threshold_cfg.is_active and threshold_cfg.value is not None)
        else Decimal("0.00")
    )

    effective_eligible = (
        money_2dp(platform_eligible_subtotal)
        if platform_eligible_subtotal is not None
        else subtotal_2dp
    )

    # 1. Zero subtotal shipment
    if subtotal_2dp <= Decimal("0.00"):
        return ShipmentDeliveryResult(
            dealer_id=dealer_id,
            dealer_name=dealer_name,
            items_subtotal=subtotal_2dp,
            delivery_charge=Decimal("0.00"),
            is_free=True,
            free_above=threshold,
            remaining_for_free=money_2dp(max(Decimal("0.00"), threshold - effective_eligible)),
            is_self_logistics=False,
        )

    # 2. Super Admin Free-Delivery Threshold: at or above threshold, delivery is ₹0.00
    if threshold > Decimal("0.00") and effective_eligible >= threshold:
        return ShipmentDeliveryResult(
            dealer_id=dealer_id,
            dealer_name=dealer_name,
            items_subtotal=subtotal_2dp,
            delivery_charge=Decimal("0.00"),
            is_free=True,
            free_above=threshold,
            remaining_for_free=Decimal("0.00"),
            is_self_logistics=False,
        )

    # 3. Below threshold: calculate delivery fee using applicable active logistics slab
    if active_slabs is None:
        stmt = (
            select(BillingSlab)
            .where(BillingSlab.is_active == True)
            .order_by(BillingSlab.min_price.desc())
        )
        res = await db.execute(stmt)
        active_slabs = list(res.scalars().all())

    matches = [
        s for s in active_slabs
        if s.category_key == "logistics"
        and s.is_active
        and (s.min_price is None or Decimal(str(s.min_price)) <= subtotal_2dp or (subtotal_2dp < Decimal(str(s.min_price)) and Decimal(str(s.min_price)) <= Decimal("1.00")))
        and (s.max_price is None or Decimal(str(s.max_price)) >= subtotal_2dp)
    ]

    if len(matches) > 1:
        slab_summaries = ", ".join(
            [f"ID {s.id} (₹{s.min_price}-₹{s.max_price if s.max_price is not None else '∞'})" for s in matches]
        )
        raise DeliveryPricingConfigurationError(
            f"Multiple active logistics billing slabs match subtotal ₹{subtotal_2dp}: {slab_summaries}"
        )

    if not matches:
        raise DeliveryPricingConfigurationError(
            f"No active logistics billing slab configured for subtotal ₹{subtotal_2dp}."
        )

    slab = matches[0]

    # Calculate fee using slab customer_amount or customer_percentage
    if slab.customer_amount is not None:
        charge = money_2dp(Decimal(str(slab.customer_amount)))
    elif slab.customer_percentage is not None:
        pct_dec = Decimal(str(slab.customer_percentage))
        pct_factor = pct_dec if pct_dec < Decimal("1.0") else pct_dec / Decimal("100.0")
        charge = money_2dp(subtotal_2dp * pct_factor)
    else:
        max_price_display = f"₹{slab.max_price}" if slab.max_price is not None else "∞"
        raise DeliveryPricingConfigurationError(
            f"Missing customer logistics fee percentage or amount on active billing slab ID {slab.id} "
            f"(range: ₹{slab.min_price}-{max_price_display}) for subtotal ₹{subtotal_2dp}."
        )

    is_free = (charge == Decimal("0.00"))
    remaining = (
        money_2dp(max(Decimal("0.00"), threshold - effective_eligible))
        if (threshold > Decimal("0.00") and not is_free)
        else Decimal("0.00")
    )

    return ShipmentDeliveryResult(
        dealer_id=dealer_id,
        dealer_name=dealer_name,
        items_subtotal=subtotal_2dp,
        delivery_charge=charge,
        is_free=is_free,
        free_above=threshold,
        remaining_for_free=remaining,
        is_self_logistics=False,
    )


async def calculate_cart_delivery_pricing(
    db: AsyncSession,
    dealer_shipments: List[Dict[str, Any]],  # [{"dealer": Dealer, "subtotal": Decimal}]
    active_slabs: Optional[List[BillingSlab]] = None,
) -> CartDeliveryPricingResult:
    """
    Calculates delivery fees across all shipments in a cart.
    Applies overall cart-level free delivery threshold across all platform-managed dealers,
    while completely excluding self-logistics dealers.
    """
    if active_slabs is None:
        stmt = (
            select(BillingSlab)
            .where(BillingSlab.is_active == True)
            .order_by(BillingSlab.min_price.desc())
        )
        res = await db.execute(stmt)
        active_slabs = list(res.scalars().all())

    threshold_cfg = await get_fee_config(db, "platform_free_delivery_threshold")
    threshold = (
        money_2dp(threshold_cfg.value)
        if (threshold_cfg and threshold_cfg.is_active and threshold_cfg.value is not None)
        else Decimal("0.00")
    )

    # 1. Separate platform shipments and self-logistics shipments
    # Free delivery thresholds are applied ONLY to serviceable items.
    platform_shipments = [
        s for s in dealer_shipments
        if not bool(getattr(s["dealer"], "is_delivery_self_logistics", False))
        and s.get("is_serviceable", True)
    ]

    platform_eligible_subtotal = money_2dp(
        sum((money_2dp(s["subtotal"]) for s in platform_shipments), Decimal("0.00"))
    )
    qualifies_for_free = (threshold > Decimal("0.00") and platform_eligible_subtotal >= threshold)
    remaining_for_free = (
        money_2dp(max(Decimal("0.00"), threshold - platform_eligible_subtotal))
        if (threshold > Decimal("0.00") and not qualifies_for_free)
        else Decimal("0.00")
    )

    shipments_map: Dict[Any, ShipmentDeliveryResult] = {}
    total_delivery = Decimal("0.00")

    for s in dealer_shipments:
        dealer = s["dealer"]
        subtotal = money_2dp(s["subtotal"])
        is_self = bool(getattr(dealer, "is_delivery_self_logistics", False))
        is_serv = s.get("is_serviceable", True)
        shipment_res = await calculate_shipment_delivery_fee(
            db=db,
            dealer=dealer,
            subtotal=subtotal,
            active_slabs=active_slabs,
            platform_eligible_subtotal=None if (is_self or not is_serv) else platform_eligible_subtotal,
        )
        if not is_serv:
            shipment_res.is_free = False
        shipments_map[dealer.id] = shipment_res
        if str(dealer.id) != dealer.id:
            shipments_map[str(dealer.id)] = shipment_res
        total_delivery = money_2dp(total_delivery + shipment_res.delivery_charge)

    return CartDeliveryPricingResult(
        shipments=shipments_map,
        total_delivery_charge=total_delivery,
        platform_eligible_subtotal=platform_eligible_subtotal,
        platform_free_delivery_threshold=threshold,
        platform_qualifies_for_free=qualifies_for_free,
        platform_remaining_for_free=remaining_for_free,
    )


async def check_pincode_serviceability(
    db: AsyncSession,
    pincode: Optional[str],
    dealer_id: Optional[Any],
    lat: Optional[float] = None,
    long: Optional[float] = None
) -> bool:
    """
    Check if a delivery destination pincode is serviceable for a dealer.
    If no pincode is provided, returns True (unrestricted until address is selected).
    Rules:
    1. Active entry exists in ServiceablePincode for dealer_id or global (dealer_id is None).
    2. Active DeliveryHub exists for this dealer covering the location via radius.
    """
    if not pincode or not str(pincode).strip():
        return True

    clean_pincode = str(pincode).strip()
    from models.location import ServiceablePincode

    # 1. Courier Whitelist (dealer-specific or global platform entry)
    result = await db.execute(
        select(ServiceablePincode)
        .where(
            ServiceablePincode.pincode == clean_pincode,
            ServiceablePincode.is_active == True,
            (ServiceablePincode.dealer_id == dealer_id) | ServiceablePincode.dealer_id.is_(None)
        )
        .limit(1)
    )
    if result.scalars().first() is not None:
        return True

    # 2. Local Hub check (if lat/long available)
    if lat is not None and long is not None and dealer_id:
        from models.hub import DeliveryHub
        hub_res = await db.execute(
            select(DeliveryHub)
            .where(
                DeliveryHub.dealer_id == dealer_id,
                DeliveryHub.is_active == True,
                DeliveryHub.lat_long != None,
                DeliveryHub.max_delivery_radius != None
            )
        )
        for hub in hub_res.scalars().all():
            try:
                from utils.distance import get_distance_km
                h_lat, h_lon = map(float, hub.lat_long.split(","))
                if get_distance_km(lat, long, h_lat, h_lon) <= hub.max_delivery_radius:
                    return True
            except Exception:
                continue

    return False

