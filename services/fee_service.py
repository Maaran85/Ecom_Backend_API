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


def _apply_gst(base: Decimal, is_applicable: bool = True, rate: Decimal = Decimal("0.18")) -> Decimal:
    """Returns the 18% GST component on top of a base platform service fee (Marketplace, Marketing, Logistics)."""
    if not is_applicable or rate <= 0:
        return Decimal("0.00")
    # If rate passed as percentage (e.g. 18.0 or 0.18)
    rate_factor = rate if rate < 1 else rate / Decimal("100")
    return money(base * rate_factor)


async def get_applicable_slab(db: AsyncSession, category_key: str, net_basic_amount: Decimal) -> Optional[BillingSlab]:
    """
    Finds the active BillingSlab for category_key where:
      min_price <= net_basic_amount AND (max_price IS NULL OR net_basic_amount <= max_price)
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
        .limit(1)
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def validate_no_overlap(
    db: AsyncSession,
    category_key: str,
    min_price: float,
    max_price: Optional[float],
    exclude_id: Optional[int] = None,
) -> None:
    """
    Ensures that adding/updating a BillingSlab does not overlap with any existing active slab in category_key.
    """
    stmt = select(BillingSlab).where(
        and_(BillingSlab.category_key == category_key, BillingSlab.is_active == True)
    )
    if exclude_id is not None:
        stmt = stmt.where(BillingSlab.id != exclude_id)
    
    res = await db.execute(stmt)
    existing_slabs = res.scalars().all()

    for s in existing_slabs:
        s_min = s.min_price
        s_max = s.max_price if s.max_price is not None else float("inf")
        cur_min = min_price
        cur_max = max_price if max_price is not None else float("inf")

        if max(s_min, cur_min) <= min(s_max, cur_max):
            max_str = f"₹{s.max_price}" if s.max_price is not None else "∞"
            raise ValueError(f"Price range ₹{min_price}-{max_price if max_price is not None else '∞'} overlaps with existing active slab ₹{s_min}-{max_str}")


def compute_gross_sale(item: OrderItem, order: Order) -> Decimal:
    """
    Line 14 (Dealer Net Selling Price Total):
    GST-inclusive net selling price for the item = (Unit Price * Qty) - Discount + Product GST.
    """
    item_subtotal = money(item.price) * item.quantity
    discount_amount = money(order.discount_amount)
    if discount_amount > 0 and order.subtotal and money(order.subtotal) > 0:
        discount_share = money(item_subtotal / money(order.subtotal) * discount_amount)
    else:
        discount_share = Decimal("0.00")
    
    net_basic = money(item_subtotal - discount_share)
    
    # Calculate or retrieve Product GST Amount
    tax_amt = money(
        getattr(item, 'tax_amount', 0.0) or
        ((getattr(item, 'cgst_amount', 0.0) or 0.0) +
         (getattr(item, 'sgst_amount', 0.0) or 0.0) +
         (getattr(item, 'igst_amount', 0.0) or 0.0))
    )
    if tax_amt == 0 and (getattr(item, 'cgst_rate', 0) > 0 or getattr(item, 'igst_rate', 0) > 0):
        c_rate = getattr(item, 'cgst_rate', 0.0) or 0.0
        s_rate = getattr(item, 'sgst_rate', 0.0) or 0.0
        i_rate = getattr(item, 'igst_rate', 0.0) or 0.0
        tot_rate = i_rate if i_rate > 0 else (c_rate + s_rate)
        tax_amt = money(net_basic * (Decimal(str(tot_rate)) / Decimal("100")))

    return money_2dp(net_basic + tax_amt)


def compute_shipping_share(item: OrderItem, order: Order) -> Decimal:
    """
    Line 7 (Customer Shipment Charge Total incl. 18% GST).
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
    
    # Add 18% GST to delivery basic to get Total Customer Shipment Charge
    ship_gst = money(ship_basic * Decimal("0.18"))
    return money_2dp(ship_basic + ship_gst)


async def compute_item_fees(
    db: AsyncSession,
    item: OrderItem,
    order: Order,
    gross_sale: Decimal,
) -> Dict[str, Any]:
    """
    Computes the Dealer fee breakdown for one order item following Dealer Excel specification:
    
    Line 14 = Gross Sale Amount (Net Selling Price Total incl. Product GST)
    Line 15 = Marketing Commission Total (incl. 18% GST)
    Line 16 = Marketplace Charge Total (incl. 18% GST)
    Line 7  = Customer Shipment Total (incl. 18% GST, added for Self Logistics)
    Line 17 = Partner Logistics Charge Total (incl. 18% GST, deducted for Partner Logistics)
    """
    # Basic net amount before product GST for slab matching
    item_subtotal = money(item.price) * item.quantity
    discount_amount = money(order.discount_amount)
    discount_share = money(item_subtotal / money(order.subtotal) * discount_amount) if (discount_amount > 0 and order.subtotal and money(order.subtotal) > 0) else Decimal("0.00")
    net_basic = money(item_subtotal - discount_share)

    # 1. Marketplace Fee (Line 16: Dealer Deduction)
    snap_mp_dealer = getattr(item, 'marketplace_dealer_fee', 0.0) or 0.0
    snap_mp_cust = getattr(item, 'marketplace_customer_charge', 0.0) or 0.0
    
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
        # Check if snapshot is already GST-inclusive or basic
        base_mp = money(snap_mp_dealer)
        gst_mp = _apply_gst(base_mp, True, Decimal("0.18"))
        marketplace_fee = money_2dp(base_mp + gst_mp)
    else:
        is_auction = getattr(order, "is_auction", False) or getattr(order, "order_type", "") == "auction" or getattr(item, "is_auction", False)
        category = "auction_marketplace" if is_auction else "marketplace"
        mp_slab = await get_applicable_slab(db, category, net_basic)
        if mp_slab is None and is_auction:
            mp_slab = await get_applicable_slab(db, "marketplace", net_basic)
        marketplace_cfg = await get_fee_config(db, "marketplace_fee")

        if mp_slab is not None:
            marketplace_dealer_pct = money(mp_slab.dealer_percentage)
            marketplace_base = money(net_basic * marketplace_dealer_pct)
        elif marketplace_cfg is not None and money(marketplace_cfg.value) > 0:
            if marketplace_cfg.fee_type.value == "percentage":
                marketplace_base = money(net_basic * money(marketplace_cfg.value))
            else:
                marketplace_base = money(money(marketplace_cfg.value) * item.quantity)
        else:
            marketplace_base = money(item.platform_fee or 0)

        marketplace_gst = _apply_gst(
            marketplace_base,
            bool(marketplace_cfg.is_gst_applicable) if marketplace_cfg else True,
            money(marketplace_cfg.gst_rate) if (marketplace_cfg and marketplace_cfg.gst_rate) else Decimal("0.18"),
        )
        marketplace_fee = money_2dp(marketplace_base + marketplace_gst)

    # 2. Marketing Fee (Line 15: Dealer Deduction)
    snap_mkt = getattr(item, 'marketing_fee_amount', 0.0) or 0.0
    if snap_mkt > 0:
        base_mkt = money(snap_mkt)
        gst_mkt = _apply_gst(base_mkt, True, Decimal("0.18"))
        marketing_fee = money_2dp(base_mkt + gst_mkt)
    else:
        mkt_slab = await get_applicable_slab(db, "marketing", net_basic)
        marketing_cfg = await get_fee_config(db, "marketing_fee")

        if mkt_slab is not None:
            marketing_pct = money(mkt_slab.dealer_percentage)
            marketing_base = money(net_basic * marketing_pct)
        elif marketing_cfg is not None:
            if marketing_cfg.fee_type.value == "percentage":
                marketing_base = money(net_basic * money(marketing_cfg.value))
            else:
                marketing_base = money(money(marketing_cfg.value) * item.quantity)
        else:
            marketing_base = Decimal("0.00")

        marketing_gst = _apply_gst(
            marketing_base,
            bool(marketing_cfg.is_gst_applicable) if marketing_cfg else True,
            money(marketing_cfg.gst_rate) if (marketing_cfg and marketing_cfg.gst_rate) else Decimal("0.18"),
        )
        marketing_fee = money_2dp(marketing_base + marketing_gst)

    # 3. Shipping / Logistics (Line 7 vs Line 17)
    self_logistics = await is_delivery_self_logistics(item)
    if self_logistics:
        shipping_received = compute_shipping_share(item, order)
        logistics_charge = Decimal("0.00")
        logistics_gst = Decimal("0.00")
    else:
        shipping_received = Decimal("0.00")
        snap_log = getattr(item, 'logistics_charge_amount', 0.0) or 0.0
        if snap_log > 0:
            base_log = money(snap_log)
            gst_log = _apply_gst(base_log, True, Decimal("0.18"))
            logistics_charge = money_2dp(base_log + gst_log)
        else:
            log_slab = await get_applicable_slab(db, "logistics", net_basic)
            logistics_cfg = await get_fee_config(db, "partner_logistics_fee")

            if log_slab is not None:
                logistics_pct = money(log_slab.dealer_percentage)
                logistics_base = money(net_basic * logistics_pct)
            elif logistics_cfg is not None:
                if logistics_cfg.fee_type.value == "percentage":
                    logistics_base = money(net_basic * money(logistics_cfg.value))
                else:
                    logistics_base = money(money(logistics_cfg.value) * item.quantity)
            else:
                raise SettlementFeeError("partner_logistics_fee config missing for partner-logistics order")

            logistics_gst = _apply_gst(
                logistics_base,
                bool(logistics_cfg.is_gst_applicable) if logistics_cfg else True,
                money(logistics_cfg.gst_rate) if (logistics_cfg and logistics_cfg.gst_rate) else Decimal("0.18"),
            )
            logistics_charge = money_2dp(logistics_base + logistics_gst)

    gst_on_fees = money_2dp(marketplace_fee - (marketplace_base if 'marketplace_base' in locals() else marketplace_fee/Decimal('1.18')) +
                         marketing_fee - (marketing_base if 'marketing_base' in locals() else marketing_fee/Decimal('1.18')))

    return {
        "gross_sale_amount": money_2dp(gross_sale),
        "marketplace_fee": money_2dp(marketplace_fee),
        "marketplace_customer_charge": money_2dp(marketplace_customer_charge),
        "marketing_fee": money_2dp(marketing_fee),
        "shipping_received": money_2dp(shipping_received),
        "logistics_charge": money_2dp(logistics_charge),
        "gst_on_fees": money_2dp(gst_on_fees),
        "delivery_type": getattr(item, 'delivery_type', None),
    }
