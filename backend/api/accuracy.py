"""
Accuracy tracking API endpoints
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db
from auth import get_current_user

router = APIRouter()


@router.get("/summary")
async def get_accuracy_summary(
    from_date: date = Query(..., description="Start date"),
    to_date: date = Query(..., description="End date"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get model accuracy comparison over date range.
    Returns MAE, RMSE, MAPE for each model.
    """
    query = """
        SELECT
            metric_type,
            COUNT(*) as sample_count,
            -- Prophet metrics
            AVG(ABS(prophet_error)) as prophet_mae,
            SQRT(AVG(prophet_error * prophet_error)) as prophet_rmse,
            AVG(ABS(prophet_pct_error)) as prophet_mape,
            -- XGBoost metrics
            AVG(ABS(xgboost_error)) as xgboost_mae,
            SQRT(AVG(xgboost_error * xgboost_error)) as xgboost_rmse,
            AVG(ABS(xgboost_pct_error)) as xgboost_mape,
            -- Pickup metrics
            AVG(ABS(pickup_error)) as pickup_mae,
            SQRT(AVG(pickup_error * pickup_error)) as pickup_rmse,
            AVG(ABS(pickup_pct_error)) as pickup_mape,
            -- Best model distribution
            SUM(CASE WHEN best_model = 'prophet' THEN 1 ELSE 0 END) as prophet_wins,
            SUM(CASE WHEN best_model = 'xgboost' THEN 1 ELSE 0 END) as xgboost_wins,
            SUM(CASE WHEN best_model = 'pickup' THEN 1 ELSE 0 END) as pickup_wins
        FROM actual_vs_forecast
        WHERE date BETWEEN :from_date AND :to_date
            AND actual_value IS NOT NULL
        GROUP BY metric_type
        ORDER BY metric_type
    """

    result = await db.execute(text(query), {"from_date": from_date, "to_date": to_date})
    rows = result.fetchall()

    return [
        {
            "metric_type": row.metric_type,
            "sample_count": row.sample_count,
            "prophet": {
                "mae": round(float(row.prophet_mae), 2) if row.prophet_mae else None,
                "rmse": round(float(row.prophet_rmse), 2) if row.prophet_rmse else None,
                "mape": round(float(row.prophet_mape), 2) if row.prophet_mape else None,
                "wins": row.prophet_wins
            },
            "xgboost": {
                "mae": round(float(row.xgboost_mae), 2) if row.xgboost_mae else None,
                "rmse": round(float(row.xgboost_rmse), 2) if row.xgboost_rmse else None,
                "mape": round(float(row.xgboost_mape), 2) if row.xgboost_mape else None,
                "wins": row.xgboost_wins
            },
            "pickup": {
                "mae": round(float(row.pickup_mae), 2) if row.pickup_mae else None,
                "rmse": round(float(row.pickup_rmse), 2) if row.pickup_rmse else None,
                "mape": round(float(row.pickup_mape), 2) if row.pickup_mape else None,
                "wins": row.pickup_wins
            }
        }
        for row in rows
    ]


@router.get("/by-model")
async def get_accuracy_by_model(
    model: str = Query(..., description="Model: prophet, xgboost, pickup"),
    from_date: date = Query(...),
    to_date: date = Query(...),
    metric_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get detailed accuracy for a specific model.
    """
    column_map = {
        "prophet": ("prophet_forecast", "prophet_error", "prophet_pct_error"),
        "xgboost": ("xgboost_forecast", "xgboost_error", "xgboost_pct_error"),
        "pickup": ("pickup_forecast", "pickup_error", "pickup_pct_error")
    }

    if model not in column_map:
        raise ValueError(f"Invalid model: {model}")

    forecast_col, error_col, pct_error_col = column_map[model]

    query = f"""
        SELECT
            date,
            metric_type,
            actual_value,
            {forecast_col} as forecast,
            {error_col} as error,
            {pct_error_col} as pct_error,
            best_model
        FROM actual_vs_forecast
        WHERE date BETWEEN :from_date AND :to_date
            AND actual_value IS NOT NULL
    """
    params = {"from_date": from_date, "to_date": to_date}

    if metric_type:
        query += " AND metric_type = :metric_type"
        params["metric_type"] = metric_type

    query += " ORDER BY date, metric_type"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "date": row.date,
            "metric_type": row.metric_type,
            "actual": float(row.actual_value),
            "forecast": float(row.forecast) if row.forecast else None,
            "error": float(row.error) if row.error else None,
            "pct_error": float(row.pct_error) if row.pct_error else None,
            "was_best": row.best_model == model
        }
        for row in rows
    ]


@router.get("/best-model")
async def get_best_model_analysis(
    from_date: date = Query(...),
    to_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Analyze which model performs best by metric type and time period.
    """
    query = """
        WITH model_performance AS (
            SELECT
                metric_type,
                DATE_TRUNC('week', date) as week,
                best_model,
                COUNT(*) as count
            FROM actual_vs_forecast
            WHERE date BETWEEN :from_date AND :to_date
                AND actual_value IS NOT NULL
            GROUP BY metric_type, DATE_TRUNC('week', date), best_model
        )
        SELECT
            metric_type,
            week,
            best_model,
            count,
            ROUND(count * 100.0 / SUM(count) OVER (PARTITION BY metric_type, week), 1) as pct
        FROM model_performance
        ORDER BY metric_type, week, count DESC
    """

    result = await db.execute(text(query), {"from_date": from_date, "to_date": to_date})
    rows = result.fetchall()

    return [
        {
            "metric_type": row.metric_type,
            "week": row.week,
            "best_model": row.best_model,
            "count": row.count,
            "percentage": float(row.pct)
        }
        for row in rows
    ]


@router.get("/by-lead-time")
async def get_accuracy_by_lead_time(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    metric_code: Optional[str] = Query(None, description="Filter by metric code"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get accuracy aggregated by lead time brackets from backtest data.
    Returns MAPE for each model at different lead times (7, 14, 28, 60, 90 days).
    """
    if from_date is None:
        from_date = date.today() - timedelta(days=365)
    if to_date is None:
        to_date = date.today()

    # Define lead time brackets
    brackets = [
        (0, 7, "1 week"),
        (8, 14, "2 weeks"),
        (15, 28, "1 month"),
        (29, 60, "2 months"),
        (61, 90, "3 months"),
        (91, 180, "6 months"),
        (181, 365, "1 year")
    ]

    query = """
        SELECT
            CASE
                WHEN days_out <= 7 THEN '1 week'
                WHEN days_out <= 14 THEN '2 weeks'
                WHEN days_out <= 28 THEN '1 month'
                WHEN days_out <= 60 THEN '2 months'
                WHEN days_out <= 90 THEN '3 months'
                WHEN days_out <= 180 THEN '6 months'
                ELSE '1 year'
            END as lead_time_label,
            CASE
                WHEN days_out <= 7 THEN 1
                WHEN days_out <= 14 THEN 2
                WHEN days_out <= 28 THEN 3
                WHEN days_out <= 60 THEN 4
                WHEN days_out <= 90 THEN 5
                WHEN days_out <= 180 THEN 6
                ELSE 7
            END as sort_order,
            model,
            metric_code,
            AVG(ABS((forecast_value - actual_value) / NULLIF(actual_value, 0) * 100)) as mape,
            AVG(ABS(forecast_value - actual_value)) as mae,
            COUNT(*) as sample_count
        FROM forecast_snapshots
        WHERE target_date BETWEEN :from_date AND :to_date
            AND actual_value IS NOT NULL
    """
    params = {"from_date": from_date, "to_date": to_date}

    if metric_code:
        query += " AND metric_code = :metric_code"
        params["metric_code"] = metric_code

    query += """
        GROUP BY
            CASE
                WHEN days_out <= 7 THEN '1 week'
                WHEN days_out <= 14 THEN '2 weeks'
                WHEN days_out <= 28 THEN '1 month'
                WHEN days_out <= 60 THEN '2 months'
                WHEN days_out <= 90 THEN '3 months'
                WHEN days_out <= 180 THEN '6 months'
                ELSE '1 year'
            END,
            CASE
                WHEN days_out <= 7 THEN 1
                WHEN days_out <= 14 THEN 2
                WHEN days_out <= 28 THEN 3
                WHEN days_out <= 60 THEN 4
                WHEN days_out <= 90 THEN 5
                WHEN days_out <= 180 THEN 6
                ELSE 7
            END,
            model,
            metric_code
        ORDER BY sort_order, model
    """

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "lead_time": row.lead_time_label,
            "model": row.model,
            "metric_code": row.metric_code,
            "mape": round(float(row.mape), 2) if row.mape else None,
            "mae": round(float(row.mae), 2) if row.mae else None,
            "sample_count": row.sample_count
        }
        for row in rows
    ]


@router.get("/by-horizon")
async def get_accuracy_by_horizon(
    horizon: int = Query(..., description="Lead time in days (7, 14, 28)"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get accuracy at different lead times from backtest data.
    Shows how forecast accuracy degrades as horizon increases.
    Uses forecast_snapshots table populated by backtests.
    """
    if from_date is None:
        from_date = date.today() - timedelta(days=90)
    if to_date is None:
        to_date = date.today()

    # Query forecast_snapshots table (populated by backtests)
    query = """
        SELECT
            metric_code as forecast_type,
            days_out as horizon_days,
            model as model_type,
            AVG(ABS(forecast_value - actual_value)) as mae,
            AVG(ABS((forecast_value - actual_value) / NULLIF(actual_value, 0) * 100)) as mape,
            COUNT(*) as sample_count
        FROM forecast_snapshots
        WHERE target_date BETWEEN :from_date AND :to_date
            AND days_out = :horizon
            AND actual_value IS NOT NULL
        GROUP BY metric_code, days_out, model
        ORDER BY metric_code, model
    """

    result = await db.execute(text(query), {
        "from_date": from_date,
        "to_date": to_date,
        "horizon": horizon
    })
    rows = result.fetchall()

    return [
        {
            "forecast_type": row.forecast_type,
            "horizon_days": row.horizon_days,
            "model_type": row.model_type,
            "mae": round(float(row.mae), 2) if row.mae else None,
            "mape": round(float(row.mape), 2) if row.mape else None,
            "sample_count": row.sample_count
        }
        for row in rows
    ]
