"""
Budget API endpoints
"""
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from database import get_db
from auth import get_current_user

router = APIRouter()


class MonthlyBudgetCreate(BaseModel):
    year: int
    month: int
    budget_type: str
    budget_value: float
    notes: Optional[str] = None


class MonthlyBudgetResponse(BaseModel):
    id: int
    year: int
    month: int
    budget_type: str
    budget_value: float
    notes: Optional[str]


@router.get("/monthly")
async def get_monthly_budgets(
    year: int = Query(..., description="Year to get budgets for"),
    budget_type: Optional[str] = Query(None, description="Filter by budget type"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get monthly budgets for a year.
    """
    query = """
        SELECT id, year, month, budget_type, budget_value, notes, created_at, updated_at
        FROM monthly_budgets
        WHERE year = :year
    """
    params = {"year": year}

    if budget_type:
        query += " AND budget_type = :budget_type"
        params["budget_type"] = budget_type

    query += " ORDER BY month, budget_type"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "id": row.id,
            "year": row.year,
            "month": row.month,
            "budget_type": row.budget_type,
            "budget_value": float(row.budget_value),
            "notes": row.notes,
            "created_at": row.created_at,
            "updated_at": row.updated_at
        }
        for row in rows
    ]


@router.post("/monthly")
async def create_or_update_monthly_budget(
    budget: MonthlyBudgetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create or update a monthly budget.
    """
    query = """
        INSERT INTO monthly_budgets (year, month, budget_type, budget_value, notes, updated_at)
        VALUES (:year, :month, :budget_type, :budget_value, :notes, NOW())
        ON CONFLICT (year, month, budget_type)
        DO UPDATE SET budget_value = :budget_value, notes = :notes, updated_at = NOW()
        RETURNING id
    """

    result = await db.execute(text(query), {
        "year": budget.year,
        "month": budget.month,
        "budget_type": budget.budget_type,
        "budget_value": budget.budget_value,
        "notes": budget.notes
    })
    await db.commit()

    row = result.fetchone()
    return {"id": row.id, "status": "saved", **budget.model_dump()}


@router.get("/daily")
async def get_daily_budgets(
    from_date: date = Query(...),
    to_date: date = Query(...),
    budget_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get daily distributed budgets for a date range.
    """
    query = """
        SELECT
            date,
            budget_type,
            budget_value,
            distribution_method,
            prior_year_pct
        FROM daily_budgets
        WHERE date BETWEEN :from_date AND :to_date
    """
    params = {"from_date": from_date, "to_date": to_date}

    if budget_type:
        query += " AND budget_type = :budget_type"
        params["budget_type"] = budget_type

    query += " ORDER BY date, budget_type"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "date": row.date,
            "budget_type": row.budget_type,
            "budget_value": float(row.budget_value),
            "distribution_method": row.distribution_method,
            "prior_year_pct": float(row.prior_year_pct) if row.prior_year_pct else None
        }
        for row in rows
    ]


@router.post("/distribute")
async def distribute_monthly_budget(
    year: int = Query(...),
    month: int = Query(...),
    budget_type: Optional[str] = Query(None, description="Budget type to distribute, or all if not specified"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Distribute monthly budget to daily values using prior year patterns.
    """
    from services.forecasting.budget_service import distribute_budget

    result = await distribute_budget(db, year, month, budget_type)

    return {
        "status": "distributed",
        "year": year,
        "month": month,
        "budget_type": budget_type or "all",
        "days_distributed": result.get("days_distributed", 0)
    }


@router.get("/variance")
async def get_budget_variance(
    from_date: date = Query(...),
    to_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get forecast vs budget vs actual variance for date range.
    """
    query = """
        SELECT
            db.date,
            db.budget_type,
            db.budget_value,
            f.predicted_value as forecast_value,
            dm.actual_value,
            (f.predicted_value - db.budget_value) as forecast_vs_budget,
            CASE WHEN db.budget_value != 0 THEN
                ROUND(((f.predicted_value - db.budget_value) / db.budget_value * 100)::numeric, 2)
            END as forecast_vs_budget_pct,
            CASE WHEN dm.actual_value IS NOT NULL THEN
                (dm.actual_value - db.budget_value)
            END as actual_vs_budget,
            CASE WHEN dm.actual_value IS NOT NULL AND db.budget_value != 0 THEN
                ROUND(((dm.actual_value - db.budget_value) / db.budget_value * 100)::numeric, 2)
            END as actual_vs_budget_pct
        FROM daily_budgets db
        LEFT JOIN forecasts f ON db.date = f.forecast_date
            AND db.budget_type = f.forecast_type
            AND f.model_type = 'prophet'
        LEFT JOIN daily_metrics dm ON db.date = dm.date
            AND db.budget_type = dm.metric_code
        WHERE db.date BETWEEN :from_date AND :to_date
        ORDER BY db.date, db.budget_type
    """

    result = await db.execute(text(query), {"from_date": from_date, "to_date": to_date})
    rows = result.fetchall()

    return [
        {
            "date": row.date,
            "budget_type": row.budget_type,
            "budget": float(row.budget_value) if row.budget_value else None,
            "forecast": float(row.forecast_value) if row.forecast_value else None,
            "actual": float(row.actual_value) if row.actual_value else None,
            "forecast_vs_budget": float(row.forecast_vs_budget) if row.forecast_vs_budget else None,
            "forecast_vs_budget_pct": float(row.forecast_vs_budget_pct) if row.forecast_vs_budget_pct else None,
            "actual_vs_budget": float(row.actual_vs_budget) if row.actual_vs_budget else None,
            "actual_vs_budget_pct": float(row.actual_vs_budget_pct) if row.actual_vs_budget_pct else None
        }
        for row in rows
    ]
