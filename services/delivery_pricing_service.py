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
import math
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func

def get_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

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
    slab_id: Optional[int] = None
    applied_rate: Optional[Decimal] = None


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
    applied_slab_id: Optional[int] = slab.id
    applied_rate: Optional[Decimal] = None

    # Calculate fee using slab customer_amount or customer_percentage
    if slab.customer_amount is not None:
        charge = money_2dp(Decimal(str(slab.customer_amount)))
    elif slab.customer_percentage is not None:
        pct_dec = Decimal(str(slab.customer_percentage))
        applied_rate = pct_dec
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
        slab_id=applied_slab_id,
        applied_rate=applied_rate,
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


from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import re

@dataclass
class CarrierCoverageResult:
    is_covered: bool
    carrier_name: str
    min_days: int = 3
    max_days: int = 5
    estimated_delivery_days: int = 5
    source: str = "configured_courier"
    notes: Optional[str] = None


class CarrierServiceabilityAdapter(ABC):
    """
    Extensible adapter contract for checking carrier delivery coverage.
    Allows swapping in third-party logistics APIs (Shiprocket, Delhivery, Blue Dart, etc.)
    without modifying core pricing, checkout, or router logic.
    """
    @abstractmethod
    async def check_carrier_coverage(
        self,
        db: AsyncSession,
        dest_pincode: str,
        origin_pincode: Optional[str] = None,
        dealer_id: Optional[Any] = None,
        weight_kg: Optional[float] = None,
    ) -> Optional[CarrierCoverageResult]:
        pass


class ConfiguredDatabaseCarrierAdapter(CarrierServiceabilityAdapter):
    """
    Default carrier serviceability adapter backed by the internal database table `serviceable_pincodes`.
    Evaluates configured dealer-specific or platform-wide courier routes.
    """
    async def check_carrier_coverage(
        self,
        db: AsyncSession,
        dest_pincode: str,
        origin_pincode: Optional[str] = None,
        dealer_id: Optional[Any] = None,
        weight_kg: Optional[float] = None,
    ) -> Optional[CarrierCoverageResult]:
        from models.location import ServiceablePincode
        conds = [
            ServiceablePincode.pincode == dest_pincode,
            ServiceablePincode.is_active == True,
        ]
        if dealer_id:
            conds.append(or_(ServiceablePincode.dealer_id == dealer_id, ServiceablePincode.dealer_id.is_(None)))
        else:
            conds.append(ServiceablePincode.dealer_id.is_(None))

        stmt = select(ServiceablePincode).where(*conds).order_by(
            ServiceablePincode.dealer_id.isnot(None).desc()
        ).limit(1)

        res = await db.execute(stmt)
        sp = res.scalars().first()
        if sp is None:
            return None

        min_d = getattr(sp, "min_delivery_days", 3) or 3
        max_d = getattr(sp, "max_delivery_days", 5) or 5
        carrier_label = "Seller Configured Courier" if sp.dealer_id is not None else "Platform Courier Network"

        return CarrierCoverageResult(
            is_covered=True,
            carrier_name=carrier_label,
            min_days=min_d,
            max_days=max_d,
            estimated_delivery_days=max_d,
            source="dealer_courier" if sp.dealer_id is not None else "platform_courier",
        )


_DEFAULT_CARRIER_ADAPTER: CarrierServiceabilityAdapter = ConfiguredDatabaseCarrierAdapter()


def get_carrier_adapter() -> CarrierServiceabilityAdapter:
    """Return the currently configured carrier serviceability adapter."""
    return _DEFAULT_CARRIER_ADAPTER


def set_carrier_adapter(adapter: CarrierServiceabilityAdapter) -> None:
    """Plug in a carrier serviceability adapter (e.g. for testing or future carrier integrations)."""
    global _DEFAULT_CARRIER_ADAPTER
    _DEFAULT_CARRIER_ADAPTER = adapter


@dataclass
class ServiceabilityResult:
    is_serviceable: bool
    delivery_type: Optional[str] = None  # "warehouse_direct", "local_hub", "courier"
    serviceability_source: Optional[str] = None  # "same_pincode_warehouse", "local_hub_radius", "courier_whitelist"
    message: str = ""
    estimated_days: Optional[int] = None
    estimated_delivery_date: Optional[str] = None
    pincode: Optional[str] = None
    product_id: Optional[Any] = None
    variant_id: Optional[Any] = None
    dealer_id: Optional[Any] = None
    warehouse_id: Optional[int] = None
    reason_code: Optional[str] = None  # "SERVICEABLE", "INVALID_PINCODE", "OUT_OF_STOCK", "NO_ELIGIBLE_FULFILLMENT_SOURCE", "NO_DELIVERY_COVERAGE"
    delivery_fee: Optional[float] = None
    locality: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    is_interstate: bool = False
    origin_state: Optional[str] = None
    destination_state: Optional[str] = None
    origin_warehouse_name: Optional[str] = None

    @property
    def serviceable(self) -> bool:
        """Alias for client compatibility."""
        return self.is_serviceable


async def check_serviceability_full(
    db: AsyncSession,
    pincode: Optional[str],
    dealer_id: Optional[Any] = None,
    product_id: Optional[Any] = None,
    variant_id: Optional[Any] = None,
    quantity: int = 1,
    lat: Optional[float] = None,
    long: Optional[float] = None,
) -> ServiceabilityResult:
    """
    Authoritative serviceability check evaluating all 4 business rules:
    - Step 1: Normalization, format validation, and postal directory resolution (PincodeMaster).
    - Step 2: Identification of active eligible dispatch warehouses with sufficient stock.
    - Step 3: Exact variant inventory evaluation.
    - Step 4: Multi-tier delivery determination:
        * Rule A: Same warehouse PIN match (warehouse_direct).
        * Rule B: Explicit local delivery radius (local_hub, only when configured > 0).
                  Local delivery radius restrictions DO NOT block courier delivery.
        * Rule C: Configured courier serviceability (intrastate or interstate delivery).
        * Rule D: No supported route or out of stock -> NO_DELIVERY_COVERAGE / OUT_OF_STOCK.
    """
    if not pincode or not str(pincode).strip():
        return ServiceabilityResult(
            is_serviceable=True,
            message="Pincode not specified; delivery availability unrestricted until address is selected.",
            reason_code="PINCODE_UNSPECIFIED"
        )

    clean_pincode = str(pincode).strip()
    if not re.match(r"^\d{6}$", clean_pincode):
        return ServiceabilityResult(
            is_serviceable=False,
            pincode=clean_pincode,
            product_id=product_id,
            variant_id=variant_id,
            dealer_id=dealer_id,
            message=f"Invalid PIN code '{clean_pincode}'. Please enter a valid 6-digit number.",
            reason_code="INVALID_PINCODE"
        )

    # ── Step 1: Postal Directory Resolution (PincodeMaster) ─────────────────────
    from models.location import PincodeMaster
    p_res = await db.execute(select(PincodeMaster).where(PincodeMaster.pincode == clean_pincode).limit(1))
    p_info = p_res.scalars().first()

    resolved_locality = None
    resolved_district = None
    resolved_city = None
    resolved_state = None

    if p_info is not None and (isinstance(p_info, PincodeMaster) or hasattr(p_info, 'state_name')):
        resolved_locality = getattr(p_info, 'office_name', None)
        resolved_district = getattr(p_info, 'district', None)
        resolved_state = getattr(p_info, 'state_name', None)

        loc_clean = resolved_locality or ""
        for suffix in [" S.O", " B.O", " H.O", " SO", " BO", " HO"]:
            if loc_clean.endswith(suffix):
                loc_clean = loc_clean[:-len(suffix)]
        if loc_clean and resolved_district and loc_clean.lower() != resolved_district.lower():
            resolved_city = f"{loc_clean}, {resolved_district}"
        else:
            resolved_city = loc_clean or resolved_district

        if lat is None and getattr(p_info, 'latitude', None):
            try:
                lat = float(p_info.latitude)
            except (ValueError, TypeError):
                pass
        if long is None and getattr(p_info, 'longitude', None):
            try:
                long = float(p_info.longitude)
            except (ValueError, TypeError):
                pass

    target_item = None
    target_product = None
    dealer = None

    # ── Step 2: Resolve Product & Variant ───────────────────────────────────────
    if product_id:
        from models.product import Product
        p_res = await db.execute(
            select(Product).where(Product.id == product_id, Product.is_deleted == False)
        )
        target_product = p_res.scalars().first()
        if not target_product:
            return ServiceabilityResult(
                is_serviceable=False,
                pincode=clean_pincode,
                product_id=product_id,
                variant_id=variant_id,
                dealer_id=dealer_id,
                locality=resolved_locality,
                district=resolved_district,
                city=resolved_city,
                state=resolved_state,
                message="Product not found or is no longer available.",
                reason_code="PRODUCT_NOT_FOUND"
            )
        if not target_product.is_approved:
            return ServiceabilityResult(
                is_serviceable=False,
                pincode=clean_pincode,
                product_id=product_id,
                variant_id=variant_id,
                dealer_id=dealer_id,
                locality=resolved_locality,
                district=resolved_district,
                city=resolved_city,
                state=resolved_state,
                message="This product is currently pending approval.",
                reason_code="PRODUCT_NOT_APPROVED"
            )
        if not dealer_id:
            dealer_id = target_product.dealer_id

        if variant_id and str(variant_id) != str(product_id):
            v_res = await db.execute(
                select(Product).where(
                    Product.id == variant_id,
                    Product.is_deleted == False
                )
            )
            target_variant = v_res.scalars().first()
            if not target_variant or (target_variant.parent_product_id != target_product.id and target_variant.id != target_product.id):
                return ServiceabilityResult(
                    is_serviceable=False,
                    pincode=clean_pincode,
                    product_id=product_id,
                    variant_id=variant_id,
                    dealer_id=dealer_id,
                    locality=resolved_locality,
                    district=resolved_district,
                    city=resolved_city,
                    state=resolved_state,
                    message="Selected variant does not belong to this product.",
                    reason_code="VARIANT_MISMATCH"
                )
            if not target_variant.is_approved:
                return ServiceabilityResult(
                    is_serviceable=False,
                    pincode=clean_pincode,
                    product_id=product_id,
                    variant_id=variant_id,
                    dealer_id=dealer_id,
                    locality=resolved_locality,
                    district=resolved_district,
                    city=resolved_city,
                    state=resolved_state,
                    message="Selected variant is currently pending approval.",
                    reason_code="VARIANT_NOT_APPROVED"
                )
            target_item = target_variant
        else:
            target_item = target_product

    # ── Step 3: Verify Seller Eligibility ──────────────────────────────────────
    if dealer_id:
        from models.dealer import Dealer
        d_res = await db.execute(select(Dealer).where(Dealer.id == dealer_id))
        d_cand = d_res.scalars().first()
        if isinstance(d_cand, Dealer):
            dealer = d_cand
            if (
                not getattr(dealer, 'is_active', True)
                or getattr(dealer, 'is_deleted', False)
                or (getattr(dealer, 'access_status', 'active') and getattr(dealer, 'access_status', 'active') != 'active')
            ):
                return ServiceabilityResult(
                    is_serviceable=False,
                    pincode=clean_pincode,
                    product_id=product_id,
                    variant_id=variant_id,
                    dealer_id=dealer_id,
                    locality=resolved_locality,
                    district=resolved_district,
                    city=resolved_city,
                    state=resolved_state,
                    message="Seller for this product is currently inactive.",
                    reason_code="NO_ELIGIBLE_FULFILLMENT_SOURCE"
                )

    # ── Step 4: Identify Eligible Dispatch Warehouses with Stock ────────────────
    from models.hub import DeliveryHub
    from models.inventory import ProductInventory

    eligible_warehouses_with_stock: List[Dict[str, Any]] = []
    has_active_warehouse = False
    matched_coverage_but_out_of_stock = False

    if dealer_id:
        hub_res = await db.execute(
            select(DeliveryHub).where(
                DeliveryHub.dealer_id == dealer_id,
                DeliveryHub.is_active == True
            )
        )
        active_hubs = list(hub_res.scalars().all()) if hasattr(hub_res, 'scalars') else []
        has_active_warehouse = len(active_hubs) > 0

        for hub in active_hubs:
            hub_stock = 0
            if target_item:
                inv_res = await db.execute(
                    select(ProductInventory).where(
                        ProductInventory.hub_id == hub.id,
                        ProductInventory.product_id == target_item.id
                    )
                )
                inv_obj = inv_res.scalars().first() if hasattr(inv_res, 'scalars') else None
                if inv_obj is None and hasattr(inv_res, 'scalar_one_or_none'):
                    try:
                        inv_obj = inv_res.scalar_one_or_none()
                    except Exception:
                        pass

                if inv_obj is not None:
                    if hasattr(inv_obj, 'stock'):
                        hub_stock = int(getattr(inv_obj, 'stock', 0) or 0)
                    elif isinstance(inv_obj, (int, float, Decimal)):
                        hub_stock = int(inv_obj)
                    else:
                        try:
                            hub_stock = int(inv_obj)
                        except Exception:
                            hub_stock = 0
                else:
                    from models.product import Product
                    child_res = await db.execute(
                        select(Product.id).where(Product.parent_product_id == target_item.id)
                    )
                    child_ids = list(child_res.scalars().all()) if hasattr(child_res, 'scalars') else []
                    if child_ids:
                        c_res = await db.execute(
                            select(func.coalesce(func.sum(ProductInventory.stock), 0)).where(
                                ProductInventory.hub_id == hub.id,
                                ProductInventory.product_id.in_(child_ids)
                            )
                        )
                        c_val = c_res.scalar() if hasattr(c_res, 'scalar') else (c_res.scalar_one_or_none() if hasattr(c_res, 'scalar_one_or_none') else None)
                        hub_stock = int(c_val) if isinstance(c_val, (int, float, Decimal)) else 0
                    else:
                        p_st = getattr(target_item, 'stock', 0) or 0
                        hub_stock = int(p_st) if isinstance(p_st, (int, float, Decimal)) else 0
            else:
                hub_stock = 999

            hub_pin = (hub.pincode or "").strip()
            # Check if this warehouse covers destination via Rule A
            if hub_pin == clean_pincode:
                if hub_stock >= quantity:
                    eligible_warehouses_with_stock.append({
                        "hub": hub,
                        "stock": hub_stock,
                        "pincode": hub_pin,
                        "state": (hub.state or "").strip()
                    })
                else:
                    matched_coverage_but_out_of_stock = True
            # Check if this warehouse covers destination via Rule B
            elif lat is not None and long is not None and hub.lat_long and hub.max_delivery_radius and hub.max_delivery_radius > 0:
                try:
                    parts = [p.strip() for p in hub.lat_long.split(",")]
                    if len(parts) == 2:
                        h_lat, h_lon = float(parts[0]), float(parts[1])
                        dist = get_distance_km(float(lat), float(long), h_lat, h_lon)
                        if dist <= hub.max_delivery_radius:
                            if hub_stock >= quantity:
                                eligible_warehouses_with_stock.append({
                                    "hub": hub,
                                    "stock": hub_stock,
                                    "pincode": hub_pin,
                                    "state": (hub.state or "").strip()
                                })
                            else:
                                matched_coverage_but_out_of_stock = True
                        else:
                            if hub_stock >= quantity:
                                eligible_warehouses_with_stock.append({
                                    "hub": hub,
                                    "stock": hub_stock,
                                    "pincode": hub_pin,
                                    "state": (hub.state or "").strip()
                                })
                    else:
                        if hub_stock >= quantity:
                            eligible_warehouses_with_stock.append({
                                "hub": hub,
                                "stock": hub_stock,
                                "pincode": hub_pin,
                                "state": (hub.state or "").strip()
                            })
                except Exception:
                    if hub_stock >= quantity:
                        eligible_warehouses_with_stock.append({
                            "hub": hub,
                            "stock": hub_stock,
                            "pincode": hub_pin,
                            "state": (hub.state or "").strip()
                        })
            else:
                if hub_stock >= quantity:
                    eligible_warehouses_with_stock.append({
                        "hub": hub,
                        "stock": hub_stock,
                        "pincode": hub_pin,
                        "state": (hub.state or "").strip()
                    })

    # Helper: calculate delivery fee if serviceable
    async def _compute_delivery_fee() -> Optional[float]:
        if not dealer or not target_item:
            return None
        try:
            item_price = Decimal(str(getattr(target_item, 'selling_price', 0.0) or 0.0))
            fee_res = await calculate_shipment_delivery_fee(db, dealer, item_price)
            return float(fee_res.delivery_charge)
        except Exception:
            return None

    # Helper: format delivery date string
    def _format_delivery_date(days: int) -> str:
        target_dt = datetime.now() + timedelta(days=days)
        return target_dt.strftime("%A, %d %b")

    # ── Rule A: Active warehouse in the exact same normalized PIN code ─────────
    if eligible_warehouses_with_stock:
        for item_wh in eligible_warehouses_with_stock:
            hub = item_wh["hub"]
            if item_wh["pincode"] == clean_pincode:
                est_days = getattr(hub, 'estimated_delivery_days', None) or (dealer.estimated_delivery_days if dealer else 2) or 2
                est_days = min(est_days, 3)
                fee = await _compute_delivery_fee()
                wh_state = item_wh["state"] or resolved_state
                return ServiceabilityResult(
                    is_serviceable=True,
                    delivery_type="warehouse_direct",
                    serviceability_source="same_pincode_warehouse",
                    message=f"Fast delivery available from seller's local warehouse in {clean_pincode}.",
                    estimated_days=est_days,
                    estimated_delivery_date=_format_delivery_date(est_days),
                    pincode=clean_pincode,
                    product_id=product_id,
                    variant_id=variant_id,
                    dealer_id=dealer_id,
                    warehouse_id=hub.id,
                    origin_warehouse_name=hub.name,
                    origin_state=wh_state,
                    destination_state=resolved_state,
                    is_interstate=False,
                    reason_code="SERVICEABLE",
                    delivery_fee=fee,
                    locality=resolved_locality,
                    district=resolved_district,
                    city=resolved_city,
                    state=resolved_state,
                )

    # ── Rule B: Explicit local delivery zones / radius ─────────────────────────
    if lat is not None and long is not None and eligible_warehouses_with_stock:
        for item_wh in eligible_warehouses_with_stock:
            hub = item_wh["hub"]
            if not hub.lat_long or not hub.max_delivery_radius or hub.max_delivery_radius <= 0:
                continue
            try:
                parts = [p.strip() for p in hub.lat_long.split(",")]
                if len(parts) != 2:
                    continue
                h_lat, h_lon = float(parts[0]), float(parts[1])
                dist = get_distance_km(float(lat), float(long), h_lat, h_lon)
                if dist <= hub.max_delivery_radius:
                    est_days = 1
                    fee = await _compute_delivery_fee()
                    wh_state = item_wh["state"] or resolved_state
                    return ServiceabilityResult(
                        is_serviceable=True,
                        delivery_type="local_hub",
                        serviceability_source="local_hub_radius",
                        message="Same-day or next-day local delivery available.",
                        estimated_days=est_days,
                        estimated_delivery_date=_format_delivery_date(est_days),
                        pincode=clean_pincode,
                        product_id=product_id,
                        variant_id=variant_id,
                        dealer_id=dealer_id,
                        warehouse_id=hub.id,
                        origin_warehouse_name=hub.name,
                        origin_state=wh_state,
                        destination_state=resolved_state,
                        is_interstate=False,
                        reason_code="SERVICEABLE",
                        delivery_fee=fee,
                        locality=resolved_locality,
                        district=resolved_district,
                        city=resolved_city,
                        state=resolved_state,
                    )
            except Exception:
                continue

    # ── Rule C: Configured courier serviceability (Intrastate & Interstate) ─────
    # Local radius restrictions do NOT block courier coverage. If warehouse is in Gujarat
    # and customer is in Bengaluru, courier coverage permits interstate delivery.
    origin_pin = eligible_warehouses_with_stock[0]["pincode"] if eligible_warehouses_with_stock else None
    weight_val = float(getattr(target_item, 'weight', 0.0) or 0.0) if target_item else None

    carrier_cov = await get_carrier_adapter().check_carrier_coverage(
        db=db,
        dest_pincode=clean_pincode,
        origin_pincode=origin_pin,
        dealer_id=dealer_id,
        weight_kg=weight_val
    )

    if carrier_cov and carrier_cov.is_covered:
        has_courier_stock = False
        if not target_item:
            has_courier_stock = True
        elif eligible_warehouses_with_stock:
            has_courier_stock = True
        else:
            inv_sum_res = await db.execute(
                select(func.coalesce(func.sum(ProductInventory.stock), 0)).where(
                    ProductInventory.product_id == target_item.id
                )
            )
            c_stock = inv_sum_res.scalar() if hasattr(inv_sum_res, 'scalar') else (inv_sum_res.scalar_one_or_none() if hasattr(inv_sum_res, 'scalar_one_or_none') else None)
            if c_stock is None or c_stock == 0:
                c_stock = getattr(target_item, 'stock', 0) or 0
            c_stock = int(c_stock) if isinstance(c_stock, (int, float, Decimal)) else 0
            if c_stock >= quantity:
                has_courier_stock = True
            else:
                matched_coverage_but_out_of_stock = True

        if has_courier_stock:
            dispatch_wh = eligible_warehouses_with_stock[0]["hub"] if eligible_warehouses_with_stock else None
            origin_state = eligible_warehouses_with_stock[0]["state"] if eligible_warehouses_with_stock else None
            if not origin_state and has_active_warehouse and active_hubs:
                origin_state = getattr(active_hubs[0], 'state', None)
            if not origin_state and dealer:
                origin_state = getattr(dealer, 'state', None)

            is_interstate = False
            if origin_state and resolved_state and origin_state.strip().lower() != resolved_state.strip().lower():
                is_interstate = True

            min_d = carrier_cov.min_days
            max_d = carrier_cov.max_days
            fee = await _compute_delivery_fee()

            if is_interstate:
                carrier_msg = f"Interstate courier delivery available from {origin_state} to {resolved_state or 'your location'} in {min_d}-{max_d} business days."
            else:
                carrier_msg = f"Standard courier delivery available in {min_d}-{max_d} business days."

            return ServiceabilityResult(
                is_serviceable=True,
                delivery_type="courier",
                serviceability_source="courier_whitelist",
                message=carrier_msg,
                estimated_days=max_d,
                estimated_delivery_date=_format_delivery_date(max_d),
                pincode=clean_pincode,
                product_id=product_id,
                variant_id=variant_id,
                dealer_id=dealer_id,
                warehouse_id=dispatch_wh.id if dispatch_wh else None,
                origin_warehouse_name=dispatch_wh.name if dispatch_wh else None,
                origin_state=origin_state,
                destination_state=resolved_state,
                is_interstate=is_interstate,
                reason_code="SERVICEABLE",
                delivery_fee=fee,
                locality=resolved_locality,
                district=resolved_district,
                city=resolved_city,
                state=resolved_state,
            )
        else:
            matched_coverage_but_out_of_stock = True

    # ── Rule D: Fallback - Out of Stock or No Delivery Coverage ────────────────
    if matched_coverage_but_out_of_stock:
        return ServiceabilityResult(
            is_serviceable=False,
            delivery_type=None,
            serviceability_source=None,
            message=f"This product variant is currently out of stock for delivery to PIN code {clean_pincode}.",
            estimated_days=None,
            estimated_delivery_date=None,
            pincode=clean_pincode,
            product_id=product_id,
            variant_id=variant_id,
            dealer_id=dealer_id,
            reason_code="OUT_OF_STOCK",
            locality=resolved_locality,
            district=resolved_district,
            city=resolved_city,
            state=resolved_state,
        )

    fallback_reason = "PINCODE_LOOKUP_FAILED" if p_info is None else "NO_DELIVERY_COVERAGE"
    fallback_message = (
        f"PIN code '{clean_pincode}' could not be verified in the postal directory."
        if p_info is None
        else f"Sorry, this product cannot be delivered to PIN code {clean_pincode}."
    )

    return ServiceabilityResult(
        is_serviceable=False,
        delivery_type=None,
        serviceability_source=None,
        message=fallback_message,
        estimated_days=None,
        estimated_delivery_date=None,
        pincode=clean_pincode,
        product_id=product_id,
        variant_id=variant_id,
        dealer_id=dealer_id,
        reason_code=fallback_reason,
        locality=resolved_locality,
        district=resolved_district,
        city=resolved_city,
        state=resolved_state,
    )



async def check_pincode_serviceability(
    db: AsyncSession,
    pincode: Optional[str],
    dealer_id: Optional[Any] = None,
    lat: Optional[float] = None,
    long: Optional[float] = None,
    product_id: Optional[Any] = None,
    variant_id: Optional[Any] = None,
    quantity: int = 1
) -> bool:
    """
    Check if a delivery destination pincode is serviceable for a dealer/item.
    Maintains backward compatibility while checking carrier coverage, warehouse direct (Rule A), and local hubs.
    """
    if not pincode or not str(pincode).strip():
        return True

    clean_pincode = str(pincode).strip()

    # If product context is provided, delegate to authoritative check_serviceability_full
    if product_id:
        res = await check_serviceability_full(
            db=db,
            pincode=clean_pincode,
            dealer_id=dealer_id,
            product_id=product_id,
            variant_id=variant_id,
            quantity=quantity,
            lat=lat,
            long=long
        )
        return res.is_serviceable

    # 1. Courier check via configured CarrierServiceabilityAdapter
    carrier_cov = await get_carrier_adapter().check_carrier_coverage(
        db=db,
        dest_pincode=clean_pincode,
        dealer_id=dealer_id
    )
    if carrier_cov and carrier_cov.is_covered:
        return True

    # 2. Warehouse Direct PIN match check (Rule A)
    if dealer_id:
        from models.hub import DeliveryHub
        wh_res = await db.execute(
            select(DeliveryHub).where(
                DeliveryHub.dealer_id == dealer_id,
                DeliveryHub.is_active == True,
                DeliveryHub.pincode == clean_pincode
            ).limit(1)
        )
        wh = wh_res.scalars().first() if hasattr(wh_res, 'scalars') else None
        if wh is not None and getattr(wh, "pincode", None) == clean_pincode:
            return True

    # 3. Local Hub check (if lat/long available)
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
        hubs = hub_res.scalars().all() if hasattr(hub_res, 'scalars') else []
        for hub in hubs:
            try:
                lat_long_str = getattr(hub, 'lat_long', None)
                max_rad = getattr(hub, 'max_delivery_radius', None)
                if not lat_long_str or max_rad is None or max_rad <= 0:
                    continue
                parts = [p.strip() for p in str(lat_long_str).split(",")]
                if len(parts) == 2:
                    h_lat, h_lon = float(parts[0]), float(parts[1])
                    if get_distance_km(lat, long, h_lat, h_lon) <= max_rad:
                        return True
            except Exception:
                continue

    return False


