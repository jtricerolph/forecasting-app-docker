"""
Scheduled Booking.com Rate Scraping Job

Priority-based scheduling for 365-day coverage (all queued daily):
- High (priority 10): next 30 days
- Medium (priority 5): days 31-180
- Low (priority 2): days 181-365

Queue processes in priority order. If rate-limited/blocked, lower priority
dates remain queued for the next run.

Uses a queue-based approach:
1. Populate the queue with dates and priorities
2. Process the queue in priority order
3. Failed dates are retried (up to 3 attempts)
4. On blocking, the queue pauses and resumes after cooldown

Schedule: Daily at configurable time (default 05:30)
"""
import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy import text
from database import SyncSessionLocal
from services.booking_scraper import (
    populate_queue,
    process_queue,
    clear_old_queue_items,
    cleanup_stale_batches,
    get_scrape_config,
)

logger = logging.getLogger(__name__)

# Priority levels (higher = processed first)
PRIORITY_HIGH = 10    # 0-30 days
PRIORITY_MEDIUM = 5   # 31-180 days
PRIORITY_LOW = 2      # 181-365 days


def get_high_priority_dates() -> list[date]:
    """High priority: today + 30 days."""
    today = date.today()
    return [today + timedelta(days=i) for i in range(31)]


def get_medium_priority_dates() -> list[date]:
    """Medium priority: days 31-180."""
    today = date.today()
    return [today + timedelta(days=i) for i in range(31, 181)]


def get_low_priority_dates() -> list[date]:
    """Low priority: days 181-365."""
    today = date.today()
    return [today + timedelta(days=i) for i in range(181, 366)]


def compute_next_scrape_for_date(target_date: date) -> tuple[str, date | None]:
    """
    For a target date, determine its priority tier and when it will next be scraped.

    Returns (tier, next_scrape_date) where tier is 'high'/'medium'/'low'/'none'.
    All dates are queued daily, so next scrape is always today (or tomorrow if
    today's run has passed).
    """
    today = date.today()
    offset = (target_date - today).days

    if offset < 0:
        return ('none', None)
    if offset > 365:
        return ('none', None)

    # All tiers run daily - next scrape is today
    if offset <= 30:
        return ('high', today)
    elif offset <= 180:
        return ('medium', today)
    else:
        return ('low', today)


def run_scheduled_booking_scrape():
    """
    Main scheduled job: populate queue with today's dates, then process.
    """
    db = SyncSessionLocal()
    try:
        # Check if scraper is enabled
        result = db.execute(
            text("SELECT config_value FROM system_config WHERE config_key = 'booking_scraper_enabled'")
        ).fetchone()
        if not result or result.config_value != 'true':
            logger.debug("Scheduled booking scrape skipped (disabled)")
            return

        if not get_scrape_config(db):
            logger.warning("Scheduled booking scrape skipped (no location configured)")
            return

        # Clean up stale running batches and old queue items
        cleanup_stale_batches(db, max_age_minutes=60)
        clear_old_queue_items(db, days=3)

        # Gather dates with priorities
        high = get_high_priority_dates()
        medium = get_medium_priority_dates()
        low = get_low_priority_dates()

        priorities = {}
        for d in high:
            priorities[d] = PRIORITY_HIGH
        for d in medium:
            priorities[d] = max(priorities.get(d, 0), PRIORITY_MEDIUM)
        for d in low:
            priorities[d] = max(priorities.get(d, 0), PRIORITY_LOW)

        all_dates = sorted(priorities.keys())

        if not all_dates:
            logger.info("Scheduled booking scrape: no dates to scrape today")
            return

        logger.info(
            f"Scheduled booking scrape: queuing {len(all_dates)} dates "
            f"(high={len(high)}, medium={len(medium)}, low={len(low)})"
        )

        # Populate queue
        populate_queue(db, all_dates, priorities)

        # Process queue
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(process_queue(db))
            if result.get('success'):
                logger.info(
                    f"Scheduled booking scrape completed: "
                    f"{result.get('dates_completed', 0)} dates, "
                    f"{result.get('rates_scraped', 0)} rates"
                )
            elif result.get('blocked'):
                logger.warning(
                    f"Scheduled booking scrape blocked: {result.get('block_reason')}. "
                    f"Completed {result.get('dates_completed', 0)} dates. "
                    f"Remaining dates stay queued for retry."
                )
            else:
                logger.error(f"Scheduled booking scrape failed: {result.get('error')}")
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Scheduled booking scrape error: {e}", exc_info=True)
    finally:
        db.close()


async def run_scheduled_booking_scrape_async():
    """Async wrapper for APScheduler."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_scheduled_booking_scrape)
