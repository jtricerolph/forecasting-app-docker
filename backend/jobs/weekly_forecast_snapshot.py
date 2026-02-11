"""
Weekly Forecast Snapshot Job
Automatically creates blended forecast snapshots using MAPE-weighted model blending with 60/40 budget/prior year blend.
Uses the blended_tuned_weighted service for accuracy-optimized forecasts.
"""
import logging
import uuid
from datetime import date, datetime, timedelta
from sqlalchemy import text
from database import SyncSessionLocal

logger = logging.getLogger(__name__)


def get_config_value(db, key: str, default: str = None) -> str:
    """Get a config value from system_config"""
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


def is_forecast_snapshot_enabled(db) -> bool:
    """Check if automated forecast snapshots are enabled"""
    value = get_config_value(db, "forecast_snapshot_enabled")
    if value:
        return value.lower() in ('true', '1', 'yes', 'enabled')
    return False


def get_forecast_snapshot_days_ahead(db) -> int:
    """Get number of days ahead to forecast"""
    days_str = get_config_value(db, "forecast_snapshot_days_ahead", "90")
    try:
        return int(days_str)
    except ValueError:
        return 90


async def run_weekly_forecast_snapshot():
    """
    Run weekly blended forecast snapshot using MAPE-weighted + 60/40 blend.
    This is the single source of truth for forecast snapshots.
    - Stage 1: MAPE-weighted blend of Prophet, XGBoost, CatBoost (+ Pickup for pace metrics)
    - Stage 2: 60% model blend + 40% budget (revenue) or prior year (non-revenue)
    """
    db = SyncSessionLocal()
    run_id = str(uuid.uuid4())

    try:
        # Check if enabled
        if not is_forecast_snapshot_enabled(db):
            logger.info("Weekly forecast snapshot is disabled, skipping")
            return

        days_ahead = get_forecast_snapshot_days_ahead(db)
        forecast_from = date.today()
        forecast_to = date.today() + timedelta(days=days_ahead)

        logger.info(f"Starting weekly blended forecast snapshot: {forecast_from} to {forecast_to}")

        # Log run start
        db.execute(
            text("""
            INSERT INTO forecast_runs (
                run_id, run_type, started_at, status,
                forecast_from, forecast_to, models_run, triggered_by
            ) VALUES (
                :run_id, 'scheduled', NOW(), 'running',
                :forecast_from, :forecast_to, :models, :triggered_by
            )
            """),
            {
                "run_id": run_id,
                "forecast_from": forecast_from,
                "forecast_to": forecast_to,
                "models": '["blended"]',
                "triggered_by": "forecast_snapshot"
            }
        )
        db.commit()

        # Get active metrics
        result = db.execute(
            text("""
                SELECT metric_code, metric_name
                FROM forecast_metrics
                WHERE is_active = TRUE
            """)
        )
        metrics = result.fetchall()

        # Import MAPE-weighted blended model with 60/40 budget blend
        from services.forecasting.blended_tuned_weighted import run_blended_tuned_weighted_forecast

        # Run blended forecast for each metric
        total_forecasts = 0
        for metric in metrics:
            metric_code = metric.metric_code
            try:
                logger.info(f"Generating MAPE-weighted + 60/40 blended forecast for {metric_code}")
                forecasts = await run_blended_tuned_weighted_forecast(
                    db=db,
                    metric_code=metric_code,
                    start_date=forecast_from,
                    end_date=forecast_to,
                    save_to_db=True,
                    run_id=run_id
                    # apply_60_40_blend defaults to True
                )
                total_forecasts += len(forecasts)
                logger.info(f"Generated {len(forecasts)} MAPE-weighted + 60/40 forecasts for {metric_code}")
            except Exception as e:
                logger.error(f"Blended forecast failed for {metric_code}: {e}")
                db.rollback()
                continue

        # Update run status to success
        db.execute(
            text("""
            UPDATE forecast_runs
            SET completed_at = NOW(), status = 'success'
            WHERE run_id = :run_id
            """),
            {"run_id": run_id}
        )
        db.commit()

        # Log completion to sync_log
        db.execute(
            text("""
                INSERT INTO sync_log (sync_type, source, started_at, completed_at, status, records_created, triggered_by)
                VALUES (:sync_type, :source, :started_at, :completed_at, :status, :records_created, :triggered_by)
            """),
            {
                "sync_type": "forecast_snapshot",
                "source": "blended_tuned_weighted",
                "started_at": datetime.now(),
                "completed_at": datetime.now(),
                "status": "success",
                "records_created": total_forecasts,
                "triggered_by": "scheduler"
            }
        )
        db.commit()

        logger.info(f"Weekly forecast snapshot completed: {total_forecasts} total forecasts generated")

    except Exception as e:
        logger.error(f"Weekly forecast snapshot failed: {e}")

        # Rollback and update run status
        db.rollback()
        try:
            db.execute(
                text("""
                UPDATE forecast_runs
                SET completed_at = NOW(), status = 'failed', error_message = :error
                WHERE run_id = :run_id
                """),
                {"run_id": run_id, "error": str(e)}
            )
            db.commit()
        except:
            pass

        # Log error to sync_log
        try:
            db.execute(
                text("""
                    INSERT INTO sync_log (sync_type, source, started_at, completed_at, status, error_message, triggered_by)
                    VALUES (:sync_type, :source, :started_at, :completed_at, :status, :error_message, :triggered_by)
                """),
                {
                    "sync_type": "forecast_snapshot",
                    "source": "blended_tuned_weighted",
                    "started_at": datetime.now(),
                    "completed_at": datetime.now(),
                    "status": "error",
                    "error_message": str(e),
                    "triggered_by": "scheduler"
                }
            )
            db.commit()
        except:
            pass
        raise
    finally:
        db.close()
