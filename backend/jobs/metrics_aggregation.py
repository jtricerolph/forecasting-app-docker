"""
Metrics aggregation job for forecast_data database
Populates daily_metrics from newbook_bookings_stats

This is the data source for forecasting models (Prophet, XGBoost, TFT).
"""
import logging
from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import text
from database import SyncSessionLocal

logger = logging.getLogger(__name__)


async def run_metrics_aggregation(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None
):
    """
    Populate daily_metrics table from newbook_bookings_stats.

    This provides the historical actuals needed for forecasting models.

    Args:
        from_date: Start date (defaults to 2 years ago)
        to_date: End date (defaults to yesterday)
    """
    logger.info("Starting metrics aggregation job")

    db = next(iter([SyncSessionLocal()]))

    try:
        # Default date range: 2 years of history
        if from_date is None:
            from_date = date.today() - timedelta(days=730)
        if to_date is None:
            to_date = date.today() - timedelta(days=1)

        logger.info(f"Aggregating metrics from {from_date} to {to_date}")

        # Get data from newbook_bookings_stats
        result = db.execute(
            text("""
            SELECT
                date,
                booking_count,           -- room nights (occupied rooms)
                total_occupancy_pct,     -- occupancy percentage
                guests_count,            -- total guests
                adults_count,
                children_count,
                rooms_count,             -- available rooms
                bookable_count           -- bookable rooms (rooms - maintenance)
            FROM newbook_bookings_stats
            WHERE date BETWEEN :from_date AND :to_date
            ORDER BY date
            """),
            {"from_date": from_date, "to_date": to_date}
        )
        stats_rows = result.fetchall()

        if not stats_rows:
            logger.warning("No data found in newbook_bookings_stats")
            return

        logger.info(f"Found {len(stats_rows)} days of data to aggregate")

        # Metrics to populate
        metrics_count = 0

        for row in stats_rows:
            d = row.date

            # Define metrics from newbook_bookings_stats
            metrics_to_insert = []

            # Room nights (occupied rooms)
            if row.booking_count is not None:
                metrics_to_insert.append(("hotel_room_nights", row.booking_count))

            # Occupancy percentage
            if row.total_occupancy_pct is not None:
                metrics_to_insert.append(("hotel_occupancy_pct", float(row.total_occupancy_pct)))

            # Guest count
            if row.guests_count is not None:
                metrics_to_insert.append(("hotel_guests", row.guests_count))

            # Insert/update all metrics
            for metric_code, actual_value in metrics_to_insert:
                db.execute(
                    text("""
                    INSERT INTO daily_metrics (date, metric_code, actual_value, source, updated_at)
                    VALUES (:date, :metric_code, :actual_value, 'newbook', NOW())
                    ON CONFLICT (date, metric_code) DO UPDATE SET
                        actual_value = :actual_value,
                        updated_at = NOW()
                    """),
                    {
                        "date": d,
                        "metric_code": metric_code,
                        "actual_value": actual_value
                    }
                )
                metrics_count += 1

        db.commit()
        logger.info(f"Aggregated {metrics_count} metric records from {len(stats_rows)} days")

    except Exception as e:
        logger.error(f"Metrics aggregation failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


async def backfill_daily_metrics():
    """
    Backfill all available history from newbook_bookings_stats to daily_metrics.
    Call this once when setting up forecasting on forecast_data database.
    """
    logger.info("Starting full backfill of daily_metrics")

    db = next(iter([SyncSessionLocal()]))

    try:
        # Find the earliest date in newbook_bookings_stats
        result = db.execute(text("SELECT MIN(date) as min_date FROM newbook_bookings_stats"))
        row = result.fetchone()

        if not row or not row.min_date:
            logger.warning("No data in newbook_bookings_stats to backfill")
            return

        from_date = row.min_date
        to_date = date.today() - timedelta(days=1)

        logger.info(f"Backfilling from {from_date} to {to_date}")

        await run_metrics_aggregation(from_date=from_date, to_date=to_date)

        logger.info("Backfill completed successfully")

    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        raise
    finally:
        db.close()
