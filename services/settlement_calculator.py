from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Tuple, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from models import OrderItem, Order, Product, Dealer
from core.money import money, money_2dp
from services.fee_service import compute_gross_sale, compute_item_fees
from services.tds_resolver import resolve_tds_batch
from services.configuration_service import get_active_tds_config_required
from services.financial_year_service import DealerFinancialYearSummary


@dataclass
class SettlementLineResult:
    item: OrderItem
    order: Order
    gross_sale: Decimal
    marketplace_fee: Decimal
    marketing_fee: Decimal
    shipping_received: Decimal
    logistics_charge: Decimal
    gst_on_fees: Decimal
    tds_rate: Decimal
    tds_exempt_portion: Decimal
    tds_base: Decimal
    tds_amount: Decimal
    net_payable: Decimal
    delivery_type: Optional[str] = None
    precise: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SettlementCalculationResult:
    dealer: Dealer
    lines: List[SettlementLineResult]
    tds_rate: Decimal
    has_pan: bool
    organization_type: Optional[str]
    gross_sale_total: Decimal
    marketplace_fee_total: Decimal
    marketing_fee_total: Decimal
    shipping_received_total: Decimal
    logistics_charge_total: Decimal
    gst_on_fees_total: Decimal
    tds_exempt_total: Decimal
    tds_base_total: Decimal
    tds_total: Decimal
    adjustment_total: Decimal = Decimal("0")
    net_payable: Decimal = Decimal("0")
    precise: Dict[str, Any] = field(default_factory=dict)

    def finalize(self, adjustment_total: Decimal = Decimal("0")):
        self.adjustment_total = money(adjustment_total)
        raw_net = (
            self.gross_sale_total
            - self.marketplace_fee_total
            - self.marketing_fee_total
            + self.shipping_received_total
            - self.logistics_charge_total
            + self.adjustment_total
            - self.tds_total
        )
        self.net_payable = money_2dp(raw_net)
        return self


async def calculate_settlement(
    db: AsyncSession,
    dealer: Dealer,
    eligible_items: List[Tuple[OrderItem, Order, Product, Dealer]],
    fy_summary: Optional[DealerFinancialYearSummary] = None,
    adjustment_total: Decimal = Decimal("0"),
) -> SettlementCalculationResult:
    """
    Runs the full settlement math for one dealer across eligible order items.

    Formula per item (Excel 'billing' sheet):
      gross_sale = net selling price (GST-inclusive) after discount
      net = gross_sale - marketplace_fee - marketing_fee
            + shipping_received (self-logistics) - logistics_charge (partner)
            - tds
    TDS base = gross_sale + shipping_received (self-logistics reimbursement added to TDS base).
    """
    config = await get_active_tds_config_required(db, dealer.organization_type)
    has_pan = bool(getattr(dealer, "pan_number", None))

    cumulative_before = money(fy_summary.cumulative_gross_sale) if fy_summary else Decimal("0")

    lines: List[SettlementLineResult] = []
    tds_bases: List[Decimal] = []

    # Pass 1: compute gross sales + fees (fee resolution has no cross-line dependency)
    for item, order, product, _ in eligible_items:
        gross_sale = compute_gross_sale(item, order)
        fees = await compute_item_fees(db, item, order, gross_sale)
        line_tds_base = gross_sale + fees["shipping_received"]
        tds_bases.append(line_tds_base)
        lines.append((item, order, gross_sale, fees))

    # Pass 2: resolve TDS across all lines (cumulative exemption consumption)
    tds_batch = resolve_tds_batch(config, has_pan, cumulative_before, tds_bases)

    # Pass 3: build results
    result_lines: List[SettlementLineResult] = []
    for idx, (item, order, gross_sale, fees) in enumerate(lines):
        tds = tds_batch["items"][idx]
        
        gross_sale_2dp = money_2dp(gross_sale)
        mp_fee_2dp = money_2dp(fees["marketplace_fee"])
        mkt_fee_2dp = money_2dp(fees["marketing_fee"])
        ship_rec_2dp = money_2dp(fees["shipping_received"])
        log_chg_2dp = money_2dp(fees["logistics_charge"])
        tds_amt_2dp = money_2dp(tds["tds_amount"])

        raw_net = (
            gross_sale_2dp
            - mp_fee_2dp
            - mkt_fee_2dp
            + ship_rec_2dp
            - log_chg_2dp
            - tds_amt_2dp
        )
        net_payable_2dp = money_2dp(raw_net)

        result_lines.append(
            SettlementLineResult(
                item=item,
                order=order,
                gross_sale=gross_sale_2dp,
                marketplace_fee=mp_fee_2dp,
                marketing_fee=mkt_fee_2dp,
                shipping_received=ship_rec_2dp,
                logistics_charge=log_chg_2dp,
                gst_on_fees=money_2dp(fees["gst_on_fees"]),
                tds_rate=tds["rate"],
                tds_exempt_portion=money_2dp(tds["tds_exempt_portion"]),
                tds_base=money_2dp(tds["tds_base"]),
                tds_amount=tds_amt_2dp,
                net_payable=net_payable_2dp,
                delivery_type=fees["delivery_type"],
                precise={
                    "gross_sale": str(gross_sale_2dp),
                    "marketplace_fee": str(mp_fee_2dp),
                    "marketing_fee": str(mkt_fee_2dp),
                    "shipping_received": str(ship_rec_2dp),
                    "logistics_charge": str(log_chg_2dp),
                    "gst_on_fees": str(money_2dp(fees["gst_on_fees"])),
                    "tds_exempt_portion": str(money_2dp(tds["tds_exempt_portion"])),
                    "tds_base": str(money_2dp(tds["tds_base"])),
                    "tds_rate": str(tds["rate"]),
                    "tds_amount": str(tds_amt_2dp),
                    "net_raw": str(raw_net),
                    "net_rounded": str(net_payable_2dp),
                },
            )
        )

    result = SettlementCalculationResult(
        dealer=dealer,
        lines=result_lines,
        tds_rate=result_lines[0].tds_rate if result_lines else Decimal("0"),
        has_pan=has_pan,
        organization_type=dealer.organization_type,
        gross_sale_total=money_2dp(sum((l.gross_sale for l in result_lines), Decimal("0"))),
        marketplace_fee_total=money_2dp(sum((l.marketplace_fee for l in result_lines), Decimal("0"))),
        marketing_fee_total=money_2dp(sum((l.marketing_fee for l in result_lines), Decimal("0"))),
        shipping_received_total=money_2dp(sum((l.shipping_received for l in result_lines), Decimal("0"))),
        logistics_charge_total=money_2dp(sum((l.logistics_charge for l in result_lines), Decimal("0"))),
        gst_on_fees_total=money_2dp(sum((l.gst_on_fees for l in result_lines), Decimal("0"))),
        tds_exempt_total=money_2dp(tds_batch["total_exempt"]),
        tds_base_total=money_2dp(tds_batch["total_base"]),
        tds_total=money_2dp(sum((l.tds_amount for l in result_lines), Decimal("0"))),
    )
    result.finalize(adjustment_total)

    result.precise = {
        "gross_sale_total": str(result.gross_sale_total),
        "marketplace_fee_total": str(result.marketplace_fee_total),
        "marketing_fee_total": str(result.marketing_fee_total),
        "shipping_received_total": str(result.shipping_received_total),
        "logistics_charge_total": str(result.logistics_charge_total),
        "gst_on_fees_total": str(result.gst_on_fees_total),
        "tds_exempt_total": str(result.tds_exempt_total),
        "tds_base_total": str(result.tds_base_total),
        "tds_total": str(result.tds_total),
        "net_raw": str(
            result.gross_sale_total
            - result.marketplace_fee_total
            - result.marketing_fee_total
            + result.shipping_received_total
            - result.logistics_charge_total
            + result.adjustment_total
            - result.tds_total
        ),
        "net_rounded": str(result.net_payable),
    }

    return result
