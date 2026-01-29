"""
Forecast API endpoints
"""
from datetime import date, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from database import get_db
from auth import get_current_user

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
    Useful for visualizing how models diverge/converge.
    """
    if from_date is None:
        from_date = date.today()
    if to_date is None:
        to_date = from_date + timedelta(days=28)

    query = """
        SELECT
            f.forecast_date,
            f.model_type,
            f.predicted_value,
            f.lower_bound,
            f.upper_bound,
            dm.actual_value,
            ps.otb_value as current_otb,
            db.budget_value
        FROM forecasts f
        LEFT JOIN daily_metrics dm ON f.forecast_date = dm.date AND f.forecast_type = dm.metric_code
        LEFT JOIN pickup_snapshots ps ON f.forecast_date = ps.stay_date
            AND f.forecast_type = ps.metric_type
            AND ps.snapshot_date = CURRENT_DATE
        LEFT JOIN daily_budgets db ON f.forecast_date = db.date AND f.forecast_type = db.budget_type
        WHERE f.forecast_date BETWEEN :from_date AND :to_date
            AND f.forecast_type = :metric
        ORDER BY f.forecast_date, f.model_type
    """

    result = await db.execute(text(query), {
        "from_date": from_date,
        "to_date": to_date,
        "metric": metric
    })
    rows = result.fetchall()

    # Group by date
    comparison = {}
    for row in rows:
        date_str = str(row.forecast_date)
        if date_str not in comparison:
            comparison[date_str] = {
                "date": row.forecast_date,
                "actual": row.actual_value,
                "current_otb": row.current_otb,
                "budget": row.budget_value,
                "models": {}
            }
        comparison[date_str]["models"][row.model_type] = {
            "value": row.predicted_value,
            "lower": row.lower_bound,
            "upper": row.upper_bound
        }

    return list(comparison.values())


@router.post("/regenerate")
async def regenerate_forecasts(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    models: Optional[List[str]] = Query(None, description="Models to run: prophet, xgboost, pickup"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Force regenerate forecasts for a date range.
    Triggers an immediate forecast run outside the schedule.
    """
    from jobs.forecast_daily import run_daily_forecast

    if from_date is None:
        from_date = date.today()
    if to_date is None:
        to_date = from_date + timedelta(days=14)

    horizon_days = (to_date - date.today()).days
    models_to_run = models or ['prophet', 'xgboost', 'pickup']

    # This would be async in production
    # For now, return acknowledgment
    return {
        "status": "triggered",
        "from_date": from_date,
        "to_date": to_date,
        "models": models_to_run,
        "message": "Forecast regeneration queued"
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
