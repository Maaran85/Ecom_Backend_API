import asyncio
import logging
from datetime import date, datetime, timezone

from core.database import SessionLocal
from services.configuration_service import get_settlement_configuration, ensure_default_configurations
from services.settlement_eligibility_service import get_eligible_order_items
from services.settlement_workflow import generate_settlement

logger = logging.getLogger(__name__)

# Run daily at a fixed UTC hour (e.g. 02:30 UTC).
RUN_HOUR = 2
RUN_MINUTE = 30


async def _generate_daily_settlements():
    """
    Automatic daily settlement run: settles every dealer's matured order items.

    Only runs if settlement_configurations.is_daily_auto_enabled is True.
    Idempotent: the eligibility query excludes order items already claimed by a
    non-cancelled settlement, so a re-run won't double-settle.
    """
    try:
        async with SessionLocal() as db:
            await ensure_default_configurations(db)
            await db.commit()

            config = await get_settlement_configuration(db)
            if not config.is_daily_auto_enabled:
                logger.info("Daily settlement auto-run is disabled; skipping.")
                return

            # Find dealers with eligible items (borrow the router's helper logic inline)
            from models import OrderItem as OI, Order as O, Product as P
            from models.cart import OrderStatus
            from sqlalchemy import select

            rows = await db.execute(
                select(P.dealer_id)
                .join(O, O.id == OI.order_id)
                .join(P, P.id == OI.product_id)
                .where(O.status == OrderStatus.DELIVERED, O.delivered_at.isnot(None))
                .distinct()
            )
            dealer_ids = [r[0] for r in rows.all()]

            today = date.today()
            generated = []
            for dealer_id in dealer_ids:
                from models import Dealer
                dealer = await db.get(Dealer, dealer_id)
                if not dealer:
                    continue
                eligible = await get_eligible_order_items(
                    db,
                    dealer_id=dealer_id,
                    as_of=datetime.combine(today, datetime.min.time(), timezone.utc),
                )
                if not eligible:
                    continue
                settlement = await generate_settlement(
                    db, dealer, eligible, settlement_date=today
                )
                generated.append(settlement.id)

            await db.commit()
            if generated:
                logger.info(f"Daily settlement run generated {len(generated)} settlement(s).")
    except Exception as e:
        logger.error(f"Error in daily settlement run: {e}")


async def _seconds_until_daily_run() -> float:
    now = datetime.now(timezone.utc)
    target = now.replace(hour=RUN_HOUR, minute=RUN_MINUTE, second=0, microsecond=0)
    if now >= target:
        target = target.replace(day=now.day + 1)  # next day
    return (target - now).total_seconds()


async def start_settlement_scheduler():
    """Runs the daily settlement generation loop in the background."""
    logger.info("Starting settlement scheduler (daily run at %02d:%02d UTC)...", RUN_HOUR, RUN_MINUTE)
    while True:
        await asyncio.sleep(await _seconds_until_daily_run())
        await _generate_daily_settlements()
