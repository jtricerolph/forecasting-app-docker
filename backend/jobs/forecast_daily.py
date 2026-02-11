"""
Daily forecast generation job
Runs Prophet, XGBoost, and Pickup models
"""
import json
import logging
import uuid
from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import text
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
        models = ['prophet', 'xgboost', 'pickup', 'catboost']

    run_id = str(uuid.uuid4())
    forecast_from = date.today() + timedelta(days=start_days)
    forecast_to = date.today() + timedelta(days=horizon_days)

    logger.info(f"Starting forecast run {run_id}: {forecast_from} to {forecast_to}, models: {models}")

    db = next(iter([SyncSessionLocal()]))

    try:
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
                "models": json.dumps(models),
                "triggered_by": triggered_by
            }
        )
        db.commit()

        # Get metrics to forecast
        result = db.execute(
            text("""
            SELECT metric_code, use_prophet, use_xgboost, use_pickup,
                   COALESCE(use_catboost, TRUE) as use_catboost
            FROM forecast_metrics
            WHERE is_active = TRUE
            """)
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
                    db.rollback()  # Rollback failed transaction

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
                    db.rollback()  # Rollback failed transaction

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
                    db.rollback()  # Rollback failed transaction

            # Run CatBoost if applicable
            if 'catboost' in models and getattr(metric, 'use_catboost', True):
                try:
                    from services.forecasting.catboost_model import run_catboost_forecast
                    catboost_forecasts = await run_catboost_forecast(
                        db, metric_code, forecast_from, forecast_to
                    )
                    forecasts_generated += len(catboost_forecasts)
                except Exception as e:
                    logger.error(f"CatBoost forecast failed for {metric_code}: {e}")
                    db.rollback()  # Rollback failed transaction

        # Run blended model (accuracy-weighted average of prophet, xgboost, catboost)
        if 'blended' in models:
            try:
                logger.info("Generating blended forecasts with accuracy-based weighting")

                # Get accuracy scores for model weighting (from last 90 days)
                # Calculate weights per metric
                metric_weights = {}
                for metric in metrics:
                    metric_code = metric.metric_code
                    try:
                        accuracy_result = db.execute(
                            text("""
                                SELECT
                                    AVG(ABS(prophet_pct_error)) as prophet_mape,
                                    AVG(ABS(xgboost_pct_error)) as xgboost_mape,
                                    AVG(ABS(catboost_pct_error)) as catboost_mape
                                FROM actual_vs_forecast
                                WHERE date >= CURRENT_DATE - INTERVAL '90 days'
                                    AND date < CURRENT_DATE
                                    AND metric_type = :metric
                                    AND actual_value IS NOT NULL
                            """),
                            {"metric": metric_code}
                        )
                        accuracy_row = accuracy_result.fetchone()

                        # Calculate inverse-MAPE weights (lower MAPE = higher weight)
                        if accuracy_row and accuracy_row.prophet_mape and accuracy_row.xgboost_mape and accuracy_row.catboost_mape:
                            prophet_mape = float(accuracy_row.prophet_mape) or 10
                            xgboost_mape = float(accuracy_row.xgboost_mape) or 10
                            catboost_mape = float(accuracy_row.catboost_mape) or 10

                            inv_prophet = 1 / max(prophet_mape, 0.1)
                            inv_xgboost = 1 / max(xgboost_mape, 0.1)
                            inv_catboost = 1 / max(catboost_mape, 0.1)
                            total_inv = inv_prophet + inv_xgboost + inv_catboost

                            metric_weights[metric_code] = {
                                'prophet': inv_prophet / total_inv,
                                'xgboost': inv_xgboost / total_inv,
                                'catboost': inv_catboost / total_inv
                            }
                        else:
                            # Equal weights if no accuracy data
                            metric_weights[metric_code] = {'prophet': 1/3, 'xgboost': 1/3, 'catboost': 1/3}
                    except Exception:
                        # Default to equal weights on error
                        metric_weights[metric_code] = {'prophet': 1/3, 'xgboost': 1/3, 'catboost': 1/3}

                # Get all forecasts from the three models for this run
                result = db.execute(
                    text("""
                        SELECT forecast_date, forecast_type, model_type, predicted_value
                        FROM forecasts
                        WHERE run_id = :run_id
                        AND model_type IN ('prophet', 'xgboost', 'catboost')
                        ORDER BY forecast_date, forecast_type
                    """),
                    {"run_id": run_id}
                )
                rows = result.fetchall()

                if rows:
                    # Group by forecast_date and forecast_type
                    forecasts_by_date_type = {}
                    for row in rows:
                        key = (row.forecast_date, row.forecast_type)
                        if key not in forecasts_by_date_type:
                            forecasts_by_date_type[key] = {}
                        forecasts_by_date_type[key][row.model_type] = float(row.predicted_value)

                    # Calculate weighted blended forecast for each date/type combination
                    blended_count = 0
                    for (forecast_date, forecast_type), model_forecasts in forecasts_by_date_type.items():
                        # Only blend if we have at least 2 models
                        if len(model_forecasts) >= 2:
                            # Get weights for this metric
                            weights = metric_weights.get(forecast_type, {'prophet': 1/3, 'xgboost': 1/3, 'catboost': 1/3})

                            # Calculate weighted average
                            weighted_sum = 0
                            weight_total = 0
                            for model, value in model_forecasts.items():
                                weight = weights.get(model, 0)
                                weighted_sum += value * weight
                                weight_total += weight

                            blended_value = weighted_sum / weight_total if weight_total > 0 else sum(model_forecasts.values()) / len(model_forecasts)

                            # Insert blended forecast
                            db.execute(
                                text("""
                                    INSERT INTO forecasts
                                        (run_id, forecast_date, forecast_type, model_type, predicted_value, generated_at)
                                    VALUES
                                        (:run_id, :forecast_date, :forecast_type, 'blended', :predicted_value, NOW())
                                """),
                                {
                                    "run_id": run_id,
                                    "forecast_date": forecast_date,
                                    "forecast_type": forecast_type,
                                    "predicted_value": round(blended_value, 2)
                                }
                            )
                            blended_count += 1

                    db.commit()
                    forecasts_generated += blended_count
                    logger.info(f"Generated {blended_count} accuracy-weighted blended forecasts")
                else:
                    logger.warning("No individual model forecasts found for blending")

            except Exception as e:
                logger.error(f"Blended forecast generation failed: {e}")

        # Update run status
        db.execute(
            text("""
            UPDATE forecast_runs
            SET completed_at = NOW(), status = 'success'
            WHERE run_id = :run_id
            """),
            {"run_id": run_id}
        )
        db.commit()

        logger.info(f"Forecast run {run_id} completed: {forecasts_generated} forecasts generated")

    except Exception as e:
        logger.error(f"Forecast run {run_id} failed: {e}")
        # Rollback the failed transaction first
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
        except Exception as update_error:
            logger.error(f"Failed to update error status: {update_error}")
        raise
    finally:
        db.close()
