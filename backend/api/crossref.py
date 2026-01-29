"""
Cross-Reference Validation API endpoints
Validate that related forecasts align with each other
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db
from auth import get_current_user

router = APIRouter()


@router.get("/check")
async def run_cross_reference_check(
    check_date: date = Query(..., description="Date to run cross-reference checks for"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Run all cross-reference checks for a specific date.
    Returns validation results showing if forecasts are internally consistent.
    """
    # Get all active cross-reference configurations
    config_query = """
        SELECT check_name, check_category, formula, compares_to, tolerance_pct, input_metrics
        FROM cross_reference_config
        WHERE is_active = TRUE
        ORDER BY display_order
    """

    config_result = await db.execute(text(config_query))
    configs = config_result.fetchall()

    # Get all forecast values for the date
    forecast_query = """
        SELECT forecast_type, predicted_value
        FROM forecasts
        WHERE forecast_date = :check_date
            AND model_type = 'prophet'
    """

    forecast_result = await db.execute(text(forecast_query), {"check_date": check_date})
    forecasts = {row.forecast_type: float(row.predicted_value) for row in forecast_result.fetchall()}

    results = []
    for config in configs:
        # For now, return placeholder results
        # In production, would evaluate formula against forecasts
        compares_to_value = forecasts.get(config.compares_to)

        results.append({
            "check_name": config.check_name,
            "check_category": config.check_category,
            "formula": config.formula,
            "compares_to": config.compares_to,
            "forecasted_value": compares_to_value,
            "calculated_value": None,  # Would be calculated from formula
            "difference": None,
            "difference_pct": None,
            "tolerance_pct": float(config.tolerance_pct),
            "status": "ok"  # Would be evaluated based on tolerance
        })

    return {
        "check_date": check_date,
        "results": results,
        "alignment_score": 100  # Would be calculated
    }


@router.get("/report")
async def get_cross_reference_report(
    from_date: date = Query(...),
    to_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get cross-reference validation report for date range.
    """
    query = """
        SELECT
            forecast_date,
            check_name,
            check_category,
            calculated_value,
            forecasted_value,
            difference,
            difference_pct,
            tolerance_pct,
            status
        FROM forecast_cross_reference
        WHERE forecast_date BETWEEN :from_date AND :to_date
        ORDER BY forecast_date, check_category, check_name
    """

    result = await db.execute(text(query), {"from_date": from_date, "to_date": to_date})
    rows = result.fetchall()

    return [
        {
            "date": row.forecast_date,
            "check_name": row.check_name,
            "category": row.check_category,
            "calculated": float(row.calculated_value) if row.calculated_value else None,
            "forecasted": float(row.forecasted_value) if row.forecasted_value else None,
            "difference": float(row.difference) if row.difference else None,
            "difference_pct": float(row.difference_pct) if row.difference_pct else None,
            "tolerance_pct": float(row.tolerance_pct),
            "status": row.status
        }
        for row in rows
    ]


@router.get("/discrepancies")
async def get_discrepancies(
    from_date: date = Query(...),
    to_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of dates with cross-reference discrepancies.
    """
    query = """
        SELECT
            forecast_date,
            check_name,
            check_category,
            difference_pct,
            tolerance_pct,
            possible_causes,
            recommendation
        FROM forecast_cross_reference
        WHERE forecast_date BETWEEN :from_date AND :to_date
            AND status = 'discrepancy'
        ORDER BY ABS(difference_pct) DESC
    """

    result = await db.execute(text(query), {"from_date": from_date, "to_date": to_date})
    rows = result.fetchall()

    return [
        {
            "date": row.forecast_date,
            "check_name": row.check_name,
            "category": row.check_category,
            "difference_pct": float(row.difference_pct) if row.difference_pct else None,
            "tolerance_pct": float(row.tolerance_pct),
            "possible_causes": row.possible_causes,
            "recommendation": row.recommendation
        }
        for row in rows
    ]


@router.get("/alignment-score")
async def get_alignment_score(
    from_date: date = Query(...),
    to_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get overall alignment score for date range.
    Higher score = more internally consistent forecasts.
    """
    query = """
        SELECT
            COUNT(*) as total_checks,
            SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN status = 'warning' THEN 1 ELSE 0 END) as warnings,
            SUM(CASE WHEN status = 'discrepancy' THEN 1 ELSE 0 END) as discrepancies
        FROM forecast_cross_reference
        WHERE forecast_date BETWEEN :from_date AND :to_date
    """

    result = await db.execute(text(query), {"from_date": from_date, "to_date": to_date})
    row = result.fetchone()

    if not row or row.total_checks == 0:
        return {
            "from_date": from_date,
            "to_date": to_date,
            "alignment_score": 100,
            "total_checks": 0,
            "passed": 0,
            "warnings": 0,
            "discrepancies": 0
        }

    # Score: 100 * (passed / total), with warnings counting as 0.5
    score = ((row.passed + row.warnings * 0.5) / row.total_checks) * 100

    return {
        "from_date": from_date,
        "to_date": to_date,
        "alignment_score": round(score, 1),
        "total_checks": row.total_checks,
        "passed": row.passed,
        "warnings": row.warnings,
        "discrepancies": row.discrepancies
    }


@router.get("/config")
async def get_crossref_config(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get cross-reference check configuration.
    """
    query = """
        SELECT
            check_name,
            check_category,
            description,
            formula,
            compares_to,
            tolerance_pct,
            input_metrics,
            is_correlation_check,
            expected_correlation,
            is_active,
            display_order
        FROM cross_reference_config
        ORDER BY display_order
    """

    result = await db.execute(text(query))
    rows = result.fetchall()

    return [
        {
            "check_name": row.check_name,
            "category": row.check_category,
            "description": row.description,
            "formula": row.formula,
            "compares_to": row.compares_to,
            "tolerance_pct": float(row.tolerance_pct),
            "input_metrics": row.input_metrics,
            "is_correlation_check": row.is_correlation_check,
            "expected_correlation": float(row.expected_correlation) if row.expected_correlation else None,
            "is_active": row.is_active
        }
        for row in rows
    ]


@router.put("/config/{check_name}")
async def update_crossref_config(
    check_name: str,
    tolerance_pct: Optional[float] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update tolerance or active status for a cross-reference check.
    """
    updates = []
    params = {"check_name": check_name}

    if tolerance_pct is not None:
        updates.append("tolerance_pct = :tolerance_pct")
        params["tolerance_pct"] = tolerance_pct

    if is_active is not None:
        updates.append("is_active = :is_active")
        params["is_active"] = is_active

    if not updates:
        return {"status": "no_changes", "check_name": check_name}

    query = f"""
        UPDATE cross_reference_config
        SET {', '.join(updates)}
        WHERE check_name = :check_name
        RETURNING check_name
    """

    result = await db.execute(text(query), params)
    await db.commit()

    row = result.fetchone()
    if not row:
        raise ValueError(f"Check not found: {check_name}")

    return {
        "status": "updated",
        "check_name": check_name,
        "updates": {k: v for k, v in params.items() if k != "check_name"}
    }
