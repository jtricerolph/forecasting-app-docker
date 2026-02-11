"""
Prophet Tuned Model Service

This is the production-tuned Prophet model extracted from the prophet-preview endpoint.
Uses the exact same logic as the frontend preview to ensure value consistency.

Features:
- 2 years of training data
- Logistic growth with floor/cap
- UK holidays + custom special dates
- OTB floor capping
- Per-date bookable cap adjustments
- Metric-specific handling
"""
import logging
from datetime import date, timedelta
from typing import List, Dict, Optional
import pandas as pd
import warnings
from prophet import Prophet
from sqlalchemy import text

from utils.capacity import get_bookable_cap

logger = logging.getLogger(__name__)
warnings.filterwarnings('ignore')


# Metric configuration mapping
METRIC_COLUMN_MAP = {
    'occupancy': ('s.occupancy_pct', False, True),
    'rooms': ('s.booking_count', False, False),
    'guests': ('s.guest_count', False, False),
    'ave_guest_rate': ('s.arr_net', False, False),
    'arr': ('s.arr_net', False, False),
    'net_accom': ('r.accommodation', True, False),
    'net_dry': ('r.dry', True, False),
    'net_wet': ('r.wet', True, False),
    'total_rev': ('(COALESCE(r.accommodation, 0) + COALESCE(r.dry, 0) + COALESCE(r.wet, 0))', True, False),
}


def get_metric_query_parts(metric: str) -> tuple:
    """
    Get SQL query parts for a metric.
    Returns: (column_expr, from_clause, is_percentage)
    """
    if metric not in METRIC_COLUMN_MAP:
        # Default to rooms if unknown metric
        metric = 'rooms'

    col_expr, needs_revenue, is_pct = METRIC_COLUMN_MAP[metric]

    if needs_revenue:
        from_clause = """
            FROM newbook_bookings_stats s
            LEFT JOIN newbook_net_revenue_data r ON s.date = r.date
        """
    else:
        from_clause = "FROM newbook_bookings_stats s"

    return col_expr, from_clause, is_pct


def get_lead_time_column(lead_days: int) -> str:
    """
    Map lead days to the appropriate column in newbook_booking_pace.
    """
    if lead_days <= 0:
        return "d0"
    elif lead_days <= 30:
        return f"d{lead_days}"
    elif lead_days <= 177:
        # Weekly intervals - find nearest column
        weekly_cols = [37, 44, 51, 58, 65, 72, 79, 86, 93, 100, 107, 114, 121, 128, 135, 142, 149, 156, 163, 170, 177]
        for col in weekly_cols:
            if lead_days <= col:
                return f"d{col}"
        return "d177"
    else:
        # Monthly intervals
        monthly_cols = [210, 240, 270, 300, 330, 365]
        for col in monthly_cols:
            if lead_days <= col:
                return f"d{col}"
        return "d365"


async def run_prophet_tuned_forecast(
    db,
    metric_code: str,
    start_date: date,
    end_date: date,
    perception_date: Optional[date] = None
) -> List[Dict]:
    """
    Generate Prophet forecast using production-tuned model.

    This uses the exact same logic as the prophet-preview endpoint to ensure
    backend snapshots match frontend preview values.

    Args:
        db: Database session
        metric_code: Metric to forecast (e.g., 'hotel_occupancy_pct', 'hotel_room_nights')
        start_date: Start date for forecast
        end_date: End date for forecast
        perception_date: Optional date to generate forecast as-of (for backtesting)

    Returns:
        List of forecast dicts with forecast_date and predicted_value
    """
    logger.info(f"Running Prophet tuned forecast for {metric_code}: {start_date} to {end_date}")

    # Map metric codes to preview endpoint metric names
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

    metric = metric_map.get(metric_code, 'rooms')

    # Use perception_date if provided, otherwise use actual today
    today = perception_date if perception_date else date.today()

    # Get default bookable cap
    default_bookable_cap = await get_bookable_cap(db)

    # Get metric column and query parts
    col_expr, from_clause, is_pct_metric = get_metric_query_parts(metric)

    # Get historical data for Prophet training (past 2 years)
    history_start = today - timedelta(days=730)
    history_query = f"""
        SELECT s.date as ds, {col_expr} as y
        {from_clause}
        WHERE s.date >= :history_start
        AND s.date < :today
        AND {col_expr} IS NOT NULL
        ORDER BY s.date
    """
    history_result = await db.execute(text(history_query), {"history_start": history_start, "today": today})
    history_rows = history_result.fetchall()

    if len(history_rows) < 30:
        logger.warning(f"Insufficient historical data for Prophet model: {len(history_rows)} rows")
        return []

    # Build training dataframe
    df = pd.DataFrame([{"ds": row.ds, "y": float(row.y) if row.y is not None else 0} for row in history_rows])

    # Set floor/cap based on metric type
    if is_pct_metric:
        # Percentage metrics (occupancy)
        training_cap = 100
    elif metric == 'rooms':
        # Room counts - cap at bookable rooms
        training_cap = default_bookable_cap
    elif metric == 'guests':
        # Guests can exceed rooms (multiple per room) - use historical max * 1.5
        training_cap = df["y"].max() * 1.5 if len(df) > 0 and df["y"].max() > 0 else default_bookable_cap * 3
    else:
        # Revenue/rate metrics - use percentile-based cap
        training_cap = df["y"].quantile(0.99) * 1.5 if len(df) > 0 and df["y"].quantile(0.99) > 0 else 10000

    df["floor"] = 0
    df["cap"] = training_cap

    # Train Prophet model with logistic growth (respects floor/cap)
    model = Prophet(
        growth='logistic',
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        interval_width=0.8,
        changepoint_prior_scale=0.05
    )

    # Add UK holidays
    model.add_country_holidays(country_name='UK')

    # Add custom special dates from settings
    try:
        from api.special_dates import get_special_dates_for_prophet
        # Get special dates for training period + forecast period
        min_year = history_start.year
        max_year = end_date.year + 1
        custom_holidays = await get_special_dates_for_prophet(db, min_year, max_year)

        if custom_holidays:
            # Create holidays dataframe for Prophet
            holidays_df = pd.DataFrame(custom_holidays)
            # Group by holiday name and add lower/upper windows
            for holiday_name in holidays_df['holiday'].unique():
                holiday_dates = holidays_df[holidays_df['holiday'] == holiday_name][['ds', 'holiday']]
                holiday_dates = holiday_dates.copy()
                holiday_dates['lower_window'] = 0
                holiday_dates['upper_window'] = 0
                model.holidays = pd.concat([model.holidays, holiday_dates]) if model.holidays is not None else holiday_dates
    except Exception as e:
        logger.warning(f"Could not load special dates for Prophet: {e}")

    model.fit(df)

    # Create future dataframe for forecast period
    future_dates = []
    current_date = start_date
    while current_date <= end_date:
        if (current_date - today).days >= 0:
            future_dates.append({"ds": current_date})
        current_date += timedelta(days=1)

    if not future_dates:
        logger.warning("No future dates to forecast")
        return []

    future_df = pd.DataFrame(future_dates)

    # Add floor/cap for logistic growth predictions (must match training cap)
    future_df["floor"] = 0
    future_df["cap"] = training_cap

    forecast = model.predict(future_df)

    # Process forecast results
    forecasts = []
    is_room_based = metric in ('occupancy', 'rooms')

    for _, row in forecast.iterrows():
        forecast_date = row["ds"].date()
        lead_days = (forecast_date - today).days
        lead_col = get_lead_time_column(lead_days)

        # Get current OTB (only for room-based metrics)
        current_otb = None
        if is_room_based:
            current_query = text("""
                SELECT booking_count as current_otb
                FROM newbook_bookings_stats
                WHERE date = :arrival_date
            """)
            current_result = await db.execute(current_query, {"arrival_date": forecast_date})
            current_row = current_result.fetchone()
            current_otb = current_row.current_otb if current_row and current_row.current_otb is not None else 0

        # Get per-date bookable cap for room-based metrics
        date_bookable_cap = await get_bookable_cap(db, forecast_date, default_bookable_cap)

        # Convert to occupancy if needed
        if metric == "occupancy" and date_bookable_cap > 0:
            if current_otb is not None:
                current_otb = (current_otb / date_bookable_cap) * 100

        # Get Prophet forecast values
        yhat = row["yhat"]

        # Cap at max capacity based on metric type (uses per-date bookable cap)
        if is_pct_metric:
            yhat = min(yhat, 100.0)
        elif metric == 'rooms':
            yhat = min(yhat, float(date_bookable_cap))
        # Guests and revenue/rate metrics don't have a hard cap

        # Floor forecast to current OTB if we have it (room-based metrics only)
        # But never exceed the bookable capacity (e.g., closed/maintenance periods)
        if is_room_based and current_otb is not None and yhat < current_otb:
            yhat = min(current_otb, float(date_bookable_cap))

        forecasts.append({
            'forecast_date': forecast_date,
            'predicted_value': round(yhat, 2)
        })

    logger.info(f"Prophet tuned generated {len(forecasts)} forecasts for {metric_code}")
    return forecasts
