import asyncio
import logging
from datetime import datetime, timezone, timedelta

from core.database import SessionLocal
from services.reward_service import run_daily_reward_maturity_evaluation
from services.financial_year_service import IST_TZ

logger = logging.getLogger(__name__)

# Run daily at 18:35 UTC (12:05 AM IST) — right after settlements run
RUN_HOUR = 18
RUN_MINUTE = 35


async def _run_daily_rewards():
    """Executes the daily reward maturation check across all eligible delivered orders."""
    try:
        async with SessionLocal() as db:
            logger.info("Starting daily EOD reward maturation job...")
            result = await run_daily_reward_maturity_evaluation(db)
            logger.info(f"Completed daily EOD reward maturation job: {result}")
    except Exception as e:
        logger.error(f"Error during daily EOD reward maturation run: {e}", exc_info=True)


async def start_reward_scheduler():
    """
    Background loop that runs daily at RUN_HOUR:RUN_MINUTE UTC (12:05 AM IST).
    """
    logger.info("Starting reward scheduler (daily EOD run at %02d:%02d UTC / 12:05 AM IST)...", RUN_HOUR, RUN_MINUTE)
    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            target = now_utc.replace(hour=RUN_HOUR, minute=RUN_MINUTE, second=0, microsecond=0)
            if target <= now_utc:
                target += timedelta(days=1)
            wait_seconds = (target - now_utc).total_seconds()
            logger.info("Next daily reward maturation run scheduled at %s UTC (in %.1f hours)", target, wait_seconds / 3600)
            await asyncio.sleep(wait_seconds)
            await _run_daily_rewards()
        except asyncio.CancelledError:
            logger.info("Reward scheduler task cancelled.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in reward scheduler loop: {e}", exc_info=True)
            await asyncio.sleep(60)
