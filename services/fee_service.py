import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from models import OrderItem, Order, BillingSlab
from core.money import money, money_2dp
from services.configuration_service import get_fee_config, get_fee_config_required
from services.settlement_eligibility_service import is_delivery_self_logistics


class SettlementFeeError(Exception):
    """Raised when required fee configuration is missing/invalid."""


from models.tax import TaxCategory

_GLOBAL_TAX_CATEGORIES_CACHE: List[Any] = []


def extract_tax_category_rate(tc: Any) -> tuple[float, Decimal, bool]:
    """Extract numeric display rate, rate factor, and applicability from an active TaxCategory database model."""
    igst = getattr(tc, "igst_rate", None)
    if igst is not None and float(igst) > 0:
        rate = float(igst)
    else:
        cgst = float(getattr(tc, "cgst_rate", 0.0) or 0.0)
        sgst = float(getattr(tc, "sgst_rate", 0.0) or 0.0)
        rate = cgst + sgst
    rate_factor = Decimal(str(rate)) / Decimal("100.0") if rate > 0 else Decimal("0.00")
    is_applicable = bool(getattr(tc, "is_active", True) and rate > 0)
    return (rate, rate_factor, is_applicable)


def _ensure_tax_categories(cats: Optional[List[Any]]) -> List[Any]:
    global _GLOBAL_TAX_CATEGORIES_CACHE
    if cats is not None:
        return cats
    if _GLOBAL_TAX_CATEGORIES_CACHE:
        return _GLOBAL_TAX_CATEGORIES_CACHE
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return _GLOBAL_TAX_CATEGORIES_CACHE
    except RuntimeError:
        pass
    try:
        import asyncio
        from core.database import SessionLocal
        async def _fetch():
            async with SessionLocal() as s:
                res = await s.execute(select(TaxCategory).where(TaxCategory.is_active == True))
                return list(res.scalars().all())
        cats = asyncio.run(_fetch())
        _GLOBAL_TAX_CATEGORIES_CACHE = cats
        return cats
    except Exception:
        return _GLOBAL_TAX_CATEGORIES_CACHE


async def get_all_active_tax_categories(db: AsyncSession) -> List[TaxCategory]:
    """Fetch all active TaxCategory records from the database and refresh the dynamic cache."""
    global _GLOBAL_TAX_CATEGORIES_CACHE
    stmt = select(TaxCategory).where(TaxCategory.is_active == True)
    res = await db.execute(stmt)
    cats = list(res.scalars().all())
    _GLOBAL_TAX_CATEGORIES_CACHE = cats
    return cats


def resolve_slab_gst_rate(
    gst_type: Optional[str],
    category_key: str = "",
    fallback_cfg: Optional[Any] = None,
    tax_categories: Optional[List[Any]] = None,
) -> tuple[float, Decimal, bool]:
    """
    Authoritative resolver from GST classification to numeric tax rates
    using active TaxCategory records from the database table 'tax_categories'.

    - No hardcoded tax classification dictionaries or alias maps.
    - No regex string-guessing.
    - Resolves directly against database TaxCategory (by ID or exact name).
    - Fails loudly (SettlementFeeError) if classification is unrecognized, inactive, or unmapped.
    - Never silently defaults to 18% or 28%.
    """
    if gst_type is not None and str(gst_type).strip() and str(gst_type).strip().lower() != "none":
        raw = str(gst_type).strip()
        norm = raw.upper()
        cats = _ensure_tax_categories(tax_categories)

        if not cats:
            raise SettlementFeeError(
                f"No active tax categories found in database to resolve GST classification '{gst_type}' for category '{category_key}'."
            )

        # 1. Match by Relational Database Primary Key (ID)
        if raw.isdigit():
            target_id = int(raw)
            matched = next((tc for tc in cats if tc.id == target_id and getattr(tc, "is_active", True)), None)
            if matched:
                return extract_tax_category_rate(matched)

        # 2. Match by Authoritative Name in database (case-insensitive)
        matched = next((tc for tc in cats if tc.name and tc.name.strip().upper() == norm and getattr(tc, "is_active", True)), None)
        if matched:
            return extract_tax_category_rate(matched)

        # 3. Match by Whitespace-Normalized Name in database
        clean_norm = re.sub(r"\s+", " ", norm)
        matched = next((tc for tc in cats if tc.name and re.sub(r"\s+", " ", tc.name.strip().upper()) == clean_norm and getattr(tc, "is_active", True)), None)
        if matched:
            return extract_tax_category_rate(matched)

        # 4. Backward-compatible Legacy Resolution (STANDARD_*, GST_*, CONCESSIONAL_*, REDUCED_*, EXEMPT) against active DB records
        if norm == "EXEMPT":
            matched = next((tc for tc in cats if extract_tax_category_rate(tc)[0] == 0.0 and getattr(tc, "is_active", True)), None)
            if matched:
                return (0.0, Decimal("0.00"), False)

        parts = norm.split("_")
        if len(parts) > 1 and parts[-1].isdigit():
            try:
                target_rate = float(parts[-1])
                matching_cats = [tc for tc in cats if extract_tax_category_rate(tc)[0] == target_rate and getattr(tc, "is_active", True)]
                if matching_cats:
                    pref = next((tc for tc in matching_cats if f"GST {int(target_rate)}%" in tc.name.upper()), matching_cats[0])
                    return extract_tax_category_rate(pref)
            except ValueError:
                pass

        raise SettlementFeeError(
            f"Unrecognized or unapproved GST classification '{gst_type}' configured for category '{category_key}'. "
            "An approved tax classification mapping is required rather than defaulting."
        )

    # If gst_type is None or blank, check fallback_cfg
    if fallback_cfg is not None:
        is_app = getattr(fallback_cfg, "is_gst_applicable", False)
        raw_rate = getattr(fallback_cfg, "gst_rate", None)
        if raw_rate is None and hasattr(fallback_cfg, "value"):
            raw_rate = getattr(fallback_cfg, "value")
        if raw_rate is not None and is_app:
            rate_val = float(raw_rate)
            factor = Decimal(str(rate_val if rate_val < 1.0 else rate_val / 100.0))
            display = rate_val if rate_val >= 1.0 else round(rate_val * 100.0, 2)
            return (display, factor, True)
        elif not is_app:
            return (0.0, Decimal("0.00"), False)

    raise SettlementFeeError(
        f"Missing GST classification and fallback tax configuration for category '{category_key}'. "
        "Active billing slab requires an approved database TaxCategory rather than defaulting."
    )


def _apply_gst(base: Decimal, is_applicable: bool = True, rate: Optional[Decimal] = None) -> Decimal:
    """Returns the GST component on top of a base platform service fee using configured rate."""
    if not is_applicable or rate is None or rate <= Decimal("0.00"):
        return Decimal("0.00")
    # If rate passed as percentage (e.g. 18.0 or 0.18)
    rate_factor = rate if rate < Decimal("1.0") else rate / Decimal("100.0")
    return money_2dp(base * rate_factor)


async def get_applicable_slab(db: AsyncSession, category_key: str, net_basic_amount: Decimal) -> Optional[BillingSlab]:
    """
    Finds the active BillingSlab for category_key where:
      min_price <= net_basic_amount AND (max_price IS NULL OR net_basic_amount <= max_price)
    Safely raises SettlementFeeError if ambiguous multiple active slabs match.
    """
    sale_val = float(net_basic_amount)
    stmt = (
        select(BillingSlab)
        .where(
            and_(
                BillingSlab.category_key == category_key,
                BillingSlab.is_active == True,
                BillingSlab.min_price <= sale_val,
                or_(BillingSlab.max_price.is_(None), BillingSlab.max_price >= sale_val),
            )
        )
        .order_by(BillingSlab.min_price.desc())
    )
    res = await db.execute(stmt)
    matching = res.scalars().all()
    if len(matching) > 1:
        slab_summaries = ", ".join([f"ID {s.id} (₹{s.min_price}-₹{s.max_price if s.max_price is not None else '∞'})" for s in matching])
        raise SettlementFeeError(
            f"Ambiguous active billing slabs found for category '{category_key}' at amount ₹{net_basic_amount}: {slab_summaries}"
        )
    return matching[0] if matching else None


async def get_all_active_slabs(db: AsyncSession) -> List[BillingSlab]:
    """Pre-fetch all active billing slabs in a single query to eliminate per-item DB round trips."""
    stmt = (
        select(BillingSlab)
        .where(BillingSlab.is_active == True)
        .order_by(BillingSlab.min_price.desc())
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


def match_slab_from_list(slabs: List[BillingSlab], category_key: str, net_basic_amount: Decimal) -> Optional[BillingSlab]:
    """
    Finds the active BillingSlab for category_key from pre-fetched slabs using identical price range rules.
    Safely raises SettlementFeeError if ambiguous multiple active slabs match.
    """
    sale_val = round(float(net_basic_amount), 2)
    matches = []
    for slab in slabs:
        if slab.category_key == category_key and slab.is_active:
            s_min = round(float(slab.min_price), 2) if slab.min_price is not None else 0.0
            s_max = round(float(slab.max_price), 2) if slab.max_price is not None else float("inf")
            if (s_min <= sale_val <= s_max) or (sale_val < s_min and s_min <= 1.0):
                matches.append(slab)
    if len(matches) > 1:
        slab_summaries = ", ".join([f"ID {s.id} (₹{s.min_price}-₹{s.max_price if s.max_price is not None else '∞'})" for s in matches])
        raise SettlementFeeError(
            f"Ambiguous active billing slabs found for category '{category_key}' at amount ₹{net_basic_amount}: {slab_summaries}"
        )
    return matches[0] if matches else None



async def validate_no_overlap(
    db: AsyncSession,
    category_key: str,
    min_price: float,
    max_price: Optional[float],
    exclude_id: Optional[int] = None,
) -> None:
    """
    Ensures that adding/updating/activating a BillingSlab does not overlap with any existing active slab in category_key.
    Enforces 2-decimal precision and boundary rules.
    """
    if min_price < 0:
        raise ValueError("Minimum price cannot be negative")
    if max_price is not None and max_price < min_price:
        raise ValueError(f"Maximum price (₹{max_price}) cannot be less than minimum price (₹{min_price})")

    stmt = select(BillingSlab).where(
        and_(BillingSlab.category_key == category_key, BillingSlab.is_active == True)
    )
    if exclude_id is not None:
        stmt = stmt.where(BillingSlab.id != exclude_id)
    
    res = await db.execute(stmt)
    existing_slabs = res.scalars().all()

    cur_min = round(float(min_price), 2)
    cur_max = round(float(max_price), 2) if max_price is not None else float("inf")

    for s in existing_slabs:
        s_min = round(float(s.min_price), 2)
        s_max = round(float(s.max_price), 2) if s.max_price is not None else float("inf")

        if max(s_min, cur_min) <= min(s_max, cur_max):
            max_str = f"₹{s.max_price}" if s.max_price is not None else "∞"
            cur_max_str = f"₹{max_price}" if max_price is not None else "∞"
            raise ValueError(
                f"Price range ₹{cur_min}-{cur_max_str} overlaps with existing active slab ID {s.id} (₹{s_min}-{max_str})"
            )


def compute_gross_sale(item: OrderItem, order: Order) -> Decimal:
    """
    Line 14 (Dealer Net Selling Price Total):
    GST-inclusive net selling price for the item = (Unit Price * Qty) - Discount.
    OrderItem.price is already stored as the inclusive price at checkout.
    """
    item_subtotal = money(item.price) * item.quantity
    discount_amount = money(order.discount_amount)
    if discount_amount > 0 and order.subtotal and money(order.subtotal) > 0:
        discount_share = money(item_subtotal / money(order.subtotal) * discount_amount)
    else:
        discount_share = Decimal("0.00")
    
    net_inclusive = money(item_subtotal - discount_share)
    return money_2dp(net_inclusive)


def compute_shipping_share(item: OrderItem, order: Order, shipping_gst_rate: Optional[Decimal] = None) -> Decimal:
    """
    Line 7 (Customer Shipment Charge Total incl. configured GST).
    Item's share of customer delivery charge.
    """
    delivery_basic = money(order.delivery_charge)
    if delivery_basic <= 0:
        return Decimal("0.00")
    
    item_subtotal = money(item.price) * item.quantity
    if order.subtotal and money(order.subtotal) > 0:
        ship_basic = money(delivery_basic * item_subtotal / money(order.subtotal))
    else:
        ship_basic = delivery_basic
    
    if shipping_gst_rate and shipping_gst_rate > 0:
        rate_factor = shipping_gst_rate if shipping_gst_rate < Decimal("1.0") else shipping_gst_rate / Decimal("100.0")
        ship_gst = money(ship_basic * rate_factor)
        return money_2dp(ship_basic + ship_gst)
    return money_2dp(ship_basic)


async def compute_item_fees(
    db: AsyncSession,
    item: OrderItem,
    order: Order,
    gross_sale: Decimal,
) -> Dict[str, Any]:
    """
    Computes the Dealer fee breakdown for one order item following Dealer Excel specification:
    
    Line 14 = Gross Sale Amount (Net Selling Price Total incl. Product GST)
    Line 15 = Marketing Commission Total (incl. configured fee GST)
    Line 16 = Marketplace Charge Total (incl. configured fee GST)
    Line 7  = Customer Shipment Total (incl. configured fee GST, added for Self Logistics)
    Line 17 = Partner Logistics Charge Total (incl. configured fee GST, deducted for Partner Logistics)
    """
    item_subtotal = money(item.price) * item.quantity
    discount_amount = money(order.discount_amount)
    discount_share = money(item_subtotal / money(order.subtotal) * discount_amount) if (discount_amount > 0 and order.subtotal and money(order.subtotal) > 0) else Decimal("0.00")
    net_basic = money(item_subtotal - discount_share)
    item_tax = money(getattr(item, 'tax_amount', 0.0) or 0.0)
    taxable_item_base = max(Decimal("0.00"), net_basic - item_tax) if item_tax > Decimal("0.00") else net_basic
    active_tax_cats = await get_all_active_tax_categories(db)

    # 1. Marketplace Fee (Line 16: Dealer Deduction)
    marketplace_cfg = await get_fee_config_required(db, "marketplace_fee")
    snap_mp_dealer = getattr(item, 'marketplace_dealer_fee', 0.0) or 0.0
    snap_mp_cust = getattr(item, 'marketplace_customer_charge', 0.0) or 0.0
    snap_mp_gst_rate = getattr(item, 'marketplace_fee_gst_rate', None)
    snap_mp_gst_amt = getattr(item, 'marketplace_fee_gst_amount', None)

    is_auction = getattr(order, "is_auction", False) or getattr(order, "order_type", "") == "auction" or getattr(item, "is_auction", False)
    category = "auction_marketplace" if is_auction else "marketplace"
    mp_slab = await get_applicable_slab(db, category, taxable_item_base)
    if mp_slab is None and is_auction:
        mp_slab = await get_applicable_slab(db, "marketplace", taxable_item_base)

    if snap_mp_gst_rate is not None:
        eff_mp_gst_rate = Decimal(str(snap_mp_gst_rate))
    else:
        _, eff_mp_gst_rate, _ = resolve_slab_gst_rate(mp_slab.gst_type if mp_slab else None, category, marketplace_cfg, tax_categories=active_tax_cats)
    
    if snap_mp_cust > 0:
        marketplace_customer_charge = money_2dp(snap_mp_cust)
    else:
        is_auction = getattr(order, "is_auction", False) or getattr(order, "order_type", "") == "auction" or getattr(item, "is_auction", False)
        category = "auction_marketplace" if is_auction else "marketplace"
        mp_slab = await get_applicable_slab(db, category, net_basic)
        if mp_slab is None and is_auction:
            mp_slab = await get_applicable_slab(db, "marketplace", net_basic)
        marketplace_cust_pct = money(mp_slab.customer_percentage) if (mp_slab and mp_slab.customer_percentage is not None) else Decimal("0.00")
        marketplace_customer_charge = money_2dp(net_basic * marketplace_cust_pct)

    if snap_mp_dealer > 0:
        marketplace_base = money(snap_mp_dealer)
        if snap_mp_gst_amt is not None:
            marketplace_gst = money(snap_mp_gst_amt)
        else:
            marketplace_gst = _apply_gst(marketplace_base, marketplace_cfg.is_gst_applicable, eff_mp_gst_rate)
        marketplace_fee = money_2dp(marketplace_base + marketplace_gst)
    else:
        is_auction = getattr(order, "is_auction", False) or getattr(order, "order_type", "") == "auction" or getattr(item, "is_auction", False)
        category = "auction_marketplace" if is_auction else "marketplace"
        mp_slab = await get_applicable_slab(db, category, taxable_item_base)
        if mp_slab is None and is_auction:
            mp_slab = await get_applicable_slab(db, "marketplace", taxable_item_base)

        if mp_slab is not None:
            marketplace_dealer_pct = money(mp_slab.dealer_percentage)
            marketplace_base = money(taxable_item_base * marketplace_dealer_pct)
        elif marketplace_cfg is not None and money(marketplace_cfg.value) > 0:
            if marketplace_cfg.fee_type.value == "percentage":
                marketplace_base = money(net_basic * money(marketplace_cfg.value))
            else:
                marketplace_base = money(money(marketplace_cfg.value) * item.quantity)
        else:
            marketplace_base = money(item.platform_fee or 0)

        marketplace_gst = _apply_gst(
            marketplace_base,
            bool(marketplace_cfg.is_gst_applicable),
            eff_mp_gst_rate,
        )
        marketplace_fee = money_2dp(marketplace_base + marketplace_gst)

    # 2. Marketing Fee (Line 15: Dealer Deduction)
    marketing_cfg = await get_fee_config_required(db, "marketing_fee")
    snap_mkt = getattr(item, 'marketing_fee_amount', 0.0) or 0.0
    snap_mkt_gst_rate = getattr(item, 'marketing_fee_gst_rate', None)
    snap_mkt_gst_amt = getattr(item, 'marketing_fee_gst_amount', None)

    mkt_slab = await get_applicable_slab(db, "marketing", net_basic)
    if snap_mkt_gst_rate is not None:
        eff_mkt_gst_rate = Decimal(str(snap_mkt_gst_rate))
    else:
        _, eff_mkt_gst_rate, _ = resolve_slab_gst_rate(mkt_slab.gst_type if mkt_slab else None, "marketing", marketing_cfg, tax_categories=active_tax_cats)

    if snap_mkt > 0:
        marketing_base = money(snap_mkt)
        if snap_mkt_gst_amt is not None:
            marketing_gst = money(snap_mkt_gst_amt)
        else:
            marketing_gst = _apply_gst(marketing_base, marketing_cfg.is_gst_applicable, eff_mkt_gst_rate)
        marketing_fee = money_2dp(marketing_base + marketing_gst)
    else:
        mkt_slab = await get_applicable_slab(db, "marketing", taxable_item_base)
        if mkt_slab is not None:
            marketing_pct = money(mkt_slab.dealer_percentage)
            marketing_base = money(taxable_item_base * marketing_pct)
        elif marketing_cfg is not None and money(marketing_cfg.value) > 0:
            if marketing_cfg.fee_type.value == "percentage":
                marketing_base = money(taxable_item_base * money(marketing_cfg.value))
            else:
                marketing_base = money(money(marketing_cfg.value) * item.quantity)
        else:
            marketing_base = Decimal("0.00")

        marketing_gst = _apply_gst(
            marketing_base,
            bool(marketing_cfg.is_gst_applicable),
            eff_mkt_gst_rate,
        )
        marketing_fee = money_2dp(marketing_base + marketing_gst)

    # 3. Shipping / Logistics (Line 7 vs Line 17)
    self_logistics = await is_delivery_self_logistics(item)
    if self_logistics:
        cust_ship_cfg = await get_fee_config(db, "customer_shipping_gst_rate")
        snap_del_gst_rate = getattr(item, 'customer_delivery_gst_rate', None)
        if snap_del_gst_rate is not None:
            ship_gst_rate = Decimal(str(snap_del_gst_rate))
        elif cust_ship_cfg:
            rate_val = cust_ship_cfg.gst_rate if (cust_ship_cfg.gst_rate is not None and cust_ship_cfg.gst_rate > 0) else (cust_ship_cfg.value or 0.0)
            ship_gst_rate = Decimal(str(rate_val))
        else:
            ship_gst_rate = Decimal("0.00")
        shipping_received = compute_shipping_share(item, order, ship_gst_rate)
        logistics_charge = Decimal("0.00")
        logistics_gst = Decimal("0.00")
        logistics_base = Decimal("0.00")
    else:
        shipping_received = Decimal("0.00")
        logistics_cfg = await get_fee_config_required(db, "partner_logistics_fee")
        snap_log_gst_rate = getattr(item, 'logistics_fee_gst_rate', None)
        snap_log_gst_amt = getattr(item, 'logistics_fee_gst_amount', None)

        log_slab = await get_applicable_slab(db, "logistics", taxable_item_base)
        if snap_log_gst_rate is not None:
            eff_log_gst_rate = Decimal(str(snap_log_gst_rate))
        else:
            _, eff_log_gst_rate, _ = resolve_slab_gst_rate(log_slab.gst_type if log_slab else None, "logistics", logistics_cfg, tax_categories=active_tax_cats)

        snap_log = getattr(item, 'logistics_charge_amount', 0.0) or 0.0
        if snap_log > 0:
            logistics_base = money(snap_log)
            if snap_log_gst_amt is not None:
                logistics_gst = money(snap_log_gst_amt)
            else:
                logistics_gst = _apply_gst(logistics_base, logistics_cfg.is_gst_applicable, eff_log_gst_rate)
            logistics_charge = money_2dp(logistics_base + logistics_gst)
        else:
            log_slab = await get_applicable_slab(db, "logistics", taxable_item_base)
            if log_slab is not None:
                logistics_pct = money(log_slab.dealer_percentage)
                logistics_base = money(taxable_item_base * logistics_pct)
            elif logistics_cfg is not None and money(logistics_cfg.value) > 0:
                if logistics_cfg.fee_type.value == "percentage":
                    logistics_base = money(net_basic * money(logistics_cfg.value))
                else:
                    logistics_base = money(money(logistics_cfg.value) * item.quantity)
            else:
                raise SettlementFeeError("partner_logistics_fee config missing for partner-logistics order")

            logistics_gst = _apply_gst(
                logistics_base,
                bool(logistics_cfg.is_gst_applicable),
                eff_log_gst_rate,
            )
            logistics_charge = money_2dp(logistics_base + logistics_gst)

    gst_on_fees = money_2dp(marketplace_gst + marketing_gst + logistics_gst)

    return {
        "gross_sale_amount": money_2dp(gross_sale),
        "marketplace_base": money_2dp(marketplace_base),
        "marketplace_fee": money_2dp(marketplace_fee),
        "marketplace_customer_charge": money_2dp(marketplace_customer_charge),
        "marketing_base": money_2dp(marketing_base),
        "marketing_fee": money_2dp(marketing_fee),
        "shipping_received": money_2dp(shipping_received),
        "logistics_base": money_2dp(logistics_base),
        "logistics_charge": money_2dp(logistics_charge),
        "gst_on_fees": money_2dp(gst_on_fees),
        "delivery_type": getattr(item, 'delivery_type', None),
    }
