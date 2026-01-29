"""
Export API endpoints for Excel/CSV downloads
"""
import io
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import pandas as pd

from database import get_db
from auth import get_current_user

router = APIRouter()


@router.get("/excel")
async def export_excel(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Download Excel workbook with multiple sheets:
    - Daily Forecast (all models)
    - Weekly Summary
    - Budget Comparison
    - Model Accuracy
    """
    if from_date is None:
        from_date = date.today()
    if to_date is None:
        to_date = from_date + timedelta(days=28)

    # Create Excel writer
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Daily forecasts sheet
        daily_query = """
            SELECT
                f.forecast_date as "Date",
                f.forecast_type as "Metric",
                MAX(CASE WHEN f.model_type = 'prophet' THEN f.predicted_value END) as "Prophet",
                MAX(CASE WHEN f.model_type = 'prophet' THEN f.lower_bound END) as "Prophet Lower",
                MAX(CASE WHEN f.model_type = 'prophet' THEN f.upper_bound END) as "Prophet Upper",
                MAX(CASE WHEN f.model_type = 'xgboost' THEN f.predicted_value END) as "XGBoost",
                MAX(CASE WHEN f.model_type = 'pickup' THEN f.predicted_value END) as "Pickup",
                db.budget_value as "Budget"
            FROM forecasts f
            LEFT JOIN daily_budgets db ON f.forecast_date = db.date AND f.forecast_type = db.budget_type
            WHERE f.forecast_date BETWEEN :from_date AND :to_date
            GROUP BY f.forecast_date, f.forecast_type, db.budget_value
            ORDER BY f.forecast_date, f.forecast_type
        """
        result = await db.execute(text(daily_query), {"from_date": from_date, "to_date": to_date})
        daily_df = pd.DataFrame(result.fetchall())
        if not daily_df.empty:
            daily_df.to_excel(writer, sheet_name='Daily Forecast', index=False)

        # Weekly summary sheet
        weekly_query = """
            SELECT
                DATE_TRUNC('week', f.forecast_date) as "Week Start",
                f.forecast_type as "Metric",
                AVG(f.predicted_value) as "Avg Forecast",
                SUM(f.predicted_value) as "Total Forecast",
                AVG(db.budget_value) as "Avg Budget",
                SUM(db.budget_value) as "Total Budget"
            FROM forecasts f
            LEFT JOIN daily_budgets db ON f.forecast_date = db.date AND f.forecast_type = db.budget_type
            WHERE f.forecast_date BETWEEN :from_date AND :to_date
                AND f.model_type = 'prophet'
            GROUP BY DATE_TRUNC('week', f.forecast_date), f.forecast_type
            ORDER BY "Week Start", f.forecast_type
        """
        result = await db.execute(text(weekly_query), {"from_date": from_date, "to_date": to_date})
        weekly_df = pd.DataFrame(result.fetchall())
        if not weekly_df.empty:
            weekly_df.to_excel(writer, sheet_name='Weekly Summary', index=False)

        # Budget variance sheet
        variance_query = """
            SELECT
                f.forecast_date as "Date",
                f.forecast_type as "Metric",
                f.predicted_value as "Forecast",
                db.budget_value as "Budget",
                (f.predicted_value - db.budget_value) as "Variance",
                CASE
                    WHEN db.budget_value != 0 THEN
                        ROUND(((f.predicted_value - db.budget_value) / db.budget_value * 100)::numeric, 1)
                    ELSE NULL
                END as "Variance %"
            FROM forecasts f
            LEFT JOIN daily_budgets db ON f.forecast_date = db.date AND f.forecast_type = db.budget_type
            WHERE f.forecast_date BETWEEN :from_date AND :to_date
                AND f.model_type = 'prophet'
            ORDER BY f.forecast_date, f.forecast_type
        """
        result = await db.execute(text(variance_query), {"from_date": from_date, "to_date": to_date})
        variance_df = pd.DataFrame(result.fetchall())
        if not variance_df.empty:
            variance_df.to_excel(writer, sheet_name='Budget Variance', index=False)

        # Accuracy sheet (historical)
        accuracy_query = """
            SELECT
                date as "Date",
                metric_type as "Metric",
                actual_value as "Actual",
                prophet_forecast as "Prophet",
                xgboost_forecast as "XGBoost",
                pickup_forecast as "Pickup",
                best_model as "Best Model"
            FROM actual_vs_forecast
            WHERE date BETWEEN :from_date - INTERVAL '30 days' AND :from_date
            ORDER BY date, metric_type
        """
        result = await db.execute(text(accuracy_query), {"from_date": from_date, "to_date": to_date})
        accuracy_df = pd.DataFrame(result.fetchall())
        if not accuracy_df.empty:
            accuracy_df.to_excel(writer, sheet_name='Historical Accuracy', index=False)

    output.seek(0)

    filename = f"forecast_{from_date}_{to_date}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/csv/{metric}")
async def export_csv(
    metric: str,
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Download CSV for a specific metric.
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
            db.budget_value
        FROM forecasts f
        LEFT JOIN daily_metrics dm ON f.forecast_date = dm.date AND f.forecast_type = dm.metric_code
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

    df = pd.DataFrame(result.fetchall())

    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)

    filename = f"{metric}_{from_date}_{to_date}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/model-comparison")
async def export_model_comparison(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Export model comparison data for all metrics.
    """
    if from_date is None:
        from_date = date.today()
    if to_date is None:
        to_date = from_date + timedelta(days=28)

    query = """
        SELECT
            f.forecast_date,
            f.forecast_type,
            fm.metric_name,
            MAX(CASE WHEN f.model_type = 'prophet' THEN f.predicted_value END) as prophet,
            MAX(CASE WHEN f.model_type = 'xgboost' THEN f.predicted_value END) as xgboost,
            MAX(CASE WHEN f.model_type = 'pickup' THEN f.predicted_value END) as pickup,
            dm.actual_value
        FROM forecasts f
        LEFT JOIN forecast_metrics fm ON f.forecast_type = fm.metric_code
        LEFT JOIN daily_metrics dm ON f.forecast_date = dm.date AND f.forecast_type = dm.metric_code
        WHERE f.forecast_date BETWEEN :from_date AND :to_date
        GROUP BY f.forecast_date, f.forecast_type, fm.metric_name, dm.actual_value
        ORDER BY f.forecast_date, f.forecast_type
    """

    result = await db.execute(text(query), {"from_date": from_date, "to_date": to_date})
    df = pd.DataFrame(result.fetchall())

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Model Comparison', index=False)

    output.seek(0)

    filename = f"model_comparison_{from_date}_{to_date}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
