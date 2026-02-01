"""
Forecast API endpoints
"""
import asyncio
from datetime import date, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from database import get_db
from auth import get_current_user
from api.special_dates import resolve_special_date

router = APIRouter()


class ForecastResponse(BaseModel):
    date: date
    metric_code: str
    metric_name: str
    prophet_value: Optional[float]
    prophet_lower: Optional[float]
    prophet_upper: Optional[float]
    xgboost_value: Optional[float]
    pickup_value: Optional[float]
    tft_value: Optional[float]
    tft_lower: Optional[float]
    tft_upper: Optional[float]
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
            MAX(CASE WHEN f.model_type = 'tft' THEN f.predicted_value END) as tft_value,
            MAX(CASE WHEN f.model_type = 'tft' THEN f.lower_bound END) as tft_lower,
            MAX(CASE WHEN f.model_type = 'tft' THEN f.upper_bound END) as tft_upper,
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
            "tft_value": row.tft_value,
            "tft_lower": row.tft_lower,
            "tft_upper": row.tft_upper,
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
    models: Optional[List[str]] = Query(None, description="Models to run: prophet, xgboost, pickup, tft"),
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
    models_to_run = models or ['prophet', 'xgboost', 'pickup', 'tft']

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
            COALESCE(use_tft, FALSE) as use_tft,
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
                "pickup": row.use_pickup,
                "tft": row.use_tft
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

    # Get bookable rooms count from latest stats (accounts for maintenance/non-bookable rooms)
    bookable_result = await db.execute(text("""
        SELECT bookable_count
        FROM newbook_bookings_stats
        WHERE bookable_count IS NOT NULL
        ORDER BY date DESC
        LIMIT 1
    """))
    bookable_row = bookable_result.fetchone()
    total_rooms = int(bookable_row.bookable_count) if bookable_row and bookable_row.bookable_count else 25

    # Get historical data for Prophet training (past 2 years from newbook_bookings_stats)
    # Use booking_count for room nights, guests_count for guest forecast
    history_start = today - timedelta(days=730)
    history_result = await db.execute(text("""
        SELECT date as ds, booking_count as y
        FROM newbook_bookings_stats
        WHERE date >= :history_start
        AND date < :today
        AND booking_count IS NOT NULL
        ORDER BY date
    """), {"history_start": history_start, "today": today})
    history_rows = history_result.fetchall()

    if len(history_rows) < 30:
        raise HTTPException(status_code=400, detail="Insufficient historical data for Prophet model")

    # Build training dataframe
    df = pd.DataFrame([{"ds": row.ds, "y": float(row.y)} for row in history_rows])

    # Convert to occupancy if needed and set floor/cap
    if metric == "occupancy" and total_rooms > 0:
        df["y"] = (df["y"] / total_rooms) * 100
        df["floor"] = 0
        df["cap"] = 100
    else:
        # Room nights mode - floor at 0, cap at total_rooms
        df["floor"] = 0
        df["cap"] = total_rooms

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

    # Add floor/cap for logistic growth predictions
    if metric == "occupancy":
        future_df["floor"] = 0
        future_df["cap"] = 100
    else:
        future_df["floor"] = 0
        future_df["cap"] = total_rooms

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

        # Get current OTB
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
            # Normal mode: get current OTB from bookings_stats (today's actual booking count)
            current_query = text("""
                SELECT booking_count as current_otb
                FROM newbook_bookings_stats
                WHERE date = :arrival_date
            """)
            current_result = await db.execute(current_query, {"arrival_date": forecast_date})
            current_row = current_result.fetchone()

        # Get prior year OTB from booking_pace (for lead time comparison - uses 364-day offset)
        prior_year_for_otb = forecast_date - timedelta(days=364)
        prior_otb_query = text(f"""
            SELECT {lead_col} as prior_otb
            FROM newbook_booking_pace
            WHERE arrival_date = :prior_date
        """)
        prior_otb_result = await db.execute(prior_otb_query, {"prior_date": prior_year_for_otb})
        prior_otb_row = prior_otb_result.fetchone()

        # Get prior year final from newbook_bookings_stats (booking_count = room nights)
        prior_query = text("""
            SELECT booking_count as prior_final
            FROM newbook_bookings_stats
            WHERE date = :prior_date
        """)
        prior_result = await db.execute(prior_query, {"prior_date": prior_year_date})
        prior_row = prior_result.fetchone()

        # Default to 0 for stats (no row = no bookings), None for pace (no historical tracking)
        current_otb = current_row.current_otb if current_row and current_row.current_otb is not None else 0
        prior_otb = prior_otb_row.prior_otb if prior_otb_row and prior_otb_row.prior_otb is not None else None
        prior_final = prior_row.prior_final if prior_row and prior_row.prior_final is not None else 0

        # Convert to occupancy if needed
        if metric == "occupancy" and total_rooms > 0:
            if current_otb is not None:
                current_otb = (current_otb / total_rooms) * 100
            if prior_otb is not None:
                prior_otb = (prior_otb / total_rooms) * 100
            if prior_final is not None:
                prior_final = (prior_final / total_rooms) * 100

        # Get Prophet forecast values
        yhat = row["yhat"]
        yhat_lower = row["yhat_lower"]
        yhat_upper = row["yhat_upper"]

        # Cap at max capacity
        if metric == "occupancy":
            yhat = min(yhat, 100.0)
            yhat_upper = min(yhat_upper, 100.0)
        else:  # rooms mode
            yhat = min(yhat, float(total_rooms))
            yhat_upper = min(yhat_upper, float(total_rooms))

        # Floor forecast to current OTB if we have it
        if current_otb is not None and yhat < current_otb:
            yhat = current_otb
            yhat_lower = current_otb

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

    return ProphetResponse(
        data=data_points,
        summary=ProphetSummary(
            otb_total=round(otb_total, 1),
            prior_otb_total=round(prior_otb_total, 1),
            forecast_total=round(forecast_total, 1),
            prior_final_total=round(prior_final_total, 1),
            days_count=len(data_points),
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

    # Get bookable rooms count
    bookable_result = await db.execute(text("""
        SELECT bookable_count
        FROM newbook_bookings_stats
        WHERE bookable_count IS NOT NULL
        ORDER BY date DESC
        LIMIT 1
    """))
    bookable_row = bookable_result.fetchone()
    total_rooms = int(bookable_row.bookable_count) if bookable_row and bookable_row.bookable_count else 25

    # Get historical data for XGBoost training (past 2 years)
    # Join with booking_pace to get OTB at various lead times
    history_start = today - timedelta(days=730)

    # Lead times to train on (key intervals)
    train_lead_times = [0, 1, 3, 7, 14, 21, 28, 30]

    # Get final values and pace data
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

    # Build lookup dict for pace data by date
    pace_by_date = {}
    final_by_date = {}
    for row in history_rows:
        pace_by_date[row.ds] = {
            0: row.d0, 1: row.d1, 3: row.d3, 7: row.d7,
            14: row.d14, 21: row.d21, 28: row.d28, 30: row.d30
        }
        final_by_date[row.ds] = row.final

    # Build training examples - one per (date, lead_time) combination
    training_rows = []
    for row in history_rows:
        ds = row.ds
        final = float(row.final)
        prior_ds = ds - timedelta(days=364)  # Same DOW prior year

        # Get prior year final if available
        prior_final = final_by_date.get(prior_ds)
        if prior_final is None:
            continue  # Skip if no prior year data

        for lead_time in train_lead_times:
            # Get current OTB at this lead time
            current_otb = pace_by_date.get(ds, {}).get(lead_time)
            if current_otb is None:
                continue

            # Get prior year OTB at same lead time
            prior_otb = pace_by_date.get(prior_ds, {}).get(lead_time)
            if prior_otb is None:
                prior_otb = 0  # Default to 0 if no prior pace data

            # Calculate OTB as % of prior year final
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

    if len(training_rows) < 30:
        raise HTTPException(status_code=400, detail="Insufficient pace data for XGBoost training")

    df = pd.DataFrame(training_rows)
    df['ds'] = pd.to_datetime(df['ds'])

    # Convert to occupancy if needed
    if metric == "occupancy" and total_rooms > 0:
        df["y"] = (df["y"] / total_rooms) * 100
        df["current_otb"] = (df["current_otb"] / total_rooms) * 100
        df["prior_otb_same_lead"] = (df["prior_otb_same_lead"] / total_rooms) * 100
        df["lag_364"] = (df["lag_364"] / total_rooms) * 100

    # Create time-based features
    df['day_of_week'] = df['ds'].dt.dayofweek
    df['month'] = df['ds'].dt.month
    df['week_of_year'] = df['ds'].dt.isocalendar().week.astype(int)
    df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
    df['is_special_date'] = df['ds'].dt.date.apply(lambda x: 1 if x in special_date_set else 0)

    df_train = df.dropna()

    if len(df_train) < 30:
        raise HTTPException(status_code=400, detail="Insufficient data after creating features")

    # Define features - now includes pace features
    feature_cols = ['day_of_week', 'month', 'week_of_year', 'is_weekend', 'is_special_date',
                   'days_out', 'current_otb', 'prior_otb_same_lead', 'lag_364', 'otb_pct_of_prior_final']

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

        # Get current OTB
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

        # Get prior year OTB from booking_pace (uses 364-day offset)
        prior_year_for_otb = forecast_date - timedelta(days=364)
        prior_otb_query = text(f"""
            SELECT {lead_col} as prior_otb
            FROM newbook_booking_pace
            WHERE arrival_date = :prior_date
        """)
        prior_otb_result = await db.execute(prior_otb_query, {"prior_date": prior_year_for_otb})
        prior_otb_row = prior_otb_result.fetchone()

        # Get prior year final from newbook_bookings_stats
        prior_query = text("""
            SELECT booking_count as prior_final
            FROM newbook_bookings_stats
            WHERE date = :prior_date
        """)
        prior_result = await db.execute(prior_query, {"prior_date": prior_year_date})
        prior_row = prior_result.fetchone()

        # Default to 0 for stats, None for pace
        current_otb = current_row.current_otb if current_row and current_row.current_otb is not None else 0
        prior_otb = prior_otb_row.prior_otb if prior_otb_row and prior_otb_row.prior_otb is not None else None
        prior_final = prior_row.prior_final if prior_row and prior_row.prior_final is not None else 0

        # Build features for this date
        forecast_dt = pd.Timestamp(forecast_date)
        lag_364_val = prior_final if prior_final else 0

        # Convert to occupancy if needed
        if metric == "occupancy" and total_rooms > 0:
            if current_otb is not None:
                current_otb = (current_otb / total_rooms) * 100
            if prior_otb is not None:
                prior_otb = (prior_otb / total_rooms) * 100
            if prior_final is not None:
                prior_final = (prior_final / total_rooms) * 100
            lag_364_val = prior_final if prior_final else 0

        # prior_otb is already the prior year OTB at same lead time
        prior_otb_same_lead = prior_otb if prior_otb is not None else 0
        current_otb_val = current_otb if current_otb is not None else 0

        # Calculate OTB as % of prior year final
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

        # Predict
        yhat = float(model.predict(features)[0])

        # Cap at max capacity and round appropriately
        if metric == "occupancy":
            yhat = min(max(yhat, 0), 100.0)
        else:
            # Round to whole rooms for non-occupancy metrics
            yhat = round(min(max(yhat, 0), float(total_rooms)))

        # Floor forecast to current OTB
        if current_otb is not None and yhat < current_otb:
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
                forecast=round(yhat),
                prior_year_final=round(prior_final) if prior_final is not None else None
            ))

    # Round summary totals appropriately
    if metric == "occupancy":
        return XGBoostResponse(
            data=data_points,
            summary=XGBoostSummary(
                otb_total=round(otb_total, 1),
                prior_otb_total=round(prior_otb_total, 1),
                forecast_total=round(forecast_total, 1),
                prior_final_total=round(prior_final_total, 1),
                days_count=len(data_points),
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
                days_count=len(data_points),
                days_forecasting_more=days_forecasting_more,
                days_forecasting_less=days_forecasting_less
            )
        )


# ============================================
# LIVE TFT ENDPOINT
# ============================================

class TFTDataPoint(BaseModel):
    date: str
    day_of_week: str
    current_otb: Optional[float]
    prior_year_otb: Optional[float]
    forecast: Optional[float]
    forecast_lower: Optional[float]
    forecast_upper: Optional[float]
    prior_year_final: Optional[float]


class TFTSummary(BaseModel):
    otb_total: float
    prior_otb_total: float
    forecast_total: float
    prior_final_total: float
    days_count: int
    days_forecasting_more: int
    days_forecasting_less: int


class TFTResponse(BaseModel):
    data: List[TFTDataPoint]
    summary: TFTSummary


@router.get("/tft-preview", response_model=TFTResponse)
async def get_tft_preview(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    metric: str = Query("occupancy", description="Metric: occupancy or rooms"),
    perception_date: Optional[str] = Query(None, description="Optional: Generate forecast as if it was this date (YYYY-MM-DD) for backtesting"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Live forecast using Temporal Fusion Transformer (TFT) model.
    Trains on historical data and forecasts future dates with uncertainty quantiles.
    Uses attention mechanism for feature importance.
    No logging or persistence - pure read-only preview.

    If perception_date is provided, generates forecast as if it was that date,
    training only on data available at that time (for backtesting).
    """
    from datetime import datetime
    import pandas as pd
    import numpy as np
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

    # Get bookable rooms count
    bookable_result = await db.execute(text("""
        SELECT bookable_count
        FROM newbook_bookings_stats
        WHERE bookable_count IS NOT NULL
        ORDER BY date DESC
        LIMIT 1
    """))
    bookable_row = bookable_result.fetchone()
    total_rooms = int(bookable_row.bookable_count) if bookable_row and bookable_row.bookable_count else 25

    # Check if TFT dependencies are available
    try:
        import torch
        from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet
        from pytorch_forecasting.metrics import QuantileLoss
        # Use lightning.pytorch (not pytorch_lightning) to match pytorch_forecasting's internal imports
        from lightning.pytorch import Trainer
        from lightning.pytorch.callbacks import EarlyStopping
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="TFT model dependencies not installed. Install pytorch-forecasting and pytorch-lightning."
        )

    # Get historical data for TFT training (past 2 years)
    history_start = today - timedelta(days=730)
    history_result = await db.execute(text("""
        SELECT date as ds, booking_count as y
        FROM newbook_bookings_stats
        WHERE date >= :history_start
        AND date < :today
        AND booking_count IS NOT NULL
        ORDER BY date
    """), {"history_start": history_start, "today": today})
    history_rows = history_result.fetchall()

    if len(history_rows) < 90:
        raise HTTPException(status_code=400, detail="Insufficient historical data for TFT model (need 90+ days)")

    # Build training dataframe
    df = pd.DataFrame([{"ds": pd.Timestamp(row.ds), "y": float(row.y)} for row in history_rows])

    # Convert to occupancy if needed
    if metric == "occupancy" and total_rooms > 0:
        df["y"] = (df["y"] / total_rooms) * 100

    # Create features (same as tft_model.py)
    df['day_of_week'] = df['ds'].dt.dayofweek
    df['month'] = df['ds'].dt.month
    df['week_of_year'] = df['ds'].dt.isocalendar().week.astype(int)
    df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)

    # Cyclical encoding
    df['dow_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
    df['dow_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)

    # Lag features
    for lag in [7, 14, 21, 28]:
        df[f'lag_{lag}'] = df['y'].shift(lag)

    # Rolling statistics
    for window in [7, 14, 28]:
        df[f'rolling_mean_{window}'] = df['y'].rolling(window=window, min_periods=1).mean()
        df[f'rolling_std_{window}'] = df['y'].rolling(window=window, min_periods=1).std().fillna(0)

    # Add time index and group for TFT
    df['time_idx'] = range(len(df))
    df['group'] = 'hotel'

    # Drop NaN from lag features
    df = df.dropna(subset=['lag_7', 'lag_14', 'lag_21', 'lag_28'])

    if len(df) < 90:
        raise HTTPException(status_code=400, detail="Insufficient data after feature creation")

    # TFT configuration
    ENCODER_LENGTH = 60
    PREDICTION_LENGTH = min(28, (end - start).days + 1)

    # Define features
    time_varying_known = [
        'day_of_week', 'month', 'week_of_year', 'is_weekend',
        'dow_sin', 'dow_cos', 'month_sin', 'month_cos'
    ]

    time_varying_unknown = [
        'y', 'lag_7', 'lag_14', 'lag_21', 'lag_28',
        'rolling_mean_7', 'rolling_mean_14', 'rolling_mean_28',
        'rolling_std_7', 'rolling_std_14', 'rolling_std_28'
    ]

    # Create TimeSeriesDataSet
    training_cutoff = len(df) - PREDICTION_LENGTH

    training = TimeSeriesDataSet(
        df.iloc[:training_cutoff].copy(),
        time_idx="time_idx",
        target="y",
        group_ids=["group"],
        min_encoder_length=ENCODER_LENGTH // 2,
        max_encoder_length=ENCODER_LENGTH,
        min_prediction_length=1,
        max_prediction_length=PREDICTION_LENGTH,
        static_categoricals=["group"],
        time_varying_known_reals=time_varying_known,
        time_varying_unknown_reals=time_varying_unknown,
        add_relative_time_idx=True,
        add_target_scales=True,
        add_encoder_length=True,
    )

    # Create dataloaders
    train_dataloader = training.to_dataloader(train=True, batch_size=64, num_workers=0)

    # Create TFT model
    tft = TemporalFusionTransformer.from_dataset(
        training,
        learning_rate=0.001,
        hidden_size=32,
        attention_head_size=4,
        dropout=0.1,
        hidden_continuous_size=16,
        output_size=7,
        loss=QuantileLoss(),
        reduce_on_plateau_patience=4,
    )

    # Train (limited epochs for live preview)
    early_stop = EarlyStopping(monitor="train_loss", min_delta=1e-4, patience=5, mode="min")
    trainer = Trainer(
        max_epochs=20,  # Reduced for live preview
        accelerator="cpu",
        devices=1,
        enable_model_summary=False,
        callbacks=[early_stop],
        enable_progress_bar=False,
        logger=False,
    )
    trainer.fit(tft, train_dataloaders=train_dataloader)

    # Generate forecasts for future dates
    future_dates = []
    current_date = start
    while current_date <= end:
        if (current_date - today).days >= 0:
            future_dates.append(current_date)
        current_date += timedelta(days=1)

    if not future_dates:
        return TFTResponse(
            data=[],
            summary=TFTSummary(
                otb_total=0, prior_otb_total=0, forecast_total=0,
                prior_final_total=0, days_count=0,
                days_forecasting_more=0, days_forecasting_less=0
            )
        )

    # Build prediction dataframe with placeholder values (not NaN - TFT doesn't allow NaN)
    future_df = pd.DataFrame({'ds': [pd.Timestamp(d) for d in future_dates]})
    # Use last known value as placeholder (will be overwritten by prediction)
    last_known_y = df['y'].iloc[-1]
    future_df['y'] = last_known_y

    # Add features for future dates
    future_df['day_of_week'] = future_df['ds'].dt.dayofweek
    future_df['month'] = future_df['ds'].dt.month
    future_df['week_of_year'] = future_df['ds'].dt.isocalendar().week.astype(int)
    future_df['is_weekend'] = (future_df['day_of_week'] >= 5).astype(int)
    future_df['dow_sin'] = np.sin(2 * np.pi * future_df['day_of_week'] / 7)
    future_df['dow_cos'] = np.cos(2 * np.pi * future_df['day_of_week'] / 7)
    future_df['month_sin'] = np.sin(2 * np.pi * future_df['month'] / 12)
    future_df['month_cos'] = np.cos(2 * np.pi * future_df['month'] / 12)

    # Forward fill lag features from last known values
    for lag in [7, 14, 21, 28]:
        future_df[f'lag_{lag}'] = df['y'].iloc[-1]
    for window in [7, 14, 28]:
        future_df[f'rolling_mean_{window}'] = df[f'rolling_mean_{window}'].iloc[-1]
        future_df[f'rolling_std_{window}'] = df[f'rolling_std_{window}'].iloc[-1]

    # Combine with historical for prediction
    combined = pd.concat([df, future_df], ignore_index=True)
    combined['time_idx'] = range(len(combined))
    combined['group'] = 'hotel'

    # Get predictions - use the last encoder_length + prediction_length rows
    prediction_data = combined.iloc[-(len(future_dates) + ENCODER_LENGTH):].copy()

    try:
        predict_dataset = TimeSeriesDataSet.from_dataset(
            training,
            prediction_data,
            predict=True,
            stop_randomization=True
        )
        predict_dataloader = predict_dataset.to_dataloader(train=False, batch_size=1, num_workers=0)
        # Get raw predictions - returns predictions for all samples in dataloader
        raw_predictions = tft.predict(predict_dataloader, mode="raw", return_x=False)
        # raw_predictions has shape (batch, horizon, n_quantiles)
        pred_values = raw_predictions["prediction"]
        import logging
        logging.info(f"TFT prediction shape: {pred_values.shape}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TFT prediction failed: {str(e)}")

    # Get current OTB and prior year data for each date
    data_points = []
    otb_total = 0.0
    prior_otb_total = 0.0
    forecast_total = 0.0
    prior_final_total = 0.0
    days_forecasting_more = 0
    days_forecasting_less = 0

    for i, forecast_date in enumerate(future_dates):
        if i >= pred_values.shape[1]:
            break

        lead_days = (forecast_date - today).days
        lead_col = get_lead_time_column(lead_days)
        prior_year_date = forecast_date - timedelta(days=364)
        day_of_week = forecast_date.strftime("%a")

        # Get current OTB
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

        # Get prior year OTB
        prior_year_for_otb = forecast_date - timedelta(days=364)
        prior_otb_query = text(f"""
            SELECT {lead_col} as prior_otb
            FROM newbook_booking_pace
            WHERE arrival_date = :prior_date
        """)
        prior_otb_result = await db.execute(prior_otb_query, {"prior_date": prior_year_for_otb})
        prior_otb_row = prior_otb_result.fetchone()

        # Get prior year final
        prior_query = text("""
            SELECT booking_count as prior_final
            FROM newbook_bookings_stats
            WHERE date = :prior_date
        """)
        prior_result = await db.execute(prior_query, {"prior_date": prior_year_date})
        prior_row = prior_result.fetchone()

        current_otb = current_row.current_otb if current_row and current_row.current_otb is not None else 0
        prior_otb = prior_otb_row.prior_otb if prior_otb_row and prior_otb_row.prior_otb is not None else None
        prior_final = prior_row.prior_final if prior_row and prior_row.prior_final is not None else 0

        # Convert to occupancy if needed
        if metric == "occupancy" and total_rooms > 0:
            if current_otb is not None:
                current_otb = (current_otb / total_rooms) * 100
            if prior_otb is not None:
                prior_otb = (prior_otb / total_rooms) * 100
            if prior_final is not None:
                prior_final = (prior_final / total_rooms) * 100

        # Get TFT predictions (quantiles: q10=idx1, q50=idx3, q90=idx5)
        yhat = float(pred_values[0, i, 3])  # Median
        yhat_lower = float(pred_values[0, i, 1])  # 10th percentile
        yhat_upper = float(pred_values[0, i, 5])  # 90th percentile

        # Apply floor/cap
        if metric == "occupancy":
            yhat = min(max(yhat, 0), 100.0)
            yhat_lower = min(max(yhat_lower, 0), 100.0)
            yhat_upper = min(max(yhat_upper, 0), 100.0)
        else:
            yhat = min(max(yhat, 0), float(total_rooms))
            yhat_lower = min(max(yhat_lower, 0), float(total_rooms))
            yhat_upper = min(max(yhat_upper, 0), float(total_rooms))

        # Floor forecast to current OTB and ensure bounds consistency
        if current_otb is not None:
            if yhat < current_otb:
                yhat = current_otb
            if yhat_lower < current_otb:
                yhat_lower = current_otb
            if yhat_upper < current_otb:
                yhat_upper = current_otb
        # Ensure lower <= median <= upper
        yhat_lower = min(yhat_lower, yhat)
        yhat_upper = max(yhat_upper, yhat)

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

        data_points.append(TFTDataPoint(
            date=str(forecast_date),
            day_of_week=day_of_week,
            current_otb=round(current_otb, 1) if current_otb is not None else None,
            prior_year_otb=round(prior_otb, 1) if prior_otb is not None else None,
            forecast=round(yhat, 1),
            forecast_lower=round(yhat_lower, 1),
            forecast_upper=round(yhat_upper, 1),
            prior_year_final=round(prior_final, 1) if prior_final is not None else None
        ))

    return TFTResponse(
        data=data_points,
        summary=TFTSummary(
            otb_total=round(otb_total, 1),
            prior_otb_total=round(prior_otb_total, 1),
            forecast_total=round(forecast_total, 1),
            prior_final_total=round(prior_final_total, 1),
            days_count=len(data_points),
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

    # Get bookable rooms count from latest stats (accounts for maintenance/non-bookable rooms)
    bookable_result = await db.execute(text("""
        SELECT bookable_count
        FROM newbook_bookings_stats
        WHERE bookable_count IS NOT NULL
        ORDER BY date DESC
        LIMIT 1
    """))
    bookable_row = bookable_result.fetchone()
    total_rooms = int(bookable_row.bookable_count) if bookable_row and bookable_row.bookable_count else 25

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

        # Convert to occupancy % if metric is occupancy
        if metric == "occupancy" and total_rooms > 0:
            if current_otb is not None:
                current_otb = (current_otb / total_rooms) * 100
            if prior_otb is not None:
                prior_otb = (prior_otb / total_rooms) * 100
            if prior_final is not None:
                prior_final = (prior_final / total_rooms) * 100

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
                # Cap at max capacity
                if metric == "occupancy" and forecast > 100:
                    forecast = 100.0
                elif metric == "rooms" and forecast > total_rooms:
                    forecast = float(total_rooms)
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

    return PreviewResponse(
        data=data_points,
        summary=PreviewSummary(
            otb_total=round(otb_total, 1),
            forecast_total=round(forecast_total, 1),
            prior_otb_total=round(prior_otb_total, 1),
            prior_final_total=round(prior_final_total, 1),
            pace_pct=pace_pct,
            days_count=len(data_points)
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
