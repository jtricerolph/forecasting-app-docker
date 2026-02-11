"""
Pickup Tuned Model Service

This is the production-tuned Pickup model extracted from the preview endpoint.
Uses the exact same logic as the frontend preview to ensure value consistency.

Pickup Formula: Forecast = Current OTB + (Prior Year Final - Prior Year OTB)

This transparent model calculates expected pickup based on prior year booking patterns.
Only works for room-based metrics (occupancy, rooms). Not applicable to revenue metrics.
"""
import logging
from datetime import date, timedelta
from typing import List, Dict, Optional
from sqlalchemy import text

from utils.capacity import get_bookable_cap

logger = logging.getLogger(__name__)


def get_lead_time_column(lead_days: int) -> str:
    """Map lead days to the appropriate column in newbook_booking_pace."""
    if lead_days <= 0:
        return "d0"
    elif lead_days <= 30:
        return f"d{lead_days}"
    elif lead_days <= 177:
        weekly_cols = [37, 44, 51, 58, 65, 72, 79, 86, 93, 100, 107, 114, 121, 128, 135, 142, 149, 156, 163, 170, 177]
        for col in weekly_cols:
            if lead_days <= col:
                return f"d{col}"
        return "d177"
    else:
        monthly_cols = [210, 240, 270, 300, 330, 365]
        for col in monthly_cols:
            if lead_days <= col:
                return f"d{col}"
        return "d365"


async def run_pickup_tuned_forecast(
    db,
    metric_code: str,
    start_date: date,
    end_date: date,
    perception_date: Optional[date] = None
) -> List[Dict]:
    """
    Generate Pickup forecast using production-tuned model.

    Uses transparent booking pace formula:
    Forecast = Current OTB + (Prior Year Final - Prior Year OTB)

    This uses the exact same logic as the preview endpoint to ensure
    backend snapshots match frontend preview values.

    Args:
        db: Database session
        metric_code: Metric to forecast (only room-based metrics supported)
        start_date: Start date for forecast
        end_date: End date for forecast
        perception_date: Optional date to generate forecast as-of (for backtesting)

    Returns:
        List of forecast dicts with forecast_date and predicted_value
    """
    logger.info(f"Running Pickup tuned forecast for {metric_code}: {start_date} to {end_date}")

    # Map metric codes to preview endpoint metric names
    metric_map = {
        'hotel_occupancy_pct': 'occupancy',
        'hotel_room_nights': 'rooms',
        'hotel_guests': 'guests',
    }

    metric = metric_map.get(metric_code, 'rooms')

    # Check if metric is room-based (pickup model only works for these)
    is_room_based = metric in ('occupancy', 'rooms')
    if not is_room_based:
        logger.warning(f"Pickup model doesn't apply to non-room metric: {metric_code}")
        return []

    # Use perception_date if provided, otherwise use actual today
    today = perception_date if perception_date else date.today()

    # Get default bookable cap
    default_bookable_cap = await get_bookable_cap(db)

    # Generate forecasts for each date
    forecasts = []

    current_date = start_date
    while current_date <= end_date:
        lead_days = (current_date - today).days
        if lead_days < 0:
            current_date += timedelta(days=1)
            continue

        lead_col = get_lead_time_column(lead_days)
        prior_year_date = current_date - timedelta(days=364)  # 52 weeks for DOW alignment

        # Get current OTB
        current_query = text("""
            SELECT booking_count as current_otb
            FROM newbook_bookings_stats
            WHERE date = :arrival_date
        """)
        current_result = await db.execute(current_query, {"arrival_date": current_date})
        current_row = current_result.fetchone()

        # Get prior year OTB from booking_pace (for lead time comparison)
        prior_year_for_otb = current_date - timedelta(days=364)
        prior_otb_query = text(f"""
            SELECT {lead_col} as prior_otb
            FROM newbook_booking_pace
            WHERE arrival_date = :prior_date
        """)
        prior_otb_result = await db.execute(prior_otb_query, {"prior_date": prior_year_for_otb})
        prior_otb_row = prior_otb_result.fetchone()

        # Get prior year FINAL from bookings_stats
        prior_final_query = text("""
            SELECT booking_count as prior_final
            FROM newbook_bookings_stats
            WHERE date = :prior_date
        """)
        prior_final_result = await db.execute(prior_final_query, {"prior_date": prior_year_date})
        prior_final_row = prior_final_result.fetchone()

        # Extract values
        current_otb = current_row.current_otb if current_row and current_row.current_otb is not None else 0
        prior_otb = prior_otb_row.prior_otb if prior_otb_row and prior_otb_row.prior_otb is not None else None
        prior_final = prior_final_row.prior_final if prior_final_row and prior_final_row.prior_final is not None else 0

        # Get per-date bookable cap
        date_bookable_cap = await get_bookable_cap(db, current_date, default_bookable_cap)

        # Convert to occupancy % if metric is occupancy
        if metric == "occupancy" and date_bookable_cap > 0:
            if current_otb is not None:
                current_otb = (current_otb / date_bookable_cap) * 100
            if prior_otb is not None:
                prior_otb = (prior_otb / date_bookable_cap) * 100
            if prior_final is not None:
                prior_final = (prior_final / date_bookable_cap) * 100

        # Calculate forecast using pickup formula
        forecast = None

        if current_otb is not None:
            if prior_final is not None and prior_otb is not None:
                expected_pickup = prior_final - prior_otb
                forecast = current_otb + expected_pickup
                # Floor to current OTB if pickup is negative
                if forecast < current_otb:
                    forecast = current_otb
                # Cap at max capacity (uses per-date bookable cap)
                if metric == "occupancy" and forecast > 100:
                    forecast = 100.0
                elif metric == "rooms" and forecast > date_bookable_cap:
                    forecast = float(date_bookable_cap)
            else:
                # No prior year data - use current OTB as forecast
                forecast = current_otb

        if forecast is not None:
            forecasts.append({
                'forecast_date': current_date,
                'predicted_value': round(forecast, 1)
            })

        current_date += timedelta(days=1)

    logger.info(f"Pickup tuned generated {len(forecasts)} forecasts for {metric_code}")
    return forecasts
