"""
Revenue aggregation - consolidates earned revenue by department
"""
import logging
from datetime import datetime
from sqlalchemy import text
from database import SyncSessionLocal

logger = logging.getLogger(__name__)


def get_config_value(db, key: str) -> str | None:
    """Get a config value from system_config"""
    result = db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = :key"),
        {"key": key}
    )
    row = result.fetchone()
    return row.config_value if row else None


def set_config_value(db, key: str, value: str):
    """Set a config value in system_config"""
    db.execute(
        text("""
            INSERT INTO system_config (config_key, config_value, updated_at)
            VALUES (:key, :value, NOW())
            ON CONFLICT (config_key) DO UPDATE SET
                config_value = :value,
                updated_at = NOW()
        """),
        {"key": key, "value": value}
    )


async def aggregate_revenue(since_timestamp: str = None):
    """
    Aggregate earned revenue data by department into newbook_net_revenue_data.

    - Joins newbook_earned_revenue_data with newbook_gl_accounts to get department
    - Sums net amounts by date and department
    - Only processes dates with data fetched since last aggregation (or all if first run)

    Args:
        since_timestamp: Optional timestamp to process data from (ISO format)
                        If not provided, uses last_revenue_aggregation_at config
    """
    logger.info("Starting revenue aggregation...")

    db = SyncSessionLocal()
    try:
        # Get last aggregation time if not provided
        if since_timestamp is None:
            since_timestamp = get_config_value(db, 'last_revenue_aggregation_at')

        # Find dates with new/updated data
        if since_timestamp:
            logger.info(f"Aggregating revenue data updated since {since_timestamp}")
            result = db.execute(
                text("""
                    SELECT DISTINCT date
                    FROM newbook_earned_revenue_data
                    WHERE fetched_at > :since
                    ORDER BY date
                """),
                {"since": since_timestamp}
            )
        else:
            logger.info("Aggregating all revenue data (first run)")
            result = db.execute(
                text("""
                    SELECT DISTINCT date
                    FROM newbook_earned_revenue_data
                    ORDER BY date
                """)
            )

        dates_to_process = [row.date for row in result.fetchall()]

        if not dates_to_process:
            logger.info("No new revenue data to aggregate")
            return {"dates_processed": 0, "message": "No new data"}

        logger.info(f"Found {len(dates_to_process)} dates to aggregate")

        # Aggregate each date
        for target_date in dates_to_process:
            # Get totals by department for this date
            result = db.execute(
                text("""
                    SELECT
                        COALESCE(g.department, 'other') as department,
                        SUM(e.amount_net) as total_net
                    FROM newbook_earned_revenue_data e
                    LEFT JOIN newbook_gl_accounts g ON e.gl_code = g.gl_code
                    WHERE e.date = :date
                    GROUP BY g.department
                """),
                {"date": target_date}
            )

            totals = {"accommodation": 0, "dry": 0, "wet": 0}
            for row in result.fetchall():
                if row.department in totals:
                    totals[row.department] = float(row.total_net or 0)

            # Upsert into newbook_net_revenue_data
            db.execute(
                text("""
                    INSERT INTO newbook_net_revenue_data (date, accommodation, dry, wet, aggregated_at)
                    VALUES (:date, :accommodation, :dry, :wet, NOW())
                    ON CONFLICT (date) DO UPDATE SET
                        accommodation = :accommodation,
                        dry = :dry,
                        wet = :wet,
                        aggregated_at = NOW()
                """),
                {
                    "date": target_date,
                    "accommodation": round(totals["accommodation"], 2),
                    "dry": round(totals["dry"], 2),
                    "wet": round(totals["wet"], 2)
                }
            )

        db.commit()

        # Update last aggregation timestamp
        set_config_value(db, 'last_revenue_aggregation_at', datetime.now().isoformat())
        db.commit()

        logger.info(f"Revenue aggregation complete: {len(dates_to_process)} dates")
        return {
            "dates_processed": len(dates_to_process),
            "message": f"Aggregated {len(dates_to_process)} dates"
        }

    except Exception as e:
        logger.error(f"Revenue aggregation failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


async def backfill_revenue_aggregation():
    """
    Backfill all historical revenue data.
    Forces re-aggregation of all dates regardless of last run time.
    """
    logger.info("Starting revenue backfill aggregation...")
    # Pass epoch time to force processing all data
    return await aggregate_revenue(since_timestamp="1970-01-01T00:00:00")
