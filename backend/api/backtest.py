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
    metric: str = Query("occupancy", description="Metric to backtest"),
    model: str = Query("xgboost", description="Model to backtest: xgboost, prophet, pickup, or catboost"),
    exclude_covid: bool = Query(False, description="Exclude pre-COVID data (train from May 2021+ only)"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Run batch backtests from multiple perception dates (every Monday in range).

    Stores forecasts in forecast_snapshots table for accuracy analysis.
    Use this to generate data for model weighting by lead time bracket.

    Specify model to run one at a time - allows adding new model backtests
    without re-running existing ones.

    Metrics:
    - occupancy, rooms: All models supported (uses booking pace data)
    - guests, ave_guest_rate, arr, net_accom, net_dry, net_wet: Prophet only (no pace data)

    Set exclude_covid=true to train models only on post-COVID data (May 2021+).
    Results will be stored with '_postcovid' suffix (e.g., 'xgboost_postcovid')
    so you can compare accuracy with vs without COVID-era training data.

    Example: Run XGBoost for all Mondays of 2024:
    - start_perception: 2024-01-01
    - end_perception: 2024-12-31
    - forecast_days: 365
    - model: xgboost

    Results can be analyzed via /backtest/accuracy-by-bracket endpoint.
    """
    from jobs.batch_backtest import run_batch_backtest

    valid_models = ['xgboost', 'prophet', 'pickup', 'pickup_avg', 'catboost', 'blended']
    valid_metrics = ['occupancy', 'rooms', 'guests', 'ave_guest_rate', 'arr', 'net_accom', 'net_dry', 'net_wet']
    # Pickup models require pace data - only work with occupancy and rooms
    pace_only_metrics = ['occupancy', 'rooms']
    pickup_models = ['pickup', 'pickup_avg']
    # Blended model requires existing prophet, xgboost, catboost forecasts
    derived_models = ['blended']

    if model not in valid_models:
        raise HTTPException(status_code=400, detail=f"Invalid model. Must be one of: {valid_models}")

    if metric not in valid_metrics:
        raise HTTPException(status_code=400, detail=f"Invalid metric. Must be one of: {valid_metrics}")

    # Pickup models require pace data
    if model in pickup_models and metric not in pace_only_metrics:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model}' only supports occupancy and rooms metrics (requires booking pace data). "
                   f"Use XGBoost, CatBoost, or Prophet for {metric}."
        )

    # Blended model requires existing prophet, xgboost, catboost forecasts
    if model in derived_models:
        # Note: blended model averages existing forecasts, doesn't train from scratch
        pass

    # Training cutoff for post-COVID: May 1, 2021
    training_start = date(2021, 5, 1) if exclude_covid else None

    # Run in background
    background_tasks.add_task(
        run_batch_backtest,
        start_perception,
        end_perception,
        forecast_days,
        metric,
        [model],  # Single model at a time
        training_start  # Training cutoff date
    )

    return {
        "status": "started",
        "message": f"Batch backtest for {model}{' (post-COVID)' if exclude_covid else ''} running in background",
        "params": {
            "start_perception": str(start_perception),
            "end_perception": str(end_perception),
            "forecast_days": forecast_days,
            "metric": metric,
            "model": model,
            "exclude_covid": exclude_covid,
            "training_start": str(training_start) if training_start else None
        }
    }


@router.get("/batch/status")
async def get_batch_backtest_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get status of batch backtests - snapshot counts per model/metric and perception date range.
    """
    result = await db.execute(text("""
        SELECT
            model,
            metric_code,
            COUNT(*) as total_snapshots,
            COUNT(actual_value) as with_actuals,
            MIN(perception_date) as first_perception,
            MAX(perception_date) as last_perception,
            COUNT(DISTINCT perception_date) as perception_dates
        FROM forecast_snapshots
        GROUP BY model, metric_code
        ORDER BY metric_code, model
    """))
    rows = result.fetchall()

    return [
        {
            "model": row.model,
            "metric_code": row.metric_code,
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
        CASE
            WHEN days_out BETWEEN 0 AND 7 THEN 1
            WHEN days_out BETWEEN 8 AND 14 THEN 2
            WHEN days_out BETWEEN 15 AND 30 THEN 3
            WHEN days_out BETWEEN 31 AND 60 THEN 4
            WHEN days_out BETWEEN 61 AND 90 THEN 5
            ELSE 6
        END as sort_order,
        COUNT(*) as n,
        AVG(ABS(forecast_value - actual_value)) as mae,
        AVG(ABS((forecast_value - actual_value) / NULLIF(actual_value, 0)) * 100) as mape
    FROM forecast_snapshots
    WHERE actual_value IS NOT NULL
    AND metric_code = :metric_code
    {model_filter}
    GROUP BY model,
        CASE
            WHEN days_out BETWEEN 0 AND 7 THEN '0-7'
            WHEN days_out BETWEEN 8 AND 14 THEN '8-14'
            WHEN days_out BETWEEN 15 AND 30 THEN '15-30'
            WHEN days_out BETWEEN 31 AND 60 THEN '31-60'
            WHEN days_out BETWEEN 61 AND 90 THEN '61-90'
            ELSE '90+'
        END,
        CASE
            WHEN days_out BETWEEN 0 AND 7 THEN 1
            WHEN days_out BETWEEN 8 AND 14 THEN 2
            WHEN days_out BETWEEN 15 AND 30 THEN 3
            WHEN days_out BETWEEN 31 AND 60 THEN 4
            WHEN days_out BETWEEN 61 AND 90 THEN 5
            ELSE 6
        END
    ORDER BY model, sort_order
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


@router.get("/accuracy-by-day-of-week")
async def get_accuracy_by_day_of_week(
    metric_code: str = Query("occupancy", description="Metric code"),
    model: Optional[str] = Query(None, description="Filter by model (default: all)"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get model accuracy (MAE, MAPE) by day of week.

    Returns accuracy metrics grouped by:
    - Sunday (0)
    - Monday (1)
    - Tuesday (2)
    - Wednesday (3)
    - Thursday (4)
    - Friday (5)
    - Saturday (6)

    Useful for identifying if models perform better on certain days.
    """
    model_filter = "AND model = :model" if model else ""
    params = {"metric_code": metric_code}
    if model:
        params["model"] = model

    query = f"""
    SELECT
        model,
        EXTRACT(DOW FROM target_date)::int as dow_num,
        CASE EXTRACT(DOW FROM target_date)::int
            WHEN 0 THEN 'Sunday'
            WHEN 1 THEN 'Monday'
            WHEN 2 THEN 'Tuesday'
            WHEN 3 THEN 'Wednesday'
            WHEN 4 THEN 'Thursday'
            WHEN 5 THEN 'Friday'
            WHEN 6 THEN 'Saturday'
        END as day_name,
        COUNT(*) as n,
        AVG(ABS(forecast_value - actual_value)) as mae,
        AVG(ABS((forecast_value - actual_value) / NULLIF(actual_value, 0)) * 100) as mape
    FROM forecast_snapshots
    WHERE actual_value IS NOT NULL
    AND metric_code = :metric_code
    {model_filter}
    GROUP BY model,
        EXTRACT(DOW FROM target_date)::int,
        CASE EXTRACT(DOW FROM target_date)::int
            WHEN 0 THEN 'Sunday'
            WHEN 1 THEN 'Monday'
            WHEN 2 THEN 'Tuesday'
            WHEN 3 THEN 'Wednesday'
            WHEN 4 THEN 'Thursday'
            WHEN 5 THEN 'Friday'
            WHEN 6 THEN 'Saturday'
        END
    ORDER BY model, dow_num
    """

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "model": row.model,
            "dow_num": row.dow_num,
            "day_name": row.day_name,
            "n": row.n,
            "mae": round(float(row.mae), 2) if row.mae else None,
            "mape": round(float(row.mape), 2) if row.mape else None
        }
        for row in rows
    ]


@router.get("/accuracy-by-month")
async def get_accuracy_by_month(
    metric_code: str = Query("occupancy", description="Metric code"),
    model: Optional[str] = Query(None, description="Filter by model (default: all)"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get model accuracy (MAE, MAPE) by month of year.

    Returns accuracy metrics grouped by month (January through December).

    Useful for identifying seasonal patterns in model accuracy.
    """
    model_filter = "AND model = :model" if model else ""
    params = {"metric_code": metric_code}
    if model:
        params["model"] = model

    query = f"""
    SELECT
        model,
        EXTRACT(MONTH FROM target_date)::int as month_num,
        CASE EXTRACT(MONTH FROM target_date)::int
            WHEN 1 THEN 'January'
            WHEN 2 THEN 'February'
            WHEN 3 THEN 'March'
            WHEN 4 THEN 'April'
            WHEN 5 THEN 'May'
            WHEN 6 THEN 'June'
            WHEN 7 THEN 'July'
            WHEN 8 THEN 'August'
            WHEN 9 THEN 'September'
            WHEN 10 THEN 'October'
            WHEN 11 THEN 'November'
            WHEN 12 THEN 'December'
        END as month_name,
        COUNT(*) as n,
        AVG(ABS(forecast_value - actual_value)) as mae,
        AVG(ABS((forecast_value - actual_value) / NULLIF(actual_value, 0)) * 100) as mape
    FROM forecast_snapshots
    WHERE actual_value IS NOT NULL
    AND metric_code = :metric_code
    {model_filter}
    GROUP BY model,
        EXTRACT(MONTH FROM target_date)::int,
        CASE EXTRACT(MONTH FROM target_date)::int
            WHEN 1 THEN 'January'
            WHEN 2 THEN 'February'
            WHEN 3 THEN 'March'
            WHEN 4 THEN 'April'
            WHEN 5 THEN 'May'
            WHEN 6 THEN 'June'
            WHEN 7 THEN 'July'
            WHEN 8 THEN 'August'
            WHEN 9 THEN 'September'
            WHEN 10 THEN 'October'
            WHEN 11 THEN 'November'
            WHEN 12 THEN 'December'
        END
    ORDER BY model, month_num
    """

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "model": row.model,
            "month_num": row.month_num,
            "month_name": row.month_name,
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
        GROUP BY model,
            CASE
                WHEN days_out BETWEEN 0 AND 7 THEN '0-7'
                WHEN days_out BETWEEN 8 AND 14 THEN '8-14'
                WHEN days_out BETWEEN 15 AND 30 THEN '15-30'
                WHEN days_out BETWEEN 31 AND 60 THEN '31-60'
                WHEN days_out BETWEEN 61 AND 90 THEN '61-90'
                ELSE '90+'
            END
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
    Backfill actual_value in forecast_snapshots from newbook_bookings_stats and newbook_net_revenue_data.

    Run this after target dates have passed to populate actual values
    for accuracy analysis.

    Handles all metrics:
    - occupancy: booking_count / bookable_count * 100
    - rooms: booking_count
    - guests: guests_count
    - ave_guest_rate: guest_rate_total / booking_count
    - arr: accommodation / booking_count (from revenue data)
    - net_accom, net_dry, net_wet: from revenue data
    """
    # First, update stats-based metrics (occupancy, rooms, guests, ave_guest_rate)
    result1 = await db.execute(text("""
        UPDATE forecast_snapshots fs
        SET actual_value = CASE
            WHEN fs.metric_code = 'occupancy' THEN
                (s.booking_count::decimal / NULLIF(s.bookable_count, 0)) * 100
            WHEN fs.metric_code = 'rooms' THEN
                s.booking_count
            WHEN fs.metric_code = 'guests' THEN
                s.guests_count
            WHEN fs.metric_code = 'ave_guest_rate' THEN
                s.guest_rate_total / NULLIF(s.booking_count, 0)
            ELSE NULL
        END
        FROM newbook_bookings_stats s
        WHERE fs.target_date = s.date
        AND fs.actual_value IS NULL
        AND fs.target_date < CURRENT_DATE
        AND fs.metric_code IN ('occupancy', 'rooms', 'guests', 'ave_guest_rate')
        AND s.booking_count IS NOT NULL
    """))

    # Then, update revenue-based metrics (arr, net_accom, net_dry, net_wet)
    result2 = await db.execute(text("""
        UPDATE forecast_snapshots fs
        SET actual_value = CASE
            WHEN fs.metric_code = 'arr' THEN
                r.accommodation / NULLIF(s.booking_count, 0)
            WHEN fs.metric_code = 'net_accom' THEN
                r.accommodation
            WHEN fs.metric_code = 'net_dry' THEN
                r.dry
            WHEN fs.metric_code = 'net_wet' THEN
                r.wet
            ELSE NULL
        END
        FROM newbook_net_revenue_data r
        JOIN newbook_bookings_stats s ON r.date = s.date
        WHERE fs.target_date = r.date
        AND fs.actual_value IS NULL
        AND fs.target_date < CURRENT_DATE
        AND fs.metric_code IN ('arr', 'net_accom', 'net_dry', 'net_wet')
    """))

    await db.commit()

    return {
        "status": "complete",
        "rows_updated": result1.rowcount + result2.rowcount
    }


@router.delete("/snapshots/{model}")
async def delete_model_snapshots(
    model: str,
    metric_code: Optional[str] = Query(None, description="Optional: Only delete for this metric"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Delete all backtest snapshots for a specific model.

    Use this to remove backtest data for models you want to exclude from
    accuracy analysis (e.g., models affected by COVID training data).

    The model name must match exactly (e.g., 'xgboost', 'prophet', 'pickup_postcovid').
    """
    query = "DELETE FROM forecast_snapshots WHERE model = :model"
    params = {"model": model}

    if metric_code:
        query += " AND metric_code = :metric_code"
        params["metric_code"] = metric_code

    result = await db.execute(text(query), params)
    await db.commit()

    return {
        "status": "complete",
        "model": model,
        "metric_code": metric_code,
        "rows_deleted": result.rowcount
    }


@router.post("/fill-to-today")
async def fill_backtests_to_today(
    background_tasks: BackgroundTasks,
    metric: str = Query("occupancy", description="Metric to backtest"),
    models: str = Query("prophet,xgboost,catboost,blended", description="Comma-separated models to run (blended runs last)"),
    forecast_days: int = Query(365, description="Days ahead to forecast from each perception date"),
    exclude_covid: bool = Query(True, description="Exclude pre-COVID data (train from May 2021+ only)"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Fill in backtests from earliest available data up to today.

    Finds missing perception dates (Mondays) and runs backtests for each model.
    Use this to backfill historical forecast data for accuracy analysis and 3D visualization.

    The 'blended' model averages prophet, xgboost, and catboost - those must run first.
    If included, blended is automatically moved to run last.
    """
    from jobs.batch_backtest import run_batch_backtest

    model_list = [m.strip() for m in models.split(",")]
    valid_models = ['xgboost', 'prophet', 'pickup', 'pickup_avg', 'catboost', 'blended']

    for m in model_list:
        if m not in valid_models:
            raise HTTPException(status_code=400, detail=f"Invalid model: {m}")

    # Ensure blended runs last (it depends on other model outputs)
    if 'blended' in model_list:
        model_list.remove('blended')
        model_list.append('blended')

    # Find earliest historical data date
    earliest_result = await db.execute(text("""
        SELECT MIN(date) as earliest
        FROM newbook_bookings_stats
        WHERE booking_count IS NOT NULL
    """))
    earliest_row = earliest_result.fetchone()
    earliest_data = earliest_row.earliest if earliest_row else None

    if not earliest_data:
        raise HTTPException(status_code=400, detail="No historical data available")

    # Start from 2 years after earliest data (need training history)
    start_date = earliest_data + timedelta(days=730)

    # Find most recent Monday before today
    today = date.today()
    days_since_monday = today.weekday()  # Monday=0
    last_monday = today - timedelta(days=days_since_monday)

    # Move start_date to first Monday
    while start_date.weekday() != 0:
        start_date += timedelta(days=1)

    # Training cutoff for post-COVID: May 1, 2021
    training_start = date(2021, 5, 1) if exclude_covid else None

    # Check existing perception dates
    existing_result = await db.execute(text("""
        SELECT DISTINCT perception_date
        FROM forecast_snapshots
        WHERE metric_code = :metric
        AND model = :first_model
        ORDER BY perception_date
    """), {"metric": metric, "first_model": f"{model_list[0]}{'_postcovid' if exclude_covid else ''}"})
    existing_dates = {row.perception_date for row in existing_result.fetchall()}

    # Count how many Mondays need processing
    check_date = start_date
    missing_count = 0
    while check_date <= last_monday:
        if check_date not in existing_dates:
            missing_count += 1
        check_date += timedelta(days=7)

    # Run in background
    background_tasks.add_task(
        run_batch_backtest,
        start_date,
        last_monday,
        forecast_days,
        metric,
        model_list,
        training_start
    )

    return {
        "status": "started",
        "message": f"Filling backtests from {start_date} to {last_monday}",
        "params": {
            "start_perception": str(start_date),
            "end_perception": str(last_monday),
            "forecast_days": forecast_days,
            "metric": metric,
            "models": model_list,
            "exclude_covid": exclude_covid,
            "existing_perception_dates": len(existing_dates),
            "missing_perception_dates": missing_count
        }
    }


@router.get("/3d-data")
async def get_3d_forecast_data(
    metric_code: str = Query("occupancy", description="Metric code"),
    target_date: date = Query(..., description="Target date to analyze"),
    model: str = Query("blended", description="Model to show"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get forecast evolution data for 3D visualization.

    Returns all forecasts for a specific target date from different perception dates,
    showing how the forecast changed as the target date approached.

    Data structure for 3D chart:
    - X axis: perception_date (when forecast was made)
    - Y axis: days_out (lead time)
    - Z axis: forecast_value

    This shows how forecast accuracy improves as lead time decreases.
    """
    query = """
    SELECT
        perception_date,
        target_date,
        days_out,
        forecast_value,
        actual_value
    FROM forecast_snapshots
    WHERE target_date = :target_date
    AND metric_code = :metric_code
    AND model = :model
    ORDER BY perception_date
    """

    result = await db.execute(text(query), {
        "target_date": target_date,
        "metric_code": metric_code,
        "model": model
    })
    rows = result.fetchall()

    return {
        "target_date": str(target_date),
        "metric_code": metric_code,
        "model": model,
        "actual_value": float(rows[0].actual_value) if rows and rows[0].actual_value else None,
        "snapshots": [
            {
                "perception_date": str(row.perception_date),
                "days_out": row.days_out,
                "forecast_value": float(row.forecast_value) if row.forecast_value else None
            }
            for row in rows
        ]
    }


@router.get("/3d-surface")
async def get_3d_surface_data(
    metric_code: str = Query("occupancy", description="Metric code"),
    from_date: date = Query(..., description="Start of target date range"),
    to_date: date = Query(..., description="End of target date range"),
    model: str = Query("blended", description="Model to show"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get forecast surface data for 3D visualization across multiple target dates.

    Returns a grid of forecasts where:
    - Rows = target dates
    - Columns = days_out (lead time brackets)
    - Values = forecast values

    This creates a surface showing forecast evolution across both time and lead time.
    """
    query = """
    SELECT
        target_date,
        days_out,
        AVG(forecast_value) as avg_forecast,
        AVG(actual_value) as avg_actual
    FROM forecast_snapshots
    WHERE target_date BETWEEN :from_date AND :to_date
    AND metric_code = :metric_code
    AND model = :model
    GROUP BY target_date, days_out
    ORDER BY target_date, days_out
    """

    result = await db.execute(text(query), {
        "from_date": from_date,
        "to_date": to_date,
        "metric_code": metric_code,
        "model": model
    })
    rows = result.fetchall()

    # Organize into grid format
    grid_data = {}
    for row in rows:
        date_str = str(row.target_date)
        if date_str not in grid_data:
            grid_data[date_str] = {"actual": float(row.avg_actual) if row.avg_actual else None}
        grid_data[date_str][row.days_out] = float(row.avg_forecast) if row.avg_forecast else None

    return {
        "metric_code": metric_code,
        "model": model,
        "from_date": str(from_date),
        "to_date": str(to_date),
        "data": grid_data
    }


@router.get("/3d-monthly-progress")
async def get_3d_monthly_progress(
    metric_code: str = Query("occupancy", description="Metric code"),
    year: int = Query(..., description="Year (e.g., 2025)"),
    month: int = Query(..., description="Month (1-12)"),
    model: str = Query("blended", description="Model to show"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get forecast progress data for 3D visualization of a specific month.

    Shows how forecasts for a given month evolved over time as perception dates
    approached the target dates.

    Returns:
    - target_dates: Array of dates in the selected month (X axis)
    - perception_dates: Array of unique perception dates (Y axis)
    - surface_data: 2D array [perception_idx][target_idx] of forecast values (Z axis)
    - actuals: Array of actual values for each target date

    This visualization shows how forecast accuracy improved over time.
    """
    from calendar import monthrange

    # Calculate date range for the selected month
    _, last_day = monthrange(year, month)
    from_date = date(year, month, 1)
    to_date = date(year, month, last_day)

    query = """
    SELECT
        perception_date,
        target_date,
        forecast_value,
        actual_value
    FROM forecast_snapshots
    WHERE target_date BETWEEN :from_date AND :to_date
    AND metric_code = :metric_code
    AND model = :model
    ORDER BY perception_date, target_date
    """

    result = await db.execute(text(query), {
        "from_date": from_date,
        "to_date": to_date,
        "metric_code": metric_code,
        "model": model
    })
    rows = result.fetchall()

    if not rows:
        return {
            "metric_code": metric_code,
            "model": model,
            "year": year,
            "month": month,
            "target_dates": [],
            "perception_dates": [],
            "surface_data": [],
            "actuals": []
        }

    # Extract unique dates and build lookup
    target_dates_set = set()
    perception_dates_set = set()
    forecasts = {}  # (perception_date, target_date) -> forecast_value
    actuals_map = {}  # target_date -> actual_value

    for row in rows:
        target_dates_set.add(row.target_date)
        perception_dates_set.add(row.perception_date)
        forecasts[(row.perception_date, row.target_date)] = row.forecast_value
        if row.actual_value is not None:
            actuals_map[row.target_date] = row.actual_value

    # Sort dates
    target_dates = sorted(target_dates_set)
    perception_dates = sorted(perception_dates_set)

    # Build surface data: surface_data[perception_idx][target_idx]
    surface_data = []
    for p_date in perception_dates:
        row_data = []
        for t_date in target_dates:
            val = forecasts.get((p_date, t_date))
            row_data.append(float(val) if val is not None else None)
        surface_data.append(row_data)

    # Actuals array aligned with target_dates
    actuals = [float(actuals_map.get(t)) if t in actuals_map else None for t in target_dates]

    return {
        "metric_code": metric_code,
        "model": model,
        "year": year,
        "month": month,
        "target_dates": [str(d) for d in target_dates],
        "perception_dates": [str(d) for d in perception_dates],
        "surface_data": surface_data,
        "actuals": actuals
    }
