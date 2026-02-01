"""
Pickup forecasting model
Hotel industry standard pace/pickup tracking
Compares current on-the-books vs historical patterns

Uses ADDITIVE method for small properties:
- Projected = current_otb + expected_pickup_count
- Where expected_pickup_count = prior_year_final - prior_year_otb

This avoids ratio distortion with small numbers (e.g., 2→6 = 3x ratio
applied to 5 = 15 rooms, which is unrealistic)

Prior year comparison uses 364 days (52 weeks) for day-of-week alignment:
- Monday compares to Monday
- Saturday compares to Saturday
"""
import logging
from datetime import date, timedelta
from typing import List, Optional
from sqlalchemy import text

from utils.time_alignment import get_prior_year_daily, get_comparison_info

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
    2. Comparing to prior year SAME DAY OF WEEK at same lead time
    3. Projecting final using ADDITIVE method (not ratio) for reliability

    Additive method: projected = current_otb + (prior_final - prior_otb)
    This represents: "what I have now + what typically picks up from here"

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

        # Calculate prior year comparison date (same day of week alignment)
        prior_year_date = get_prior_year_daily(forecast_date)

        # Get total available rooms for this date (for capping room_nights)
        total_rooms = 25  # Default fallback
        if metric_code in ('hotel_room_nights', 'hotel_occupancy_pct'):
            rooms_result = db.execute(
                text("""
                SELECT COALESCE(SUM(available), 25) as total_rooms
                FROM newbook_occupancy_report_data
                WHERE date = :forecast_date
                """),
                {"forecast_date": forecast_date}
            )
            rooms_row = rooms_result.fetchone()
            if rooms_row and rooms_row.total_rooms:
                total_rooms = int(rooms_row.total_rooms)

        # Get current OTB from snapshots
        otb_result = db.execute(
            text("""
            SELECT otb_value, prior_year_otb, prior_year_final
            FROM pickup_snapshots
            WHERE stay_date = :forecast_date
                AND metric_type = :metric_code
                AND snapshot_date = :today
            """),
            {"forecast_date": forecast_date, "metric_code": metric_code, "today": today}
        )
        otb_row = otb_result.fetchone()

        if not otb_row:
            # No OTB data available, skip
            continue

        current_otb = float(otb_row.otb_value) if otb_row.otb_value is not None else 0
        # Use 'is not None' - 0 is valid data meaning no bookings at that lead time
        prior_otb = float(otb_row.prior_year_otb) if otb_row.prior_year_otb is not None else None
        prior_final = float(otb_row.prior_year_final) if otb_row.prior_year_final is not None else None

        # Get pickup curve for this day of week and season (fallback)
        day_of_week = forecast_date.weekday()
        day_name = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][day_of_week]
        month = forecast_date.month

        # Determine season
        if month in [6, 7, 8]:
            season = 'peak'
        elif month in [12, 1, 2]:
            season = 'low'
        else:
            season = 'shoulder'

        curve_result = db.execute(
            text("""
            SELECT avg_pct_of_final, std_dev
            FROM pickup_curves
            WHERE day_of_week = :dow
                AND season = :season
                AND metric_type = :metric_code
                AND days_out = :lead_time
            """),
            {"dow": day_of_week, "season": season, "metric_code": metric_code, "lead_time": lead_time}
        )
        curve_row = curve_result.fetchone()

        # Calculate projection
        projected_value = current_otb
        projection_method = 'current_otb'
        pace_vs_prior = None
        confidence_note = "Using current on-the-books"

        if prior_otb is not None and prior_final is not None:
            # Calculate expected pickup count from prior year
            prior_pickup_count = prior_final - prior_otb  # How many picked up from this lead time

            # Calculate pace vs prior year
            if prior_otb > 0:
                pace_vs_prior = ((current_otb - prior_otb) / prior_otb) * 100

            # ADDITIVE METHOD: current + expected pickup
            # This is more reliable for small properties than ratio method
            # Example: prior had 2 OTB → 6 final = 4 pickup
            #          current has 5 OTB → project 5 + 4 = 9
            projected_value = current_otb + prior_pickup_count

            # Ensure projection is at least current OTB (pickup can't be negative in projection)
            if projected_value < current_otb:
                projected_value = current_otb
                projection_method = 'additive_floor'
                confidence_note = f"vs {day_name} {prior_year_date.strftime('%d %b %Y')}: {prior_otb:.0f}→{prior_final:.0f} (negative pickup, using OTB)"
            else:
                projection_method = 'additive'
                confidence_note = f"vs {day_name} {prior_year_date.strftime('%d %b %Y')}: {prior_otb:.0f}→{prior_final:.0f} (+{prior_pickup_count:.0f} pickup)"

            # Apply physical caps
            if metric_code == 'hotel_occupancy_pct' and projected_value > 100:
                projected_value = 100
                confidence_note += " (capped at 100%)"
            if metric_code == 'hotel_room_nights' and projected_value > total_rooms:
                projected_value = total_rooms
                confidence_note += f" (capped at {total_rooms} rooms)"

        elif prior_final is not None and prior_final > 0:
            # No prior OTB, but have prior final - use as guidance
            # Estimate typical OTB percentage at this lead time
            if lead_time >= 28:
                estimated_pct = 0.35
            elif lead_time >= 14:
                estimated_pct = 0.55
            elif lead_time >= 7:
                estimated_pct = 0.75
            else:
                estimated_pct = 0.90

            # Calculate implied pickup from typical percentages
            implied_prior_otb = prior_final * estimated_pct
            implied_pickup = prior_final - implied_prior_otb

            # Apply additive method with implied pickup
            projected_value = current_otb + implied_pickup
            projected_value = max(projected_value, current_otb)

            projection_method = 'implied_additive'
            confidence_note = f"vs {day_name} {prior_year_date.strftime('%d %b %Y')}: final was {prior_final:.0f}, est +{implied_pickup:.0f} pickup at {lead_time}d"

            # Apply physical caps
            if metric_code == 'hotel_occupancy_pct' and projected_value > 100:
                projected_value = 100
                confidence_note += " (capped at 100%)"
            if metric_code == 'hotel_room_nights' and projected_value > total_rooms:
                projected_value = total_rooms
                confidence_note += f" (capped at {total_rooms} rooms)"

        elif curve_row and curve_row.avg_pct_of_final > 0:
            # Curve method: project based on historical pickup curve
            projected_value = current_otb / (curve_row.avg_pct_of_final / 100)
            projection_method = 'curve'
            confidence_note = f"Based on pickup curve ({curve_row.avg_pct_of_final:.1f}% typical at {lead_time} days out)"

            # Apply physical caps
            if metric_code == 'hotel_occupancy_pct' and projected_value > 100:
                projected_value = 100
                confidence_note += " (capped at 100%)"
            if metric_code == 'hotel_room_nights' and projected_value > total_rooms:
                projected_value = total_rooms
                confidence_note += f" (capped at {total_rooms} rooms)"

        forecast_record = {
            "forecast_date": forecast_date,
            "forecast_type": metric_code,
            "model_type": "pickup",
            "predicted_value": round(projected_value, 2)
        }
        forecasts.append(forecast_record)

        # Store in database
        db.execute(
            text("""
            INSERT INTO forecasts (
                forecast_date, forecast_type, model_type, predicted_value, generated_at
            ) VALUES (
                :forecast_date, :forecast_type, :model_type, :predicted_value, NOW()
            )
            """),
            forecast_record
        )

        # Store explanation
        try:
            db.execute(
                text("""
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
                """),
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
        except Exception:
            pass  # Skip if conflict, explanations are supplementary

    db.commit()
    logger.info(f"Pickup forecast generated for {metric_code}: {len(forecasts)} records")
    return forecasts


async def update_pickup_curves(db, metric_code: str, lookback_days: int = 2555):
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
                text("""
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
                """),
                {"metric_code": metric_code, "lookback": lookback_days, "dow": dow}
            )

            for row in result.fetchall():
                db.execute(
                    text("""
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
                    """),
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
