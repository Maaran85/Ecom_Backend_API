from decimal import Decimal
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from models import OrderItem, Order
from core.money import money
from services.configuration_service import get_fee_config, get_fee_config_required
from services.settlement_eligibility_service import is_delivery_self_logistics


class SettlementFeeError(Exception):
    """Raised when required fee configuration is missing/invalid."""


def _apply_gst(base: Decimal, is_applicable: bool, rate: Decimal) -> Decimal:
    """Returns the GST component on top of a base amount (kept as platform revenue)."""
    if not is_applicable or rate <= 0:
        return Decimal("0")
    return money(base * rate)


def compute_gross_sale(item: OrderItem, order: Order) -> Decimal:
    """
    GST-inclusive net selling price for the item = (price * qty) - discount share.
    Prorates the order-level coupon discount the same way checkout does.
    """
    item_subtotal = money(item.price) * item.quantity
    discount_amount = money(order.discount_amount)
    if discount_amount > 0 and order.subtotal and money(order.subtotal) > 0:
        discount_share = money(item_subtotal / money(order.subtotal) * discount_amount)
    else:
        discount_share = Decimal("0")
    return money(item_subtotal - discount_share)


def compute_shipping_share(item: OrderItem, order: Order) -> Decimal:
    """Item's share of the customer delivery charge stored on the order."""
    delivery = money(order.delivery_charge)
    if delivery <= 0:
        return Decimal("0")
    item_subtotal = money(item.price) * item.quantity
    if order.subtotal and money(order.subtotal) > 0:
        return money(delivery * item_subtotal / money(order.subtotal))
    return delivery


async def compute_item_fees(
    db: AsyncSession,
    item: OrderItem,
    order: Order,
    gross_sale: Decimal,
) -> Dict[str, Any]:
    """
    Computes the fee breakdown for one order item.

    Returns (all values Decimal, 4dp):
      gross_sale_amount, marketplace_fee, marketing_fee, shipping_received,
      logistics_charge, gst_on_fees, delivery_type
    """
    marketplace_cfg = await get_fee_config(db, "marketplace_fee")
    marketing_cfg = await get_fee_config_required(db, "marketing_fee")
    logistics_cfg = await get_fee_config(db, "partner_logistics_fee")

    # ---- Marketplace fee ----
    # Explicit config (value > 0) overrides the amount collected at checkout.
    if marketplace_cfg is not None and money(marketplace_cfg.value) > 0:
        if marketplace_cfg.fee_type.value == "percentage":
            marketplace_base = money(gross_sale * money(marketplace_cfg.value))
        else:
            marketplace_base = money(money(marketplace_cfg.value) * item.quantity)
    else:
        marketplace_base = money(item.platform_fee or 0)
    marketplace_gst = _apply_gst(
        marketplace_base,
        bool(marketplace_cfg.is_gst_applicable) if marketplace_cfg else False,
        money(marketplace_cfg.gst_rate) if marketplace_cfg else Decimal("0"),
    )
    marketplace_fee = money(marketplace_base + marketplace_gst)

    # ---- Marketing fee ----
    if marketing_cfg.fee_type.value == "percentage":
        marketing_base = money(gross_sale * money(marketing_cfg.value))
    else:
        marketing_base = money(money(marketing_cfg.value) * item.quantity)
    marketing_gst = _apply_gst(
        marketing_base,
        marketing_cfg.is_gst_applicable,
        money(marketing_cfg.gst_rate),
    )
    marketing_fee = money(marketing_base + marketing_gst)

    # ---- Shipping / logistics ----
    self_logistics = await is_delivery_self_logistics(item)
    if self_logistics:
        shipping_received = compute_shipping_share(item, order)
        # Optional GST on the customer shipping passed to the dealer.
        shipping_gst_cfg = await get_fee_config(db, "customer_shipping_gst_rate")
        if shipping_gst_cfg and money(shipping_gst_cfg.value) > 0:
            shipping_gst = money(shipping_received * money(shipping_gst_cfg.value))
            shipping_received = money(shipping_received + shipping_gst)
        logistics_charge = Decimal("0")
        logistics_gst = Decimal("0")
    else:
        shipping_received = Decimal("0")
        if logistics_cfg is None:
            raise SettlementFeeError("partner_logistics_fee config missing for partner-logistics order")
        if logistics_cfg.fee_type.value == "percentage":
            logistics_base = money(gross_sale * money(logistics_cfg.value))
        else:
            logistics_base = money(money(logistics_cfg.value) * item.quantity)
        logistics_gst = _apply_gst(
            logistics_base,
            logistics_cfg.is_gst_applicable,
            money(logistics_cfg.gst_rate),
        )
        logistics_charge = money(logistics_base + logistics_gst)

    gst_on_fees = money(marketplace_gst + marketing_gst + logistics_gst)

    return {
        "gross_sale_amount": gross_sale,
        "marketplace_fee": marketplace_fee,
        "marketing_fee": marketing_fee,
        "shipping_received": shipping_received,
        "logistics_charge": logistics_charge,
        "gst_on_fees": gst_on_fees,
        "delivery_type": item.delivery_type,
    }
