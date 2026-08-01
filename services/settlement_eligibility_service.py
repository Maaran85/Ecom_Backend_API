from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import OrderItem, Order, Product, Dealer, OrderReturn
from models.cart import OrderStatus
from models.order_return import ReturnStatus
from models.settlement import Settlement, SettlementItem
from core.enums import SettlementStatus
from services.configuration_service import get_settlement_configuration

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
    """Order items already attached to a non-cancelled settlement."""
    return (
        select(SettlementItem.order_item_id)
        .join(Settlement, Settlement.id == SettlementItem.settlement_id)
        .where(
            SettlementItem.order_item_id.isnot(None),
            Settlement.status != SettlementStatus.CANCELLED,
        )
    )


async def get_eligible_order_items(
    db: AsyncSession,
    dealer_id: Optional[UUID] = None,
    as_of: Optional[datetime] = None,
) -> List[Tuple[OrderItem, Order, Product, Dealer]]:
    """
    Returns (OrderItem, Order, Product, Dealer) tuples for order items eligible
    to enter a settlement as of `as_of`:

      - order delivered and return window (settlement_configurations.return_window_days) has matured
      - item not returned / not part of an active return
      - item not already claimed by a non-cancelled settlement
    """
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)

    config = await get_settlement_configuration(db)
    window = config.return_window_days
    matured_before = as_of - timedelta(days=window)

    claimed = await _claimed_item_ids_query()

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
            Order.delivered_at <= matured_before,
            OrderItem.status == OrderStatus.DELIVERED.value,
            OrderItem.id.not_in(claimed),
            OrderItem.id.not_in(returned_item_ids),
        )
    )
    if dealer_id is not None:
        query = query.where(Dealer.id == dealer_id)

    query = query.order_by(Order.delivered_at.asc())

    result = await db.execute(query)
    return result.all()


async def is_delivery_self_logistics(item: OrderItem) -> bool:
    """True when the dealer handled logistics itself (keeps the customer shipping charge)."""
    if item.logistics_partner_id is not None:
        return False
    delivery_type = (item.delivery_type or "").strip().lower()
    if delivery_type == "logistics":
        return False
    return True
