"""
Backtesting API endpoints for model accuracy evaluation.

Run backtests to evaluate how well models would have performed
on historical data using only information available at the time.
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db
from auth import get_current_user
from utils.time_alignment import get_prior_year_daily

router = APIRouter()


@router.post("/run")
async def run_backtest(
    metric_code: str = Query(..., description="Metric to backtest"),
    from_date: date = Query(..., description="Start of backtest period"),
    to_date: date = Query(..., description="End of backtest period"),
    lead_times: str = Query("7,14,21,28", description="Comma-separated lead times in days"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Run backtest for a metric over a date range.

    For each historical date, simulates what the forecast would have been
    at various lead times using only data available at that time.

    Uses booking_placed timestamps from newbook_bookings to reconstruct
    what OTB values would have been at each simulated date.

    Returns accuracy metrics comparing predicted vs actual values.
    """
    lead_time_list = [int(x.strip()) for x in lead_times.split(",")]

    results = []
    total_rooms = 25

    # Overflow room category (category_id=5) is used for chargeable no-shows/cancellations
    # and should be excluded from room night counts
    overflow_category_id = '5'

    # Get room capacity (SUM across all room categories for a single date)
    if metric_code in ('hotel_room_nights', 'hotel_occupancy_pct'):
        rooms_result = await db.execute(
            text("""
            SELECT COALESCE(SUM(available), 25) as total_rooms
            FROM newbook_occupancy_report
            WHERE date = (
                SELECT MAX(date) FROM newbook_occupancy_report
                WHERE date <= :from_date
            )
            """),
            {"from_date": from_date}
        )
        rooms_row = rooms_result.fetchone()
        if rooms_row and rooms_row.total_rooms:
            total_rooms = int(rooms_row.total_rooms)

    # Process each date
    current_date = from_date
    while current_date <= to_date:
        # Get actual value for this date
        actual_result = await db.execute(
            text("""
            SELECT actual_value
            FROM daily_metrics
            WHERE date = :target_date AND metric_code = :metric
            """),
            {"target_date": current_date, "metric": metric_code}
        )
        actual_row = actual_result.fetchone()
        actual_value = float(actual_row.actual_value) if actual_row and actual_row.actual_value else None

        if actual_value is None:
            current_date += timedelta(days=1)
            continue

        # For each lead time, simulate the forecast
        for lead_time in lead_time_list:
            simulated_today = current_date - timedelta(days=lead_time)

            # First try to get OTB from snapshots
            otb_result = await db.execute(
                text("""
                SELECT otb_value, snapshot_date, days_out
                FROM pickup_snapshots
                WHERE stay_date = :target_date
                    AND metric_type = :metric
                    AND snapshot_date <= :simulated_today
                ORDER BY snapshot_date DESC
                LIMIT 1
                """),
                {
                    "target_date": current_date,
                    "metric": metric_code,
                    "simulated_today": simulated_today
                }
            )
            otb_row = otb_result.fetchone()

            current_otb = None
            actual_lead_time = lead_time

            if otb_row:
                # Use 'is not None' - 0 is valid OTB data
                current_otb = float(otb_row.otb_value) if otb_row.otb_value is not None else 0
                actual_lead_time = otb_row.days_out or lead_time
            else:
                # Reconstruct OTB from booking data using booking_placed timestamps
                # EXCLUDES overflow category
                if metric_code in ('hotel_room_nights', 'hotel_occupancy_pct'):
                    # Count bookings that were placed before simulated_today
                    # and cover the target date
                    otb_recon_result = await db.execute(
                        text("""
                        SELECT COUNT(DISTINCT newbook_id) as otb_count
                        FROM newbook_bookings
                        WHERE arrival_date <= :target_date
                            AND departure_date > :target_date
                            AND LOWER(status) NOT IN ('cancelled', 'no show', 'no_show', 'quote', 'waitlist')
                            AND (raw_json->>'booking_placed')::timestamp <= :simulated_today::timestamp
                            AND (category_id IS NULL OR category_id != :overflow_cat)
                        """),
                        {
                            "target_date": current_date,
                            "simulated_today": simulated_today,
                            "overflow_cat": overflow_category_id
                        }
                    )
                    otb_recon_row = otb_recon_result.fetchone()
                    if otb_recon_row:
                        otb_count = otb_recon_row.otb_count or 0
                        if metric_code == 'hotel_occupancy_pct':
                            current_otb = (otb_count / total_rooms) * 100 if total_rooms > 0 else 0
                        else:
                            current_otb = otb_count

            if current_otb is None:
                continue

            # Get prior year comparison
            prior_year_date = get_prior_year_daily(current_date)
            prior_year_simulated_today = get_prior_year_daily(simulated_today)

            # Get prior year OTB - first try snapshots, then reconstruct from bookings
            prior_otb_result = await db.execute(
                text("""
                SELECT otb_value
                FROM pickup_snapshots
                WHERE stay_date = :prior_date
                    AND metric_type = :metric
                    AND snapshot_date <= :prior_simulated_today
                ORDER BY snapshot_date DESC
                LIMIT 1
                """),
                {
                    "prior_date": prior_year_date,
                    "metric": metric_code,
                    "prior_simulated_today": prior_year_simulated_today
                }
            )
            prior_otb_row = prior_otb_result.fetchone()
            # Use 'is not None' - 0 is valid OTB data
            prior_otb = float(prior_otb_row.otb_value) if prior_otb_row and prior_otb_row.otb_value is not None else None

            # If no snapshot, reconstruct prior year OTB from booking data
            # EXCLUDES overflow category
            if prior_otb is None and metric_code in ('hotel_room_nights', 'hotel_occupancy_pct'):
                prior_otb_recon_result = await db.execute(
                    text("""
                    SELECT COUNT(DISTINCT newbook_id) as otb_count
                    FROM newbook_bookings
                    WHERE arrival_date <= :prior_date
                        AND departure_date > :prior_date
                        AND LOWER(status) NOT IN ('cancelled', 'no show', 'no_show', 'quote', 'waitlist')
                        AND (raw_json->>'booking_placed')::timestamp <= :prior_simulated_today::timestamp
                        AND (category_id IS NULL OR category_id != :overflow_cat)
                    """),
                    {
                        "prior_date": prior_year_date,
                        "prior_simulated_today": prior_year_simulated_today,
                        "overflow_cat": overflow_category_id
                    }
                )
                prior_otb_recon_row = prior_otb_recon_result.fetchone()
                if prior_otb_recon_row:
                    prior_otb_count = prior_otb_recon_row.otb_count or 0
                    if metric_code == 'hotel_occupancy_pct':
                        prior_otb = (prior_otb_count / total_rooms) * 100 if total_rooms > 0 else 0
                    else:
                        prior_otb = prior_otb_count

            # Get prior year final
            prior_final_result = await db.execute(
                text("""
                SELECT actual_value
                FROM daily_metrics
                WHERE date = :prior_date AND metric_code = :metric
                """),
                {"prior_date": prior_year_date, "metric": metric_code}
            )
            prior_final_row = prior_final_result.fetchone()
            prior_final = float(prior_final_row.actual_value) if prior_final_row and prior_final_row.actual_value else None

            # Calculate forecast using ADDITIVE method
            projected_value = current_otb
            projection_method = 'current_otb'

            if prior_otb is not None and prior_final is not None:
                prior_pickup = prior_final - prior_otb
                projected_value = current_otb + prior_pickup

                if projected_value < current_otb:
                    projected_value = current_otb
                    projection_method = 'additive_floor'
                else:
                    projection_method = 'additive'

                # Apply caps
                if metric_code == 'hotel_occupancy_pct' and projected_value > 100:
                    projected_value = 100
                if metric_code == 'hotel_room_nights' and projected_value > total_rooms:
                    projected_value = total_rooms

            elif prior_final is not None and prior_final > 0:
                # Implied additive
                if lead_time >= 28:
                    estimated_pct = 0.35
                elif lead_time >= 14:
                    estimated_pct = 0.55
                elif lead_time >= 7:
                    estimated_pct = 0.75
                else:
                    estimated_pct = 0.90

                implied_prior_otb = prior_final * estimated_pct
                implied_pickup = prior_final - implied_prior_otb
                projected_value = current_otb + implied_pickup
                projected_value = max(projected_value, current_otb)
                projection_method = 'implied_additive'

                if metric_code == 'hotel_occupancy_pct' and projected_value > 100:
                    projected_value = 100
                if metric_code == 'hotel_room_nights' and projected_value > total_rooms:
                    projected_value = total_rooms

            # Calculate errors
            error = projected_value - actual_value
            abs_error = abs(error)
            pct_error = (error / actual_value * 100) if actual_value != 0 else None
            abs_pct_error = abs(pct_error) if pct_error is not None else None

            result_record = {
                "target_date": str(current_date),
                "lead_time": lead_time,
                "actual_lead_time": actual_lead_time,
                "simulated_today": str(simulated_today),
                "current_otb": round(current_otb, 2),
                "prior_otb": round(prior_otb, 2) if prior_otb is not None else None,
                "prior_final": round(prior_final, 2) if prior_final is not None else None,
                "projected_value": round(projected_value, 2),
                "actual_value": round(actual_value, 2),
                "error": round(error, 2),
                "abs_error": round(abs_error, 2),
                "pct_error": round(pct_error, 2) if pct_error is not None else None,
                "abs_pct_error": round(abs_pct_error, 2) if abs_pct_error is not None else None,
                "projection_method": projection_method
            }
            results.append(result_record)

            # Store result
            try:
                await db.execute(
                    text("""
                    INSERT INTO backtest_results (
                        target_date, metric_code, lead_time, simulated_today,
                        current_otb, prior_otb, prior_final,
                        projected_value, actual_value,
                        error, abs_error, pct_error, abs_pct_error,
                        projection_method, created_at
                    ) VALUES (
                        :target_date, :metric, :lead_time, :simulated_today,
                        :current_otb, :prior_otb, :prior_final,
                        :projected_value, :actual_value,
                        :error, :abs_error, :pct_error, :abs_pct_error,
                        :projection_method, NOW()
                    )
                    ON CONFLICT (target_date, metric_code, lead_time) DO UPDATE SET
                        projected_value = :projected_value,
                        actual_value = :actual_value,
                        error = :error,
                        abs_error = :abs_error,
                        pct_error = :pct_error,
                        abs_pct_error = :abs_pct_error,
                        projection_method = :projection_method,
                        created_at = NOW()
                    """),
                    {
                        "target_date": current_date,
                        "metric": metric_code,
                        "lead_time": lead_time,
                        "simulated_today": simulated_today,
                        "current_otb": round(current_otb, 2),
                        "prior_otb": round(prior_otb, 2) if prior_otb is not None else None,
                        "prior_final": round(prior_final, 2) if prior_final is not None else None,
                        "projected_value": round(projected_value, 2),
                        "actual_value": round(actual_value, 2),
                        "error": round(error, 2),
                        "abs_error": round(abs_error, 2),
                        "pct_error": round(pct_error, 2) if pct_error is not None else None,
                        "abs_pct_error": round(abs_pct_error, 2) if abs_pct_error is not None else None,
                        "projection_method": projection_method
                    }
                )
            except Exception:
                pass  # Continue on storage errors

        current_date += timedelta(days=1)

    await db.commit()

    # Calculate summary statistics
    summary = _calculate_summary(results, lead_time_list)

    return {
        "metric_code": metric_code,
        "backtest_from": str(from_date),
        "backtest_to": str(to_date),
        "lead_times": lead_time_list,
        "total_forecasts": len(results),
        "summary": summary,
        "results": results
    }


def _calculate_summary(results: List[dict], lead_times: List[int]) -> dict:
    """Calculate summary statistics from backtest results."""
    if not results:
        return {}

    summary = {"overall": {}, "by_lead_time": {}, "by_method": {}}

    # Overall
    all_errors = [r['abs_error'] for r in results if r['abs_error'] is not None]
    all_pct_errors = [r['abs_pct_error'] for r in results if r['abs_pct_error'] is not None]

    if all_errors:
        summary["overall"] = {
            "mae": round(sum(all_errors) / len(all_errors), 2),
            "mape": round(sum(all_pct_errors) / len(all_pct_errors), 2) if all_pct_errors else None,
            "count": len(all_errors)
        }

    # By lead time
    for lt in lead_times:
        lt_results = [r for r in results if r['lead_time'] == lt]
        lt_errors = [r['abs_error'] for r in lt_results if r['abs_error'] is not None]
        lt_pct_errors = [r['abs_pct_error'] for r in lt_results if r['abs_pct_error'] is not None]

        if lt_errors:
            summary["by_lead_time"][str(lt)] = {
                "mae": round(sum(lt_errors) / len(lt_errors), 2),
                "mape": round(sum(lt_pct_errors) / len(lt_pct_errors), 2) if lt_pct_errors else None,
                "count": len(lt_errors)
            }

    # By method
    methods = set(r['projection_method'] for r in results)
    for method in methods:
        method_results = [r for r in results if r['projection_method'] == method]
        method_errors = [r['abs_error'] for r in method_results if r['abs_error'] is not None]
        method_pct_errors = [r['abs_pct_error'] for r in method_results if r['abs_pct_error'] is not None]

        if method_errors:
            summary["by_method"][method] = {
                "mae": round(sum(method_errors) / len(method_errors), 2),
                "mape": round(sum(method_pct_errors) / len(method_pct_errors), 2) if method_pct_errors else None,
                "count": len(method_errors)
            }

    return summary


@router.get("/results")
async def get_backtest_results(
    metric_code: str = Query(..., description="Metric code"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    lead_time: Optional[int] = Query(None, description="Filter by specific lead time"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieve stored backtest results.
    """
    query = """
    SELECT
        target_date, metric_code, lead_time, simulated_today,
        current_otb, prior_otb, prior_final,
        projected_value, actual_value,
        error, abs_error, pct_error, abs_pct_error,
        projection_method, created_at
    FROM backtest_results
    WHERE metric_code = :metric
    """
    params = {"metric": metric_code}

    if from_date:
        query += " AND target_date >= :from_date"
        params["from_date"] = from_date

    if to_date:
        query += " AND target_date <= :to_date"
        params["to_date"] = to_date

    if lead_time:
        query += " AND lead_time = :lead_time"
        params["lead_time"] = lead_time

    query += " ORDER BY target_date, lead_time"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "target_date": str(row.target_date),
            "metric_code": row.metric_code,
            "lead_time": row.lead_time,
            "simulated_today": str(row.simulated_today) if row.simulated_today else None,
            "current_otb": float(row.current_otb) if row.current_otb is not None else None,
            "prior_otb": float(row.prior_otb) if row.prior_otb is not None else None,
            "prior_final": float(row.prior_final) if row.prior_final is not None else None,
            "projected_value": float(row.projected_value) if row.projected_value is not None else None,
            "actual_value": float(row.actual_value) if row.actual_value is not None else None,
            "error": float(row.error) if row.error is not None else None,
            "abs_error": float(row.abs_error) if row.abs_error is not None else None,
            "pct_error": float(row.pct_error) if row.pct_error is not None else None,
            "abs_pct_error": float(row.abs_pct_error) if row.abs_pct_error is not None else None,
            "projection_method": row.projection_method
        }
        for row in rows
    ]


@router.get("/summary")
async def get_backtest_summary(
    metric_code: str = Query(..., description="Metric code"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get summary accuracy metrics from backtest results.
    """
    base_filter = "WHERE metric_code = :metric"
    params = {"metric": metric_code}

    if from_date:
        base_filter += " AND target_date >= :from_date"
        params["from_date"] = from_date
    if to_date:
        base_filter += " AND target_date <= :to_date"
        params["to_date"] = to_date

    # Overall summary
    overall_query = f"""
    SELECT
        COUNT(*) as count,
        AVG(abs_error) as mae,
        AVG(abs_pct_error) as mape,
        MIN(target_date) as min_date,
        MAX(target_date) as max_date
    FROM backtest_results
    {base_filter}
    """
    overall_result = await db.execute(text(overall_query), params)
    overall = overall_result.fetchone()

    # By lead time
    lead_query = f"""
    SELECT
        lead_time,
        COUNT(*) as count,
        AVG(abs_error) as mae,
        AVG(abs_pct_error) as mape
    FROM backtest_results
    {base_filter}
    GROUP BY lead_time
    ORDER BY lead_time
    """
    lead_result = await db.execute(text(lead_query), params)
    lead_rows = lead_result.fetchall()

    # By projection method
    method_query = f"""
    SELECT
        projection_method,
        COUNT(*) as count,
        AVG(abs_error) as mae,
        AVG(abs_pct_error) as mape
    FROM backtest_results
    {base_filter}
    GROUP BY projection_method
    ORDER BY count DESC
    """
    method_result = await db.execute(text(method_query), params)
    method_rows = method_result.fetchall()

    return {
        "metric_code": metric_code,
        "overall": {
            "count": overall.count if overall else 0,
            "mae": round(float(overall.mae), 2) if overall and overall.mae else None,
            "mape": round(float(overall.mape), 2) if overall and overall.mape else None,
            "date_range": {
                "from": str(overall.min_date) if overall and overall.min_date else None,
                "to": str(overall.max_date) if overall and overall.max_date else None
            }
        },
        "by_lead_time": [
            {
                "lead_time": row.lead_time,
                "count": row.count,
                "mae": round(float(row.mae), 2) if row.mae else None,
                "mape": round(float(row.mape), 2) if row.mape else None
            }
            for row in lead_rows
        ],
        "by_method": [
            {
                "method": row.projection_method,
                "count": row.count,
                "mae": round(float(row.mae), 2) if row.mae else None,
                "mape": round(float(row.mape), 2) if row.mape else None
            }
            for row in method_rows
        ]
    }


@router.post("/historical-forecast")
async def run_historical_forecasts(
    simulated_dates: str = Query(..., description="Comma-separated dates to simulate (YYYY-MM-DD)"),
    metrics: str = Query("hotel_room_nights,hotel_occupancy_pct,resos_dinner_covers,resos_lunch_covers", description="Comma-separated metrics"),
    models: str = Query("prophet,xgboost,pickup", description="Comma-separated models to run"),
    forecast_days: int = Query(60, description="Days to forecast from each simulated date"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Run all forecast models as if it were specific historical dates.

    This populates the forecasts table with historical predictions
    that can then be evaluated against actual outcomes using the
    existing accuracy tracking pages.

    Example: Run forecasts as if it were April 1, 2025:
    - Prophet, XGBoost, and Pickup models will only use data before April 1
    - Forecasts will be generated for April 2 - May 31 (60 days)
    - Results stored with generated_at = 2025-04-01

    Use this to backtest all models and populate the forecast evaluation pages.
    """
    from services.forecasting.historical_forecast import run_historical_forecast

    # Parse inputs
    date_list = [date.fromisoformat(d.strip()) for d in simulated_dates.split(",")]
    metric_list = [m.strip() for m in metrics.split(",")]
    model_list = [m.strip() for m in models.split(",")]

    all_results = []

    for sim_date in date_list:
        try:
            result = await run_historical_forecast(
                db=db,
                simulated_today=sim_date,
                metric_codes=metric_list,
                models=model_list,
                forecast_days=forecast_days
            )
            all_results.append(result)
        except Exception as e:
            all_results.append({
                "simulated_today": str(sim_date),
                "error": str(e)
            })

    return {
        "status": "complete",
        "dates_processed": len(date_list),
        "results": all_results
    }


@router.get("/historical-forecast/status")
async def get_historical_forecast_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get summary of historical forecasts that have been generated.

    Shows which dates have been used as "simulated today" and
    how many forecasts exist for each.
    """
    query = """
    SELECT
        DATE(generated_at) as simulated_date,
        model_type,
        forecast_type,
        COUNT(*) as forecast_count,
        MIN(forecast_date) as forecast_from,
        MAX(forecast_date) as forecast_to
    FROM forecasts
    WHERE DATE(generated_at) < CURRENT_DATE - INTERVAL '7 days'
    GROUP BY DATE(generated_at), model_type, forecast_type
    ORDER BY DATE(generated_at) DESC, model_type, forecast_type
    LIMIT 100
    """

    result = await db.execute(text(query))
    rows = result.fetchall()

    return [
        {
            "simulated_date": str(row.simulated_date),
            "model": row.model_type,
            "metric": row.forecast_type,
            "count": row.forecast_count,
            "forecast_range": f"{row.forecast_from} to {row.forecast_to}"
        }
        for row in rows
    ]


# ============================================
# BATCH BACKTEST FOR MODEL ACCURACY & WEIGHTING
# ============================================

@router.post("/batch")
async def run_batch_backtest_endpoint(
    background_tasks: BackgroundTasks,
    start_perception: date = Query(..., description="First Monday to use as perception date"),
    end_perception: date = Query(..., description="Last Monday to use as perception date"),
    forecast_days: int = Query(365, description="Days ahead to forecast from each perception date"),
    metric: str = Query("occupancy", description="Metric: occupancy or rooms"),
    model: str = Query("xgboost", description="Model to backtest: xgboost, prophet, or pickup"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Run batch backtests from multiple perception dates (every Monday in range).

    Stores forecasts in forecast_snapshots table for accuracy analysis.
    Use this to generate data for model weighting by lead time bracket.

    Specify model to run one at a time - allows adding new model backtests
    without re-running existing ones.

    Example: Run XGBoost for all Mondays of 2024:
    - start_perception: 2024-01-01
    - end_perception: 2024-12-31
    - forecast_days: 365
    - model: xgboost

    Results can be analyzed via /backtest/accuracy-by-bracket endpoint.
    """
    from jobs.batch_backtest import run_batch_backtest

    valid_models = ['xgboost', 'prophet', 'pickup']
    if model not in valid_models:
        raise HTTPException(status_code=400, detail=f"Invalid model. Must be one of: {valid_models}")

    # Run in background
    background_tasks.add_task(
        run_batch_backtest,
        start_perception,
        end_perception,
        forecast_days,
        metric,
        [model]  # Single model at a time
    )

    return {
        "status": "started",
        "message": f"Batch backtest for {model} running in background",
        "params": {
            "start_perception": str(start_perception),
            "end_perception": str(end_perception),
            "forecast_days": forecast_days,
            "metric": metric,
            "model": model
        }
    }


@router.get("/batch/status")
async def get_batch_backtest_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get status of batch backtests - snapshot counts per model and perception date range.
    """
    result = await db.execute(text("""
        SELECT
            model,
            COUNT(*) as total_snapshots,
            COUNT(actual_value) as with_actuals,
            MIN(perception_date) as first_perception,
            MAX(perception_date) as last_perception,
            COUNT(DISTINCT perception_date) as perception_dates
        FROM forecast_snapshots
        GROUP BY model
        ORDER BY model
    """))
    rows = result.fetchall()

    return [
        {
            "model": row.model,
            "total_snapshots": row.total_snapshots,
            "with_actuals": row.with_actuals,
            "first_perception": str(row.first_perception),
            "last_perception": str(row.last_perception),
            "perception_dates": row.perception_dates
        }
        for row in rows
    ]


@router.get("/snapshots")
async def get_forecast_snapshots(
    perception_date: Optional[date] = Query(None, description="Filter by perception date"),
    target_date: Optional[date] = Query(None, description="Filter by target date"),
    model: Optional[str] = Query(None, description="Filter by model"),
    metric_code: str = Query("occupancy", description="Metric code"),
    limit: int = Query(100, description="Max rows to return"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get stored forecast snapshots."""
    query = """
    SELECT perception_date, target_date, model, metric_code, days_out,
           forecast_value, actual_value, created_at
    FROM forecast_snapshots
    WHERE metric_code = :metric_code
    """
    params = {"metric_code": metric_code}

    if perception_date:
        query += " AND perception_date = :perception_date"
        params["perception_date"] = perception_date

    if target_date:
        query += " AND target_date = :target_date"
        params["target_date"] = target_date

    if model:
        query += " AND model = :model"
        params["model"] = model

    query += " ORDER BY perception_date DESC, target_date LIMIT :limit"
    params["limit"] = limit

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "perception_date": str(row.perception_date),
            "target_date": str(row.target_date),
            "model": row.model,
            "metric_code": row.metric_code,
            "days_out": row.days_out,
            "forecast_value": float(row.forecast_value) if row.forecast_value else None,
            "actual_value": float(row.actual_value) if row.actual_value else None
        }
        for row in rows
    ]


@router.get("/accuracy-by-bracket")
async def get_accuracy_by_bracket(
    metric_code: str = Query("occupancy", description="Metric code"),
    model: Optional[str] = Query(None, description="Filter by model (default: all)"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get model accuracy (MAE, MAPE) by lead time bracket.

    Returns accuracy metrics grouped by:
    - 0-7 days out
    - 8-14 days out
    - 15-30 days out
    - 31-60 days out
    - 61-90 days out
    - 90+ days out

    Use this to derive weights for ensemble forecasting.
    """
    model_filter = "AND model = :model" if model else ""
    params = {"metric_code": metric_code}
    if model:
        params["model"] = model

    query = f"""
    SELECT
        model,
        CASE
            WHEN days_out BETWEEN 0 AND 7 THEN '0-7'
            WHEN days_out BETWEEN 8 AND 14 THEN '8-14'
            WHEN days_out BETWEEN 15 AND 30 THEN '15-30'
            WHEN days_out BETWEEN 31 AND 60 THEN '31-60'
            WHEN days_out BETWEEN 61 AND 90 THEN '61-90'
            ELSE '90+'
        END as lead_bracket,
        COUNT(*) as n,
        AVG(ABS(forecast_value - actual_value)) as mae,
        AVG(ABS((forecast_value - actual_value) / NULLIF(actual_value, 0)) * 100) as mape
    FROM forecast_snapshots
    WHERE actual_value IS NOT NULL
    AND metric_code = :metric_code
    {model_filter}
    GROUP BY model, lead_bracket
    ORDER BY
        model,
        CASE lead_bracket
            WHEN '0-7' THEN 1
            WHEN '8-14' THEN 2
            WHEN '15-30' THEN 3
            WHEN '31-60' THEN 4
            WHEN '61-90' THEN 5
            ELSE 6
        END
    """

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "model": row.model,
            "lead_bracket": row.lead_bracket,
            "n": row.n,
            "mae": round(float(row.mae), 2) if row.mae else None,
            "mape": round(float(row.mape), 2) if row.mape else None
        }
        for row in rows
    ]


@router.get("/model-weights")
async def get_model_weights(
    metric_code: str = Query("occupancy", description="Metric code"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Calculate model weights based on inverse MAPE by lead time bracket.

    Lower MAPE = higher weight.
    Weights are normalized to sum to 1.0 within each bracket.

    Use these weights for ensemble forecasting.
    """
    query = """
    WITH accuracy AS (
        SELECT
            model,
            CASE
                WHEN days_out BETWEEN 0 AND 7 THEN '0-7'
                WHEN days_out BETWEEN 8 AND 14 THEN '8-14'
                WHEN days_out BETWEEN 15 AND 30 THEN '15-30'
                WHEN days_out BETWEEN 31 AND 60 THEN '31-60'
                WHEN days_out BETWEEN 61 AND 90 THEN '61-90'
                ELSE '90+'
            END as lead_bracket,
            AVG(ABS((forecast_value - actual_value) / NULLIF(actual_value, 0)) * 100) as mape
        FROM forecast_snapshots
        WHERE actual_value IS NOT NULL
        AND metric_code = :metric_code
        GROUP BY model, lead_bracket
    ),
    inverse_mape AS (
        SELECT
            model,
            lead_bracket,
            mape,
            CASE WHEN mape > 0 THEN 1.0 / mape ELSE 0 END as inv_mape
        FROM accuracy
    ),
    bracket_totals AS (
        SELECT lead_bracket, SUM(inv_mape) as total_inv
        FROM inverse_mape
        GROUP BY lead_bracket
    )
    SELECT
        i.model,
        i.lead_bracket,
        i.mape,
        CASE WHEN b.total_inv > 0 THEN i.inv_mape / b.total_inv ELSE 0 END as weight
    FROM inverse_mape i
    JOIN bracket_totals b ON i.lead_bracket = b.lead_bracket
    ORDER BY
        i.lead_bracket,
        weight DESC
    """

    result = await db.execute(text(query), {"metric_code": metric_code})
    rows = result.fetchall()

    return [
        {
            "model": row.model,
            "lead_bracket": row.lead_bracket,
            "mape": round(float(row.mape), 2) if row.mape else None,
            "weight": round(float(row.weight), 4) if row.weight else 0
        }
        for row in rows
    ]


@router.post("/backfill-actuals")
async def backfill_snapshot_actuals(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Backfill actual_value in forecast_snapshots from newbook_bookings_stats.

    Run this after target dates have passed to populate actual values
    for accuracy analysis.
    """
    result = await db.execute(text("""
        UPDATE forecast_snapshots fs
        SET actual_value = CASE
            WHEN fs.metric_code = 'occupancy' THEN
                (s.booking_count::decimal / NULLIF(s.bookable_count, 0)) * 100
            ELSE
                s.booking_count
        END
        FROM newbook_bookings_stats s
        WHERE fs.target_date = s.date
        AND fs.actual_value IS NULL
        AND fs.target_date < CURRENT_DATE
        AND s.booking_count IS NOT NULL
    """))

    await db.commit()

    return {
        "status": "complete",
        "rows_updated": result.rowcount
    }
