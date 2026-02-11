"""
Prophet forecasting model
Time series forecasting with trend, seasonality, and holiday effects
"""
import logging
from datetime import date, timedelta
from typing import List, Optional
import pandas as pd
import numpy as np
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def run_prophet_forecast(
    db,
    metric_code: str,
    forecast_from: date,
    forecast_to: date,
    training_days: int = 2555  # ~7 years - use all available history
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

        # Revenue metrics use earned_revenue_data joined with gl_accounts
        revenue_metrics = ['net_accom', 'net_dry', 'net_wet', 'total_rev']
        if metric_code in revenue_metrics:
            revenue_departments = {
                'net_accom': 'accommodation',
                'net_dry': 'dry',
                'net_wet': 'wet',
                'total_rev': None,  # All departments
            }
            department = revenue_departments.get(metric_code)
            if department is None and metric_code != 'total_rev':
                logger.warning(f"Unknown revenue metric for Prophet: {metric_code}")
                return []

            if metric_code == 'total_rev':
                # Total revenue across all departments
                result = db.execute(
                    text("""
                    SELECT date, SUM(amount_net) as actual_value
                    FROM newbook_earned_revenue_data
                    WHERE date BETWEEN :from_date AND :to_date
                    GROUP BY date
                    HAVING SUM(amount_net) IS NOT NULL
                    ORDER BY date
                    """),
                    {"from_date": training_from, "to_date": forecast_from - timedelta(days=1)}
                )
            else:
                # Revenue by department
                result = db.execute(
                    text("""
                    SELECT r.date, SUM(r.amount_net) as actual_value
                    FROM newbook_earned_revenue_data r
                    JOIN newbook_gl_accounts g ON r.gl_account_id = g.gl_account_id
                    WHERE r.date BETWEEN :from_date AND :to_date
                        AND g.department = :department
                    GROUP BY r.date
                    HAVING SUM(r.amount_net) IS NOT NULL
                    ORDER BY r.date
                    """),
                    {"from_date": training_from, "to_date": forecast_from - timedelta(days=1), "department": department}
                )
        else:
            # Hotel metrics use newbook_bookings_stats table
            metric_column_map = {
                'hotel_occupancy_pct': 'total_occupancy_pct',
                'hotel_room_nights': 'booking_count',
                'hotel_guests': 'guests_count',
            }

            column_name = metric_column_map.get(metric_code)
            if not column_name:
                logger.warning(f"Unknown metric_code for Prophet: {metric_code}")
                return []

            result = db.execute(
                text(f"""
                SELECT date, {column_name} as actual_value
                FROM newbook_bookings_stats
                WHERE date BETWEEN :from_date AND :to_date
                    AND {column_name} IS NOT NULL
                ORDER BY date
                """),
                {"from_date": training_from, "to_date": forecast_from - timedelta(days=1)}
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
                "predicted_value": round(float(row["yhat"]), 2),
                "lower_bound": round(float(row["yhat_lower"]), 2),
                "upper_bound": round(float(row["yhat_upper"]), 2)
            }
            forecasts.append(forecast_record)

            # Store in database - simple insert (latest value wins)
            db.execute(
                text("""
                INSERT INTO forecasts (
                    forecast_date, forecast_type, model_type,
                    predicted_value, lower_bound, upper_bound, generated_at
                ) VALUES (
                    :forecast_date, :forecast_type, :model_type,
                    :predicted_value, :lower_bound, :upper_bound, NOW()
                )
                """),
                forecast_record
            )

            # Store decomposition for explainability
            # Simple insert - decomposition stored per generation
            try:
                db.execute(
                    text("""
                    INSERT INTO prophet_decomposition (
                        forecast_date, forecast_type, trend,
                        yearly_seasonality, weekly_seasonality, generated_at
                    ) VALUES (
                        :date, :metric, :trend, :yearly, :weekly, NOW()
                    )
                    """),
                    {
                        "date": row["ds"].date(),
                        "metric": metric_code,
                        "trend": round(float(row.get("trend", 0)), 4),
                        "yearly": round(float(row.get("yearly", 0)), 4),
                        "weekly": round(float(row.get("weekly", 0)), 4)
                    }
                )
            except Exception:
                pass  # Skip if conflict, decomposition is supplementary

        db.commit()
        logger.info(f"Prophet forecast generated for {metric_code}: {len(forecasts)} records")
        return forecasts

    except ImportError:
        logger.error("Prophet not installed. Install with: pip install prophet")
        return []
    except Exception as e:
        logger.error(f"Prophet forecast failed for {metric_code}: {e}")
        return []
