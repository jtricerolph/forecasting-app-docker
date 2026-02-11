"""
Accuracy calculation job
Compares forecasts to actuals once dates have passed
"""
import logging
from datetime import date, timedelta

from sqlalchemy import text
from database import SyncSessionLocal

logger = logging.getLogger(__name__)


async def run_accuracy_calculation():
    """
    Calculate forecast accuracy for dates that have passed.
    Updates actual_vs_forecast table with error metrics.
    """
    logger.info("Starting accuracy calculation")

    db = next(iter([SyncSessionLocal()]))

    try:
        # Process yesterday's actuals
        calc_date = date.today() - timedelta(days=1)

        # Get all metrics
        metrics_result = db.execute(
            text("""
            SELECT metric_code FROM forecast_metrics WHERE is_active = TRUE
            """)
        )
        metrics = [row.metric_code for row in metrics_result.fetchall()]

        for metric_code in metrics:
            # Get actual value from daily_metrics
            actual_result = db.execute(
                text("""
                SELECT actual_value FROM daily_metrics
                WHERE date = :calc_date AND metric_code = :metric_code
                """),
                {"calc_date": calc_date, "metric_code": metric_code}
            )
            actual_row = actual_result.fetchone()
            actual_value = actual_row.actual_value if actual_row else None

            if actual_value is None:
                continue  # Skip if no actual available

            # Get forecasts for this date
            forecast_result = db.execute(
                text("""
                SELECT model_type, predicted_value, lower_bound, upper_bound
                FROM forecasts
                WHERE forecast_date = :calc_date AND forecast_type = :metric_code
                """),
                {"calc_date": calc_date, "metric_code": metric_code}
            )
            forecasts = {row.model_type: row for row in forecast_result.fetchall()}

            prophet_forecast = forecasts.get('prophet')
            xgboost_forecast = forecasts.get('xgboost')
            pickup_forecast = forecasts.get('pickup')
            catboost_forecast = forecasts.get('catboost')

            # Calculate errors
            def calc_error(forecast_val):
                if forecast_val is None:
                    return None, None
                error = actual_value - forecast_val
                pct_error = (error / actual_value * 100) if actual_value != 0 else None
                return error, pct_error

            prophet_error, prophet_pct = calc_error(
                prophet_forecast.predicted_value if prophet_forecast else None
            )
            xgboost_error, xgboost_pct = calc_error(
                xgboost_forecast.predicted_value if xgboost_forecast else None
            )
            pickup_error, pickup_pct = calc_error(
                pickup_forecast.predicted_value if pickup_forecast else None
            )
            catboost_error, catboost_pct = calc_error(
                catboost_forecast.predicted_value if catboost_forecast else None
            )

            # Determine best model
            errors = []
            if prophet_error is not None:
                errors.append(('prophet', abs(prophet_error)))
            if xgboost_error is not None:
                errors.append(('xgboost', abs(xgboost_error)))
            if pickup_error is not None:
                errors.append(('pickup', abs(pickup_error)))
            if catboost_error is not None:
                errors.append(('catboost', abs(catboost_error)))

            best_model = min(errors, key=lambda x: x[1])[0] if errors else None

            # Get budget value
            budget_result = db.execute(
                text("""
                SELECT budget_value FROM daily_budgets
                WHERE date = :calc_date AND budget_type = :metric_code
                """),
                {"calc_date": calc_date, "metric_code": metric_code}
            )
            budget_row = budget_result.fetchone()
            budget_value = budget_row.budget_value if budget_row else None

            # Upsert accuracy record
            db.execute(
                text("""
                INSERT INTO actual_vs_forecast (
                    date, metric_type, actual_value,
                    prophet_forecast, prophet_lower, prophet_upper,
                    xgboost_forecast, pickup_forecast,
                    catboost_forecast,
                    budget_value,
                    prophet_error, prophet_pct_error,
                    xgboost_error, xgboost_pct_error,
                    pickup_error, pickup_pct_error,
                    catboost_error, catboost_pct_error,
                    best_model, calculated_at
                ) VALUES (
                    :date, :metric_type, :actual,
                    :prophet_val, :prophet_lower, :prophet_upper,
                    :xgboost_val, :pickup_val,
                    :catboost_val,
                    :budget,
                    :prophet_error, :prophet_pct,
                    :xgboost_error, :xgboost_pct,
                    :pickup_error, :pickup_pct,
                    :catboost_error, :catboost_pct,
                    :best_model, NOW()
                )
                ON CONFLICT (date, metric_type) DO UPDATE SET
                    actual_value = :actual,
                    prophet_error = :prophet_error,
                    prophet_pct_error = :prophet_pct,
                    xgboost_error = :xgboost_error,
                    xgboost_pct_error = :xgboost_pct,
                    pickup_error = :pickup_error,
                    pickup_pct_error = :pickup_pct,
                    catboost_forecast = :catboost_val,
                    catboost_error = :catboost_error,
                    catboost_pct_error = :catboost_pct,
                    best_model = :best_model,
                    calculated_at = NOW()
                """),
                {
                    "date": calc_date,
                    "metric_type": metric_code,
                    "actual": actual_value,
                    "prophet_val": prophet_forecast.predicted_value if prophet_forecast else None,
                    "prophet_lower": prophet_forecast.lower_bound if prophet_forecast else None,
                    "prophet_upper": prophet_forecast.upper_bound if prophet_forecast else None,
                    "xgboost_val": xgboost_forecast.predicted_value if xgboost_forecast else None,
                    "pickup_val": pickup_forecast.predicted_value if pickup_forecast else None,
                    "catboost_val": catboost_forecast.predicted_value if catboost_forecast else None,
                    "budget": budget_value,
                    "prophet_error": prophet_error,
                    "prophet_pct": prophet_pct,
                    "xgboost_error": xgboost_error,
                    "xgboost_pct": xgboost_pct,
                    "pickup_error": pickup_error,
                    "pickup_pct": pickup_pct,
                    "catboost_error": catboost_error,
                    "catboost_pct": catboost_pct,
                    "best_model": best_model
                }
            )

        db.commit()
        logger.info(f"Accuracy calculation completed for {calc_date}")

    except Exception as e:
        logger.error(f"Accuracy calculation failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()
