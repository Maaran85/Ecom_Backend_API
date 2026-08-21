"""
Golden-number tests for the settlement engine against the 'billing' sheet of
ecommerce-taxation structure.xlsx.

Reference numbers (Excel):
  MRP 1000, SP 500, discount 5% -> net selling price 475
  GST 18% on 475            -> 85.50
  Gross sale (TDS base)     -> 560.50
  Marketplace fee 25 + 4.50 -> 29.50
  Marketing fee 10 + 1.80   -> 11.80
  Shipping (customer) 18 + 3.24 -> 21.24
  Dealer partner logistics 15 + 2.70 -> 17.70
  TDS 0.1% x 560.50         -> 0.5605   (dealer already above the 5L exemption)

  Self-logistics payout     -> 539.8795  (~539.88)
  Partner-logistics payout  -> 500.9395  (~500.94)
  Customer total            -> 611.24    (560.50 + 21.24 + 29.50)
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from core.enums import TDSThresholdStrategy
from services.fee_service import compute_gross_sale
from services.settlement_calculator import calculate_settlement
from services.tds_resolver import resolve_tds_line


def _tds_config():
    return SimpleNamespace(
        organization_type="individual",
        section="194-O",
        tds_rate_with_pan=0.001,
        exemption_limit_with_pan=500000.0,
        tds_rate_without_pan=0.05,
        exemption_limit_without_pan=None,
        threshold_strategy=TDSThresholdStrategy.PROSPECTIVE,
    )


def _fee_cfg(key, fee_type, value, gst_applicable, gst_rate):
    return SimpleNamespace(
        key=key,
        fee_type=SimpleNamespace(value=fee_type),
        value=value,
        is_gst_applicable=gst_applicable,
        gst_rate=gst_rate,
    )


def _fees_config():
    return {
        "marketplace_fee": _fee_cfg("marketplace_fee", "flat", 25, True, 0.18),
        "marketing_fee": _fee_cfg("marketing_fee", "flat", 10, True, 0.18),
        "partner_logistics_fee": _fee_cfg("partner_logistics_fee", "flat", 15, True, 0.18),
        "customer_shipping_gst_rate": _fee_cfg("customer_shipping_gst_rate", "percentage", 0.18, False, 0),
    }


def _dealer():
    return SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        organization_type="individual",
        pan_number="AAAAA1234A",
    )


def _order(item_price=560.5, delivery_charge=18.0):
    return SimpleNamespace(
        id=1,
        order_number="ORD-1",
        subtotal=item_price,
        discount_amount=0.0,
        delivery_charge=delivery_charge,
        created_at=None,
    )


def _item(delivery_type, logistics_partner_id=None, price=560.5):
    return SimpleNamespace(
        id=10,
        price=price,
        quantity=1,
        platform_fee=0.0,
        delivery_type=delivery_type,
        logistics_partner_id=logistics_partner_id,
    )


@pytest.fixture
def monkeypatch_config(monkeypatch):
    import services.fee_service as fee_service
    import services.settlement_calculator as calculator

    fees = _fees_config()
    tds = _tds_config()

    async def fake_get_fee_config(db, key):
        return fees.get(key)

    async def fake_get_fee_config_required(db, key):
        if key not in fees:
            raise ValueError(f"missing fee config {key}")
        return fees[key]

    async def fake_get_active_tds_config(db, org_type):
        return tds

    async def fake_get_applicable_slab(db, category_key, net_basic_amount):
        return None

    monkeypatch.setattr(fee_service, "get_fee_config", fake_get_fee_config)
    monkeypatch.setattr(fee_service, "get_fee_config_required", fake_get_fee_config_required)
    monkeypatch.setattr(fee_service, "get_applicable_slab", fake_get_applicable_slab)
    monkeypatch.setattr(calculator, "get_active_tds_config_required", fake_get_active_tds_config)


class FakeDB:
    """Config lookups are monkeypatched away; this is just a placeholder."""


def _crossed_threshold_fy_summary():
    """Dealer whose FY gross already exceeds the 5L exemption (as in the Excel example)."""
    return SimpleNamespace(cumulative_gross_sale=500000.0)


def _fresh_fy_summary():
    return SimpleNamespace(cumulative_gross_sale=0.0)


@pytest.mark.asyncio
async def test_self_logistics_golden(monkeypatch_config):
    item = _item(delivery_type="own_rider", logistics_partner_id=None)
    order = _order()
    dealer = _dealer()
    calc = await calculate_settlement(
        FakeDB(), dealer, [(item, order, None, dealer)],
        fy_summary=_crossed_threshold_fy_summary(),
    )

    line = calc.lines[0]
    assert line.gross_sale == Decimal("560.50")
    assert line.marketplace_fee == Decimal("29.50")
    assert line.marketing_fee == Decimal("11.80")
    assert line.shipping_received == Decimal("21.24")
    assert line.logistics_charge == Decimal("0.00")
    assert line.tds_amount == Decimal("0.56")
    assert line.net_payable == Decimal("539.88")  # 560.50 - 29.50 - 11.80 + 21.24 - 0.56 = 539.88
    assert calc.net_payable == Decimal("539.88")


@pytest.mark.asyncio
async def test_partner_logistics_golden(monkeypatch_config):
    item = _item(delivery_type="logistics", logistics_partner_id=1)
    order = _order()
    dealer = _dealer()
    calc = await calculate_settlement(
        FakeDB(), dealer, [(item, order, None, dealer)],
        fy_summary=_crossed_threshold_fy_summary(),
    )

    line = calc.lines[0]
    assert line.shipping_received == Decimal("0.00")
    assert line.logistics_charge == Decimal("17.70")
    assert line.tds_amount == Decimal("0.56")
    assert line.net_payable == Decimal("500.94")  # 560.50 - 29.50 - 11.80 - 17.70 - 0.56 = 500.94
    assert calc.net_payable == Decimal("500.94")


@pytest.mark.asyncio
async def test_order_8712519463_self_logistics_golden(monkeypatch_config):
    """Specific test for Order #8712519463 Excel model matching ₹662.03."""
    item = SimpleNamespace(
        id=66,
        price=650.0,
        quantity=1,
        platform_fee=0.0,
        delivery_type="own_rider",
        logistics_partner_id=None,
        marketplace_dealer_fee=9.75, # Basic 1.5% snapshot
        marketing_fee_amount=19.50, # Basic 3.0% snapshot
    )
    order = SimpleNamespace(
        id=123,
        order_number="8712519463",
        subtotal=650.0,
        discount_amount=0.0,
        delivery_charge=40.0, # Basic 40 + 18% GST = 47.20
        created_at=None,
    )
    dealer = _dealer()
    calc = await calculate_settlement(
        FakeDB(), dealer, [(item, order, None, dealer)],
        fy_summary=_crossed_threshold_fy_summary(),
    )

    line = calc.lines[0]
    assert line.gross_sale == Decimal("650.00")
    assert line.marketing_fee == Decimal("23.01") # 19.50 * 1.18
    assert line.marketplace_fee == Decimal("11.51") # 9.75 * 1.18 = 11.505 -> 11.51
    assert line.shipping_received == Decimal("47.20") # 40.00 * 1.18
    assert line.tds_amount == Decimal("0.65") # 0.1% of 650
    assert line.net_payable == Decimal("662.03") # 650.00 - 23.01 - 11.51 + 47.20 - 0.65 = 662.03
    assert calc.net_payable == Decimal("662.03")


@pytest.mark.asyncio
async def test_fresh_fy_exemption_shields_sales(monkeypatch_config):
    """Below the 5L exemption, prospective strategy deducts NO TDS."""
    item = _item(delivery_type="own_rider", logistics_partner_id=None)
    order = _order()
    dealer = _dealer()
    calc = await calculate_settlement(
        FakeDB(), dealer, [(item, order, None, dealer)],
        fy_summary=_fresh_fy_summary(),
    )

    line = calc.lines[0]
    assert line.tds_exempt_portion == Decimal("560.50")
    assert line.tds_base == Decimal("0.00")
    assert line.tds_amount == Decimal("0.00")
    assert calc.net_payable == Decimal("540.44")  # 560.50 - 29.50 - 11.80 + 21.24


@pytest.mark.asyncio
async def test_threshold_crossing_applies_tds_on_excess(monkeypatch_config):
    """Crossing mid-settlement: exemption only shields the portion below the limit."""
    cfg = _tds_config()
    # cumulative already at 499000, gross of 2000 -> only 1000 is exempt, 1000 taxed
    line1 = resolve_tds_line(cfg, has_pan=True, cumulative_before=Decimal("499000"), gross_sale=Decimal("2000"))
    assert line1["tds_exempt_portion"] == Decimal("1000")
    assert line1["tds_base"] == Decimal("1000")
    assert line1["tds_amount"] == Decimal("1.0")


@pytest.mark.asyncio
async def test_gross_sale_is_net_selling_price_after_discount():
    order = _order(item_price=560.5)
    order.subtotal = 600.0
    order.discount_amount = 39.5  # coupon -> net 560.5
    item = _item(delivery_type="own_rider")
    item.price = 600.0
    gross = compute_gross_sale(item, order)
    assert gross == Decimal("560.50")
