"""
Forecast Evolution API endpoints
Track how forecasts change over time as dates approach
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db
from auth import get_current_user

router = APIRouter()


@router.get("/date")
async def get_forecast_evolution_for_date(
    forecast_date: date = Query(..., description="The date to see evolution for"),
    forecast_type: str = Query(..., description="Metric code"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get full forecast history for a specific date.
    Shows how predictions changed as the date approached.
    """
    query = """
        SELECT
            fh.generated_at,
            fh.model_type,
            fh.predicted_value,
            fh.lower_bound,
            fh.upper_bound,
            fh.horizon_days,
            fh.change_amount,
            fh.change_pct,
            fh.change_reason,
            dm.actual_value
        FROM forecast_history fh
        LEFT JOIN daily_metrics dm ON fh.forecast_date = dm.date AND fh.forecast_type = dm.metric_code
        WHERE fh.forecast_date = :forecast_date
            AND fh.forecast_type = :forecast_type
        ORDER BY fh.generated_at, fh.model_type
    """

    result = await db.execute(text(query), {
        "forecast_date": forecast_date,
        "forecast_type": forecast_type
    })
    rows = result.fetchall()

    return [
        {
            "generated_at": row.generated_at,
            "model_type": row.model_type,
            "predicted_value": float(row.predicted_value),
            "lower_bound": float(row.lower_bound) if row.lower_bound else None,
            "upper_bound": float(row.upper_bound) if row.upper_bound else None,
            "horizon_days": row.horizon_days,
            "change_amount": float(row.change_amount) if row.change_amount else None,
            "change_pct": float(row.change_pct) if row.change_pct else None,
            "change_reason": row.change_reason,
            "actual_value": float(row.actual_value) if row.actual_value else None
        }
        for row in rows
    ]


@router.get("/chart-data")
async def get_evolution_chart_data(
    forecast_date: date = Query(...),
    forecast_type: str = Query(...),
    model: str = Query("prophet", description="Model: prophet, xgboost, pickup"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get evolution data formatted for charting.
    Returns time series of forecast values as date approached.
    """
    query = """
        SELECT
            DATE(fh.generated_at) as update_date,
            fh.horizon_days,
            fh.predicted_value,
            fh.lower_bound,
            fh.upper_bound,
            dm.actual_value
        FROM forecast_history fh
        LEFT JOIN daily_metrics dm ON fh.forecast_date = dm.date AND fh.forecast_type = dm.metric_code
        WHERE fh.forecast_date = :forecast_date
            AND fh.forecast_type = :forecast_type
            AND fh.model_type = :model
        ORDER BY fh.generated_at
    """

    result = await db.execute(text(query), {
        "forecast_date": forecast_date,
        "forecast_type": forecast_type,
        "model": model
    })
    rows = result.fetchall()

    actual_value = None
    chart_data = []

    for row in rows:
        if row.actual_value:
            actual_value = float(row.actual_value)
        chart_data.append({
            "update_date": row.update_date,
            "horizon_days": row.horizon_days,
            "predicted_value": float(row.predicted_value),
            "lower_bound": float(row.lower_bound) if row.lower_bound else None,
            "upper_bound": float(row.upper_bound) if row.upper_bound else None
        })

    return {
        "forecast_date": forecast_date,
        "forecast_type": forecast_type,
        "model": model,
        "actual_value": actual_value,
        "data_points": chart_data
    }


@router.get("/changes")
async def get_forecast_changes(
    forecast_date: date = Query(...),
    forecast_type: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of all changes with reasons for a specific forecast.
    """
    query = """
        SELECT
            changed_at,
            model_type,
            old_value,
            new_value,
            change_amount,
            change_pct,
            change_category,
            change_reason,
            bookings_added,
            bookings_cancelled,
            covers_change,
            days_out,
            otb_at_change
        FROM forecast_change_log
        WHERE forecast_date = :forecast_date
            AND forecast_type = :forecast_type
        ORDER BY changed_at DESC
    """

    result = await db.execute(text(query), {
        "forecast_date": forecast_date,
        "forecast_type": forecast_type
    })
    rows = result.fetchall()

    return [
        {
            "changed_at": row.changed_at,
            "model_type": row.model_type,
            "old_value": float(row.old_value) if row.old_value else None,
            "new_value": float(row.new_value) if row.new_value else None,
            "change_amount": float(row.change_amount) if row.change_amount else None,
            "change_pct": float(row.change_pct) if row.change_pct else None,
            "change_category": row.change_category,
            "change_reason": row.change_reason,
            "bookings_added": row.bookings_added,
            "bookings_cancelled": row.bookings_cancelled,
            "covers_change": row.covers_change,
            "days_out": row.days_out,
            "otb_at_change": float(row.otb_at_change) if row.otb_at_change else None
        }
        for row in rows
    ]


@router.get("/convergence")
async def get_forecast_convergence(
    from_date: date = Query(...),
    to_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Analyze how quickly forecasts converge to actuals.
    Shows forecast accuracy at different lead times.
    """
    query = """
        WITH convergence_data AS (
            SELECT
                fh.forecast_type,
                fh.model_type,
                fh.horizon_days,
                ABS(fh.predicted_value - dm.actual_value) as abs_error,
                ABS((fh.predicted_value - dm.actual_value) / NULLIF(dm.actual_value, 0) * 100) as pct_error
            FROM forecast_history fh
            JOIN daily_metrics dm ON fh.forecast_date = dm.date AND fh.forecast_type = dm.metric_code
            WHERE fh.forecast_date BETWEEN :from_date AND :to_date
                AND dm.actual_value IS NOT NULL
        )
        SELECT
            forecast_type,
            model_type,
            CASE
                WHEN horizon_days <= 7 THEN '0-7 days'
                WHEN horizon_days <= 14 THEN '8-14 days'
                WHEN horizon_days <= 21 THEN '15-21 days'
                WHEN horizon_days <= 28 THEN '22-28 days'
                ELSE '29+ days'
            END as horizon_bucket,
            AVG(abs_error) as avg_error,
            AVG(pct_error) as avg_pct_error,
            COUNT(*) as sample_count
        FROM convergence_data
        GROUP BY forecast_type, model_type,
            CASE
                WHEN horizon_days <= 7 THEN '0-7 days'
                WHEN horizon_days <= 14 THEN '8-14 days'
                WHEN horizon_days <= 21 THEN '15-21 days'
                WHEN horizon_days <= 28 THEN '22-28 days'
                ELSE '29+ days'
            END
        ORDER BY forecast_type, model_type, horizon_bucket
    """

    result = await db.execute(text(query), {"from_date": from_date, "to_date": to_date})
    rows = result.fetchall()

    return [
        {
            "forecast_type": row.forecast_type,
            "model_type": row.model_type,
            "horizon_bucket": row.horizon_bucket,
            "avg_error": round(float(row.avg_error), 2) if row.avg_error else None,
            "avg_pct_error": round(float(row.avg_pct_error), 2) if row.avg_pct_error else None,
            "sample_count": row.sample_count
        }
        for row in rows
    ]


@router.get("/volatility")
async def get_forecast_volatility(
    from_date: date = Query(...),
    to_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Identify dates with high forecast volatility.
    Shows which dates had the most forecast changes.
    """
    query = """
        SELECT
            forecast_date,
            forecast_type,
            COUNT(*) as change_count,
            MAX(ABS(change_amount)) as max_change,
            SUM(ABS(change_amount)) as total_change,
            array_agg(DISTINCT change_category) as change_categories
        FROM forecast_change_log
        WHERE forecast_date BETWEEN :from_date AND :to_date
        GROUP BY forecast_date, forecast_type
        HAVING COUNT(*) > 3 OR MAX(ABS(change_pct)) > 10
        ORDER BY total_change DESC
        LIMIT 20
    """

    result = await db.execute(text(query), {"from_date": from_date, "to_date": to_date})
    rows = result.fetchall()

    return [
        {
            "forecast_date": row.forecast_date,
            "forecast_type": row.forecast_type,
            "change_count": row.change_count,
            "max_change": float(row.max_change) if row.max_change else None,
            "total_change": float(row.total_change) if row.total_change else None,
            "change_categories": row.change_categories
        }
        for row in rows
    ]
