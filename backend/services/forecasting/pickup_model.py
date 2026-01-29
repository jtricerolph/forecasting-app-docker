"""
Pickup forecasting model
Hotel industry standard pace/pickup tracking
Compares current on-the-books vs historical patterns
"""
import logging
from datetime import date, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)


async def run_pickup_forecast(
    db,
    metric_code: str,
    forecast_from: date,
    forecast_to: date
) -> List[dict]:
    """
    Run Pickup model forecast for a metric

    The pickup model works by:
    1. Getting current on-the-books (OTB) for each future date
    2. Comparing to historical OTB at same lead time
    3. Projecting final value based on historical pickup patterns

    Args:
        db: Database session
        metric_code: Metric to forecast
        forecast_from: Start date for forecasts
        forecast_to: End date for forecasts

    Returns:
        List of forecast records
    """
    forecasts = []
    today = date.today()

    for days_out in range((forecast_to - forecast_from).days + 1):
        forecast_date = forecast_from + timedelta(days=days_out)
        lead_time = (forecast_date - today).days

        if lead_time < 1:
            continue  # Can't do pickup for past dates

        # Get current OTB from snapshots
        otb_result = db.execute(
            """
            SELECT otb_value, prior_year_otb, prior_year_final
            FROM pickup_snapshots
            WHERE stay_date = :forecast_date
                AND metric_type = :metric_code
                AND snapshot_date = :today
            """,
            {"forecast_date": forecast_date, "metric_code": metric_code, "today": today}
        )
        otb_row = otb_result.fetchone()

        if not otb_row:
            # No OTB data available, skip
            continue

        current_otb = float(otb_row.otb_value) if otb_row.otb_value else 0
        prior_otb = float(otb_row.prior_year_otb) if otb_row.prior_year_otb else None
        prior_final = float(otb_row.prior_year_final) if otb_row.prior_year_final else None

        # Get pickup curve for this day of week and season
        day_of_week = forecast_date.weekday()
        month = forecast_date.month

        # Determine season
        if month in [6, 7, 8]:
            season = 'peak'
        elif month in [12, 1, 2]:
            season = 'low'
        else:
            season = 'shoulder'

        curve_result = db.execute(
            """
            SELECT avg_pct_of_final, std_dev
            FROM pickup_curves
            WHERE day_of_week = :dow
                AND season = :season
                AND metric_type = :metric_code
                AND days_out = :lead_time
            """,
            {"dow": day_of_week, "season": season, "metric_code": metric_code, "lead_time": lead_time}
        )
        curve_row = curve_result.fetchone()

        # Calculate projection
        projected_value = current_otb
        projection_method = 'current_otb'
        pace_vs_prior = None
        confidence_note = "Using current on-the-books"

        if prior_otb and prior_final and prior_otb > 0:
            # Ratio method: project based on prior year's pickup ratio
            pickup_ratio = prior_final / prior_otb
            projected_value = current_otb * pickup_ratio
            projection_method = 'ratio'
            pace_vs_prior = ((current_otb - prior_otb) / prior_otb) * 100
            confidence_note = f"Based on prior year ratio ({pickup_ratio:.2f})"

        elif curve_row and curve_row.avg_pct_of_final > 0:
            # Curve method: project based on historical pickup curve
            projected_value = current_otb / (curve_row.avg_pct_of_final / 100)
            projection_method = 'curve'
            confidence_note = f"Based on pickup curve ({curve_row.avg_pct_of_final:.1f}% typical at {lead_time} days out)"

        forecast_record = {
            "forecast_date": forecast_date,
            "forecast_type": metric_code,
            "model_type": "pickup",
            "predicted_value": round(projected_value, 2)
        }
        forecasts.append(forecast_record)

        # Store in database
        db.execute(
            """
            INSERT INTO forecasts (
                forecast_date, forecast_type, model_type, predicted_value, generated_at
            ) VALUES (
                :forecast_date, :forecast_type, :model_type, :predicted_value, NOW()
            )
            """,
            forecast_record
        )

        # Store explanation
        db.execute(
            """
            INSERT INTO pickup_explanations (
                forecast_date, forecast_type, current_otb, days_out,
                comparison_otb, comparison_final,
                pickup_curve_pct, pace_vs_prior_pct, projection_method,
                projected_value, confidence_note, generated_at
            ) VALUES (
                :date, :metric, :otb, :days_out,
                :prior_otb, :prior_final,
                :curve_pct, :pace, :method,
                :projected, :confidence, NOW()
            )
            """,
            {
                "date": forecast_date,
                "metric": metric_code,
                "otb": current_otb,
                "days_out": lead_time,
                "prior_otb": prior_otb,
                "prior_final": prior_final,
                "curve_pct": curve_row.avg_pct_of_final if curve_row else None,
                "pace": pace_vs_prior,
                "method": projection_method,
                "projected": projected_value,
                "confidence": confidence_note
            }
        )

    db.commit()
    logger.info(f"Pickup forecast generated for {metric_code}: {len(forecasts)} records")
    return forecasts


async def update_pickup_curves(db, metric_code: str, lookback_days: int = 365):
    """
    Update historical pickup curves from actuals

    Calculates average percentage of final value at each lead time
    """
    logger.info(f"Updating pickup curves for {metric_code}")

    # For each day of week and season
    for dow in range(7):
        for season in ['peak', 'shoulder', 'low']:
            # Get historical final values and snapshots
            result = db.execute(
                """
                WITH final_values AS (
                    SELECT date, actual_value
                    FROM daily_metrics
                    WHERE metric_code = :metric_code
                        AND date > CURRENT_DATE - :lookback
                        AND actual_value IS NOT NULL
                        AND EXTRACT(DOW FROM date) = :dow
                ),
                snapshot_data AS (
                    SELECT
                        ps.stay_date,
                        ps.days_out,
                        ps.otb_value,
                        fv.actual_value as final_value
                    FROM pickup_snapshots ps
                    JOIN final_values fv ON ps.stay_date = fv.date
                    WHERE ps.metric_type = :metric_code
                )
                SELECT
                    days_out,
                    AVG(otb_value / NULLIF(final_value, 0) * 100) as avg_pct,
                    STDDEV(otb_value / NULLIF(final_value, 0) * 100) as std_pct,
                    COUNT(*) as sample_count
                FROM snapshot_data
                WHERE final_value > 0
                GROUP BY days_out
                HAVING COUNT(*) >= 5
                """,
                {"metric_code": metric_code, "lookback": lookback_days, "dow": dow}
            )

            for row in result.fetchall():
                db.execute(
                    """
                    INSERT INTO pickup_curves (
                        day_of_week, season, metric_type, days_out,
                        avg_pct_of_final, std_dev, sample_count, updated_at
                    ) VALUES (
                        :dow, :season, :metric, :days_out,
                        :avg_pct, :std, :count, NOW()
                    )
                    ON CONFLICT (day_of_week, season, metric_type, days_out)
                    DO UPDATE SET
                        avg_pct_of_final = :avg_pct,
                        std_dev = :std,
                        sample_count = :count,
                        updated_at = NOW()
                    """,
                    {
                        "dow": dow,
                        "season": season,
                        "metric": metric_code,
                        "days_out": row.days_out,
                        "avg_pct": row.avg_pct,
                        "std": row.std_pct,
                        "count": row.sample_count
                    }
                )

    db.commit()
    logger.info(f"Pickup curves updated for {metric_code}")
