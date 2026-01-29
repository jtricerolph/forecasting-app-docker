"""
Prophet forecasting model
Time series forecasting with trend, seasonality, and holiday effects
"""
import logging
from datetime import date, timedelta
from typing import List, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


async def run_prophet_forecast(
    db,
    metric_code: str,
    forecast_from: date,
    forecast_to: date,
    training_days: int = 365
) -> List[dict]:
    """
    Run Prophet forecast for a metric

    Args:
        db: Database session
        metric_code: Metric to forecast (e.g., 'hotel_occupancy_pct')
        forecast_from: Start date for forecasts
        forecast_to: End date for forecasts
        training_days: Days of historical data to use for training

    Returns:
        List of forecast records
    """
    try:
        from prophet import Prophet

        # Get historical data
        training_from = forecast_from - timedelta(days=training_days)

        result = db.execute(
            """
            SELECT date, actual_value
            FROM daily_metrics
            WHERE metric_code = :metric_code
                AND date BETWEEN :from_date AND :to_date
                AND actual_value IS NOT NULL
            ORDER BY date
            """,
            {"metric_code": metric_code, "from_date": training_from, "to_date": forecast_from - timedelta(days=1)}
        )
        rows = result.fetchall()

        if len(rows) < 30:
            logger.warning(f"Insufficient data for Prophet forecast: {metric_code} has {len(rows)} records")
            return []

        # Prepare data for Prophet
        df = pd.DataFrame([{"ds": row.date, "y": float(row.actual_value)} for row in rows])

        # Initialize and fit Prophet model
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            interval_width=0.80  # 80% confidence interval
        )

        # Add UK holidays
        model.add_country_holidays(country_name='GB')

        model.fit(df)

        # Generate future dates
        future_dates = pd.date_range(start=forecast_from, end=forecast_to, freq='D')
        future_df = pd.DataFrame({"ds": future_dates})

        # Make predictions
        forecast = model.predict(future_df)

        # Store forecasts
        forecasts = []
        for _, row in forecast.iterrows():
            forecast_record = {
                "forecast_date": row["ds"].date(),
                "forecast_type": metric_code,
                "model_type": "prophet",
                "predicted_value": round(row["yhat"], 2),
                "lower_bound": round(row["yhat_lower"], 2),
                "upper_bound": round(row["yhat_upper"], 2)
            }
            forecasts.append(forecast_record)

            # Store in database
            db.execute(
                """
                INSERT INTO forecasts (
                    forecast_date, forecast_type, model_type,
                    predicted_value, lower_bound, upper_bound, generated_at
                ) VALUES (
                    :forecast_date, :forecast_type, :model_type,
                    :predicted_value, :lower_bound, :upper_bound, NOW()
                )
                ON CONFLICT (forecast_date, forecast_type, model_type, generated_at)
                DO UPDATE SET predicted_value = :predicted_value,
                    lower_bound = :lower_bound, upper_bound = :upper_bound
                """,
                forecast_record
            )

            # Store decomposition for explainability
            db.execute(
                """
                INSERT INTO prophet_decomposition (
                    forecast_date, forecast_type, trend,
                    yearly_seasonality, weekly_seasonality, generated_at
                ) VALUES (
                    :date, :metric, :trend, :yearly, :weekly, NOW()
                )
                ON CONFLICT (run_id, forecast_date, forecast_type)
                DO UPDATE SET trend = :trend, yearly_seasonality = :yearly
                """,
                {
                    "date": row["ds"].date(),
                    "metric": metric_code,
                    "trend": round(row.get("trend", 0), 4),
                    "yearly": round(row.get("yearly", 0), 4),
                    "weekly": round(row.get("weekly", 0), 4)
                }
            )

        db.commit()
        logger.info(f"Prophet forecast generated for {metric_code}: {len(forecasts)} records")
        return forecasts

    except ImportError:
        logger.error("Prophet not installed. Install with: pip install prophet")
        return []
    except Exception as e:
        logger.error(f"Prophet forecast failed for {metric_code}: {e}")
        return []
