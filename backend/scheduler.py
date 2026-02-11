"""
APScheduler configuration for scheduled jobs
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from jobs.data_sync import (
    sync_newbook_data,
    sync_resos_data,
    sync_newbook_occupancy_report,
    sync_newbook_earned_revenue
)
from jobs.resos_bookings_sync import sync_resos_bookings_data
from api.sync_bookings import run_bookings_data_sync
from jobs.aggregation import run_aggregation
from jobs.forecast_daily import run_daily_forecast
from jobs.pickup_snapshot import run_pickup_snapshot
from jobs.pace_snapshot_v2 import run_pace_snapshot_v2
from jobs.accuracy_calc import run_accuracy_calculation
from jobs.weekly_forecast_snapshot import run_weekly_forecast_snapshot
from jobs.fetch_current_rates import run_fetch_current_rates
from jobs.scrape_booking_rates import run_scheduled_booking_scrape_async
from database import SyncSessionLocal

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def get_config_value(key: str, default: str = None) -> str:
    """Get a config value from system_config"""
    db = SyncSessionLocal()
    try:
        result = db.execute(
            text("SELECT config_value FROM system_config WHERE config_key = :key"),
            {"key": key}
        )
        row = result.fetchone()
        if row and row.config_value:
            return row.config_value
        return default
    except Exception as e:
        logger.error(f"Error getting config {key}: {e}")
        return default
    finally:
        db.close()


def is_sync_enabled(source: str) -> bool:
    """Check if a sync source is enabled in config"""
    value = get_config_value(f"sync_{source}_enabled")
    if value:
        return value.lower() in ('true', '1', 'yes', 'enabled')
    return False


def get_sync_time(source: str, default_hour: int = 5, default_minute: int = 0) -> tuple:
    """Get sync time for a source, returns (hour, minute) tuple"""
    time_str = get_config_value(f"sync_{source}_time")
    if time_str:
        try:
            parts = time_str.split(':')
            return (int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            logger.warning(f"Invalid time format for {source}: {time_str}, using default")
    return (default_hour, default_minute)


async def run_scheduled_newbook_sync():
    """Wrapper to check if Newbook bookings sync is enabled before running"""
    if is_sync_enabled("newbook_bookings"):
        # Get sync type from config (incremental or full)
        sync_type = get_config_value("sync_newbook_bookings_type", "incremental")
        logger.info(f"Running scheduled Newbook bookings sync (mode={sync_type})")
        # Run synchronous function in thread pool to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            run_bookings_data_sync,
            sync_type,  # sync_mode
            None,       # from_date
            None,       # to_date
            "scheduler" # triggered_by
        )
    else:
        logger.debug("Scheduled Newbook bookings sync skipped (disabled in settings)")


async def run_scheduled_resos_bookings_sync():
    """Wrapper to check if Resos bookings sync is enabled before running"""
    from datetime import date, timedelta
    if is_sync_enabled("resos_bookings"):
        logger.info("Running scheduled Resos bookings sync")
        # Daily: -7 days to +365 days (recent history + forecast window)
        from_date = date.today() - timedelta(days=7)
        to_date = date.today() + timedelta(days=365)
        await sync_resos_bookings_data(from_date, to_date, triggered_by="scheduler")
    else:
        logger.info("Scheduled Resos bookings sync skipped (disabled in settings)")


async def run_scheduled_resos_sync():
    """Wrapper to check if Resos sync is enabled before running"""
    if is_sync_enabled("resos"):
        logger.info("Running scheduled Resos sync")
        await sync_resos_data(triggered_by="scheduler")
    else:
        logger.info("Scheduled Resos sync skipped (disabled in settings)")


async def run_scheduled_occupancy_report_sync():
    """Wrapper to run occupancy report sync (uses dedicated occupancy enabled flag)"""
    from datetime import date, timedelta
    if is_sync_enabled("newbook_occupancy"):
        logger.info("Running scheduled Newbook occupancy report sync")
        # Daily: -7 days to +365 days
        from_date = date.today() - timedelta(days=7)
        to_date = date.today() + timedelta(days=365)
        await sync_newbook_occupancy_report(from_date, to_date, triggered_by="scheduler")
    else:
        logger.info("Scheduled Newbook occupancy report sync skipped (disabled in settings)")


async def run_scheduled_earned_revenue_sync():
    """Wrapper to run earned revenue sync (uses dedicated enabled flag)"""
    from datetime import date, timedelta
    if is_sync_enabled("newbook_earned_revenue"):
        logger.info("Running scheduled Newbook earned revenue sync")
        # Daily: last 7 days only (historical data, catches adjustments)
        from_date = date.today() - timedelta(days=7)
        to_date = date.today()
        await sync_newbook_earned_revenue(from_date, to_date, triggered_by="scheduler")
    else:
        logger.info("Scheduled Newbook earned revenue sync skipped (disabled in settings)")


async def run_scheduled_current_rates_sync():
    """Wrapper to run current rates sync (for pickup-v2 upper bounds)"""
    if is_sync_enabled("newbook_current_rates"):
        logger.info("Running scheduled Newbook current rates sync")
        await run_fetch_current_rates()
    else:
        logger.debug("Scheduled Newbook current rates sync skipped (disabled in settings)")


def reschedule_sync_jobs():
    """
    Read sync times from config and reschedule sync jobs.
    Called at startup and daily at 1am to pick up config changes.
    """
    logger.info("Rescheduling sync jobs from config...")

    # Newbook bookings sync
    nb_hour, nb_min = get_sync_time("newbook_bookings", 5, 0)
    scheduler.add_job(
        run_scheduled_newbook_sync,
        CronTrigger(hour=nb_hour, minute=nb_min),
        id="newbook_sync",
        name=f"Daily Newbook Bookings Sync ({nb_hour:02d}:{nb_min:02d})",
        replace_existing=True
    )
    logger.info(f"  Newbook bookings sync scheduled for {nb_hour:02d}:{nb_min:02d}")

    # Resos bookings sync
    rsb_hour, rsb_min = get_sync_time("resos_bookings", 5, 5)
    scheduler.add_job(
        run_scheduled_resos_bookings_sync,
        CronTrigger(hour=rsb_hour, minute=rsb_min),
        id="resos_bookings_sync",
        name=f"Daily Resos Bookings Sync ({rsb_hour:02d}:{rsb_min:02d})",
        replace_existing=True
    )
    logger.info(f"  Resos bookings sync scheduled for {rsb_hour:02d}:{rsb_min:02d}")

    # Resos sync - uses general sync_schedule_time for now
    rs_time = get_config_value("sync_schedule_time", "05:05")
    try:
        rs_hour, rs_min = int(rs_time.split(':')[0]), int(rs_time.split(':')[1])
    except:
        rs_hour, rs_min = 5, 5
    scheduler.add_job(
        run_scheduled_resos_sync,
        CronTrigger(hour=rs_hour, minute=rs_min),
        id="resos_sync",
        name=f"Daily Resos Sync ({rs_hour:02d}:{rs_min:02d})",
        replace_existing=True
    )
    logger.info(f"  Resos sync scheduled for {rs_hour:02d}:{rs_min:02d}")

    # Newbook occupancy report
    occ_hour, occ_min = get_sync_time("newbook_occupancy", 5, 8)
    scheduler.add_job(
        run_scheduled_occupancy_report_sync,
        CronTrigger(hour=occ_hour, minute=occ_min),
        id="newbook_occupancy_report",
        name=f"Daily Newbook Occupancy Report ({occ_hour:02d}:{occ_min:02d})",
        replace_existing=True
    )
    logger.info(f"  Newbook occupancy report scheduled for {occ_hour:02d}:{occ_min:02d}")

    # Newbook earned revenue
    rev_hour, rev_min = get_sync_time("newbook_earned_revenue", 5, 10)
    scheduler.add_job(
        run_scheduled_earned_revenue_sync,
        CronTrigger(hour=rev_hour, minute=rev_min),
        id="newbook_earned_revenue",
        name=f"Daily Newbook Earned Revenue ({rev_hour:02d}:{rev_min:02d})",
        replace_existing=True
    )
    logger.info(f"  Newbook earned revenue scheduled for {rev_hour:02d}:{rev_min:02d}")

    # Aggregation - 15 mins after the latest sync job
    latest_sync = max(nb_hour * 60 + nb_min, occ_hour * 60 + occ_min, rev_hour * 60 + rev_min)
    agg_mins = latest_sync + 15
    agg_hour, agg_min = agg_mins // 60, agg_mins % 60
    scheduler.add_job(
        run_aggregation,
        CronTrigger(hour=agg_hour, minute=agg_min),
        id="aggregation",
        name=f"Daily Aggregation ({agg_hour:02d}:{agg_min:02d})",
        replace_existing=True
    )
    logger.info(f"  Aggregation scheduled for {agg_hour:02d}:{agg_min:02d}")

    logger.info("Sync jobs rescheduled successfully")


def start_scheduler():
    """Initialize and start the scheduler"""
    logger.info("Starting scheduler...")

    # 1am daily: reschedule sync jobs from config
    # This picks up any config changes made during the day
    scheduler.add_job(
        reschedule_sync_jobs,
        CronTrigger(hour=1, minute=0),
        id="reschedule_sync_jobs",
        name="Daily Reschedule Sync Jobs (01:00)",
        replace_existing=True
    )

    # Schedule sync jobs from config (initial schedule)
    reschedule_sync_jobs()

    # Pickup snapshot - Daily at 5:30 AM
    scheduler.add_job(
        run_pickup_snapshot,
        CronTrigger(hour=5, minute=30),
        id="pickup_snapshot",
        name="Daily Pickup Snapshot",
        replace_existing=True
    )

    # Pace snapshot v2 - Daily at 5:32 AM
    # Captures revenue pace for pickup-v2 model
    scheduler.add_job(
        run_pace_snapshot_v2,
        CronTrigger(hour=5, minute=32),
        id="pace_snapshot_v2",
        name="Daily Pace Snapshot V2",
        replace_existing=True
    )

    # Fetch current rates from Newbook - Daily at 5:20 AM
    # Populates newbook_current_rates for pickup-v2 upper bound calculations
    scheduler.add_job(
        run_scheduled_current_rates_sync,
        CronTrigger(hour=5, minute=20),
        id="fetch_current_rates",
        name="Daily Fetch Current Rates",
        replace_existing=True
    )

    # Booking.com rate scraper - Daily at configured time (default 05:30)
    # Tiered: daily 30d, weekly 31-180d (Mon-Fri), biweekly 181-365d (Wed)
    booking_time = get_config_value("booking_scraper_daily_time", "05:30")
    try:
        bk_hour, bk_min = int(booking_time.split(':')[0]), int(booking_time.split(':')[1])
    except (ValueError, IndexError):
        bk_hour, bk_min = 5, 30
    scheduler.add_job(
        run_scheduled_booking_scrape_async,
        CronTrigger(hour=bk_hour, minute=bk_min),
        id="booking_scrape",
        name=f"Daily Booking.com Scrape ({bk_hour:02d}:{bk_min:02d})",
        replace_existing=True
    )
    logger.info(f"  Booking.com scrape scheduled for {bk_hour:02d}:{bk_min:02d}")

    # Daily forecast (0-28 days) - Daily at 6:00 AM
    # Prophet, XGBoost, Pickup, and CatBoost for operational planning window
    scheduler.add_job(
        lambda: run_daily_forecast(horizon_days=28, models=['prophet', 'xgboost', 'pickup', 'catboost']),
        CronTrigger(hour=6, minute=0),
        id="forecast_daily",
        name="Daily Forecast (0-28 days)",
        replace_existing=True
    )

    # Long-term forecast (29-365 days) - Weekly on Monday at 6:30 AM
    # Prophet and XGBoost only (pickup less useful at long range)
    scheduler.add_job(
        lambda: run_daily_forecast(horizon_days=365, start_days=29, models=['prophet', 'xgboost']),
        CronTrigger(day_of_week="mon", hour=6, minute=30),
        id="forecast_weekly",
        name="Weekly Forecast (29-365 days)",
        replace_existing=True
    )

    # Accuracy calculation - Daily at 7:00 AM
    scheduler.add_job(
        run_accuracy_calculation,
        CronTrigger(hour=7, minute=0),
        id="accuracy_calc",
        name="Daily Accuracy Calculation",
        replace_existing=True
    )

    # Weekly forecast snapshot - Monday at 6:00 AM (default)
    # Get time from config (default: Monday 6:00 AM)
    snapshot_time = get_config_value("forecast_snapshot_time", "06:00")
    try:
        snapshot_hour, snapshot_min = int(snapshot_time.split(':')[0]), int(snapshot_time.split(':')[1])
    except:
        snapshot_hour, snapshot_min = 6, 0

    scheduler.add_job(
        run_weekly_forecast_snapshot,
        CronTrigger(day_of_week="mon", hour=snapshot_hour, minute=snapshot_min),
        id="weekly_forecast_snapshot",
        name=f"Weekly Forecast Snapshot (Mon {snapshot_hour:02d}:{snapshot_min:02d})",
        replace_existing=True
    )

    scheduler.start()
    logger.info("Scheduler started successfully")


def shutdown_scheduler():
    """Shutdown the scheduler"""
    logger.info("Shutting down scheduler...")
    scheduler.shutdown()
