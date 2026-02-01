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
from jobs.aggregation import run_aggregation
from jobs.forecast_daily import run_daily_forecast
from jobs.pickup_snapshot import run_pickup_snapshot
from jobs.accuracy_calc import run_accuracy_calculation
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
        logger.info("Running scheduled Newbook bookings sync")
        await sync_newbook_data(triggered_by="scheduler")
    else:
        logger.debug("Scheduled Newbook bookings sync skipped (disabled in settings)")


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

    # Daily forecast (0-28 days) - Daily at 6:00 AM
    # Prophet, XGBoost, and Pickup for operational planning window
    # (TFT excluded - runs weekly due to training time)
    scheduler.add_job(
        lambda: run_daily_forecast(horizon_days=28, models=['prophet', 'xgboost', 'pickup']),
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

    # TFT forecast (0-28 days) - Weekly on Sunday at 3:00 AM
    # TFT is computationally expensive, runs weekly instead of daily
    scheduler.add_job(
        lambda: run_daily_forecast(horizon_days=28, models=['tft']),
        CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="forecast_tft_weekly",
        name="Weekly TFT Forecast (0-28 days)",
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

    scheduler.start()
    logger.info("Scheduler started successfully")


def shutdown_scheduler():
    """Shutdown the scheduler"""
    logger.info("Shutting down scheduler...")
    scheduler.shutdown()
