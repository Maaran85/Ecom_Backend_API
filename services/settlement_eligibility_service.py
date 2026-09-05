from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import OrderItem, Order, Product, Dealer, OrderReturn, DealerRemittance
from models.cart import OrderStatus
from models.order_return import ReturnStatus
from models.settlement import Settlement, SettlementItem
from core.enums import SettlementStatus
from services.configuration_service import get_settlement_configuration
from services.financial_year_service import IST_TZ

# Return statuses that make an item unavailable for settlement.
# REJECTED / PICKUP_FAILED mean no return actually happened.
RETURN_INELIGIBLE_STATUSES = [
    ReturnStatus.REQUESTED, ReturnStatus.APPROVED, ReturnStatus.OUT_FOR_PICKUP,
    ReturnStatus.OUT_FOR_SWAP, ReturnStatus.PICKED_UP, ReturnStatus.RETURN_PICKUP_PROCESSING,
    ReturnStatus.RETURN_PICKUP_STARTED, ReturnStatus.RETURN_PICKUP_COMPLETED,
    ReturnStatus.SWAP_COMPLETED, ReturnStatus.EXCHANGE_COMPLETED,
    ReturnStatus.COMPLETED, ReturnStatus.REFUNDED,
]


async def _claimed_item_ids_query():
    """Order items already attached to an active, non-cancelled settlement."""
    return (
        select(SettlementItem.order_item_id)
        .join(Settlement, Settlement.id == SettlementItem.settlement_id)
        .where(
            SettlementItem.order_item_id.isnot(None),
            SettlementItem.is_cancelled == False,
            Settlement.status != SettlementStatus.CANCELLED,
        )
    )


async def _permanently_settled_item_ids_query():
    """Order items attached to a PAID settlement or completed remittance (defense-in-depth)."""
    return (
        select(SettlementItem.order_item_id)
        .join(Settlement, Settlement.id == SettlementItem.settlement_id)
        .outerjoin(DealerRemittance, DealerRemittance.id == Settlement.remittance_id)
        .where(
            SettlementItem.order_item_id.isnot(None),
            or_(
                Settlement.status == SettlementStatus.PAID,
                DealerRemittance.status == "completed",
                Settlement.paid_at.isnot(None),
            ),
        )
    )


def _extract_item_date(item: OrderItem, order: Order, date_basis: str = "order_date") -> Optional[date]:
    """Extract date based on date_basis ('order_date' or 'delivery_date')."""
    if date_basis == "delivery_date":
        dt = item.delivered_at or order.delivered_at or order.created_at
    else:
        dt = order.created_at or item.delivered_at or order.delivered_at
    if dt is None:
        return None
    if hasattr(dt, 'date'):
        return dt.date()
    return dt


async def get_eligible_order_items(
    db: AsyncSession,
    dealer_id: Optional[UUID] = None,
    as_of: Optional[datetime] = None,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    date_basis: str = "order_date",
    for_update: bool = False,
) -> List[Tuple[OrderItem, Order, Product, Dealer]]:
    """
    Returns (OrderItem, Order, Product, Dealer) tuples for order items eligible
    to enter a settlement as of `as_of`:

      - order delivered and return window (settlement_configurations.return_window_days) has matured
      - item not returned / not part of an active return
      - item not already claimed by a non-cancelled settlement or paid settlement
      - item falls within [period_start, period_end] if specified
    """
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)

    config = await get_settlement_configuration(db)

    claimed = await _claimed_item_ids_query()
    permanently_settled = await _permanently_settled_item_ids_query()

    # Items with a live return (not rejected/pickup-failed)
    returned_item_ids = (
        select(OrderReturn.order_item_id)
        .where(
            OrderReturn.order_item_id.isnot(None),
            OrderReturn.status.in_(RETURN_INELIGIBLE_STATUSES),
        )
    )

    query = (
        select(OrderItem, Order, Product, Dealer)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .join(Dealer, Dealer.id == Product.dealer_id)
        .where(
            Order.status == OrderStatus.DELIVERED,
            Order.delivered_at.isnot(None),
            OrderItem.status == OrderStatus.DELIVERED.value,
            OrderItem.id.not_in(claimed),
            OrderItem.id.not_in(permanently_settled),
            OrderItem.id.not_in(returned_item_ids),
        )
    )
    if dealer_id is not None:
        query = query.where(Dealer.id == dealer_id)

    query = query.order_by(Order.delivered_at.asc())

    if for_update:
        query = query.with_for_update(of=OrderItem)

    result = await db.execute(query)
    rows = result.all()

    from services.return_policy_service import is_item_settlement_matured

    eligible_tuples = []
    for item, order, product, dealer in rows:
        deliv_dt = item.delivered_at or order.delivered_at
        if not deliv_dt:
            continue
        if not is_item_settlement_matured(
            item=item,
            delivered_at=deliv_dt,
            as_of=as_of,
            product=product,
            global_config=config,
        ):
            continue

        # Period boundary filtering (billing cycle)
        if period_start or period_end:
            item_dt = _extract_item_date(item, order, date_basis)
            if item_dt:
                if period_start and item_dt < period_start:
                    continue
                if period_end and item_dt > period_end:
                    continue

        eligible_tuples.append((item, order, product, dealer))

    return eligible_tuples


async def is_delivery_self_logistics(item: OrderItem) -> bool:
    """True when the dealer handled logistics itself (keeps the customer shipping charge)."""
    if item.logistics_partner_id is not None:
        return False
    delivery_type = (item.delivery_type or "").strip().lower()
    if delivery_type == "logistics":
        return False
    return True
