import asyncio
import logging
from datetime import date, datetime, timezone, timedelta

from core.database import SessionLocal
from services.configuration_service import get_settlement_configuration, ensure_default_configurations
from services.settlement_eligibility_service import get_eligible_order_items
from services.settlement_workflow import generate_settlement
from services.financial_year_service import IST_TZ

logger = logging.getLogger(__name__)

# Run daily at 18:30 UTC (which is exactly 12:00 AM IST).
RUN_HOUR = 18
RUN_MINUTE = 30


async def _generate_daily_settlements():
    """
    Automatic daily settlement run: settles every dealer's matured order items.

    Only runs if settlement_configurations.is_daily_auto_enabled is True.
    Each dealer is processed in an isolated database transaction to ensure failure isolation.
    """
    try:
        async with SessionLocal() as db:
            await ensure_default_configurations(db)
            await db.commit()

            config = await get_settlement_configuration(db)
            if not config.is_daily_auto_enabled:
                logger.info("Daily settlement auto-run is disabled; skipping.")
                return

            # Find dealers with eligible items
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

        # Calculate target settlement_date and EOD boundary
        current_ist = datetime.now(timezone.utc).astimezone(IST_TZ)
        today_ist = current_ist.date()
        settlement_date = today_ist - timedelta(days=1)

        naive_eod = datetime.combine(settlement_date, datetime.max.time())
        localized_eod = naive_eod.replace(tzinfo=IST_TZ)
        as_of = localized_eod.astimezone(timezone.utc)

        logger.info(f"Starting EOD settlement run for date {settlement_date} (cutoff {as_of} UTC)")

        generated = []
        for dealer_id in dealer_ids:
            try:
                async with SessionLocal() as dealer_db:
                    from models import Dealer, Settlement
                    from core.enums import SettlementStatus

                    # 1. Skip if active settlement already exists for this dealer + settlement_date
                    active_stmt = select(Settlement).where(
                        Settlement.dealer_id == dealer_id,
                        Settlement.settlement_date == settlement_date,
                        Settlement.status != SettlementStatus.CANCELLED
                    )
                    active_res = await dealer_db.execute(active_stmt)
                    if active_res.scalars().first():
                        logger.info(f"Active settlement already exists for dealer {dealer_id} on {settlement_date}. Skipping EOD generation.")
                        continue

                    dealer = await dealer_db.get(Dealer, dealer_id)
                    if not dealer:
                        continue

                    # 2. Query eligible items as of EOD cutoff
                    eligible = await get_eligible_order_items(
                        dealer_db,
                        dealer_id=dealer_id,
                        as_of=as_of,
                    )
                    if not eligible:
                        continue

                    # 3. Generate settlement
                    settlement = await generate_settlement(
                        dealer_db, dealer, eligible, settlement_date=settlement_date
                    )
                    await dealer_db.commit()
                    logger.info(f"EOD settlement generated successfully for dealer {dealer.business_name} (ID: {dealer_id}) on {settlement_date}.")
                    generated.append(settlement.id)
            except Exception as dealer_err:
                logger.error(f"EOD settlement generation failed for dealer {dealer_id} on {settlement_date}: {dealer_err}", exc_info=True)

        if generated:
            logger.info(f"Daily settlement run generated {len(generated)} settlement(s).")
    except Exception as e:
        logger.error(f"Error in daily EOD settlement scheduler: {e}", exc_info=True)


async def _seconds_until_daily_run() -> float:
    now = datetime.now(timezone.utc)
    target = now.replace(hour=RUN_HOUR, minute=RUN_MINUTE, second=0, microsecond=0)
    if now >= target:
        target = target.replace(day=now.day + 1)  # next day
    return (target - now).total_seconds()


async def start_settlement_scheduler():
    """Runs the daily settlement generation loop in the background."""
    logger.info("Starting settlement scheduler (daily EOD run at %02d:%02d UTC / 12:00 AM IST)...", RUN_HOUR, RUN_MINUTE)
    while True:
        await asyncio.sleep(await _seconds_until_daily_run())
        await _generate_daily_settlements()
