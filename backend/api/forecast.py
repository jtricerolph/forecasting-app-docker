"""
Forecast API endpoints
"""
import asyncio
import math
from datetime import date, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from database import get_db
from auth import get_current_user
from api.special_dates import resolve_special_date
from utils.capacity import get_bookable_cap

router = APIRouter()


# Metric column mapping - defines how to get historical data for each metric
# Each entry: (column_expression, needs_revenue_join, is_percentage)
METRIC_COLUMN_MAP = {
    'occupancy': ('s.total_occupancy_pct', False, True),
    'rooms': ('s.booking_count', False, False),
    'guests': ('s.guests_count', False, False),
    'ave_guest_rate': ('s.guest_rate_total / NULLIF(s.booking_count, 0)', False, False),
    'arr': ('r.accommodation / NULLIF(s.booking_count, 0)', True, False),
    'net_accom': ('r.accommodation', True, False),
    'net_dry': ('r.dry', True, False),
    'net_wet': ('r.wet', True, False),
    'total_rev': ('COALESCE(r.accommodation, 0) + COALESCE(r.dry, 0) + COALESCE(r.wet, 0)', True, False),
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


def round_towards_reference(value: float, reference: Optional[float]) -> int:
    """
    Round a forecast value towards a reference value (prior year actual).

    - If forecast < reference: round up (ceil) towards reference
    - If forecast > reference: round down (floor) towards reference
    - If no reference: use standard rounding

    Examples:
    - 24.2 with prior year 25 → 25 (ceil towards reference)
    - 22.8 with prior year 20 → 22 (floor towards reference)
    """
    if reference is None:
        return round(value)

    if value < reference:
        return math.ceil(value)
    else:
        return math.floor(value)


class ForecastResponse(BaseModel):
    date: date
    metric_code: str
    metric_name: str
    prophet_value: Optional[float]
    prophet_lower: Optional[float]
    prophet_upper: Optional[float]
    xgboost_value: Optional[float]
    pickup_value: Optional[float]
    current_otb: Optional[float]
    budget_value: Optional[float]


class DailyForecastSummary(BaseModel):
    date: date
    day_of_week: str
    hotel_occupancy_pct: Optional[float]
    hotel_guests: Optional[float]
    hotel_arrivals: Optional[float]
    hotel_adr: Optional[float]
    resos_lunch_covers: Optional[float]
    resos_dinner_covers: Optional[float]
    model_used: str


@router.get("/daily")
async def get_daily_forecasts(
    from_date: Optional[date] = Query(None, description="Start date (default: today)"),
    to_date: Optional[date] = Query(None, description="End date (default: +14 days)"),
    metric: Optional[str] = Query(None, description="Filter by metric code"),
    model: Optional[str] = Query(None, description="Filter by model type: prophet, xgboost, pickup, all"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get daily forecasts with all models side-by-side.
    Returns forecasts for each date with Prophet, XGBoost, Pickup values and confidence intervals.
    """
    if from_date is None:
        from_date = date.today()
    if to_date is None:
        to_date = from_date + timedelta(days=14)

    query = """
        SELECT
            f.forecast_date,
            f.forecast_type as metric_code,
            fm.metric_name,
            MAX(CASE WHEN f.model_type = 'prophet' THEN f.predicted_value END) as prophet_value,
            MAX(CASE WHEN f.model_type = 'prophet' THEN f.lower_bound END) as prophet_lower,
            MAX(CASE WHEN f.model_type = 'prophet' THEN f.upper_bound END) as prophet_upper,
            MAX(CASE WHEN f.model_type = 'xgboost' THEN f.predicted_value END) as xgboost_value,
            MAX(CASE WHEN f.model_type = 'pickup' THEN f.predicted_value END) as pickup_value,
            ps.otb_value as current_otb,
            db.budget_value
        FROM forecasts f
        LEFT JOIN forecast_metrics fm ON f.forecast_type = fm.metric_code
        LEFT JOIN pickup_snapshots ps ON f.forecast_date = ps.stay_date
            AND f.forecast_type = ps.metric_type
            AND ps.snapshot_date = CURRENT_DATE
        LEFT JOIN daily_budgets db ON f.forecast_date = db.date AND f.forecast_type = db.budget_type
        WHERE f.forecast_date BETWEEN :from_date AND :to_date
    """

    params = {"from_date": from_date, "to_date": to_date}

    if metric:
        query += " AND f.forecast_type = :metric"
        params["metric"] = metric

    query += """
        GROUP BY f.forecast_date, f.forecast_type, fm.metric_name, ps.otb_value, db.budget_value
        ORDER BY f.forecast_date, fm.display_order
    """

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "date": row.forecast_date,
            "metric_code": row.metric_code,
            "metric_name": row.metric_name,
            "prophet_value": row.prophet_value,
            "prophet_lower": row.prophet_lower,
            "prophet_upper": row.prophet_upper,
            "xgboost_value": row.xgboost_value,
            "pickup_value": row.pickup_value,
            "current_otb": row.current_otb,
            "budget_value": row.budget_value
        }
        for row in rows
    ]


@router.get("/weekly")
async def get_weekly_summary(
    weeks: int = Query(8, description="Number of weeks to forecast"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get weekly summary forecast for the next N weeks.
    Aggregates daily forecasts into weekly totals/averages.
    """
    from_date = date.today()
    to_date = from_date + timedelta(weeks=weeks)

    query = """
        WITH weekly_data AS (
            SELECT
                DATE_TRUNC('week', f.forecast_date) as week_start,
                f.forecast_type,
                fm.metric_name,
                fm.unit,
                AVG(f.predicted_value) as avg_value,
                SUM(f.predicted_value) as sum_value,
                AVG(db.budget_value) as avg_budget,
                SUM(db.budget_value) as sum_budget
            FROM forecasts f
            LEFT JOIN forecast_metrics fm ON f.forecast_type = fm.metric_code
            LEFT JOIN daily_budgets db ON f.forecast_date = db.date AND f.forecast_type = db.budget_type
            WHERE f.forecast_date BETWEEN :from_date AND :to_date
                AND f.model_type = 'prophet'
            GROUP BY DATE_TRUNC('week', f.forecast_date), f.forecast_type, fm.metric_name, fm.unit
        )
        SELECT
            week_start,
            forecast_type,
            metric_name,
            unit,
            CASE
                WHEN unit = 'percent' THEN avg_value
                WHEN unit = 'decimal' THEN avg_value
                ELSE sum_value
            END as forecast_value,
            CASE
                WHEN unit = 'percent' THEN avg_budget
                WHEN unit = 'decimal' THEN avg_budget
                ELSE sum_budget
            END as budget_value
        FROM weekly_data
        ORDER BY week_start, forecast_type
    """

    result = await db.execute(text(query), {"from_date": from_date, "to_date": to_date})
    rows = result.fetchall()

    return [
        {
            "week_start": row.week_start,
            "metric_code": row.forecast_type,
            "metric_name": row.metric_name,
            "unit": row.unit,
            "forecast_value": row.forecast_value,
            "budget_value": row.budget_value,
            "variance": (row.forecast_value - row.budget_value) if row.budget_value else None,
            "variance_pct": ((row.forecast_value - row.budget_value) / row.budget_value * 100) if row.budget_value and row.budget_value != 0 else None
        }
        for row in rows
    ]


@router.get("/comparison")
async def get_model_comparison(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    metric: str = Query(..., description="Metric code to compare"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get side-by-side comparison of all forecasting models for a specific metric.
    Includes prior year actual for the full date range (both actuals and forecasts).
    Prior year uses 364-day offset (52 weeks) for day-of-week alignment.
    """
    if from_date is None:
        from_date = date.today()
    if to_date is None:
        to_date = from_date + timedelta(days=28)

    # Build comparison dict with all dates in range
    # Generate dates in Python to avoid asyncpg parameter issues with generate_series
    comparison = {}
    current_date = from_date
    while current_date <= to_date:
        comparison[str(current_date)] = {
            "date": current_date,
            "actual": None,
            "current_otb": None,
            "budget": None,
            "prior_year_actual": None,
            "prior_year_otb": None,
            "models": {}
        }
        current_date += timedelta(days=1)

    # Get actuals, OTB, and budget for dates with data
    dates_query = """
        SELECT
            dm.date as forecast_date,
            dm.actual_value,
            ps.otb_value as current_otb,
            db.budget_value
        FROM daily_metrics dm
        LEFT JOIN pickup_snapshots ps ON dm.date = ps.stay_date
            AND ps.metric_type = dm.metric_code
            AND ps.snapshot_date = CURRENT_DATE
        LEFT JOIN daily_budgets db ON dm.date = db.date AND db.budget_type = dm.metric_code
        WHERE dm.date BETWEEN :from_date AND :to_date
            AND dm.metric_code = :metric
        ORDER BY dm.date
    """

    dates_result = await db.execute(text(dates_query), {
        "from_date": from_date,
        "to_date": to_date,
        "metric": metric
    })
    date_rows = dates_result.fetchall()

    # Update comparison dict with actual data
    for row in date_rows:
        date_str = str(row.forecast_date)
        if date_str in comparison:
            # Use 'is not None' - 0 is valid data
            comparison[date_str]["actual"] = float(row.actual_value) if row.actual_value is not None else None
            comparison[date_str]["current_otb"] = float(row.current_otb) if row.current_otb is not None else None
            comparison[date_str]["budget"] = float(row.budget_value) if row.budget_value is not None else None

    # Get prior year actuals for ALL dates in the range
    # Calculate prior year date range in Python (364 days = 52 weeks for DOW alignment)
    prior_from = from_date - timedelta(days=364)
    prior_to = to_date - timedelta(days=364)

    prior_year_query = """
        SELECT
            dm.date as prior_date,
            dm.actual_value as prior_year_actual
        FROM daily_metrics dm
        WHERE dm.date BETWEEN :prior_from AND :prior_to
            AND dm.metric_code = :metric
    """

    prior_result = await db.execute(text(prior_year_query), {
        "prior_from": prior_from,
        "prior_to": prior_to,
        "metric": metric
    })
    prior_rows = prior_result.fetchall()

    # Map prior year dates to current year dates (+364 days)
    for row in prior_rows:
        target_date = row.prior_date + timedelta(days=364)
        date_str = str(target_date)
        if date_str in comparison:
            comparison[date_str]["prior_year_actual"] = float(row.prior_year_actual) if row.prior_year_actual is not None else None

    # Get OTB, prior year OTB, and budget for future dates
    future_data_query = """
        SELECT
            ps.stay_date as forecast_date,
            ps.otb_value as current_otb,
            ps.prior_year_otb,
            ps.prior_year_final,
            db.budget_value
        FROM pickup_snapshots ps
        LEFT JOIN daily_budgets db ON ps.stay_date = db.date AND db.budget_type = ps.metric_type
        WHERE ps.stay_date BETWEEN :from_date AND :to_date
            AND ps.metric_type = :metric
            AND ps.snapshot_date = CURRENT_DATE
    """

    future_result = await db.execute(text(future_data_query), {
        "from_date": from_date,
        "to_date": to_date,
        "metric": metric
    })
    future_rows = future_result.fetchall()

    for row in future_rows:
        date_str = str(row.forecast_date)
        if date_str in comparison:
            if comparison[date_str]["current_otb"] is None:
                comparison[date_str]["current_otb"] = float(row.current_otb) if row.current_otb is not None else None
            if comparison[date_str]["budget"] is None:
                comparison[date_str]["budget"] = float(row.budget_value) if row.budget_value is not None else None
            # Add prior year OTB for pace comparison (0 is valid - means no bookings at that lead time)
            comparison[date_str]["prior_year_otb"] = float(row.prior_year_otb) if row.prior_year_otb is not None else None
            # Prior year final is the actual from 52 weeks ago
            if comparison[date_str]["prior_year_actual"] is None and row.prior_year_final is not None:
                comparison[date_str]["prior_year_actual"] = float(row.prior_year_final)

    # Now get forecasts to overlay
    forecasts_query = """
        SELECT
            f.forecast_date,
            f.model_type,
            f.predicted_value,
            f.lower_bound,
            f.upper_bound
        FROM forecasts f
        WHERE f.forecast_date BETWEEN :from_date AND :to_date
            AND f.forecast_type = :metric
        ORDER BY f.forecast_date, f.model_type
    """

    forecasts_result = await db.execute(text(forecasts_query), {
        "from_date": from_date,
        "to_date": to_date,
        "metric": metric
    })
    forecast_rows = forecasts_result.fetchall()

    for row in forecast_rows:
        date_str = str(row.forecast_date)
        if date_str in comparison:
            comparison[date_str]["models"][row.model_type] = {
                "value": float(row.predicted_value) if row.predicted_value else None,
                "lower": float(row.lower_bound) if row.lower_bound else None,
                "upper": float(row.upper_bound) if row.upper_bound else None
            }

    return list(comparison.values())


async def _run_forecast_in_background(
    horizon_days: int,
    start_days: int,
    models: List[str],
    triggered_by: str
):
    """Background task to run forecast generation"""
    from jobs.forecast_daily import run_daily_forecast
    await run_daily_forecast(
        horizon_days=horizon_days,
        start_days=start_days,
        models=models,
        triggered_by=triggered_by
    )


@router.post("/regenerate")
async def regenerate_forecasts(
    background_tasks: BackgroundTasks,
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    models: Optional[List[str]] = Query(None, description="Models to run: prophet, xgboost, pickup, catboost"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Force regenerate forecasts for a date range.
    Triggers an immediate forecast run outside the schedule.
    """
    if from_date is None:
        from_date = date.today()
    if to_date is None:
        to_date = from_date + timedelta(days=14)

    start_days = (from_date - date.today()).days
    horizon_days = (to_date - date.today()).days
    models_to_run = models or ['prophet', 'xgboost', 'pickup', 'catboost']

    # Run forecast in background
    background_tasks.add_task(
        _run_forecast_in_background,
        horizon_days=horizon_days,
        start_days=start_days,
        models=models_to_run,
        triggered_by=f"api:manual:{current_user.get('username', 'unknown')}"
    )

    return {
        "status": "triggered",
        "from_date": from_date,
        "to_date": to_date,
        "models": models_to_run,
        "message": "Forecast regeneration started in background"
    }


@router.get("/metrics")
async def get_forecast_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of all available forecast metrics with their configuration.
    """
    query = """
        SELECT
            metric_code,
            metric_name,
            category,
            unit,
            use_prophet,
            use_xgboost,
            use_pickup,
            is_derived,
            display_order,
            show_in_dashboard,
            decimal_places
        FROM forecast_metrics
        WHERE is_active = TRUE
        ORDER BY display_order
    """

    result = await db.execute(text(query))
    rows = result.fetchall()

    return [
        {
            "metric_code": row.metric_code,
            "metric_name": row.metric_name,
            "category": row.category,
            "unit": row.unit,
            "models": {
                "prophet": row.use_prophet,
                "xgboost": row.use_xgboost,
                "pickup": row.use_pickup
            },
            "is_derived": row.is_derived,
            "display_order": row.display_order,
            "show_in_dashboard": row.show_in_dashboard,
            "decimal_places": row.decimal_places
        }
        for row in rows
    ]


# ============================================
# LIVE PREVIEW ENDPOINTS (No Logging)
# ============================================

# ============================================
# LIVE PROPHET ENDPOINT
# ============================================

class ProphetDataPoint(BaseModel):
    date: str
    day_of_week: str
    current_otb: Optional[float]
    prior_year_otb: Optional[float]
    forecast: Optional[float]
    forecast_lower: Optional[float]
    forecast_upper: Optional[float]
    prior_year_final: Optional[float]


class ProphetSummary(BaseModel):
    otb_total: float
    prior_otb_total: float
    forecast_total: float
    prior_final_total: float
    days_count: int
    days_forecasting_more: int
    days_forecasting_less: int


class ProphetResponse(BaseModel):
    data: List[ProphetDataPoint]
    summary: ProphetSummary


@router.get("/prophet-preview", response_model=ProphetResponse)
async def get_prophet_preview(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    metric: str = Query("occupancy", description="Metric: occupancy or rooms"),
    perception_date: Optional[str] = Query(None, description="Optional: Generate forecast as if it was this date (YYYY-MM-DD) for backtesting"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Live forecast using Prophet model.
    Trains on historical d0 (final) values and forecasts future dates.
    No logging or persistence - pure read-only preview.

    If perception_date is provided, generates forecast as if it was that date,
    training only on data available at that time (for backtesting).
    """
    from datetime import datetime
    from prophet import Prophet
    import pandas as pd
    import warnings
    warnings.filterwarnings('ignore')

    # Validate dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    # Use perception_date if provided, otherwise use actual today
    actual_today = date.today()
    if perception_date:
        try:
            today = datetime.strptime(perception_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid perception_date format. Use YYYY-MM-DD")
    else:
        today = actual_today

    is_backtest = perception_date is not None

    # Get default bookable cap (used as fallback for dates without specific data)
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
        raise HTTPException(status_code=400, detail="Insufficient historical data for Prophet model")

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
        max_year = end.year + 1
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
        # Log but don't fail if special dates can't be loaded
        import logging
        logging.warning(f"Could not load special dates for Prophet: {e}")

    model.fit(df)

    # Create future dataframe for forecast period
    future_dates = []
    current_date = start
    while current_date <= end:
        if (current_date - today).days >= 0:
            future_dates.append({"ds": current_date})
        current_date += timedelta(days=1)

    if not future_dates:
        return ProphetResponse(
            data=[],
            summary=ProphetSummary(
                otb_total=0,
                forecast_total=0,
                prior_final_total=0,
                days_count=0
            )
        )

    future_df = pd.DataFrame(future_dates)

    # Add floor/cap for logistic growth predictions (must match training cap)
    future_df["floor"] = 0
    future_df["cap"] = training_cap

    forecast = model.predict(future_df)

    # Get current OTB and prior year data for each date
    data_points = []
    otb_total = 0.0
    prior_otb_total = 0.0
    forecast_total = 0.0
    prior_final_total = 0.0
    days_forecasting_more = 0
    days_forecasting_less = 0

    for _, row in forecast.iterrows():
        forecast_date = row["ds"].date()
        lead_days = (forecast_date - today).days
        lead_col = get_lead_time_column(lead_days)
        prior_year_date = forecast_date - timedelta(days=364)
        day_of_week = forecast_date.strftime("%a")

        # OTB only applies to room-based metrics (occupancy, rooms, guests)
        is_room_based = metric in ('occupancy', 'rooms')

        # Get current OTB (only for room-based metrics)
        current_otb = None
        prior_otb = None
        if is_room_based:
            if is_backtest:
                # In backtest mode, get "current" OTB from booking_pace at that lead time
                current_otb_query = text(f"""
                    SELECT {lead_col} as current_otb
                    FROM newbook_booking_pace
                    WHERE arrival_date = :arrival_date
                """)
                current_result = await db.execute(current_otb_query, {"arrival_date": forecast_date})
                current_row = current_result.fetchone()
            else:
                # Normal mode: get current OTB from bookings_stats
                current_query = text("""
                    SELECT booking_count as current_otb
                    FROM newbook_bookings_stats
                    WHERE date = :arrival_date
                """)
                current_result = await db.execute(current_query, {"arrival_date": forecast_date})
                current_row = current_result.fetchone()

            # Get prior year OTB from booking_pace
            prior_year_for_otb = forecast_date - timedelta(days=364)
            prior_otb_query = text(f"""
                SELECT {lead_col} as prior_otb
                FROM newbook_booking_pace
                WHERE arrival_date = :prior_date
            """)
            prior_otb_result = await db.execute(prior_otb_query, {"prior_date": prior_year_for_otb})
            prior_otb_row = prior_otb_result.fetchone()

            current_otb = current_row.current_otb if current_row and current_row.current_otb is not None else 0
            prior_otb = prior_otb_row.prior_otb if prior_otb_row and prior_otb_row.prior_otb is not None else None

        # Get prior year final using metric mapping
        prior_query = f"""
            SELECT {col_expr} as prior_final
            {from_clause}
            WHERE s.date = :prior_date
        """
        prior_result = await db.execute(text(prior_query), {"prior_date": prior_year_date})
        prior_row = prior_result.fetchone()
        prior_final = float(prior_row.prior_final) if prior_row and prior_row.prior_final is not None else 0

        # Get per-date bookable cap for room-based metrics
        date_bookable_cap = await get_bookable_cap(db, forecast_date, default_bookable_cap)

        # Convert to occupancy if needed
        if metric == "occupancy" and date_bookable_cap > 0:
            if current_otb is not None:
                current_otb = (current_otb / date_bookable_cap) * 100
            if prior_otb is not None:
                prior_otb = (prior_otb / date_bookable_cap) * 100

        # Get Prophet forecast values
        yhat = row["yhat"]
        yhat_lower = row["yhat_lower"]
        yhat_upper = row["yhat_upper"]

        # Cap at max capacity based on metric type (uses per-date bookable cap)
        if is_pct_metric:
            yhat = min(yhat, 100.0)
            yhat_upper = min(yhat_upper, 100.0)
        elif metric == 'rooms':
            yhat = min(yhat, float(date_bookable_cap))
            yhat_upper = min(yhat_upper, float(date_bookable_cap))
        # Guests and revenue/rate metrics don't have a hard cap

        # Floor forecast to current OTB if we have it (room-based metrics only)
        # But never exceed the bookable capacity (e.g., closed/maintenance periods)
        if is_room_based and current_otb is not None and yhat < current_otb:
            yhat = min(current_otb, float(date_bookable_cap))
            yhat_lower = min(current_otb, float(date_bookable_cap))

        if current_otb is not None:
            otb_total += current_otb
        if prior_otb is not None:
            prior_otb_total += prior_otb
        forecast_total += yhat
        if prior_final is not None:
            prior_final_total += prior_final
            # Count days forecasting more/less vs prior year final
            if yhat > prior_final:
                days_forecasting_more += 1
            elif yhat < prior_final:
                days_forecasting_less += 1

        data_points.append(ProphetDataPoint(
            date=str(forecast_date),
            day_of_week=day_of_week,
            current_otb=round(current_otb, 1) if current_otb is not None else None,
            prior_year_otb=round(prior_otb, 1) if prior_otb is not None else None,
            forecast=round(yhat, 1),
            forecast_lower=round(yhat_lower, 1),
            forecast_upper=round(yhat_upper, 1),
            prior_year_final=round(prior_final, 1) if prior_final is not None else None
        ))

    # For occupancy (percentage), show averages; for rooms/guests (counts), show sums
    days_count = len(data_points)
    if metric == "occupancy" and days_count > 0:
        return ProphetResponse(
            data=data_points,
            summary=ProphetSummary(
                otb_total=round(otb_total / days_count, 1),
                prior_otb_total=round(prior_otb_total / days_count, 1) if prior_otb_total > 0 else 0,
                forecast_total=round(forecast_total / days_count, 1),
                prior_final_total=round(prior_final_total / days_count, 1) if prior_final_total > 0 else 0,
                days_count=days_count,
                days_forecasting_more=days_forecasting_more,
                days_forecasting_less=days_forecasting_less
            )
        )
    else:
        return ProphetResponse(
            data=data_points,
            summary=ProphetSummary(
                otb_total=round(otb_total, 1),
                prior_otb_total=round(prior_otb_total, 1),
                forecast_total=round(forecast_total, 1),
                prior_final_total=round(prior_final_total, 1),
                days_count=days_count,
                days_forecasting_more=days_forecasting_more,
                days_forecasting_less=days_forecasting_less
            )
        )


# ============================================
# LIVE XGBOOST ENDPOINT
# ============================================

class XGBoostDataPoint(BaseModel):
    date: str
    day_of_week: str
    current_otb: Optional[float]
    prior_year_otb: Optional[float]
    forecast: Optional[float]
    prior_year_final: Optional[float]


class XGBoostSummary(BaseModel):
    otb_total: float
    prior_otb_total: float
    forecast_total: float
    prior_final_total: float
    days_count: int
    days_forecasting_more: int
    days_forecasting_less: int


class XGBoostResponse(BaseModel):
    data: List[XGBoostDataPoint]
    summary: XGBoostSummary


@router.get("/xgboost-preview", response_model=XGBoostResponse)
async def get_xgboost_preview(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    metric: str = Query("occupancy", description="Metric: occupancy or rooms"),
    perception_date: Optional[str] = Query(None, description="Optional: Generate forecast as if it was this date (YYYY-MM-DD) for backtesting"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Live forecast using XGBoost model.
    Trains on historical d0 (final) values and forecasts future dates.
    Uses lag features from prior year same DOW.
    No logging or persistence - pure read-only preview.

    If perception_date is provided, generates forecast as if it was that date,
    training only on data available at that time (for backtesting).
    """
    from datetime import datetime
    import pandas as pd
    import numpy as np
    from xgboost import XGBRegressor
    import warnings
    warnings.filterwarnings('ignore')

    # Validate dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    # Use perception_date if provided, otherwise use actual today
    actual_today = date.today()
    if perception_date:
        try:
            today = datetime.strptime(perception_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid perception_date format. Use YYYY-MM-DD")
    else:
        today = actual_today

    is_backtest = perception_date is not None

    # Get default bookable cap (used as fallback for dates without specific data)
    default_bookable_cap = await get_bookable_cap(db)

    # Get metric column and query parts
    col_expr, from_clause, is_pct_metric = get_metric_query_parts(metric)
    is_room_based = metric in ('occupancy', 'rooms')

    # Get historical data for XGBoost training (past 2 years)
    history_start = today - timedelta(days=730)

    # Lead times to train on (key intervals) - only used for room-based metrics
    train_lead_times = [0, 1, 3, 7, 14, 21, 28, 30]

    # Get final values (and pace data for room-based metrics)
    if is_room_based:
        history_result = await db.execute(text("""
            SELECT s.date as ds, s.booking_count as final,
                   p.d0, p.d1, p.d3, p.d7, p.d14, p.d21, p.d28, p.d30
            FROM newbook_bookings_stats s
            LEFT JOIN newbook_booking_pace p ON s.date = p.arrival_date
            WHERE s.date >= :history_start
            AND s.date < :today
            AND s.booking_count IS NOT NULL
            ORDER BY s.date
        """), {"history_start": history_start, "today": today})
    else:
        # Non-room metrics: get values without pace join
        history_query = f"""
            SELECT s.date as ds, {col_expr} as final
            {from_clause}
            WHERE s.date >= :history_start
            AND s.date < :today
            AND {col_expr} IS NOT NULL
            ORDER BY s.date
        """
        history_result = await db.execute(text(history_query), {"history_start": history_start, "today": today})
    history_rows = history_result.fetchall()

    if len(history_rows) < 30:
        raise HTTPException(status_code=400, detail="Insufficient historical data for XGBoost model")

    # Load special dates for feature
    special_date_set = set()
    try:
        special_dates_result = await db.execute(text(
            "SELECT * FROM special_dates WHERE is_active = TRUE"
        ))
        special_dates_rows = special_dates_result.fetchall()
        years_needed = set(r.ds.year for r in history_rows) | {today.year, today.year + 1}
        for row in special_dates_rows:
            sd = {
                'pattern_type': row.pattern_type,
                'fixed_month': row.fixed_month,
                'fixed_day': row.fixed_day,
                'nth_week': row.nth_week,
                'weekday': row.weekday,
                'month': row.month,
                'relative_to_month': row.relative_to_month,
                'relative_to_day': row.relative_to_day,
                'relative_weekday': row.relative_weekday,
                'relative_direction': row.relative_direction,
                'duration_days': row.duration_days,
                'is_recurring': row.is_recurring,
                'one_off_year': row.one_off_year
            }
            for year in years_needed:
                resolved_dates = resolve_special_date(sd, year)
                for d in resolved_dates:
                    special_date_set.add(d)
    except Exception:
        pass

    # Build lookup dicts
    final_by_date = {}
    pace_by_date = {}
    for row in history_rows:
        final_by_date[row.ds] = row.final
        if is_room_based and hasattr(row, 'd0'):
            pace_by_date[row.ds] = {
                0: row.d0, 1: row.d1, 3: row.d3, 7: row.d7,
                14: row.d14, 21: row.d21, 28: row.d28, 30: row.d30
            }

    # Build training examples
    training_rows = []

    if is_room_based:
        # Room-based metrics: use pace features (one per date,lead_time combo)
        for row in history_rows:
            ds = row.ds
            final = float(row.final) if row.final else 0
            prior_ds = ds - timedelta(days=364)

            prior_final = final_by_date.get(prior_ds)
            if prior_final is None:
                continue

            for lead_time in train_lead_times:
                current_otb = pace_by_date.get(ds, {}).get(lead_time)
                if current_otb is None:
                    continue

                prior_otb = pace_by_date.get(prior_ds, {}).get(lead_time)
                if prior_otb is None:
                    prior_otb = 0

                otb_pct_of_prior_final = (float(current_otb) / float(prior_final) * 100) if prior_final > 0 else 0

                training_rows.append({
                    'ds': ds,
                    'y': final,
                    'days_out': lead_time,
                    'current_otb': float(current_otb),
                    'prior_otb_same_lead': float(prior_otb),
                    'lag_364': float(prior_final),
                    'otb_pct_of_prior_final': otb_pct_of_prior_final
                })
    else:
        # Non-room metrics: use time features only (one per date)
        for row in history_rows:
            ds = row.ds
            final = float(row.final) if row.final else 0
            prior_ds = ds - timedelta(days=364)

            prior_final = final_by_date.get(prior_ds)
            if prior_final is None:
                prior_final = 0  # Allow training even without prior year for revenue metrics

            training_rows.append({
                'ds': ds,
                'y': final,
                'lag_364': float(prior_final) if prior_final else 0
            })

    if len(training_rows) < 30:
        raise HTTPException(status_code=400, detail="Insufficient data for XGBoost training")

    df = pd.DataFrame(training_rows)
    df['ds'] = pd.to_datetime(df['ds'])

    # Convert to occupancy if needed
    if metric == "occupancy" and default_bookable_cap > 0:
        df["y"] = (df["y"] / default_bookable_cap) * 100
        if "current_otb" in df.columns:
            df["current_otb"] = (df["current_otb"] / default_bookable_cap) * 100
        if "prior_otb_same_lead" in df.columns:
            df["prior_otb_same_lead"] = (df["prior_otb_same_lead"] / default_bookable_cap) * 100
        df["lag_364"] = (df["lag_364"] / default_bookable_cap) * 100

    # Create time-based features
    df['day_of_week'] = df['ds'].dt.dayofweek
    df['month'] = df['ds'].dt.month
    df['week_of_year'] = df['ds'].dt.isocalendar().week.astype(int)
    df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
    df['is_special_date'] = df['ds'].dt.date.apply(lambda x: 1 if x in special_date_set else 0)

    df_train = df.dropna()

    if len(df_train) < 30:
        raise HTTPException(status_code=400, detail="Insufficient data after creating features")

    # Define features based on metric type
    if is_room_based:
        feature_cols = ['day_of_week', 'month', 'week_of_year', 'is_weekend', 'is_special_date',
                       'days_out', 'current_otb', 'prior_otb_same_lead', 'lag_364', 'otb_pct_of_prior_final']
    else:
        feature_cols = ['day_of_week', 'month', 'week_of_year', 'is_weekend', 'is_special_date', 'lag_364']

    X_train = df_train[feature_cols]
    y_train = df_train['y']

    # Train XGBoost model
    model = XGBRegressor(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        objective='reg:squarederror',
        random_state=42,
        n_jobs=-1
    )
    model.fit(X_train, y_train)

    # Create future dataframe for forecast period
    future_dates = []
    current_date = start
    while current_date <= end:
        if (current_date - today).days >= 0:
            future_dates.append(current_date)
        current_date += timedelta(days=1)

    if not future_dates:
        return XGBoostResponse(
            data=[],
            summary=XGBoostSummary(
                otb_total=0, prior_otb_total=0, forecast_total=0,
                prior_final_total=0, days_count=0,
                days_forecasting_more=0, days_forecasting_less=0
            )
        )

    # Get current OTB and prior year data for each date
    data_points = []
    otb_total = 0.0
    prior_otb_total = 0.0
    forecast_total = 0.0
    prior_final_total = 0.0
    days_forecasting_more = 0
    days_forecasting_less = 0

    for forecast_date in future_dates:
        lead_days = (forecast_date - today).days
        lead_col = get_lead_time_column(lead_days)
        prior_year_date = forecast_date - timedelta(days=364)
        day_of_week = forecast_date.strftime("%a")

        # Get OTB data only for room-based metrics
        current_otb = None
        prior_otb = None

        if is_room_based:
            if is_backtest:
                current_otb_query = text(f"""
                    SELECT {lead_col} as current_otb
                    FROM newbook_booking_pace
                    WHERE arrival_date = :arrival_date
                """)
                current_result = await db.execute(current_otb_query, {"arrival_date": forecast_date})
                current_row = current_result.fetchone()
            else:
                current_query = text("""
                    SELECT booking_count as current_otb
                    FROM newbook_bookings_stats
                    WHERE date = :arrival_date
                """)
                current_result = await db.execute(current_query, {"arrival_date": forecast_date})
                current_row = current_result.fetchone()

            prior_year_for_otb = forecast_date - timedelta(days=364)
            prior_otb_query = text(f"""
                SELECT {lead_col} as prior_otb
                FROM newbook_booking_pace
                WHERE arrival_date = :prior_date
            """)
            prior_otb_result = await db.execute(prior_otb_query, {"prior_date": prior_year_for_otb})
            prior_otb_row = prior_otb_result.fetchone()

            current_otb = current_row.current_otb if current_row and current_row.current_otb is not None else 0
            prior_otb = prior_otb_row.prior_otb if prior_otb_row and prior_otb_row.prior_otb is not None else None

        # Get prior year final using metric mapping
        prior_query = f"""
            SELECT {col_expr} as prior_final
            {from_clause}
            WHERE s.date = :prior_date
        """
        prior_result = await db.execute(text(prior_query), {"prior_date": prior_year_date})
        prior_row = prior_result.fetchone()
        prior_final = float(prior_row.prior_final) if prior_row and prior_row.prior_final is not None else 0

        # Get per-date bookable cap for this forecast date
        date_bookable_cap = await get_bookable_cap(db, forecast_date, default_bookable_cap)

        # Build features for this date
        forecast_dt = pd.Timestamp(forecast_date)
        lag_364_val = prior_final if prior_final else 0

        # Convert to occupancy if needed
        if metric == "occupancy" and date_bookable_cap > 0:
            if current_otb is not None:
                current_otb = (current_otb / date_bookable_cap) * 100
            if prior_otb is not None:
                prior_otb = (prior_otb / date_bookable_cap) * 100
            lag_364_val = (prior_final / date_bookable_cap) * 100 if prior_final else 0

        # Build features based on metric type
        if is_room_based:
            prior_otb_same_lead = prior_otb if prior_otb is not None else 0
            current_otb_val = current_otb if current_otb is not None else 0
            otb_pct_of_prior_final = (current_otb_val / lag_364_val * 100) if lag_364_val > 0 else 0

            features = pd.DataFrame([{
                'day_of_week': forecast_dt.dayofweek,
                'month': forecast_dt.month,
                'week_of_year': forecast_dt.isocalendar().week,
                'is_weekend': 1 if forecast_dt.dayofweek >= 5 else 0,
                'is_special_date': 1 if forecast_date in special_date_set else 0,
                'days_out': lead_days,
                'current_otb': current_otb_val,
                'prior_otb_same_lead': prior_otb_same_lead,
                'lag_364': lag_364_val,
                'otb_pct_of_prior_final': otb_pct_of_prior_final,
            }])
        else:
            features = pd.DataFrame([{
                'day_of_week': forecast_dt.dayofweek,
                'month': forecast_dt.month,
                'week_of_year': forecast_dt.isocalendar().week,
                'is_weekend': 1 if forecast_dt.dayofweek >= 5 else 0,
                'is_special_date': 1 if forecast_date in special_date_set else 0,
                'lag_364': lag_364_val,
            }])

        # Predict
        yhat = float(model.predict(features)[0])

        # Cap at max capacity based on metric type (uses per-date bookable cap)
        if is_pct_metric:
            yhat = min(max(yhat, 0), 100.0)
        elif metric == 'rooms':
            yhat = round(min(max(yhat, 0), float(date_bookable_cap)))
        elif metric == 'guests':
            yhat = round(max(yhat, 0))
        else:
            # Revenue/rate metrics: just ensure non-negative
            yhat = max(yhat, 0)

        # Floor forecast to current OTB (room-based only)
        if is_room_based and current_otb is not None and yhat < current_otb:
            yhat = current_otb

        if current_otb is not None:
            otb_total += current_otb
        if prior_otb is not None:
            prior_otb_total += prior_otb
        forecast_total += yhat
        if prior_final is not None:
            prior_final_total += prior_final
            if yhat > prior_final:
                days_forecasting_more += 1
            elif yhat < prior_final:
                days_forecasting_less += 1

        # Round to 1 decimal for occupancy %, whole numbers for room counts
        if metric == "occupancy":
            data_points.append(XGBoostDataPoint(
                date=str(forecast_date),
                day_of_week=day_of_week,
                current_otb=round(current_otb, 1) if current_otb is not None else None,
                prior_year_otb=round(prior_otb, 1) if prior_otb is not None else None,
                forecast=round(yhat, 1),
                prior_year_final=round(prior_final, 1) if prior_final is not None else None
            ))
        else:
            data_points.append(XGBoostDataPoint(
                date=str(forecast_date),
                day_of_week=day_of_week,
                current_otb=round(current_otb) if current_otb is not None else None,
                prior_year_otb=round(prior_otb) if prior_otb is not None else None,
                forecast=round_towards_reference(yhat, prior_final),
                prior_year_final=round(prior_final) if prior_final is not None else None
            ))

    # For occupancy (percentage), show averages; for rooms/guests (counts), show sums
    days_count = len(data_points)
    if metric == "occupancy" and days_count > 0:
        return XGBoostResponse(
            data=data_points,
            summary=XGBoostSummary(
                otb_total=round(otb_total / days_count, 1),
                prior_otb_total=round(prior_otb_total / days_count, 1) if prior_otb_total > 0 else 0,
                forecast_total=round(forecast_total / days_count, 1),
                prior_final_total=round(prior_final_total / days_count, 1) if prior_final_total > 0 else 0,
                days_count=days_count,
                days_forecasting_more=days_forecasting_more,
                days_forecasting_less=days_forecasting_less
            )
        )
    else:
        return XGBoostResponse(
            data=data_points,
            summary=XGBoostSummary(
                otb_total=round(otb_total),
                prior_otb_total=round(prior_otb_total),
                forecast_total=round(forecast_total),
                prior_final_total=round(prior_final_total),
                days_count=days_count,
                days_forecasting_more=days_forecasting_more,
                days_forecasting_less=days_forecasting_less
            )
        )


# ============================================
# LIVE CHRONOS ENDPOINT
# ============================================
# LIVE CATBOOST ENDPOINT
# ============================================


class CatBoostDataPoint(BaseModel):
    date: str
    day_of_week: str
    current_otb: Optional[float] = None
    prior_year_otb: Optional[float] = None
    forecast: Optional[float] = None
    prior_year_final: Optional[float] = None


class CatBoostSummary(BaseModel):
    otb_total: float
    prior_otb_total: float
    forecast_total: float
    prior_final_total: float
    days_count: int
    days_forecasting_more: int
    days_forecasting_less: int


class CatBoostResponse(BaseModel):
    data: List[CatBoostDataPoint]
    summary: CatBoostSummary


@router.get("/catboost-preview", response_model=CatBoostResponse)
async def get_catboost_preview(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    metric: str = Query("occupancy", description="Metric: occupancy or room-nights"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Live forecast using CatBoost model.
    Gradient boosting with native categorical feature support.
    Similar to XGBoost but handles categories natively without encoding.
    Uses same features: OTB, prior year, holidays, day-of-week.
    """
    from datetime import datetime
    import pandas as pd
    import numpy as np
    from catboost import CatBoostRegressor
    import warnings
    warnings.filterwarnings('ignore')

    # Validate dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    today = date.today()

    # Get default bookable cap
    default_bookable_cap = await get_bookable_cap(db)

    # Get metric column and query parts
    col_expr, from_clause, is_pct_metric = get_metric_query_parts(metric)
    is_room_based = metric in ('occupancy', 'rooms')

    # Get historical data (2+ years for YoY features)
    history_start = today - timedelta(days=730)

    # Lead times to train on (only used for room-based metrics)
    train_lead_times = [0, 1, 3, 7, 14, 21, 28, 30]

    # Get final values (and pace data for room-based metrics)
    if is_room_based:
        history_result = await db.execute(text("""
            SELECT s.date as ds, s.booking_count as final,
                   p.d0, p.d1, p.d3, p.d7, p.d14, p.d21, p.d28, p.d30
            FROM newbook_bookings_stats s
            LEFT JOIN newbook_booking_pace p ON s.date = p.arrival_date
            WHERE s.date >= :history_start
            AND s.date < :today
            AND s.booking_count IS NOT NULL
            ORDER BY s.date
        """), {"history_start": history_start, "today": today})
    else:
        # Non-room metrics: get values without pace join
        history_query = f"""
            SELECT s.date as ds, {col_expr} as final
            {from_clause}
            WHERE s.date >= :history_start
            AND s.date < :today
            AND {col_expr} IS NOT NULL
            ORDER BY s.date
        """
        history_result = await db.execute(text(history_query), {"history_start": history_start, "today": today})
    history_rows = history_result.fetchall()

    if len(history_rows) < 30:
        raise HTTPException(status_code=400, detail="Insufficient historical data for CatBoost model")

    # Load special dates for feature
    special_date_set = set()
    try:
        special_dates_result = await db.execute(text(
            "SELECT * FROM special_dates WHERE is_active = TRUE"
        ))
        special_dates_rows = special_dates_result.fetchall()
        years_needed = set(r.ds.year for r in history_rows) | {today.year, today.year + 1}
        for row in special_dates_rows:
            sd = {
                'pattern_type': row.pattern_type,
                'fixed_month': row.fixed_month,
                'fixed_day': row.fixed_day,
                'nth_week': row.nth_week,
                'weekday': row.weekday,
                'month': row.month,
                'relative_to_month': row.relative_to_month,
                'relative_to_day': row.relative_to_day,
                'relative_weekday': row.relative_weekday,
                'relative_direction': row.relative_direction,
                'duration_days': row.duration_days,
                'is_recurring': row.is_recurring,
                'one_off_year': row.one_off_year
            }
            for year in years_needed:
                resolved_dates = resolve_special_date(sd, year)
                for d in resolved_dates:
                    special_date_set.add(d)
    except Exception:
        pass

    # Build lookup dicts
    final_by_date = {}
    pace_by_date = {}
    for row in history_rows:
        final_by_date[row.ds] = row.final
        if is_room_based and hasattr(row, 'd0'):
            pace_by_date[row.ds] = {
                0: row.d0, 1: row.d1, 3: row.d3, 7: row.d7,
                14: row.d14, 21: row.d21, 28: row.d28, 30: row.d30
            }

    # Build training examples
    training_rows = []

    if is_room_based:
        # Room-based metrics: use pace features (one per date,lead_time combo)
        for row in history_rows:
            ds = row.ds
            final = float(row.final) if row.final else 0
            prior_ds = ds - timedelta(days=364)

            prior_final = final_by_date.get(prior_ds)
            if prior_final is None:
                continue

            for lead_time in train_lead_times:
                current_otb = pace_by_date.get(ds, {}).get(lead_time)
                if current_otb is None:
                    continue

                prior_otb = pace_by_date.get(prior_ds, {}).get(lead_time)
                if prior_otb is None:
                    prior_otb = 0

                otb_pct_of_prior_final = (float(current_otb) / float(prior_final) * 100) if prior_final > 0 else 0

                training_rows.append({
                    'ds': ds,
                    'y': final,
                    'days_out': lead_time,
                    'current_otb': float(current_otb),
                    'prior_otb_same_lead': float(prior_otb),
                    'lag_364': float(prior_final),
                    'otb_pct_of_prior_final': otb_pct_of_prior_final
                })
    else:
        # Non-room metrics: use time features only (one per date)
        for row in history_rows:
            ds = row.ds
            final = float(row.final) if row.final else 0
            prior_ds = ds - timedelta(days=364)

            prior_final = final_by_date.get(prior_ds)
            if prior_final is None:
                prior_final = 0  # Allow training even without prior year for revenue metrics

            training_rows.append({
                'ds': ds,
                'y': final,
                'lag_364': float(prior_final) if prior_final else 0
            })

    if len(training_rows) < 30:
        raise HTTPException(status_code=400, detail="Insufficient data for CatBoost training")

    df = pd.DataFrame(training_rows)
    df['ds'] = pd.to_datetime(df['ds'])

    # Convert to occupancy if needed
    if metric == "occupancy" and default_bookable_cap > 0:
        df["y"] = (df["y"] / default_bookable_cap) * 100
        if "current_otb" in df.columns:
            df["current_otb"] = (df["current_otb"] / default_bookable_cap) * 100
        if "prior_otb_same_lead" in df.columns:
            df["prior_otb_same_lead"] = (df["prior_otb_same_lead"] / default_bookable_cap) * 100
        df["lag_364"] = (df["lag_364"] / default_bookable_cap) * 100

    # Create features - CatBoost handles categoricals natively
    df['day_of_week'] = df['ds'].dt.dayofweek.astype(str)  # Categorical
    df['month'] = df['ds'].dt.month.astype(str)  # Categorical
    df['week_of_year'] = df['ds'].dt.isocalendar().week.astype(int)
    df['is_weekend'] = (df['ds'].dt.dayofweek >= 5).astype(int)
    df['is_special_date'] = df['ds'].dt.date.apply(lambda x: 1 if x in special_date_set else 0)

    df_train = df.dropna()

    if len(df_train) < 30:
        raise HTTPException(status_code=400, detail="Insufficient data after creating features")

    # Define features based on metric type - categoricals handled natively by CatBoost
    categorical_features = ['day_of_week', 'month']
    if is_room_based:
        numerical_features = ['week_of_year', 'is_weekend', 'is_special_date',
                             'days_out', 'current_otb', 'prior_otb_same_lead', 'lag_364', 'otb_pct_of_prior_final']
    else:
        numerical_features = ['week_of_year', 'is_weekend', 'is_special_date', 'lag_364']
    feature_cols = categorical_features + numerical_features

    X_train = df_train[feature_cols]
    y_train = df_train['y']

    # Train CatBoost model
    model = CatBoostRegressor(
        iterations=150,
        depth=6,
        learning_rate=0.1,
        loss_function='RMSE',
        cat_features=categorical_features,
        verbose=False,
        random_seed=42
    )
    model.fit(X_train, y_train)

    # Create future dataframe for forecast period
    future_dates = []
    current_date = start
    while current_date <= end:
        if (current_date - today).days >= 0:
            future_dates.append(current_date)
        current_date += timedelta(days=1)

    if not future_dates:
        return CatBoostResponse(
            data=[],
            summary=CatBoostSummary(
                otb_total=0, prior_otb_total=0, forecast_total=0,
                prior_final_total=0, days_count=0,
                days_forecasting_more=0, days_forecasting_less=0
            )
        )

    # Generate predictions
    data_points = []
    otb_total = 0.0
    prior_otb_total = 0.0
    forecast_total = 0.0
    prior_final_total = 0.0
    days_forecasting_more = 0
    days_forecasting_less = 0

    for forecast_date in future_dates:
        lead_days = (forecast_date - today).days
        lead_col = get_lead_time_column(lead_days)
        prior_year_date = forecast_date - timedelta(days=364)
        day_of_week = forecast_date.strftime("%a")

        # Get OTB data only for room-based metrics
        current_otb = None
        prior_otb = None

        if is_room_based:
            # Get current OTB
            current_query = text("""
                SELECT booking_count as current_otb
                FROM newbook_bookings_stats
                WHERE date = :arrival_date
            """)
            current_result = await db.execute(current_query, {"arrival_date": forecast_date})
            current_row = current_result.fetchone()

            # Get prior year OTB
            prior_year_for_otb = forecast_date - timedelta(days=364)
            prior_otb_query = text(f"""
                SELECT {lead_col} as prior_otb
                FROM newbook_booking_pace
                WHERE arrival_date = :prior_date
            """)
            prior_otb_result = await db.execute(prior_otb_query, {"prior_date": prior_year_for_otb})
            prior_otb_row = prior_otb_result.fetchone()

            current_otb = current_row.current_otb if current_row and current_row.current_otb is not None else 0
            prior_otb = prior_otb_row.prior_otb if prior_otb_row and prior_otb_row.prior_otb is not None else None

        # Get prior year final using metric mapping
        prior_query = f"""
            SELECT {col_expr} as prior_final
            {from_clause}
            WHERE s.date = :prior_date
        """
        prior_result = await db.execute(text(prior_query), {"prior_date": prior_year_date})
        prior_row = prior_result.fetchone()
        prior_final = float(prior_row.prior_final) if prior_row and prior_row.prior_final is not None else 0

        # Get per-date bookable cap
        date_bookable_cap = await get_bookable_cap(db, forecast_date, default_bookable_cap)

        forecast_dt = pd.Timestamp(forecast_date)
        lag_364_val = prior_final if prior_final else 0

        # Convert to occupancy if needed
        if metric == "occupancy" and date_bookable_cap > 0:
            if current_otb is not None:
                current_otb = (current_otb / date_bookable_cap) * 100
            if prior_otb is not None:
                prior_otb = (prior_otb / date_bookable_cap) * 100
            lag_364_val = (prior_final / date_bookable_cap) * 100 if prior_final else 0

        # Build features based on metric type
        if is_room_based:
            prior_otb_same_lead = prior_otb if prior_otb is not None else 0
            current_otb_val = current_otb if current_otb is not None else 0
            otb_pct_of_prior_final = (current_otb_val / lag_364_val * 100) if lag_364_val > 0 else 0

            features = pd.DataFrame([{
                'day_of_week': str(forecast_dt.dayofweek),  # Categorical
                'month': str(forecast_dt.month),  # Categorical
                'week_of_year': forecast_dt.isocalendar().week,
                'is_weekend': 1 if forecast_dt.dayofweek >= 5 else 0,
                'is_special_date': 1 if forecast_date in special_date_set else 0,
                'days_out': lead_days,
                'current_otb': current_otb_val,
                'prior_otb_same_lead': prior_otb_same_lead,
                'lag_364': lag_364_val,
                'otb_pct_of_prior_final': otb_pct_of_prior_final,
            }])
        else:
            features = pd.DataFrame([{
                'day_of_week': str(forecast_dt.dayofweek),  # Categorical
                'month': str(forecast_dt.month),  # Categorical
                'week_of_year': forecast_dt.isocalendar().week,
                'is_weekend': 1 if forecast_dt.dayofweek >= 5 else 0,
                'is_special_date': 1 if forecast_date in special_date_set else 0,
                'lag_364': lag_364_val,
            }])

        # Predict
        yhat = float(model.predict(features)[0])

        # Cap at max capacity based on metric type (uses per-date bookable cap)
        if is_pct_metric:
            yhat = min(max(yhat, 0), 100.0)
        elif metric == 'rooms':
            yhat = round(min(max(yhat, 0), float(date_bookable_cap)))
        elif metric == 'guests':
            yhat = round(max(yhat, 0))
        else:
            # Revenue/rate metrics: just ensure non-negative
            yhat = max(yhat, 0)

        # Floor forecast to current OTB (room-based only)
        if is_room_based and current_otb is not None and yhat < current_otb:
            yhat = current_otb

        if current_otb is not None:
            otb_total += current_otb
        if prior_otb is not None:
            prior_otb_total += prior_otb
        forecast_total += yhat
        if prior_final is not None:
            prior_final_total += prior_final
            if yhat > prior_final:
                days_forecasting_more += 1
            elif yhat < prior_final:
                days_forecasting_less += 1

        if metric == "occupancy":
            data_points.append(CatBoostDataPoint(
                date=str(forecast_date),
                day_of_week=day_of_week,
                current_otb=round(current_otb, 1) if current_otb is not None else None,
                prior_year_otb=round(prior_otb, 1) if prior_otb is not None else None,
                forecast=round(yhat, 1),
                prior_year_final=round(prior_final, 1) if prior_final is not None else None
            ))
        else:
            data_points.append(CatBoostDataPoint(
                date=str(forecast_date),
                day_of_week=day_of_week,
                current_otb=round(current_otb) if current_otb is not None else None,
                prior_year_otb=round(prior_otb) if prior_otb is not None else None,
                forecast=round_towards_reference(yhat, prior_final),
                prior_year_final=round(prior_final) if prior_final is not None else None
            ))

    days_count = len(data_points)
    if metric == "occupancy" and days_count > 0:
        return CatBoostResponse(
            data=data_points,
            summary=CatBoostSummary(
                otb_total=round(otb_total / days_count, 1),
                prior_otb_total=round(prior_otb_total / days_count, 1) if prior_otb_total > 0 else 0,
                forecast_total=round(forecast_total / days_count, 1),
                prior_final_total=round(prior_final_total / days_count, 1) if prior_final_total > 0 else 0,
                days_count=days_count,
                days_forecasting_more=days_forecasting_more,
                days_forecasting_less=days_forecasting_less
            )
        )
    else:
        return CatBoostResponse(
            data=data_points,
            summary=CatBoostSummary(
                otb_total=round(otb_total),
                prior_otb_total=round(prior_otb_total),
                forecast_total=round(forecast_total),
                prior_final_total=round(prior_final_total),
                days_count=days_count,
                days_forecasting_more=days_forecasting_more,
                days_forecasting_less=days_forecasting_less
            )
        )


class PreviewDataPoint(BaseModel):
    date: str
    day_of_week: str
    lead_days: int
    current_otb: Optional[float]
    prior_year_date: str
    prior_year_dow: str
    prior_year_otb: Optional[float]
    prior_year_final: Optional[float]
    expected_pickup: Optional[float]
    forecast: Optional[float]
    pace_vs_prior_pct: Optional[float]


class PreviewSummary(BaseModel):
    otb_total: float
    forecast_total: float
    prior_otb_total: float
    prior_final_total: float
    pace_pct: Optional[float]
    days_count: int


class PreviewResponse(BaseModel):
    data: List[PreviewDataPoint]
    summary: PreviewSummary



def get_lead_time_column(lead_days: int) -> str:
    """
    Map lead days to the appropriate column in newbook_booking_pace.
    Columns: d365, d330, d300, d270, d240, d210 (monthly)
             d177-d37 in 7-day intervals (weekly)
             d30-d0 (daily)
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


# ============================================
# LIVE BLENDED FORECAST ENDPOINT
# ============================================

REVENUE_METRICS = ['net_accom', 'net_dry', 'net_wet', 'total_rev']
MODEL_WEIGHT = 0.6  # 60% from accuracy-weighted models
BUDGET_PRIOR_WEIGHT = 0.4  # 40% from budget (revenue) or prior year (other)


class BlendedDataPoint(BaseModel):
    date: str
    day_of_week: str
    current_otb: Optional[float]
    prior_year_otb: Optional[float]
    blended_forecast: Optional[float]
    prophet_forecast: Optional[float]
    xgboost_forecast: Optional[float]
    catboost_forecast: Optional[float]
    budget_or_prior: Optional[float]
    prior_year_final: Optional[float]


class BlendedSummary(BaseModel):
    otb_total: float
    prior_otb_total: float
    forecast_total: float
    prior_final_total: float
    days_count: int
    days_forecasting_more: int
    days_forecasting_less: int
    prophet_weight: float
    xgboost_weight: float
    catboost_weight: float


class BlendedResponse(BaseModel):
    data: List[BlendedDataPoint]
    summary: BlendedSummary


@router.get("/blended-preview", response_model=BlendedResponse)
async def get_blended_preview(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    metric: str = Query("occupancy", description="Metric: occupancy, rooms, net_accom, etc."),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Live blended forecast combining multiple models with accuracy-based weighting.

    For revenue metrics (net_accom, net_dry, net_wet):
    - 60% accuracy-weighted models (Prophet/XGBoost/CatBoost)
    - 40% budget target

    For other metrics (occupancy, rooms, guests, etc.):
    - 60% accuracy-weighted models
    - 40% prior year DOW-aligned actuals

    Model weights are calculated from recent accuracy (inverse MAPE).
    """
    from datetime import datetime

    # Validate dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    today = date.today()
    is_revenue_metric = metric in REVENUE_METRICS

    # Get accuracy scores for model weighting (from last 90 days)
    accuracy_query = """
        SELECT
            AVG(ABS(prophet_pct_error)) as prophet_mape,
            AVG(ABS(xgboost_pct_error)) as xgboost_mape,
            AVG(ABS(catboost_pct_error)) as catboost_mape
        FROM actual_vs_forecast
        WHERE date >= CURRENT_DATE - INTERVAL '90 days'
            AND date < CURRENT_DATE
            AND metric_type = :metric
            AND actual_value IS NOT NULL
    """
    accuracy_result = await db.execute(text(accuracy_query), {"metric": metric})
    accuracy_row = accuracy_result.fetchone()

    # Calculate inverse-MAPE weights (lower MAPE = higher weight)
    # Use default equal weights if no accuracy data
    if accuracy_row and accuracy_row.prophet_mape and accuracy_row.xgboost_mape and accuracy_row.catboost_mape:
        prophet_mape = float(accuracy_row.prophet_mape) or 10
        xgboost_mape = float(accuracy_row.xgboost_mape) or 10
        catboost_mape = float(accuracy_row.catboost_mape) or 10

        # Inverse weights (1/MAPE), normalized
        inv_prophet = 1 / max(prophet_mape, 0.1)
        inv_xgboost = 1 / max(xgboost_mape, 0.1)
        inv_catboost = 1 / max(catboost_mape, 0.1)
        total_inv = inv_prophet + inv_xgboost + inv_catboost

        prophet_weight = inv_prophet / total_inv
        xgboost_weight = inv_xgboost / total_inv
        catboost_weight = inv_catboost / total_inv
    else:
        # Equal weights if no accuracy data
        prophet_weight = 1/3
        xgboost_weight = 1/3
        catboost_weight = 1/3

    # Get forecasts from stored forecasts table
    forecasts_query = """
        SELECT
            forecast_date,
            model_type,
            predicted_value
        FROM forecasts
        WHERE forecast_date BETWEEN :start AND :end
            AND forecast_type = :metric
        ORDER BY forecast_date
    """
    forecasts_result = await db.execute(text(forecasts_query), {
        "start": start, "end": end, "metric": metric
    })
    forecasts_rows = forecasts_result.fetchall()

    # Build forecasts dict by date and model
    forecasts_by_date = {}
    for row in forecasts_rows:
        date_str = str(row.forecast_date)
        if date_str not in forecasts_by_date:
            forecasts_by_date[date_str] = {}
        forecasts_by_date[date_str][row.model_type] = float(row.predicted_value) if row.predicted_value else None

    # Try to get current OTB from pickup_snapshots (may not exist)
    otb_by_date = {}
    try:
        otb_query = """
            SELECT
                stay_date,
                otb_value,
                prior_year_otb,
                prior_year_final
            FROM pickup_snapshots
            WHERE stay_date BETWEEN :start AND :end
                AND metric_type = :metric
                AND snapshot_date = CURRENT_DATE
        """
        otb_result = await db.execute(text(otb_query), {
            "start": start, "end": end, "metric": metric
        })
        otb_rows = otb_result.fetchall()
        otb_by_date = {str(row.stay_date): row for row in otb_rows}
    except Exception:
        # Table doesn't exist or query failed - continue without OTB data
        pass

    # Get budget OR prior year data depending on metric type
    budget_prior_by_date = {}
    if is_revenue_metric:
        # Get daily budget values
        if metric == 'total_rev':
            # For total_rev, sum all three department budgets
            budget_query = """
                SELECT date, SUM(budget_value) as budget_value
                FROM daily_budgets
                WHERE date BETWEEN :start AND :end
                    AND budget_type IN ('net_accom', 'net_dry', 'net_wet')
                GROUP BY date
            """
            budget_result = await db.execute(text(budget_query), {
                "start": start, "end": end
            })
        else:
            budget_query = """
                SELECT date, budget_value
                FROM daily_budgets
                WHERE date BETWEEN :start AND :end
                    AND budget_type = :metric
            """
            budget_result = await db.execute(text(budget_query), {
                "start": start, "end": end, "metric": metric
            })
        budget_rows = budget_result.fetchall()
        budget_prior_by_date = {str(row.date): float(row.budget_value) for row in budget_rows}
    else:
        # Get prior year DOW-aligned actuals from newbook_bookings_stats
        # Calculate prior dates (364 days back for DOW alignment)
        col_expr, from_clause, _ = get_metric_query_parts(metric)
        prior_query = f"""
            SELECT s.date, {col_expr} as value
            {from_clause}
            WHERE s.date BETWEEN :prior_start AND :prior_end
                AND {col_expr} IS NOT NULL
        """
        prior_start = start - timedelta(days=364)
        prior_end = end - timedelta(days=364)
        try:
            prior_result = await db.execute(text(prior_query), {
                "prior_start": prior_start, "prior_end": prior_end
            })
            prior_rows = prior_result.fetchall()
            # Map prior dates to target dates (+364 days)
            for row in prior_rows:
                target_date = row.date + timedelta(days=364)
                if start <= target_date <= end:
                    budget_prior_by_date[str(target_date)] = float(row.value) if row.value else None
        except Exception:
            pass

    # Build response data
    data = []
    otb_total = 0
    prior_otb_total = 0
    forecast_total = 0
    prior_final_total = 0
    days_forecasting_more = 0
    days_forecasting_less = 0

    current_date = start
    while current_date <= end:
        date_str = str(current_date)
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        day_of_week = day_names[current_date.weekday()]

        # Get OTB data (may be empty if pickup_snapshots doesn't exist)
        otb_row = otb_by_date.get(date_str)
        current_otb = float(otb_row.otb_value) if otb_row and otb_row.otb_value is not None else None
        prior_year_otb = float(otb_row.prior_year_otb) if otb_row and otb_row.prior_year_otb is not None else None
        # For prior_year_final, use OTB data if available, otherwise use budget_prior_by_date for non-revenue
        prior_year_final = float(otb_row.prior_year_final) if otb_row and otb_row.prior_year_final is not None else (
            budget_prior_by_date.get(date_str) if not is_revenue_metric else None
        )

        # Get model forecasts
        date_forecasts = forecasts_by_date.get(date_str, {})
        prophet_fc = date_forecasts.get('prophet')
        xgboost_fc = date_forecasts.get('xgboost')
        catboost_fc = date_forecasts.get('catboost')
        saved_blended = date_forecasts.get('blended')  # Check for pre-generated blended forecast

        # Get budget/prior value
        budget_prior = budget_prior_by_date.get(date_str)

        # Use saved blended forecast if available, otherwise calculate on-the-fly
        blended_forecast = None
        if saved_blended is not None:
            # Use pre-generated blended forecast from snapshot (already accuracy-weighted)
            blended_forecast = saved_blended
        elif any([prophet_fc, xgboost_fc, catboost_fc]):
            # Calculate accuracy-weighted model forecast
            model_sum = 0
            weight_sum = 0
            if prophet_fc is not None:
                model_sum += prophet_fc * prophet_weight
                weight_sum += prophet_weight
            if xgboost_fc is not None:
                model_sum += xgboost_fc * xgboost_weight
                weight_sum += xgboost_weight
            if catboost_fc is not None:
                model_sum += catboost_fc * catboost_weight
                weight_sum += catboost_weight

            if weight_sum > 0:
                accuracy_weighted = model_sum / weight_sum

                # Blend with budget/prior
                if budget_prior is not None:
                    blended_forecast = (MODEL_WEIGHT * accuracy_weighted) + (BUDGET_PRIOR_WEIGHT * budget_prior)
                else:
                    # No budget/prior data - use just accuracy-weighted models
                    blended_forecast = accuracy_weighted

        # Accumulate totals
        if current_otb is not None:
            otb_total += current_otb
        if prior_year_otb is not None:
            prior_otb_total += prior_year_otb
        if blended_forecast is not None:
            forecast_total += blended_forecast
        if prior_year_final is not None:
            prior_final_total += prior_year_final
            if blended_forecast is not None:
                if blended_forecast > prior_year_final:
                    days_forecasting_more += 1
                elif blended_forecast < prior_year_final:
                    days_forecasting_less += 1

        data.append(BlendedDataPoint(
            date=date_str,
            day_of_week=day_of_week,
            current_otb=current_otb,
            prior_year_otb=prior_year_otb,
            blended_forecast=round(blended_forecast, 2) if blended_forecast else None,
            prophet_forecast=round(prophet_fc, 2) if prophet_fc else None,
            xgboost_forecast=round(xgboost_fc, 2) if xgboost_fc else None,
            catboost_forecast=round(catboost_fc, 2) if catboost_fc else None,
            budget_or_prior=round(budget_prior, 2) if budget_prior else None,
            prior_year_final=prior_year_final
        ))

        current_date += timedelta(days=1)

    return BlendedResponse(
        data=data,
        summary=BlendedSummary(
            otb_total=round(otb_total, 2),
            prior_otb_total=round(prior_otb_total, 2),
            forecast_total=round(forecast_total, 2),
            prior_final_total=round(prior_final_total, 2),
            days_count=len(data),
            days_forecasting_more=days_forecasting_more,
            days_forecasting_less=days_forecasting_less,
            prophet_weight=round(prophet_weight, 3),
            xgboost_weight=round(xgboost_weight, 3),
            catboost_weight=round(catboost_weight, 3)
        )
    )


@router.get("/preview", response_model=PreviewResponse)
async def get_forecast_preview(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    metric: str = Query("occupancy", description="Metric: occupancy or rooms"),
    perception_date: Optional[str] = Query(None, description="Optional: Generate forecast as if it was this date (YYYY-MM-DD) for backtesting"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Live forecast preview using transparent pickup model.
    Uses newbook_booking_pace table to get current OTB and prior year comparison.
    Calculates: Forecast = Current OTB + (Prior Year Final - Prior Year OTB)

    No logging or persistence - pure read-only preview.

    If perception_date is provided, generates forecast as if it was that date,
    using only data that would have been available at that time (for backtesting).

    Note: Pickup model only works for room-based metrics (occupancy, rooms, guests).
    For revenue/rate metrics, returns empty data as OTB/pace concepts don't apply.
    """
    from datetime import datetime

    # Check if metric is room-based (pickup model only works for these)
    is_room_based = metric in ('occupancy', 'rooms')
    if not is_room_based:
        # Pickup model doesn't apply to revenue/rate metrics
        return PreviewResponse(
            data=[],
            summary=PreviewSummary(
                otb_total=0,
                forecast_total=0,
                prior_otb_total=0,
                prior_final_total=0,
                pace_pct=None,
                days_count=0
            )
        )

    # Validate dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    # Use perception_date if provided, otherwise use actual today
    actual_today = date.today()
    if perception_date:
        try:
            today = datetime.strptime(perception_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid perception_date format. Use YYYY-MM-DD")
    else:
        today = actual_today

    is_backtest = perception_date is not None

    # Get default bookable cap
    default_bookable_cap = await get_bookable_cap(db)

    # Generate date range and calculate for each date
    data_points = []
    otb_total = 0.0
    forecast_total = 0.0
    prior_otb_total = 0.0
    prior_final_total = 0.0

    current_date = start
    while current_date <= end:
        lead_days = (current_date - today).days
        if lead_days < 0:
            current_date += timedelta(days=1)
            continue

        lead_col = get_lead_time_column(lead_days)
        prior_year_date = current_date - timedelta(days=364)  # 52 weeks for DOW alignment
        day_of_week = current_date.strftime("%a")

        # Get current OTB
        if is_backtest:
            # In backtest mode, get "current" OTB from booking_pace at that lead time
            current_otb_query = text(f"""
                SELECT {lead_col} as current_otb
                FROM newbook_booking_pace
                WHERE arrival_date = :arrival_date
            """)
            current_result = await db.execute(current_otb_query, {"arrival_date": current_date})
            current_row = current_result.fetchone()
        else:
            # Normal mode: get current OTB from bookings_stats (today's actual booking count)
            current_query = text("""
                SELECT booking_count as current_otb
                FROM newbook_bookings_stats
                WHERE date = :arrival_date
            """)
            current_result = await db.execute(current_query, {"arrival_date": current_date})
            current_row = current_result.fetchone()

        # Get prior year OTB from booking_pace (for lead time comparison - always uses 364-day offset)
        prior_year_for_otb = current_date - timedelta(days=364)
        prior_otb_query = text(f"""
            SELECT {lead_col} as prior_otb
            FROM newbook_booking_pace
            WHERE arrival_date = :prior_date
        """)
        prior_otb_result = await db.execute(prior_otb_query, {"prior_date": prior_year_for_otb})
        prior_otb_row = prior_otb_result.fetchone()

        # Get prior year FINAL from bookings_stats (actual booking count for that date)
        prior_final_query = text("""
            SELECT booking_count as prior_final
            FROM newbook_bookings_stats
            WHERE date = :prior_date
        """)
        prior_final_result = await db.execute(prior_final_query, {"prior_date": prior_year_date})
        prior_final_row = prior_final_result.fetchone()

        # Extract values - default to 0 for stats (no row = no bookings), None for pace (no historical tracking)
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

        # Calculate expected pickup and forecast
        expected_pickup = None
        forecast = None
        pace_vs_prior_pct = None

        if current_otb is not None:
            if prior_final is not None and prior_otb is not None:
                expected_pickup = prior_final - prior_otb
                forecast = current_otb + expected_pickup
                # Floor to current OTB if pickup is negative
                if forecast < current_otb:
                    forecast = current_otb
                    expected_pickup = 0
                # Cap at max capacity (uses per-date bookable cap)
                if metric == "occupancy" and forecast > 100:
                    forecast = 100.0
                elif metric == "rooms" and forecast > date_bookable_cap:
                    forecast = float(date_bookable_cap)
                # Calculate pace vs prior
                if prior_otb > 0:
                    pace_vs_prior_pct = ((current_otb - prior_otb) / prior_otb) * 100
            else:
                # No prior year data - use current OTB as forecast
                forecast = current_otb
                expected_pickup = 0

            otb_total += current_otb
            forecast_total += forecast if forecast else current_otb

        if prior_otb is not None:
            prior_otb_total += prior_otb
        if prior_final is not None:
            prior_final_total += prior_final

        prior_year_dow = prior_year_date.strftime("%a")

        data_points.append(PreviewDataPoint(
            date=str(current_date),
            day_of_week=day_of_week,
            lead_days=lead_days,
            current_otb=round(current_otb, 1) if current_otb is not None else None,
            prior_year_date=str(prior_year_date),
            prior_year_dow=prior_year_dow,
            prior_year_otb=round(prior_otb, 1) if prior_otb is not None else None,
            prior_year_final=round(prior_final, 1) if prior_final is not None else None,
            expected_pickup=round(expected_pickup, 1) if expected_pickup is not None else None,
            forecast=round(forecast, 1) if forecast is not None else None,
            pace_vs_prior_pct=round(pace_vs_prior_pct, 1) if pace_vs_prior_pct is not None else None
        ))

        current_date += timedelta(days=1)

    # Calculate overall pace percentage
    pace_pct = None
    if prior_otb_total > 0:
        pace_pct = round(((otb_total - prior_otb_total) / prior_otb_total) * 100, 1)

    # For occupancy (percentage), show averages; for rooms/guests (counts), show sums
    days_count = len(data_points)
    if metric == "occupancy" and days_count > 0:
        return PreviewResponse(
            data=data_points,
            summary=PreviewSummary(
                otb_total=round(otb_total / days_count, 1),
                forecast_total=round(forecast_total / days_count, 1),
                prior_otb_total=round(prior_otb_total / days_count, 1) if prior_otb_total > 0 else 0,
                prior_final_total=round(prior_final_total / days_count, 1) if prior_final_total > 0 else 0,
                pace_pct=pace_pct,
                days_count=days_count
            )
        )
    else:
        return PreviewResponse(
            data=data_points,
            summary=PreviewSummary(
                otb_total=round(otb_total, 1),
                forecast_total=round(forecast_total, 1),
                prior_otb_total=round(prior_otb_total, 1),
                prior_final_total=round(prior_final_total, 1),
                pace_pct=pace_pct,
                days_count=days_count
            )
        )


class PaceCurvePoint(BaseModel):
    days_out: int
    rooms: Optional[int]


class PaceCurveResponse(BaseModel):
    arrival_date: str
    day_of_week: str
    current_year: List[PaceCurvePoint]
    prior_year: List[PaceCurvePoint]
    final_value: Optional[int]
    prior_year_final: Optional[int]


@router.get("/pace-curve", response_model=PaceCurveResponse)
async def get_pace_curve(
    arrival_date: str = Query(..., description="Arrival date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get booking pace curve for a specific arrival date.
    Shows how bookings built up over time from 365 days out to today.
    Includes prior year same day-of-week comparison (364-day offset).
    """
    from datetime import datetime

    try:
        target_date = datetime.strptime(arrival_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Prior year same DOW (364 days = 52 weeks exactly)
    prior_year_date = target_date - timedelta(days=364)

    # Column names in order (d365 to d0)
    lead_time_columns = [
        # Monthly intervals (6)
        ("d365", 365), ("d330", 330), ("d300", 300), ("d270", 270), ("d240", 240), ("d210", 210),
        # Weekly intervals (21)
        ("d177", 177), ("d170", 170), ("d163", 163), ("d156", 156), ("d149", 149),
        ("d142", 142), ("d135", 135), ("d128", 128), ("d121", 121), ("d114", 114),
        ("d107", 107), ("d100", 100), ("d93", 93), ("d86", 86), ("d79", 79),
        ("d72", 72), ("d65", 65), ("d58", 58), ("d51", 51), ("d44", 44), ("d37", 37),
        # Daily intervals (31)
        ("d30", 30), ("d29", 29), ("d28", 28), ("d27", 27), ("d26", 26),
        ("d25", 25), ("d24", 24), ("d23", 23), ("d22", 22), ("d21", 21),
        ("d20", 20), ("d19", 19), ("d18", 18), ("d17", 17), ("d16", 16),
        ("d15", 15), ("d14", 14), ("d13", 13), ("d12", 12), ("d11", 11),
        ("d10", 10), ("d9", 9), ("d8", 8), ("d7", 7), ("d6", 6),
        ("d5", 5), ("d4", 4), ("d3", 3), ("d2", 2), ("d1", 1), ("d0", 0)
    ]

    # Build column select list
    col_names = [col[0] for col in lead_time_columns]
    col_select = ", ".join(col_names)

    # Get current year pace data
    current_query = text(f"""
        SELECT {col_select}
        FROM newbook_booking_pace
        WHERE arrival_date = :arrival_date
    """)

    current_result = await db.execute(current_query, {"arrival_date": target_date})
    current_row = current_result.fetchone()

    # Get prior year pace data
    prior_query = text(f"""
        SELECT {col_select}
        FROM newbook_booking_pace
        WHERE arrival_date = :prior_date
    """)

    prior_result = await db.execute(prior_query, {"prior_date": prior_year_date})
    prior_row = prior_result.fetchone()

    # Build response
    current_year_data = []
    prior_year_data = []

    for col_name, days_out in lead_time_columns:
        # Current year
        if current_row:
            val = getattr(current_row, col_name, None)
            current_year_data.append(PaceCurvePoint(days_out=days_out, rooms=val))
        else:
            current_year_data.append(PaceCurvePoint(days_out=days_out, rooms=None))

        # Prior year
        if prior_row:
            val = getattr(prior_row, col_name, None)
            prior_year_data.append(PaceCurvePoint(days_out=days_out, rooms=val))
        else:
            prior_year_data.append(PaceCurvePoint(days_out=days_out, rooms=None))

    # Get final values from d0 column
    final_value = getattr(current_row, 'd0', None) if current_row else None
    prior_final = getattr(prior_row, 'd0', None) if prior_row else None

    # Get day of week
    day_of_week = target_date.strftime("%a")

    return PaceCurveResponse(
        arrival_date=arrival_date,
        day_of_week=day_of_week,
        current_year=current_year_data,
        prior_year=prior_year_data,
        final_value=final_value,
        prior_year_final=prior_final
    )


# ============================================
# ACTUALS DATA ENDPOINT
# ============================================

class ActualsDataPoint(BaseModel):
    date: str
    day_of_week: str
    actual_value: Optional[float]
    prior_year_value: Optional[float]
    budget_value: Optional[float]
    otb_value: Optional[float] = None  # On-the-books revenue for future dates


class ActualsResponse(BaseModel):
    data: List[ActualsDataPoint]
    summary: dict


@router.get("/actuals", response_model=ActualsResponse)
async def get_actuals_data(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    metric: str = Query("rooms", description="Metric type"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get actual/final data for a date range with prior year and budget comparison.
    Used for the main forecast page to show actuals for past dates.

    Note: Today's actual is excluded (set to null) since the day isn't finished.
    For net_accom metric, OTB (on-the-books) values are included for today and future dates.
    """
    from datetime import datetime, date as date_type

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    today = date_type.today()
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    # Get default bookable capacity for rooms/occupancy budget calculation
    default_cap = await get_bookable_cap(db)

    # Build query based on metric type
    if metric == 'total_rev':
        # Total revenue = sum of accommodation + dry + wet
        query = text("""
            WITH date_range AS (
                SELECT generate_series(CAST(:start_date AS date), CAST(:end_date AS date), '1 day'::interval)::date as date
            ),
            actuals AS (
                SELECT date, COALESCE(accommodation, 0) + COALESCE(dry, 0) + COALESCE(wet, 0) as value
                FROM newbook_net_revenue_data
                WHERE date BETWEEN :start_date AND :end_date
            ),
            prior_year AS (
                SELECT date + interval '364 days' as target_date,
                       COALESCE(accommodation, 0) + COALESCE(dry, 0) + COALESCE(wet, 0) as value
                FROM newbook_net_revenue_data
                WHERE date BETWEEN CAST(:start_date AS date) - interval '364 days' AND CAST(:end_date AS date) - interval '364 days'
            ),
            budgets AS (
                SELECT date, SUM(budget_value) as budget_value
                FROM daily_budgets
                WHERE date BETWEEN :start_date AND :end_date
                    AND budget_type IN ('net_accom', 'net_dry', 'net_wet')
                GROUP BY date
            ),
            otb_data AS (
                SELECT date, net_booking_rev_total as otb_gross
                FROM newbook_bookings_stats
                WHERE date BETWEEN :start_date AND :end_date
            ),
            tax_rates_lookup AS (
                SELECT DISTINCT ON (dr.date) dr.date, tr.rate
                FROM date_range dr
                LEFT JOIN tax_rates tr ON tr.tax_type = 'accommodation_vat' AND tr.effective_from <= dr.date
                ORDER BY dr.date, tr.effective_from DESC
            )
            SELECT
                dr.date,
                EXTRACT(DOW FROM dr.date) as dow,
                CASE WHEN dr.date < :today THEN a.value ELSE NULL END as actual_value,
                py.value as prior_year_value,
                b.budget_value,
                CASE
                    WHEN dr.date >= :today AND o.otb_gross IS NOT NULL AND trl.rate IS NOT NULL
                    THEN ROUND(o.otb_gross / (1 + trl.rate), 2)
                    ELSE NULL
                END as otb_value
            FROM date_range dr
            LEFT JOIN actuals a ON dr.date = a.date
            LEFT JOIN prior_year py ON dr.date = py.target_date
            LEFT JOIN budgets b ON dr.date = b.date
            LEFT JOIN otb_data o ON dr.date = o.date
            LEFT JOIN tax_rates_lookup trl ON dr.date = trl.date
            ORDER BY dr.date
        """)
    elif metric in ['net_accom', 'net_dry', 'net_wet']:
        # Revenue metrics from newbook_net_revenue_data
        col_map = {'net_accom': 'accommodation', 'net_dry': 'dry', 'net_wet': 'wet'}
        col_name = col_map[metric]

        # For net_accom, also fetch OTB values from newbook_bookings_stats
        # OTB = net_booking_rev_total / (1 + vat_rate) to get net of VAT
        if metric == 'net_accom':
            query = text(f"""
                WITH date_range AS (
                    SELECT generate_series(CAST(:start_date AS date), CAST(:end_date AS date), '1 day'::interval)::date as date
                ),
                actuals AS (
                    SELECT date, {col_name} as value
                    FROM newbook_net_revenue_data
                    WHERE date BETWEEN :start_date AND :end_date
                ),
                prior_year AS (
                    SELECT date + interval '364 days' as target_date, {col_name} as value
                    FROM newbook_net_revenue_data
                    WHERE date BETWEEN CAST(:start_date AS date) - interval '364 days' AND CAST(:end_date AS date) - interval '364 days'
                ),
                budgets AS (
                    SELECT date, budget_value
                    FROM daily_budgets
                    WHERE date BETWEEN :start_date AND :end_date
                        AND budget_type = :metric
                ),
                otb_data AS (
                    SELECT date, net_booking_rev_total as otb_gross
                    FROM newbook_bookings_stats
                    WHERE date BETWEEN :start_date AND :end_date
                ),
                tax_rates_lookup AS (
                    -- Get the effective tax rate for each date in range
                    SELECT DISTINCT ON (dr.date) dr.date, tr.rate
                    FROM date_range dr
                    LEFT JOIN tax_rates tr ON tr.tax_type = 'accommodation_vat' AND tr.effective_from <= dr.date
                    ORDER BY dr.date, tr.effective_from DESC
                )
                SELECT
                    dr.date,
                    EXTRACT(DOW FROM dr.date) as dow,
                    CASE WHEN dr.date < :today THEN a.value ELSE NULL END as actual_value,
                    py.value as prior_year_value,
                    b.budget_value,
                    CASE
                        WHEN dr.date >= :today AND o.otb_gross IS NOT NULL AND trl.rate IS NOT NULL
                        THEN ROUND(o.otb_gross / (1 + trl.rate), 2)
                        ELSE NULL
                    END as otb_value
                FROM date_range dr
                LEFT JOIN actuals a ON dr.date = a.date
                LEFT JOIN prior_year py ON dr.date = py.target_date
                LEFT JOIN budgets b ON dr.date = b.date
                LEFT JOIN otb_data o ON dr.date = o.date
                LEFT JOIN tax_rates_lookup trl ON dr.date = trl.date
                ORDER BY dr.date
            """)
        else:
            # For net_dry and net_wet, no OTB data available
            query = text(f"""
                WITH date_range AS (
                    SELECT generate_series(CAST(:start_date AS date), CAST(:end_date AS date), '1 day'::interval)::date as date
                ),
                actuals AS (
                    SELECT date, {col_name} as value
                    FROM newbook_net_revenue_data
                    WHERE date BETWEEN :start_date AND :end_date
                ),
                prior_year AS (
                    SELECT date + interval '364 days' as target_date, {col_name} as value
                    FROM newbook_net_revenue_data
                    WHERE date BETWEEN CAST(:start_date AS date) - interval '364 days' AND CAST(:end_date AS date) - interval '364 days'
                ),
                budgets AS (
                    SELECT date, budget_value
                    FROM daily_budgets
                    WHERE date BETWEEN :start_date AND :end_date
                        AND budget_type = :metric
                )
                SELECT
                    dr.date,
                    EXTRACT(DOW FROM dr.date) as dow,
                    CASE WHEN dr.date < :today THEN a.value ELSE NULL END as actual_value,
                    py.value as prior_year_value,
                    b.budget_value,
                    NULL::numeric as otb_value
                FROM date_range dr
                LEFT JOIN actuals a ON dr.date = a.date
                LEFT JOIN prior_year py ON dr.date = py.target_date
                LEFT JOIN budgets b ON dr.date = b.date
                ORDER BY dr.date
            """)
    elif metric == 'occupancy':
        # Occupancy from newbook_bookings_stats
        # Budget occupancy calculated from: (net_accom_budget / ARR) / bookable_cap * 100
        query = text("""
            WITH date_range AS (
                SELECT generate_series(CAST(:start_date AS date), CAST(:end_date AS date), '1 day'::interval)::date as date
            ),
            actuals AS (
                SELECT date, total_occupancy_pct as value
                FROM newbook_bookings_stats
                WHERE date BETWEEN :start_date AND :end_date
            ),
            prior_year AS (
                SELECT date + interval '364 days' as target_date, total_occupancy_pct as value
                FROM newbook_bookings_stats
                WHERE date BETWEEN CAST(:start_date AS date) - interval '364 days' AND CAST(:end_date AS date) - interval '364 days'
            ),
            otb_data AS (
                SELECT date, total_occupancy_pct as otb
                FROM newbook_bookings_stats
                WHERE date BETWEEN :start_date AND :end_date
            ),
            budgets AS (
                SELECT date, budget_value
                FROM daily_budgets
                WHERE date BETWEEN :start_date AND :end_date
                AND budget_type = 'net_accom'
            ),
            arr_forecast AS (
                SELECT
                    target_date as date,
                    forecast_value as arr
                FROM forecast_snapshots
                WHERE target_date BETWEEN :start_date AND :end_date
                AND metric_code = 'arr'
                AND model = 'blended'
                AND perception_date = (
                    SELECT MAX(perception_date)
                    FROM forecast_snapshots
                    WHERE metric_code = 'arr' AND model = 'blended'
                )
            ),
            bookable AS (
                SELECT date, bookable_count
                FROM newbook_bookings_stats
                WHERE date BETWEEN :start_date AND :end_date
                AND bookable_count IS NOT NULL
            ),
            prior_year_pace AS (
                SELECT
                    pace.arrival_date + 364 as target_date,
                    CASE
                        WHEN CAST(:today AS date) - 364 >= pace.arrival_date THEN NULL
                        ELSE CASE (pace.arrival_date - (CAST(:today AS date) - 364))
                            WHEN 0 THEN pace.d0 WHEN 1 THEN pace.d1 WHEN 2 THEN pace.d2 WHEN 3 THEN pace.d3
                            WHEN 4 THEN pace.d4 WHEN 5 THEN pace.d5 WHEN 6 THEN pace.d6 WHEN 7 THEN pace.d7
                            WHEN 8 THEN pace.d8 WHEN 9 THEN pace.d9 WHEN 10 THEN pace.d10 WHEN 11 THEN pace.d11
                            WHEN 12 THEN pace.d12 WHEN 13 THEN pace.d13 WHEN 14 THEN pace.d14 WHEN 15 THEN pace.d15
                            WHEN 16 THEN pace.d16 WHEN 17 THEN pace.d17 WHEN 18 THEN pace.d18 WHEN 19 THEN pace.d19
                            WHEN 20 THEN pace.d20 WHEN 21 THEN pace.d21 WHEN 22 THEN pace.d22 WHEN 23 THEN pace.d23
                            WHEN 24 THEN pace.d24 WHEN 25 THEN pace.d25 WHEN 26 THEN pace.d26 WHEN 27 THEN pace.d27
                            WHEN 28 THEN pace.d28 WHEN 29 THEN pace.d29 WHEN 30 THEN pace.d30
                            WHEN 37 THEN pace.d37 WHEN 44 THEN pace.d44 WHEN 51 THEN pace.d51 WHEN 58 THEN pace.d58
                            WHEN 65 THEN pace.d65 WHEN 72 THEN pace.d72 WHEN 79 THEN pace.d79 WHEN 86 THEN pace.d86
                            WHEN 93 THEN pace.d93 WHEN 100 THEN pace.d100 WHEN 107 THEN pace.d107 WHEN 114 THEN pace.d114
                            WHEN 121 THEN pace.d121 WHEN 128 THEN pace.d128 WHEN 135 THEN pace.d135 WHEN 142 THEN pace.d142
                            WHEN 149 THEN pace.d149 WHEN 156 THEN pace.d156 WHEN 163 THEN pace.d163 WHEN 170 THEN pace.d170
                            WHEN 177 THEN pace.d177 WHEN 210 THEN pace.d210 WHEN 240 THEN pace.d240 WHEN 270 THEN pace.d270
                            WHEN 300 THEN pace.d300 WHEN 330 THEN pace.d330 WHEN 365 THEN pace.d365
                            ELSE NULL
                        END
                    END as booking_count
                FROM newbook_booking_pace pace
                WHERE pace.arrival_date BETWEEN CAST(:start_date AS date) - 364
                      AND CAST(:end_date AS date) - 364
            )
            SELECT
                dr.date,
                EXTRACT(DOW FROM dr.date) as dow,
                CASE WHEN dr.date < :today THEN a.value ELSE NULL END as actual_value,
                CASE
                    WHEN dr.date < :today THEN py.value
                    WHEN pyp.booking_count IS NOT NULL AND bc.bookable_count IS NOT NULL AND bc.bookable_count > 0
                        THEN (pyp.booking_count::numeric / bc.bookable_count) * 100
                    ELSE NULL
                END as prior_year_value,
                CASE
                    WHEN b.budget_value IS NOT NULL AND arr.arr IS NOT NULL AND arr.arr > 0 AND COALESCE(bc.bookable_count, :default_cap) > 0
                    THEN (LEAST(COALESCE(bc.bookable_count, :default_cap), CEIL(b.budget_value / arr.arr)) / COALESCE(bc.bookable_count, :default_cap)) * 100
                    ELSE NULL
                END as budget_value,
                CASE WHEN dr.date >= :today THEN o.otb ELSE NULL END as otb_value
            FROM date_range dr
            LEFT JOIN actuals a ON dr.date = a.date
            LEFT JOIN prior_year py ON dr.date = py.target_date
            LEFT JOIN otb_data o ON dr.date = o.date
            LEFT JOIN budgets b ON dr.date = b.date
            LEFT JOIN arr_forecast arr ON dr.date = arr.date
            LEFT JOIN bookable bc ON dr.date = bc.date
            LEFT JOIN prior_year_pace pyp ON dr.date = pyp.target_date
            ORDER BY dr.date
        """)
    elif metric == 'rooms':
        # Room nights from newbook_bookings_stats
        # Budget rooms calculated from: net_accom_budget / ARR (rounded up)
        query = text("""
            WITH date_range AS (
                SELECT generate_series(CAST(:start_date AS date), CAST(:end_date AS date), '1 day'::interval)::date as date
            ),
            actuals AS (
                SELECT date, booking_count as value
                FROM newbook_bookings_stats
                WHERE date BETWEEN :start_date AND :end_date
            ),
            prior_year AS (
                SELECT date + interval '364 days' as target_date, booking_count as value
                FROM newbook_bookings_stats
                WHERE date BETWEEN CAST(:start_date AS date) - interval '364 days' AND CAST(:end_date AS date) - interval '364 days'
            ),
            otb_data AS (
                SELECT date, booking_count as otb
                FROM newbook_bookings_stats
                WHERE date BETWEEN :start_date AND :end_date
            ),
            budgets AS (
                SELECT date, budget_value
                FROM daily_budgets
                WHERE date BETWEEN :start_date AND :end_date
                AND budget_type = 'net_accom'
            ),
            arr_forecast AS (
                SELECT
                    target_date as date,
                    forecast_value as arr
                FROM forecast_snapshots
                WHERE target_date BETWEEN :start_date AND :end_date
                AND metric_code = 'arr'
                AND model = 'blended'
                AND perception_date = (
                    SELECT MAX(perception_date)
                    FROM forecast_snapshots
                    WHERE metric_code = 'arr' AND model = 'blended'
                )
            ),
            bookable AS (
                SELECT date, bookable_count
                FROM newbook_bookings_stats
                WHERE date BETWEEN :start_date AND :end_date
                AND bookable_count IS NOT NULL
            ),
            prior_year_pace AS (
                SELECT
                    pace.arrival_date + 364 as target_date,
                    CASE
                        WHEN CAST(:today AS date) - 364 >= pace.arrival_date THEN NULL
                        ELSE CASE (pace.arrival_date - (CAST(:today AS date) - 364))
                            WHEN 0 THEN pace.d0 WHEN 1 THEN pace.d1 WHEN 2 THEN pace.d2 WHEN 3 THEN pace.d3
                            WHEN 4 THEN pace.d4 WHEN 5 THEN pace.d5 WHEN 6 THEN pace.d6 WHEN 7 THEN pace.d7
                            WHEN 8 THEN pace.d8 WHEN 9 THEN pace.d9 WHEN 10 THEN pace.d10 WHEN 11 THEN pace.d11
                            WHEN 12 THEN pace.d12 WHEN 13 THEN pace.d13 WHEN 14 THEN pace.d14 WHEN 15 THEN pace.d15
                            WHEN 16 THEN pace.d16 WHEN 17 THEN pace.d17 WHEN 18 THEN pace.d18 WHEN 19 THEN pace.d19
                            WHEN 20 THEN pace.d20 WHEN 21 THEN pace.d21 WHEN 22 THEN pace.d22 WHEN 23 THEN pace.d23
                            WHEN 24 THEN pace.d24 WHEN 25 THEN pace.d25 WHEN 26 THEN pace.d26 WHEN 27 THEN pace.d27
                            WHEN 28 THEN pace.d28 WHEN 29 THEN pace.d29 WHEN 30 THEN pace.d30
                            WHEN 37 THEN pace.d37 WHEN 44 THEN pace.d44 WHEN 51 THEN pace.d51 WHEN 58 THEN pace.d58
                            WHEN 65 THEN pace.d65 WHEN 72 THEN pace.d72 WHEN 79 THEN pace.d79 WHEN 86 THEN pace.d86
                            WHEN 93 THEN pace.d93 WHEN 100 THEN pace.d100 WHEN 107 THEN pace.d107 WHEN 114 THEN pace.d114
                            WHEN 121 THEN pace.d121 WHEN 128 THEN pace.d128 WHEN 135 THEN pace.d135 WHEN 142 THEN pace.d142
                            WHEN 149 THEN pace.d149 WHEN 156 THEN pace.d156 WHEN 163 THEN pace.d163 WHEN 170 THEN pace.d170
                            WHEN 177 THEN pace.d177 WHEN 210 THEN pace.d210 WHEN 240 THEN pace.d240 WHEN 270 THEN pace.d270
                            WHEN 300 THEN pace.d300 WHEN 330 THEN pace.d330 WHEN 365 THEN pace.d365
                            ELSE NULL
                        END
                    END as booking_count
                FROM newbook_booking_pace pace
                WHERE pace.arrival_date BETWEEN CAST(:start_date AS date) - 364
                      AND CAST(:end_date AS date) - 364
            )
            SELECT
                dr.date,
                EXTRACT(DOW FROM dr.date) as dow,
                CASE WHEN dr.date < :today THEN a.value ELSE NULL END as actual_value,
                CASE
                    WHEN dr.date < :today THEN py.value
                    ELSE pyp.booking_count
                END as prior_year_value,
                CASE
                    WHEN b.budget_value IS NOT NULL AND arr.arr IS NOT NULL AND arr.arr > 0
                    THEN LEAST(COALESCE(bc.bookable_count, :default_cap), CEIL(b.budget_value / arr.arr))
                    ELSE NULL
                END as budget_value,
                CASE WHEN dr.date >= :today THEN o.otb ELSE NULL END as otb_value
            FROM date_range dr
            LEFT JOIN actuals a ON dr.date = a.date
            LEFT JOIN prior_year py ON dr.date = py.target_date
            LEFT JOIN otb_data o ON dr.date = o.date
            LEFT JOIN budgets b ON dr.date = b.date
            LEFT JOIN arr_forecast arr ON dr.date = arr.date
            LEFT JOIN bookable bc ON dr.date = bc.date
            LEFT JOIN prior_year_pace pyp ON dr.date = pyp.target_date
            ORDER BY dr.date
        """)
    elif metric == 'guests':
        # Guests from newbook_bookings_stats
        query = text("""
            WITH date_range AS (
                SELECT generate_series(CAST(:start_date AS date), CAST(:end_date AS date), '1 day'::interval)::date as date
            ),
            actuals AS (
                SELECT date, guests_count as value
                FROM newbook_bookings_stats
                WHERE date BETWEEN :start_date AND :end_date
            ),
            prior_year AS (
                SELECT date + interval '364 days' as target_date, guests_count as value
                FROM newbook_bookings_stats
                WHERE date BETWEEN CAST(:start_date AS date) - interval '364 days' AND CAST(:end_date AS date) - interval '364 days'
            ),
            otb_data AS (
                SELECT date, guests_count as otb
                FROM newbook_bookings_stats
                WHERE date BETWEEN :start_date AND :end_date
            )
            SELECT
                dr.date,
                EXTRACT(DOW FROM dr.date) as dow,
                CASE WHEN dr.date < :today THEN a.value ELSE NULL END as actual_value,
                py.value as prior_year_value,
                NULL::numeric as budget_value,
                CASE WHEN dr.date >= :today THEN o.otb ELSE NULL END as otb_value
            FROM date_range dr
            LEFT JOIN actuals a ON dr.date = a.date
            LEFT JOIN prior_year py ON dr.date = py.target_date
            LEFT JOIN otb_data o ON dr.date = o.date
            ORDER BY dr.date
        """)
    else:
        # Default to rooms
        return await get_actuals_data(start_date, end_date, 'rooms', db, current_user)

    result = await db.execute(query, {"start_date": start, "end_date": end, "metric": metric, "today": today, "default_cap": default_cap})
    rows = result.fetchall()

    data = []
    actual_total = 0
    prior_total = 0
    budget_total = 0
    otb_total = 0
    actual_count = 0
    otb_count = 0

    for row in rows:
        actual_val = float(row.actual_value) if row.actual_value is not None else None
        prior_val = float(row.prior_year_value) if row.prior_year_value is not None else None
        budget_val = float(row.budget_value) if row.budget_value is not None else None
        otb_val = float(row.otb_value) if row.otb_value is not None else None

        data.append(ActualsDataPoint(
            date=row.date.isoformat(),
            day_of_week=day_names[int(row.dow)],
            actual_value=actual_val,
            prior_year_value=prior_val,
            budget_value=budget_val,
            otb_value=otb_val
        ))

        if actual_val is not None:
            actual_total += actual_val
            actual_count += 1
        if prior_val is not None:
            prior_total += prior_val
        if budget_val is not None:
            budget_total += budget_val
        if otb_val is not None:
            otb_total += otb_val
            otb_count += 1

    summary = {
        "actual_total": actual_total,
        "prior_year_total": prior_total,
        "budget_total": budget_total,
        "otb_total": otb_total,
        "days_with_actuals": actual_count,
        "days_with_otb": otb_count,
        "total_days": len(data)
    }

    return ActualsResponse(data=data, summary=summary)


# ============================================
# PICKUP-V2 PREVIEW ENDPOINT
# ============================================

class PickupV2DataPoint(BaseModel):
    date: str
    day_of_week: str
    lead_days: int
    prior_year_date: str
    # Revenue metrics
    current_otb_rev: Optional[float] = None
    prior_year_otb_rev: Optional[float] = None
    prior_year_final_rev: Optional[float] = None
    expected_pickup_rev: Optional[float] = None
    forecast: float
    upper_bound: Optional[float] = None
    lower_bound: Optional[float] = None
    ceiling: Optional[float] = None
    # Scenario values
    at_prior_adr: Optional[float] = None      # Revenue at prior year pickup ADR
    at_current_rate: Optional[float] = None   # Revenue at current rack rates
    at_cheaper_50: Optional[float] = None     # Revenue at cheaper 50% of prior rates
    at_expensive_50: Optional[float] = None   # Revenue at expensive 50% of prior rates
    # Pricing opportunity fields
    has_pricing_opportunity: Optional[bool] = None  # True if current rate < prior ADR
    lost_potential: Optional[float] = None    # Revenue left on table (0 if none)
    rate_gap: Optional[float] = None          # Negative = opportunity to raise rates
    rate_vs_prior_pct: Optional[float] = None # % diff between current and prior rates
    pace_vs_prior_pct: Optional[float] = None
    pickup_rooms_total: Optional[int] = None  # Number of pickup rooms expected
    # Weighted average rates per room for display (net)
    weighted_avg_prior_rate: Optional[float] = None   # Prior year pickup ADR (net)
    weighted_avg_current_rate: Optional[float] = None # Current rack rate (net)
    # Gross rates (inc VAT) for UI display
    weighted_avg_prior_rate_gross: Optional[float] = None   # Prior year ADR (gross)
    weighted_avg_current_rate_gross: Optional[float] = None # Current rate (gross)
    # Listed rate at lead time (earliest bookings) - for rate comparison
    weighted_avg_listed_rate: Optional[float] = None        # LY listed rate at this lead time (net)
    weighted_avg_listed_rate_gross: Optional[float] = None  # LY listed rate (gross)
    # Effective rate = rate actually used in forecast (min of prior and current)
    effective_rate: Optional[float] = None                  # Rate used in forecast (net)
    effective_rate_gross: Optional[float] = None            # Rate used in forecast (gross)
    # Room metrics (when metric is rooms/occupancy)
    current_otb: Optional[float] = None
    prior_year_otb: Optional[int] = None
    prior_year_final: Optional[int] = None
    expected_pickup: Optional[int] = None
    floor: Optional[float] = None
    category_breakdown: Optional[dict] = None


class PickupV2Summary(BaseModel):
    otb_rev_total: Optional[float] = None
    forecast_total: float
    upper_total: Optional[float] = None
    lower_total: Optional[float] = None
    prior_final_total: Optional[float] = None
    avg_adr_position: Optional[float] = None
    avg_pace_pct: Optional[float] = None
    days_count: int
    # Pricing opportunity summary
    lost_potential_total: Optional[float] = None  # Total revenue left on table
    opportunity_days_count: Optional[int] = None  # Days with pricing opportunities


class PickupV2Response(BaseModel):
    data: List[PickupV2DataPoint]
    summary: PickupV2Summary


@router.get("/pickup-v2-preview", response_model=PickupV2Response)
async def get_pickup_v2_preview(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    metric: str = Query("net_accom", description="Metric type: net_accom, hotel_room_nights, hotel_occupancy_pct"),
    include_details: bool = Query(False, description="Include category breakdown"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Pickup-V2 preview supporting both room and revenue metrics.

    Revenue forecast uses additive pickup methodology:
    - Forecast = Current OTB + (Prior Year Final - Prior Year OTB at same lead time)
    - Floor: Current OTB (can't go below what's booked)
    - Ceiling: Based on remaining capacity × current rates per category

    Returns confidence bounds for revenue based on rate analysis:
    - Upper bound: OTB + (remaining rooms × current rate per category)
    - Lower bound: OTB + (remaining rooms × min historical rate per category)
    - ADR position: where current ADR falls between min/max (0-1 scale, indicates pricing pressure)
    """
    from datetime import datetime
    from services.forecasting.pickup_v2_model import run_pickup_v2_forecast, get_pickup_v2_summary

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Map frontend metric names to model metric codes
    metric_map = {
        'net_accom': 'net_accom',
        'rooms': 'hotel_room_nights',
        'hotel_room_nights': 'hotel_room_nights',
        'occupancy': 'hotel_occupancy_pct',
        'hotel_occupancy_pct': 'hotel_occupancy_pct'
    }
    metric_code = metric_map.get(metric, metric)

    try:
        # Run the pickup-v2 forecast
        forecasts = await run_pickup_v2_forecast(
            db, metric_code, start, end, include_details=include_details
        )

        # Build response data
        data = []
        for fc in forecasts:
            data.append(PickupV2DataPoint(
                date=fc['date'],
                day_of_week=fc['day_of_week'],
                lead_days=fc['lead_days'],
                prior_year_date=fc['prior_year_date'],
                current_otb_rev=fc.get('current_otb_rev'),
                prior_year_otb_rev=fc.get('prior_year_otb_rev'),
                prior_year_final_rev=fc.get('prior_year_final_rev'),
                expected_pickup_rev=fc.get('expected_pickup_rev'),
                forecast=fc.get('forecast', fc.get('predicted_value', 0)),
                upper_bound=fc.get('upper_bound'),
                lower_bound=fc.get('lower_bound'),
                ceiling=fc.get('ceiling'),
                # Scenario values
                at_prior_adr=fc.get('at_prior_adr'),
                at_current_rate=fc.get('at_current_rate'),
                at_cheaper_50=fc.get('at_cheaper_50'),
                at_expensive_50=fc.get('at_expensive_50'),
                # Pricing opportunity fields
                has_pricing_opportunity=fc.get('has_pricing_opportunity'),
                lost_potential=fc.get('lost_potential'),
                rate_gap=fc.get('rate_gap'),
                rate_vs_prior_pct=fc.get('rate_vs_prior_pct'),
                pace_vs_prior_pct=fc.get('pace_vs_prior_pct'),
                pickup_rooms_total=fc.get('pickup_rooms_total'),
                # Weighted average rates per room (net and gross)
                weighted_avg_prior_rate=fc.get('weighted_avg_prior_rate'),
                weighted_avg_current_rate=fc.get('weighted_avg_current_rate'),
                weighted_avg_prior_rate_gross=fc.get('weighted_avg_prior_rate_gross'),
                weighted_avg_current_rate_gross=fc.get('weighted_avg_current_rate_gross'),
                # Listed rate at lead time (earliest bookings) - for rate comparison
                weighted_avg_listed_rate=fc.get('weighted_avg_listed_rate'),
                weighted_avg_listed_rate_gross=fc.get('weighted_avg_listed_rate_gross'),
                # Effective rate = rate actually used in forecast (min of prior and current)
                effective_rate=fc.get('effective_rate'),
                effective_rate_gross=fc.get('effective_rate_gross'),
                # Room metrics
                current_otb=fc.get('current_otb'),
                prior_year_otb=fc.get('prior_year_otb'),
                prior_year_final=fc.get('prior_year_final'),
                expected_pickup=fc.get('expected_pickup'),
                floor=fc.get('floor'),
                category_breakdown=fc.get('category_breakdown') if include_details else None
            ))

        # Calculate summary
        if metric_code == 'net_accom':
            # Calculate pricing opportunity totals
            lost_potential_total = sum(f.get('lost_potential', 0) or 0 for f in forecasts)
            opportunity_days = sum(1 for f in forecasts if f.get('has_pricing_opportunity', False))

            summary = PickupV2Summary(
                otb_rev_total=sum(f.get('current_otb_rev', 0) or 0 for f in forecasts),
                forecast_total=sum(f.get('forecast', 0) or 0 for f in forecasts),
                upper_total=sum(f.get('upper_bound', 0) or 0 for f in forecasts),
                lower_total=sum(f.get('lower_bound', 0) or 0 for f in forecasts),
                prior_final_total=sum(f.get('prior_year_final_rev', 0) or 0 for f in forecasts),
                avg_adr_position=sum(f.get('adr_position', 0.5) or 0.5 for f in forecasts) / max(len(forecasts), 1),
                avg_pace_pct=sum(f.get('pace_vs_prior_pct', 0) or 0 for f in forecasts) / max(len(forecasts), 1),
                days_count=len(forecasts),
                lost_potential_total=lost_potential_total,
                opportunity_days_count=opportunity_days
            )
        else:
            summary = PickupV2Summary(
                forecast_total=sum(f.get('forecast', 0) or 0 for f in forecasts),
                prior_final_total=sum(f.get('prior_year_final', 0) or 0 for f in forecasts),
                avg_pace_pct=sum(f.get('pace_vs_prior_pct', 0) or 0 for f in forecasts) / max(len(forecasts), 1),
                days_count=len(forecasts)
            )

        return PickupV2Response(data=data, summary=summary)

    except Exception as e:
        import logging
        logging.error(f"Pickup-V2 preview failed: {e}")
        raise HTTPException(status_code=500, detail=f"Forecast generation failed: {str(e)}")


# ============================================
# RESTAURANT COVERS FORECAST
# ============================================

class CoversDataPoint(BaseModel):
    date: str
    day_of_week: str
    lead_days: int
    prior_year_date: str
    # Breakfast (based on hotel guest count from night before)
    breakfast_otb: int
    breakfast_pickup: int
    breakfast_forecast: int
    breakfast_prior: int
    breakfast_hotel_guests_otb: int
    breakfast_hotel_guests_prior: int
    breakfast_calc: Optional[dict] = None  # Calculation breakdown for tooltip
    # Lunch (simple OTB + pickup)
    lunch_otb: int
    lunch_pickup: int
    lunch_forecast: int
    lunch_prior: int
    lunch_calc: Optional[dict] = None  # Calculation breakdown for tooltip
    # Dinner
    dinner_otb: int
    dinner_resident_otb: int
    dinner_non_resident_otb: int
    dinner_resident_pickup: int
    dinner_non_resident_pickup: int
    dinner_forecast: int
    dinner_prior: int
    dinner_resident_calc: Optional[dict] = None  # Calculation breakdown for tooltip
    dinner_non_resident_calc: Optional[dict] = None  # Calculation breakdown for tooltip
    # Totals
    total_otb: int
    total_forecast: int
    total_prior: int
    pace_vs_prior_pct: Optional[float]
    # Hotel context
    hotel_occupancy_pct: float
    hotel_rooms: int


class CoversSummary(BaseModel):
    breakfast_otb: int
    breakfast_forecast: int
    breakfast_prior: int
    lunch_otb: int
    lunch_forecast: int
    lunch_prior: int
    dinner_otb: int
    dinner_forecast: int
    dinner_prior: int
    total_otb: int
    total_forecast: int
    total_prior: int
    days_count: int


class CoversResponse(BaseModel):
    data: List[CoversDataPoint]
    summary: CoversSummary


@router.get("/covers-forecast", response_model=CoversResponse)
async def get_covers_forecast(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    include_details: bool = Query(False, description="Include detailed breakdown"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get restaurant covers forecast for a date range.

    Returns covers forecast by meal period (breakfast, lunch, dinner) with
    breakdown by guest segment (resident/non-resident).

    Breakfast is forecast based on previous night's hotel occupancy.
    Lunch and dinner use OTB bookings plus pickup forecasts.
    """
    from datetime import datetime
    from services.forecasting.covers_model import forecast_covers_range

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    try:
        result = await forecast_covers_range(db, start, end, include_details)

        # Transform to response format
        data = []
        for fc in result["data"]:
            data.append(CoversDataPoint(
                date=fc["date"],
                day_of_week=fc["day_of_week"],
                lead_days=fc["lead_days"],
                prior_year_date=fc["prior_year_date"],
                # Breakfast (based on hotel guest count from night before)
                breakfast_otb=fc["breakfast"]["otb"],
                breakfast_pickup=fc["breakfast"]["pickup"],
                breakfast_forecast=fc["breakfast"]["forecast"],
                breakfast_prior=fc["breakfast"]["prior_year"],
                breakfast_hotel_guests_otb=fc["breakfast"]["hotel_guests_otb"],
                breakfast_hotel_guests_prior=fc["breakfast"]["hotel_guests_prior"],
                breakfast_calc=fc["breakfast"].get("calc"),
                # Lunch (simple OTB + pickup)
                lunch_otb=fc["lunch"]["otb"],
                lunch_pickup=fc["lunch"]["pickup"],
                lunch_forecast=fc["lunch"]["forecast"],
                lunch_prior=fc["lunch"]["prior_year"],
                lunch_calc=fc["lunch"].get("calc"),
                # Dinner
                dinner_otb=fc["dinner"]["otb"],
                dinner_resident_otb=fc["dinner"]["resident_otb"],
                dinner_non_resident_otb=fc["dinner"]["non_resident_otb"],
                dinner_resident_pickup=fc["dinner"]["resident_pickup"],
                dinner_non_resident_pickup=fc["dinner"]["non_resident_pickup"],
                dinner_forecast=fc["dinner"]["forecast"],
                dinner_prior=fc["dinner"]["prior_year"],
                dinner_resident_calc=fc["dinner"].get("resident_calc"),
                dinner_non_resident_calc=fc["dinner"].get("non_resident_calc"),
                # Totals
                total_otb=fc["totals"]["otb"],
                total_forecast=fc["totals"]["forecast"],
                total_prior=fc["totals"]["prior_year"],
                pace_vs_prior_pct=fc["totals"]["pace_vs_prior_pct"],
                # Hotel context
                hotel_occupancy_pct=fc["hotel_context"]["night_before_occupancy"],
                hotel_rooms=fc["hotel_context"]["night_before_rooms"]
            ))

        summary = CoversSummary(
            breakfast_otb=result["summary"]["breakfast_otb"],
            breakfast_forecast=result["summary"]["breakfast_forecast"],
            breakfast_prior=result["summary"]["breakfast_prior"],
            lunch_otb=result["summary"]["lunch_otb"],
            lunch_forecast=result["summary"]["lunch_forecast"],
            lunch_prior=result["summary"]["lunch_prior"],
            dinner_otb=result["summary"]["dinner_otb"],
            dinner_forecast=result["summary"]["dinner_forecast"],
            dinner_prior=result["summary"]["dinner_prior"],
            total_otb=result["summary"]["total_otb"],
            total_forecast=result["summary"]["total_forecast"],
            total_prior=result["summary"]["total_prior"],
            days_count=result["summary"]["days_count"]
        )

        return CoversResponse(data=data, summary=summary)

    except Exception as e:
        import logging
        logging.error(f"Covers forecast failed: {e}")
        raise HTTPException(status_code=500, detail=f"Covers forecast failed: {str(e)}")


@router.get("/revenue-forecast")
async def get_revenue_forecast(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    revenue_type: str = Query("dry", description="Revenue type: dry, wet, or total"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get restaurant revenue forecast for a date range.

    Returns:
    - Past dates: Actual revenue from newbook_net_revenue_data
    - Future dates: Forecast revenue (covers × spend)
    - Prior year values for comparison
    """
    from datetime import datetime, date as date_type
    from services.forecasting.covers_model import forecast_covers_range

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    today = date_type.today()
    VAT_RATE = 1.20

    def get_prior_year_date(d: date_type) -> date_type:
        """
        Get prior year date with 364-day offset for day-of-week alignment.
        52 weeks = 364 days, so Monday aligns with Monday.
        """
        return d - timedelta(days=364)

    # Get spend settings
    spend_result = await db.execute(
        text("""
            SELECT config_key, config_value
            FROM system_config
            WHERE config_key LIKE 'resos_%_spend'
        """)
    )
    spend_rows = spend_result.fetchall()
    spend_settings = {row.config_key: float(row.config_value or 0) for row in spend_rows}

    def get_spend_by_period(period: str) -> float:
        """Get net spend per cover for a period"""
        if revenue_type == 'dry':
            return spend_settings.get(f'resos_{period}_food_spend', 0) / VAT_RATE
        elif revenue_type == 'wet':
            return spend_settings.get(f'resos_{period}_drinks_spend', 0) / VAT_RATE
        else:  # total
            food = spend_settings.get(f'resos_{period}_food_spend', 0)
            drinks = spend_settings.get(f'resos_{period}_drinks_spend', 0)
            return (food + drinks) / VAT_RATE

    # Get actual revenue for past dates
    actual_result = await db.execute(
        text("""
            SELECT date, dry, wet, (dry + wet) as total
            FROM newbook_net_revenue_data
            WHERE date >= :start_date AND date <= :end_date
        """),
        {"start_date": start, "end_date": end}
    )
    actual_rows = actual_result.fetchall()
    actual_by_date = {row.date: row for row in actual_rows}

    # Get prior year actual revenue
    prior_start = get_prior_year_date(start)
    prior_end = get_prior_year_date(end)
    prior_result = await db.execute(
        text("""
            SELECT date, dry, wet, (dry + wet) as total
            FROM newbook_net_revenue_data
            WHERE date >= :start_date AND date <= :end_date
        """),
        {"start_date": prior_start, "end_date": prior_end}
    )
    prior_rows = prior_result.fetchall()
    prior_by_date = {row.date: row for row in prior_rows}

    # Get covers forecast for future dates
    covers_data = await forecast_covers_range(db, start, end, include_details=False)

    # Build response
    data = []
    current = start
    while current <= end:
        is_past = current < today
        prior_date = get_prior_year_date(current)

        # Get prior year revenue
        prior_row = prior_by_date.get(prior_date)
        if revenue_type == 'dry':
            prior_revenue = float(prior_row.dry) if prior_row else 0
        elif revenue_type == 'wet':
            prior_revenue = float(prior_row.wet) if prior_row else 0
        else:
            prior_revenue = float(prior_row.total) if prior_row else 0

        if is_past:
            # Past: use actual revenue
            actual_row = actual_by_date.get(current)
            if revenue_type == 'dry':
                actual_revenue = float(actual_row.dry) if actual_row else 0
            elif revenue_type == 'wet':
                actual_revenue = float(actual_row.wet) if actual_row else 0
            else:
                actual_revenue = float(actual_row.total) if actual_row else 0

            data.append({
                "date": current.isoformat(),
                "day_of_week": current.strftime("%A"),
                "is_past": True,
                "actual_revenue": actual_revenue,
                "otb_revenue": actual_revenue,  # For past, OTB = actual
                "pickup_revenue": 0,
                "forecast_revenue": actual_revenue,
                "prior_revenue": prior_revenue,
            })
        else:
            # Future: calculate from covers forecast
            day_covers = next((c for c in covers_data["data"] if c["date"] == current.isoformat()), None)

            if day_covers:
                breakfast_otb = day_covers["breakfast"]["otb"]
                lunch_otb = day_covers["lunch"]["otb"]
                dinner_otb = day_covers["dinner"]["otb"]

                breakfast_pickup = day_covers["breakfast"]["pickup"]
                lunch_pickup = day_covers["lunch"]["pickup"]
                dinner_resident_pickup = day_covers["dinner"]["resident_pickup"]
                dinner_non_resident_pickup = day_covers["dinner"]["non_resident_pickup"]
                dinner_pickup = dinner_resident_pickup + dinner_non_resident_pickup

                otb_revenue = (
                    breakfast_otb * get_spend_by_period('breakfast') +
                    lunch_otb * get_spend_by_period('lunch') +
                    dinner_otb * get_spend_by_period('dinner')
                )

                pickup_revenue = (
                    breakfast_pickup * get_spend_by_period('breakfast') +
                    lunch_pickup * get_spend_by_period('lunch') +
                    dinner_pickup * get_spend_by_period('dinner')
                )
            else:
                otb_revenue = 0
                pickup_revenue = 0

            data.append({
                "date": current.isoformat(),
                "day_of_week": current.strftime("%A"),
                "is_past": False,
                "actual_revenue": 0,
                "otb_revenue": otb_revenue,
                "pickup_revenue": pickup_revenue,
                "forecast_revenue": otb_revenue + pickup_revenue,
                "prior_revenue": prior_revenue,
            })

        current += timedelta(days=1)

    # Calculate summary
    past_data = [d for d in data if d["is_past"]]
    future_data = [d for d in data if not d["is_past"]]

    summary = {
        "actual_total": sum(d["actual_revenue"] for d in past_data),
        "prior_actual_total": sum(d["prior_revenue"] for d in past_data),
        "otb_total": sum(d["otb_revenue"] for d in future_data),
        "pickup_total": sum(d["pickup_revenue"] for d in future_data),
        "forecast_remaining": sum(d["forecast_revenue"] for d in future_data),
        "prior_future_total": sum(d["prior_revenue"] for d in future_data),
        "prior_year_total": sum(d["prior_revenue"] for d in data),
        "projected_total": sum(d["actual_revenue"] for d in past_data) + sum(d["forecast_revenue"] for d in future_data),
        "days_actual": len(past_data),
        "days_forecast": len(future_data),
    }

    return {"data": data, "summary": summary}


@router.get("/combined-revenue-forecast")
async def get_combined_revenue_forecast(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get combined total revenue forecast (accom + dry + wet) for a date range.

    Returns:
    - Past dates: Actual revenue from newbook_net_revenue_data (all revenue types)
    - Future dates: Forecast revenue (accom from pickup-v2, dry/wet from covers × spend)
    - Prior year actual values for comparison
    """
    from datetime import datetime, date as date_type
    from services.forecasting.covers_model import forecast_covers_range
    from services.forecasting.pickup_v2_model import forecast_revenue_for_date

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    today = date_type.today()
    VAT_RATE = 1.20

    def get_prior_year_date(d: date_type) -> date_type:
        """
        Get prior year date with 364-day offset for day-of-week alignment.
        52 weeks = 364 days, so Monday aligns with Monday.
        """
        return d - timedelta(days=364)

    # Get spend settings for restaurant revenue
    spend_result = await db.execute(
        text("""
            SELECT config_key, config_value
            FROM system_config
            WHERE config_key LIKE 'resos_%_spend'
        """)
    )
    spend_rows = spend_result.fetchall()
    spend_settings = {row.config_key: float(row.config_value or 0) for row in spend_rows}

    def get_spend_by_period(period: str, revenue_type: str) -> float:
        """Get net spend per cover for a period"""
        if revenue_type == 'dry':
            return spend_settings.get(f'resos_{period}_food_spend', 0) / VAT_RATE
        elif revenue_type == 'wet':
            return spend_settings.get(f'resos_{period}_drinks_spend', 0) / VAT_RATE
        else:  # total
            food = spend_settings.get(f'resos_{period}_food_spend', 0)
            drinks = spend_settings.get(f'resos_{period}_drinks_spend', 0)
            return (food + drinks) / VAT_RATE

    # Get actual revenue for past dates (all types: accom, dry, wet)
    actual_result = await db.execute(
        text("""
            SELECT date, accommodation, dry, wet
            FROM newbook_net_revenue_data
            WHERE date >= :start_date AND date <= :end_date
        """),
        {"start_date": start, "end_date": end}
    )
    actual_rows = actual_result.fetchall()
    actual_by_date = {row.date: row for row in actual_rows}

    # Get prior year actual revenue
    prior_start = get_prior_year_date(start)
    prior_end = get_prior_year_date(end)
    prior_result = await db.execute(
        text("""
            SELECT date, accommodation, dry, wet
            FROM newbook_net_revenue_data
            WHERE date >= :start_date AND date <= :end_date
        """),
        {"start_date": prior_start, "end_date": prior_end}
    )
    prior_rows = prior_result.fetchall()
    prior_by_date = {row.date: row for row in prior_rows}

    # Get covers forecast for restaurant revenue (future dates)
    covers_data = await forecast_covers_range(db, start, end, include_details=False)

    # Build response
    data = []
    current = start
    while current <= end:
        is_past = current < today
        prior_date = get_prior_year_date(current)
        lead_days = (current - today).days if current >= today else 0

        # Get prior year revenue (all types combined)
        prior_row = prior_by_date.get(prior_date)
        prior_accom = float(prior_row.accommodation) if prior_row and prior_row.accommodation else 0
        prior_dry = float(prior_row.dry) if prior_row and prior_row.dry else 0
        prior_wet = float(prior_row.wet) if prior_row and prior_row.wet else 0
        prior_total = prior_accom + prior_dry + prior_wet

        if is_past:
            # Past: use actual revenue from database
            actual_row = actual_by_date.get(current)
            actual_accom = float(actual_row.accommodation) if actual_row and actual_row.accommodation else 0
            actual_dry = float(actual_row.dry) if actual_row and actual_row.dry else 0
            actual_wet = float(actual_row.wet) if actual_row and actual_row.wet else 0
            actual_total = actual_accom + actual_dry + actual_wet

            data.append({
                "date": current.isoformat(),
                "day_of_week": current.strftime("%A"),
                "is_past": True,
                "actual_accom": actual_accom,
                "actual_dry": actual_dry,
                "actual_wet": actual_wet,
                "actual_revenue": actual_total,
                "otb_revenue": actual_total,  # For past, OTB = actual
                "pickup_revenue": 0,
                "forecast_revenue": actual_total,
                "prior_accom": prior_accom,
                "prior_dry": prior_dry,
                "prior_wet": prior_wet,
                "prior_revenue": prior_total,
            })
        else:
            # Future: calculate forecast
            # 1. Accommodation from pickup-v2 revenue model
            try:
                accom_forecast = await forecast_revenue_for_date(
                    db, current, lead_days, prior_date
                )
                accom_otb = accom_forecast.get('current_otb_rev', 0) or 0
                accom_pickup = accom_forecast.get('forecast_pickup_rev', 0) or 0
            except Exception as e:
                logger.warning(f"Accom forecast failed for {current}: {e}")
                accom_otb = 0
                accom_pickup = 0

            # 2. Restaurant from covers forecast × spend
            day_covers = next((c for c in covers_data["data"] if c["date"] == current.isoformat()), None)

            if day_covers:
                breakfast_otb = day_covers["breakfast"]["otb"]
                lunch_otb = day_covers["lunch"]["otb"]
                dinner_otb = day_covers["dinner"]["otb"]

                breakfast_pickup = day_covers["breakfast"]["pickup"]
                lunch_pickup = day_covers["lunch"]["pickup"]
                dinner_resident_pickup = day_covers["dinner"]["resident_pickup"]
                dinner_non_resident_pickup = day_covers["dinner"]["non_resident_pickup"]
                dinner_pickup = dinner_resident_pickup + dinner_non_resident_pickup

                dry_otb = (
                    breakfast_otb * get_spend_by_period('breakfast', 'dry') +
                    lunch_otb * get_spend_by_period('lunch', 'dry') +
                    dinner_otb * get_spend_by_period('dinner', 'dry')
                )
                dry_pickup = (
                    breakfast_pickup * get_spend_by_period('breakfast', 'dry') +
                    lunch_pickup * get_spend_by_period('lunch', 'dry') +
                    dinner_pickup * get_spend_by_period('dinner', 'dry')
                )

                wet_otb = (
                    breakfast_otb * get_spend_by_period('breakfast', 'wet') +
                    lunch_otb * get_spend_by_period('lunch', 'wet') +
                    dinner_otb * get_spend_by_period('dinner', 'wet')
                )
                wet_pickup = (
                    breakfast_pickup * get_spend_by_period('breakfast', 'wet') +
                    lunch_pickup * get_spend_by_period('lunch', 'wet') +
                    dinner_pickup * get_spend_by_period('dinner', 'wet')
                )
            else:
                dry_otb = dry_pickup = wet_otb = wet_pickup = 0

            total_otb = accom_otb + dry_otb + wet_otb
            total_pickup = accom_pickup + dry_pickup + wet_pickup

            data.append({
                "date": current.isoformat(),
                "day_of_week": current.strftime("%A"),
                "is_past": False,
                "actual_accom": 0,
                "actual_dry": 0,
                "actual_wet": 0,
                "actual_revenue": 0,
                "otb_accom": accom_otb,
                "otb_dry": dry_otb,
                "otb_wet": wet_otb,
                "otb_revenue": total_otb,
                "pickup_accom": accom_pickup,
                "pickup_dry": dry_pickup,
                "pickup_wet": wet_pickup,
                "pickup_revenue": total_pickup,
                "forecast_revenue": total_otb + total_pickup,
                "prior_accom": prior_accom,
                "prior_dry": prior_dry,
                "prior_wet": prior_wet,
                "prior_revenue": prior_total,
            })

        current += timedelta(days=1)

    # Calculate summary
    past_data = [d for d in data if d["is_past"]]
    future_data = [d for d in data if not d["is_past"]]

    summary = {
        "actual_total": sum(d["actual_revenue"] for d in past_data),
        "actual_accom": sum(d.get("actual_accom", 0) for d in past_data),
        "actual_dry": sum(d.get("actual_dry", 0) for d in past_data),
        "actual_wet": sum(d.get("actual_wet", 0) for d in past_data),
        "prior_actual_total": sum(d["prior_revenue"] for d in past_data),
        "otb_total": sum(d["otb_revenue"] for d in future_data),
        "otb_accom": sum(d.get("otb_accom", 0) for d in future_data),
        "otb_dry": sum(d.get("otb_dry", 0) for d in future_data),
        "otb_wet": sum(d.get("otb_wet", 0) for d in future_data),
        "pickup_total": sum(d["pickup_revenue"] for d in future_data),
        "pickup_accom": sum(d.get("pickup_accom", 0) for d in future_data),
        "pickup_dry": sum(d.get("pickup_dry", 0) for d in future_data),
        "pickup_wet": sum(d.get("pickup_wet", 0) for d in future_data),
        "forecast_remaining": sum(d["forecast_revenue"] for d in future_data),
        "prior_future_total": sum(d["prior_revenue"] for d in future_data),
        "prior_year_total": sum(d["prior_revenue"] for d in data),
        "projected_total": sum(d["actual_revenue"] for d in past_data) + sum(d["forecast_revenue"] for d in future_data),
        "days_actual": len(past_data),
        "days_forecast": len(future_data),
    }

    return {"data": data, "summary": summary}
