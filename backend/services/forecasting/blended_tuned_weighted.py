"""
Blended Tuned Model Service (Accuracy-Weighted + 60/40 Prior Year/Budget)

Two-stage blending:
1. MAPE-weighted model blend using backtest accuracy data
2. 60/40 blend with prior year actual or budget

Stage 1 - Model Weighting (MAPE-based):
- Query forecast_snapshots table for backtest MAPE scores
- Calculate inverse-MAPE weights (lower MAPE = higher weight)
- Pace metrics: weighted blend of Prophet + XGBoost + CatBoost + Pickup
- Other metrics: weighted blend of Prophet + XGBoost + CatBoost

Stage 2 - 60/40 Blend:
- Revenue metrics: 60% weighted model blend + 40% budget
- Non-revenue metrics: 60% weighted model blend + 40% prior year actual

Falls back to 100% model blend if prior year/budget data unavailable.
"""
import logging
from datetime import date, timedelta
from typing import List, Dict, Optional
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def get_model_weights(db, metric_code: str, is_pace_metric: bool) -> Dict[str, float]:
    """
    Calculate accuracy-based weights for each model using MAPE scores from backtest data.

    Args:
        db: Database session
        metric_code: Metric to forecast
        is_pace_metric: Whether this is a pace metric (uses pickup)

    Returns:
        Dict of model names to weights (normalized to sum to 1.0)
    """
    # Map metric codes to forecast_snapshots metric codes
    metric_map = {
        'hotel_occupancy_pct': 'occupancy',
        'hotel_room_nights': 'rooms',
        'hotel_guests': 'guests',
        'hotel_arr': 'arr',
        'ave_guest_rate': 'ave_guest_rate',
        'net_accom': 'net_accom',
        'net_dry': 'net_dry',
        'net_wet': 'net_wet',
        'total_rev': 'total_rev',
    }

    snapshot_metric = metric_map.get(metric_code, 'rooms')

    try:
        # Query MAPE from forecast_snapshots where we have actuals
        # Calculate MAPE for each model separately
        models_to_query = ['prophet', 'xgboost', 'catboost']
        if is_pace_metric:
            models_to_query.append('pickup')

        mape_scores = {}
        for model in models_to_query:
            query = text("""
                SELECT AVG(ABS((forecast_value - actual_value) / NULLIF(actual_value, 0)) * 100) as mape
                FROM forecast_snapshots
                WHERE actual_value IS NOT NULL
                    AND actual_value != 0
                    AND forecast_value IS NOT NULL
                    AND metric_code = :metric_code
                    AND model = :model
            """)
            result = await db.execute(query, {"metric_code": snapshot_metric, "model": model})
            row = result.fetchone()

            if row and row.mape is not None:
                mape_scores[model] = float(row.mape)
            else:
                mape_scores[model] = 100  # Default high MAPE if no data

        # Check if we have valid MAPE data
        if all(score == 100 for score in mape_scores.values()):
            logger.warning(f"No MAPE data found for {snapshot_metric}, using equal weights")
            # Fall back to equal weights
            if is_pace_metric:
                return {'prophet': 0.25, 'xgboost': 0.25, 'catboost': 0.25, 'pickup': 0.25}
            else:
                return {'prophet': 0.333, 'xgboost': 0.333, 'catboost': 0.334}

        logger.info(f"MAPE scores for {snapshot_metric}: " +
                   ", ".join([f"{k}={v:.2f}%" for k, v in mape_scores.items()]))

        # Calculate inverse-MAPE weights (lower MAPE = higher weight)
        weights = {model: 1.0 / max(mape, 0.1) for model, mape in mape_scores.items()}

        # Normalize weights to sum to 1.0
        weight_sum = sum(weights.values())
        normalized_weights = {k: v / weight_sum for k, v in weights.items()}

        logger.info(f"Normalized weights for {snapshot_metric}: " +
                   ", ".join([f"{k}={v:.4f}" for k, v in normalized_weights.items()]))
        return normalized_weights

    except Exception as e:
        logger.error(f"Failed to calculate model weights: {e}")
        import traceback
        traceback.print_exc()
        # Fall back to equal weights
        if is_pace_metric:
            return {'prophet': 0.25, 'xgboost': 0.25, 'catboost': 0.25, 'pickup': 0.25}
        else:
            return {'prophet': 0.333, 'xgboost': 0.333, 'catboost': 0.334}


async def run_blended_tuned_weighted_forecast(
    db,
    metric_code: str,
    start_date: date,
    end_date: date,
    save_to_db: bool = False,
    run_id: Optional[str] = None,
    perception_date: Optional[date] = None,
    apply_60_40_blend: bool = True
) -> List[Dict]:
    """
    Generate blended forecast using production-tuned models with accuracy-based weighting.

    This uses MAPE scores from the last 90 days to weight models by accuracy.
    Lower MAPE (more accurate) models receive higher weights.

    Args:
        db: Database session
        metric_code: Metric to forecast (e.g., 'hotel_occupancy_pct', 'hotel_room_nights')
        start_date: Start date for forecast
        end_date: End date for forecast
        save_to_db: If True, saves forecasts to database (for snapshots)
        run_id: Run ID for tracking (required if save_to_db=True)
        perception_date: Optional date to generate forecast as-of (for backtesting)
        apply_60_40_blend: If True, applies 60/40 blend with budget/prior year (default True)

    Returns:
        List of forecast dicts with date and predicted_value
    """
    logger.info(f"Running blended tuned WEIGHTED forecast for {metric_code}: {start_date} to {end_date}")

    # Check if metric is a pace metric (uses pickup)
    is_pace_metric = metric_code in ('hotel_occupancy_pct', 'hotel_room_nights')

    # Get accuracy-based weights
    weights = await get_model_weights(db, metric_code, is_pace_metric)

    # Step 1: Run individual tuned models
    forecasts_by_date = {}

    # Run Prophet Tuned
    try:
        from services.forecasting.prophet_tuned import run_prophet_tuned_forecast
        prophet_forecasts = await run_prophet_tuned_forecast(db, metric_code, start_date, end_date, perception_date)
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
        xgboost_forecasts = await run_xgboost_tuned_forecast(db, metric_code, start_date, end_date, perception_date)
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
        catboost_forecasts = await run_catboost_tuned_forecast(db, metric_code, start_date, end_date, perception_date)
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
            pickup_forecasts = await run_pickup_tuned_forecast(db, metric_code, start_date, end_date, perception_date)
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

    # Step 2: Calculate MAPE-weighted model blend, then apply 60/40 with prior year/budget
    # Determine if this is a revenue metric (uses budget instead of prior year)
    revenue_metrics = ['net_accom', 'net_dry', 'net_wet', 'total_rev', 'hotel_arr']
    is_revenue_metric = metric_code in revenue_metrics

    blended_forecasts = []
    for fc_date, model_forecasts in forecasts_by_date.items():
        # Need at least 2 models to blend
        if len(model_forecasts) < 2:
            continue

        # Apply accuracy-based weights to get weighted model blend
        weighted_sum = 0.0
        weight_total = 0.0

        for model_name, forecast_value in model_forecasts.items():
            if model_name in weights:
                weighted_sum += forecast_value * weights[model_name]
                weight_total += weights[model_name]

        # Calculate weighted model average
        if weight_total > 0:
            weighted_model_blend = weighted_sum / weight_total
        else:
            # Fall back to simple average if weights are missing
            weighted_model_blend = sum(model_forecasts.values()) / len(model_forecasts)

        # Apply 60/40 blend with prior year or budget (if enabled)
        final_value = weighted_model_blend  # Default: use model blend only

        if apply_60_40_blend:
            try:
                forecast_date_obj = date.fromisoformat(fc_date)

                if is_revenue_metric:
                    # Revenue metrics: 60% model + 40% budget
                    budget_query = text("""
                        SELECT budget_value
                        FROM daily_budgets
                        WHERE date = :fc_date AND budget_type = :metric_code
                    """)
                    budget_result = await db.execute(budget_query, {
                        "fc_date": forecast_date_obj,
                        "metric_code": metric_code
                    })
                    budget_row = budget_result.fetchone()
                    if budget_row and budget_row.budget_value is not None:
                        budget_value = float(budget_row.budget_value)
                        final_value = 0.6 * weighted_model_blend + 0.4 * budget_value
                        logger.debug(f"{fc_date}: Model={weighted_model_blend:.2f}, Budget={budget_value:.2f}, Final={final_value:.2f}")
                else:
                    # Non-revenue metrics: 60% model + 40% prior year
                    # Map metric codes for daily_metrics table
                    daily_metric_map = {
                        'hotel_occupancy_pct': 'hotel_occupancy_pct',
                        'hotel_room_nights': 'hotel_room_nights',
                        'hotel_guests': 'hotel_guests',
                        'ave_guest_rate': 'ave_guest_rate',
                    }
                    daily_metric_code = daily_metric_map.get(metric_code, metric_code)

                    # Get prior year date (same day of week, ~52 weeks back)
                    from utils.time_alignment import get_prior_year_daily
                    prior_year_date = get_prior_year_daily(forecast_date_obj)

                    prior_query = text("""
                        SELECT actual_value
                        FROM daily_metrics
                        WHERE date = :prior_date AND metric_code = :metric_code
                    """)
                    prior_result = await db.execute(prior_query, {
                        "prior_date": prior_year_date,
                        "metric_code": daily_metric_code
                    })
                    prior_row = prior_result.fetchone()
                    if prior_row and prior_row.actual_value is not None:
                        prior_value = float(prior_row.actual_value)
                        final_value = 0.6 * weighted_model_blend + 0.4 * prior_value
                        logger.debug(f"{fc_date}: Model={weighted_model_blend:.2f}, PriorYear={prior_value:.2f}, Final={final_value:.2f}")

            except Exception as e:
                logger.warning(f"Could not apply 60/40 blend for {fc_date}: {e}, using model blend only")
                final_value = weighted_model_blend

        blended_forecasts.append({
            'date': fc_date,
            'predicted_value': round(final_value, 2)
        })

    logger.info(f"Generated {len(blended_forecasts)} blended tuned WEIGHTED forecasts for {metric_code}")

    # Step 3: Optionally save to database (for snapshots)
    if save_to_db and run_id:
        try:
            for fc in blended_forecasts:
                db.execute(
                    text("""
                        INSERT INTO forecasts
                            (run_id, forecast_date, forecast_type, model_type, predicted_value, generated_at)
                        VALUES
                            (:run_id, :forecast_date, :forecast_type, 'blended_tuned_weighted', :predicted_value, NOW())
                    """),
                    {
                        "run_id": run_id,
                        "forecast_date": fc['date'],
                        "forecast_type": metric_code,
                        "predicted_value": fc['predicted_value']
                    }
                )
            db.commit()
            logger.info(f"Saved {len(blended_forecasts)} blended tuned weighted forecasts to database")
        except Exception as e:
            logger.error(f"Failed to save blended tuned weighted forecasts to database: {e}")
            db.rollback()
            raise

    return blended_forecasts
