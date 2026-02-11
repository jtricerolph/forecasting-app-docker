"""
Centralized Blended Forecasting Model Service

This is the single source of truth for blended forecasts.
Used by:
- Weekly snapshots (saves to DB)
- Frontend live previews (on-the-fly)
- External apps (reads saved snapshots)
"""
import logging
from datetime import date, timedelta
from typing import List, Dict, Optional
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def run_blended_forecast(
    db,
    metric_code: str,
    start_date: date,
    end_date: date,
    save_to_db: bool = False,
    run_id: Optional[str] = None
) -> List[Dict]:
    """
    Generate blended forecast by running Prophet, XGBoost, CatBoost and blending with accuracy weights.

    This is the centralized blended model used everywhere in the application.

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
    logger.info(f"Running blended forecast for {metric_code}: {start_date} to {end_date}")

    # Use simple equal-weight averaging to match frontend behavior
    # Frontend: (prophet + xgboost + catboost) / 3
    logger.info(f"Using simple equal-weight averaging for {metric_code}")

    # Step 1: Run individual models
    forecasts_by_date = {}

    # Run Prophet
    try:
        from services.forecasting.prophet_model import run_prophet_forecast
        prophet_forecasts = await run_prophet_forecast(db, metric_code, start_date, end_date)
        for fc in prophet_forecasts:
            fc_date = str(fc['forecast_date'])
            if fc_date not in forecasts_by_date:
                forecasts_by_date[fc_date] = {}
            forecasts_by_date[fc_date]['prophet'] = float(fc['predicted_value'])
        logger.info(f"Prophet generated {len(prophet_forecasts)} forecasts for {metric_code}")
        db.commit()  # Commit after successful model run
    except Exception as e:
        logger.error(f"Prophet forecast failed for {metric_code}: {e}")
        db.rollback()
        db.commit()  # Start fresh transaction

    # Run XGBoost
    try:
        from services.forecasting.xgboost_model import run_xgboost_forecast
        xgboost_forecasts = await run_xgboost_forecast(db, metric_code, start_date, end_date)
        for fc in xgboost_forecasts:
            fc_date = str(fc['forecast_date'])
            if fc_date not in forecasts_by_date:
                forecasts_by_date[fc_date] = {}
            forecasts_by_date[fc_date]['xgboost'] = float(fc['predicted_value'])
        logger.info(f"XGBoost generated {len(xgboost_forecasts)} forecasts for {metric_code}")
        db.commit()  # Commit after successful model run
    except Exception as e:
        logger.error(f"XGBoost forecast failed for {metric_code}: {e}")
        db.rollback()
        db.commit()  # Start fresh transaction

    # Run CatBoost
    try:
        from services.forecasting.catboost_model import run_catboost_forecast
        catboost_forecasts = await run_catboost_forecast(db, metric_code, start_date, end_date)
        for fc in catboost_forecasts:
            fc_date = str(fc['forecast_date'])
            if fc_date not in forecasts_by_date:
                forecasts_by_date[fc_date] = {}
            forecasts_by_date[fc_date]['catboost'] = float(fc['predicted_value'])
        logger.info(f"CatBoost generated {len(catboost_forecasts)} forecasts for {metric_code}")
        db.commit()  # Commit after successful model run
    except Exception as e:
        logger.error(f"CatBoost forecast failed for {metric_code}: {e}")
        db.rollback()
        db.commit()  # Start fresh transaction

    # Run Pickup-V2 for revenue metrics (net_accom, hotel_accommodation_rev)
    if metric_code in ('net_accom', 'hotel_accommodation_rev'):
        try:
            from services.forecasting.pickup_v2_model import run_pickup_v2_forecast
            pickup_v2_forecasts = await run_pickup_v2_forecast(db, 'net_accom', start_date, end_date)
            for fc in pickup_v2_forecasts:
                fc_date = str(fc['date'])
                if fc_date not in forecasts_by_date:
                    forecasts_by_date[fc_date] = {}
                forecasts_by_date[fc_date]['pickup_v2'] = float(fc['predicted_value'])
            logger.info(f"Pickup-V2 generated {len(pickup_v2_forecasts)} forecasts for {metric_code}")
            db.commit()
        except Exception as e:
            logger.error(f"Pickup-V2 forecast failed for {metric_code}: {e}")
            db.rollback()
            db.commit()

    # Step 3: Calculate simple average blended forecast
    # Match frontend logic: (prophet + xgboost + catboost) / 3
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

    logger.info(f"Generated {len(blended_forecasts)} blended forecasts for {metric_code}")

    # Step 4: Optionally save to database (for snapshots)
    if save_to_db and run_id:
        try:
            for fc in blended_forecasts:
                db.execute(
                    text("""
                        INSERT INTO forecasts
                            (run_id, forecast_date, forecast_type, model_type, predicted_value, generated_at)
                        VALUES
                            (:run_id, :forecast_date, :forecast_type, 'blended', :predicted_value, NOW())
                    """),
                    {
                        "run_id": run_id,
                        "forecast_date": fc['date'],
                        "forecast_type": metric_code,
                        "predicted_value": fc['predicted_value']
                    }
                )
            db.commit()
            logger.info(f"Saved {len(blended_forecasts)} blended forecasts to database")
        except Exception as e:
            logger.error(f"Failed to save blended forecasts to database: {e}")
            db.rollback()
            raise

    return blended_forecasts
