"""
Daily forecast generation job
Runs Prophet, XGBoost, and Pickup models
"""
import logging
import uuid
from datetime import date, timedelta
from typing import List, Optional

from database import SyncSessionLocal

logger = logging.getLogger(__name__)


async def run_daily_forecast(
    horizon_days: int = 14,
    start_days: int = 0,
    models: Optional[List[str]] = None,
    triggered_by: str = "scheduler"
):
    """
    Run daily forecast update for specified horizon.

    Args:
        horizon_days: How many days ahead to forecast
        start_days: Start from N days in the future (for medium/long term)
        models: Which models to run (default: all)
        triggered_by: Who triggered this run
    """
    if models is None:
        models = ['prophet', 'xgboost', 'pickup']

    run_id = str(uuid.uuid4())
    forecast_from = date.today() + timedelta(days=start_days)
    forecast_to = date.today() + timedelta(days=horizon_days)

    logger.info(f"Starting forecast run {run_id}: {forecast_from} to {forecast_to}, models: {models}")

    db = next(iter([SyncSessionLocal()]))

    try:
        # Log run start
        db.execute(
            """
            INSERT INTO forecast_runs (
                run_id, run_type, started_at, status,
                forecast_from, forecast_to, models_run, triggered_by
            ) VALUES (
                :run_id, 'scheduled', NOW(), 'running',
                :forecast_from, :forecast_to, :models, :triggered_by
            )
            """,
            {
                "run_id": run_id,
                "forecast_from": forecast_from,
                "forecast_to": forecast_to,
                "models": str(models),
                "triggered_by": triggered_by
            }
        )
        db.commit()

        # Get metrics to forecast
        result = db.execute(
            """
            SELECT metric_code, use_prophet, use_xgboost, use_pickup
            FROM forecast_metrics
            WHERE is_active = TRUE AND show_in_dashboard = TRUE
            """
        )
        metrics = result.fetchall()

        forecasts_generated = 0

        for metric in metrics:
            metric_code = metric.metric_code

            # Run Prophet if applicable
            if 'prophet' in models and metric.use_prophet:
                try:
                    from services.forecasting.prophet_model import run_prophet_forecast
                    prophet_forecasts = await run_prophet_forecast(
                        db, metric_code, forecast_from, forecast_to
                    )
                    forecasts_generated += len(prophet_forecasts)
                except Exception as e:
                    logger.error(f"Prophet forecast failed for {metric_code}: {e}")

            # Run XGBoost if applicable
            if 'xgboost' in models and metric.use_xgboost:
                try:
                    from services.forecasting.xgboost_model import run_xgboost_forecast
                    xgboost_forecasts = await run_xgboost_forecast(
                        db, metric_code, forecast_from, forecast_to
                    )
                    forecasts_generated += len(xgboost_forecasts)
                except Exception as e:
                    logger.error(f"XGBoost forecast failed for {metric_code}: {e}")

            # Run Pickup if applicable (only for short-term)
            if 'pickup' in models and metric.use_pickup and start_days < 30:
                try:
                    from services.forecasting.pickup_model import run_pickup_forecast
                    pickup_forecasts = await run_pickup_forecast(
                        db, metric_code, forecast_from, forecast_to
                    )
                    forecasts_generated += len(pickup_forecasts)
                except Exception as e:
                    logger.error(f"Pickup forecast failed for {metric_code}: {e}")

        # Update run status
        db.execute(
            """
            UPDATE forecast_runs
            SET completed_at = NOW(), status = 'success'
            WHERE run_id = :run_id
            """,
            {"run_id": run_id}
        )
        db.commit()

        logger.info(f"Forecast run {run_id} completed: {forecasts_generated} forecasts generated")

    except Exception as e:
        logger.error(f"Forecast run {run_id} failed: {e}")
        db.execute(
            """
            UPDATE forecast_runs
            SET completed_at = NOW(), status = 'failed', error_message = :error
            WHERE run_id = :run_id
            """,
            {"run_id": run_id, "error": str(e)}
        )
        db.commit()
        raise
    finally:
        db.close()
