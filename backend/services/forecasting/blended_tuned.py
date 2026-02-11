"""
Blended Tuned Model Service

This blends the production-tuned models using the exact same logic as the frontend.
Ensures backend snapshots match frontend preview values.

Blending Logic:
- Pace metrics (rooms/occupancy): Prophet + XGBoost + CatBoost + Pickup (25% each)
- Other metrics: Prophet + XGBoost + CatBoost (33.3% each)

This is the single source of truth for blended forecast snapshots.
"""
import logging
from datetime import date
from typing import List, Dict, Optional
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def run_blended_tuned_forecast(
    db,
    metric_code: str,
    start_date: date,
    end_date: date,
    save_to_db: bool = False,
    run_id: Optional[str] = None
) -> List[Dict]:
    """
    Generate blended forecast using production-tuned models.

    This uses the exact same logic as the frontend Live Blended view to ensure
    backend snapshots match frontend preview values.

    Args:
        db: Database session
        metric_code: Metric to forecast (e.g., 'hotel_occupancy_pct', 'hotel_room_nights')
        start_date: Start date for forecast
        end_date: End date for forecast
        save_to_db: If True, saves forecasts to database (for snapshots)
        run_id: Run ID for tracking (required if save_to_db=True)

    Returns:
        List of forecast dicts with date and predicted_value
    """
    logger.info(f"Running blended tuned forecast for {metric_code}: {start_date} to {end_date}")

    # Check if metric is a pace metric (uses pickup)
    is_pace_metric = metric_code in ('hotel_occupancy_pct', 'hotel_room_nights')

    # Step 1: Run individual tuned models
    forecasts_by_date = {}

    # Run Prophet Tuned
    try:
        from services.forecasting.prophet_tuned import run_prophet_tuned_forecast
        prophet_forecasts = await run_prophet_tuned_forecast(db, metric_code, start_date, end_date)
        for fc in prophet_forecasts:
            fc_date = str(fc['forecast_date'])
            if fc_date not in forecasts_by_date:
                forecasts_by_date[fc_date] = {}
            forecasts_by_date[fc_date]['prophet'] = float(fc['predicted_value'])
        logger.info(f"Prophet tuned generated {len(prophet_forecasts)} forecasts for {metric_code}")
        db.commit()  # Commit after successful model run
    except Exception as e:
        logger.error(f"Prophet tuned forecast failed for {metric_code}: {e}")
        db.rollback()
        db.commit()  # Start fresh transaction

    # Run XGBoost Tuned
    try:
        from services.forecasting.xgboost_tuned import run_xgboost_tuned_forecast
        xgboost_forecasts = await run_xgboost_tuned_forecast(db, metric_code, start_date, end_date)
        for fc in xgboost_forecasts:
            fc_date = str(fc['forecast_date'])
            if fc_date not in forecasts_by_date:
                forecasts_by_date[fc_date] = {}
            forecasts_by_date[fc_date]['xgboost'] = float(fc['predicted_value'])
        logger.info(f"XGBoost tuned generated {len(xgboost_forecasts)} forecasts for {metric_code}")
        db.commit()  # Commit after successful model run
    except Exception as e:
        logger.error(f"XGBoost tuned forecast failed for {metric_code}: {e}")
        db.rollback()
        db.commit()  # Start fresh transaction

    # Run CatBoost Tuned
    try:
        from services.forecasting.catboost_tuned import run_catboost_tuned_forecast
        catboost_forecasts = await run_catboost_tuned_forecast(db, metric_code, start_date, end_date)
        for fc in catboost_forecasts:
            fc_date = str(fc['forecast_date'])
            if fc_date not in forecasts_by_date:
                forecasts_by_date[fc_date] = {}
            forecasts_by_date[fc_date]['catboost'] = float(fc['predicted_value'])
        logger.info(f"CatBoost tuned generated {len(catboost_forecasts)} forecasts for {metric_code}")
        db.commit()  # Commit after successful model run
    except Exception as e:
        logger.error(f"CatBoost tuned forecast failed for {metric_code}: {e}")
        db.rollback()
        db.commit()  # Start fresh transaction

    # Run Pickup Tuned (only for pace metrics)
    if is_pace_metric:
        try:
            from services.forecasting.pickup_tuned import run_pickup_tuned_forecast
            pickup_forecasts = await run_pickup_tuned_forecast(db, metric_code, start_date, end_date)
            for fc in pickup_forecasts:
                fc_date = str(fc['forecast_date'])
                if fc_date not in forecasts_by_date:
                    forecasts_by_date[fc_date] = {}
                forecasts_by_date[fc_date]['pickup'] = float(fc['predicted_value'])
            logger.info(f"Pickup tuned generated {len(pickup_forecasts)} forecasts for {metric_code}")
            db.commit()  # Commit after successful model run
        except Exception as e:
            logger.error(f"Pickup tuned forecast failed for {metric_code}: {e}")
            db.rollback()
            db.commit()  # Start fresh transaction

    # Step 2: Calculate simple average blended forecast
    # Match frontend logic:
    # - Pace metrics: (prophet + xgboost + catboost + pickup) / 4
    # - Other metrics: (prophet + xgboost + catboost) / 3
    blended_forecasts = []
    for fc_date, model_forecasts in forecasts_by_date.items():
        # Need at least 2 models to blend
        if len(model_forecasts) < 2:
            continue

        # Simple average of all available models
        blended_value = sum(model_forecasts.values()) / len(model_forecasts)

        blended_forecasts.append({
            'date': fc_date,
            'predicted_value': round(blended_value, 2)
        })

    logger.info(f"Generated {len(blended_forecasts)} blended tuned forecasts for {metric_code}")

    # Step 3: Optionally save to database (for snapshots)
    if save_to_db and run_id:
        try:
            for fc in blended_forecasts:
                db.execute(
                    text("""
                        INSERT INTO forecasts
                            (run_id, forecast_date, forecast_type, model_type, predicted_value, generated_at)
                        VALUES
                            (:run_id, :forecast_date, :forecast_type, 'blended_tuned', :predicted_value, NOW())
                    """),
                    {
                        "run_id": run_id,
                        "forecast_date": fc['date'],
                        "forecast_type": metric_code,
                        "predicted_value": fc['predicted_value']
                    }
                )
            db.commit()
            logger.info(f"Saved {len(blended_forecasts)} blended tuned forecasts to database")
        except Exception as e:
            logger.error(f"Failed to save blended tuned forecasts to database: {e}")
            db.rollback()
            raise

    return blended_forecasts
