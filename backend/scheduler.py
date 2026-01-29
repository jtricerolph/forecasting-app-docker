"""
APScheduler configuration for scheduled jobs
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from jobs.data_sync import run_data_sync
from jobs.forecast_daily import run_daily_forecast
from jobs.pickup_snapshot import run_pickup_snapshot
from jobs.accuracy_calc import run_accuracy_calculation

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler():
    """Initialize and start the scheduler"""
    logger.info("Starting scheduler...")

    # Data sync - Daily at 5:00 AM
    scheduler.add_job(
        run_data_sync,
        CronTrigger(hour=5, minute=0),
        id="data_sync",
        name="Daily Data Sync",
        replace_existing=True
    )

    # Pickup snapshot - Daily at 5:30 AM
    scheduler.add_job(
        run_pickup_snapshot,
        CronTrigger(hour=5, minute=30),
        id="pickup_snapshot",
        name="Daily Pickup Snapshot",
        replace_existing=True
    )

    # Short-term forecast (0-14 days) - Daily at 6:00 AM
    scheduler.add_job(
        lambda: run_daily_forecast(horizon_days=14),
        CronTrigger(hour=6, minute=0),
        id="forecast_short_term",
        name="Short-term Forecast",
        replace_existing=True
    )

    # Medium-term forecast (15-28 days) - Daily at 6:15 AM
    scheduler.add_job(
        lambda: run_daily_forecast(horizon_days=28, start_days=15),
        CronTrigger(hour=6, minute=15),
        id="forecast_medium_term",
        name="Medium-term Forecast",
        replace_existing=True
    )

    # Long-term forecast (29-60 days) - Weekly on Monday at 6:30 AM
    scheduler.add_job(
        lambda: run_daily_forecast(horizon_days=60, start_days=29, models=['prophet', 'xgboost']),
        CronTrigger(day_of_week="mon", hour=6, minute=30),
        id="forecast_long_term",
        name="Long-term Forecast",
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
