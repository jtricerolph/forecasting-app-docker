"""
Backtesting service for forecast model evaluation.

Simulates historical forecasts using only data that would have been
available at the time, then compares to actual outcomes.

This allows model accuracy evaluation without waiting for real-time
data to accumulate.
"""
import logging
from datetime import date, timedelta
from typing import List, Optional, Dict
from sqlalchemy import text

from utils.time_alignment import get_prior_year_daily

logger = logging.getLogger(__name__)


async def run_backtest(
    db,
    metric_code: str,
    backtest_from: date,
    backtest_to: date,
    lead_times: List[int] = None
) -> Dict:
    """
    Run backtesting for a metric over a date range.

    For each date in the range, simulates what the forecast would have been
    at various lead times, using only data available at that time.

    Args:
        db: Database session
        metric_code: Metric to backtest (e.g., 'hotel_room_nights')
        backtest_from: Start of backtest period
        backtest_to: End of backtest period
        lead_times: List of lead times to test (days out). Default: [7, 14, 21, 28]

    Returns:
        Dict with backtest results and accuracy metrics
    """
    if lead_times is None:
        lead_times = [7, 14, 21, 28]

    logger.info(f"Running backtest for {metric_code} from {backtest_from} to {backtest_to}")

    results = []
    total_rooms = 25  # Default capacity

    # Get room capacity (SUM across all room categories for a single date)
    if metric_code in ('hotel_room_nights', 'hotel_occupancy_pct'):
        rooms_result = db.execute(
            text("""
            SELECT COALESCE(SUM(available), 25) as total_rooms
            FROM newbook_occupancy_report
            WHERE date = (
                SELECT MAX(date) FROM newbook_occupancy_report
                WHERE date <= :from_date
            )
            """),
            {"from_date": backtest_from}
        )
        rooms_row = rooms_result.fetchone()
        if rooms_row and rooms_row.total_rooms:
            total_rooms = int(rooms_row.total_rooms)

    # For each date in backtest range
    current_date = backtest_from
    while current_date <= backtest_to:
        # Get actual value for this date
        actual_result = db.execute(
            text("""
            SELECT actual_value
            FROM daily_metrics
            WHERE date = :target_date AND metric_code = :metric
            """),
            {"target_date": current_date, "metric": metric_code}
        ).fetchone()

        actual_value = float(actual_result.actual_value) if actual_result and actual_result.actual_value else None

        if actual_value is None:
            current_date += timedelta(days=1)
            continue

        # For each lead time, simulate the forecast
        for lead_time in lead_times:
            # The "simulated today" is lead_time days before the target date
            simulated_today = current_date - timedelta(days=lead_time)

            # Get OTB snapshot that would have been available
            # Look for snapshot closest to simulated_today
            otb_result = db.execute(
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
            ).fetchone()

            if not otb_result:
                continue

            # Use 'is not None' - 0 is valid OTB data
            current_otb = float(otb_result.otb_value) if otb_result.otb_value is not None else 0
            actual_lead_time = otb_result.days_out or lead_time

            # Get prior year comparison data (same day of week)
            prior_year_date = get_prior_year_daily(current_date)
            prior_year_simulated_today = get_prior_year_daily(simulated_today)

            # Get prior year OTB at same lead time
            prior_otb_result = db.execute(
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
            ).fetchone()

            # Use 'is not None' - 0 is valid OTB data
            prior_otb = float(prior_otb_result.otb_value) if prior_otb_result and prior_otb_result.otb_value is not None else None

            # Get prior year final actual
            prior_final_result = db.execute(
                text("""
                SELECT actual_value
                FROM daily_metrics
                WHERE date = :prior_date AND metric_code = :metric
                """),
                {"prior_date": prior_year_date, "metric": metric_code}
            ).fetchone()

            prior_final = float(prior_final_result.actual_value) if prior_final_result and prior_final_result.actual_value else None

            # Calculate forecast using ADDITIVE method
            projected_value = current_otb
            projection_method = 'current_otb'

            if prior_otb is not None and prior_final is not None:
                # Additive method: current + expected pickup
                prior_pickup = prior_final - prior_otb
                projected_value = current_otb + prior_pickup

                # Floor at current OTB
                if projected_value < current_otb:
                    projected_value = current_otb
                    projection_method = 'additive_floor'
                else:
                    projection_method = 'additive'

                # Apply physical caps
                if metric_code == 'hotel_occupancy_pct' and projected_value > 100:
                    projected_value = 100
                if metric_code == 'hotel_room_nights' and projected_value > total_rooms:
                    projected_value = total_rooms

            elif prior_final is not None and prior_final > 0:
                # Implied additive method
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

                # Apply caps
                if metric_code == 'hotel_occupancy_pct' and projected_value > 100:
                    projected_value = 100
                if metric_code == 'hotel_room_nights' and projected_value > total_rooms:
                    projected_value = total_rooms

            # Calculate error metrics
            error = projected_value - actual_value
            abs_error = abs(error)
            pct_error = (error / actual_value * 100) if actual_value != 0 else None
            abs_pct_error = abs(pct_error) if pct_error is not None else None

            result_record = {
                "target_date": current_date,
                "lead_time": lead_time,
                "actual_lead_time": actual_lead_time,
                "simulated_today": simulated_today,
                "current_otb": current_otb,
                "prior_otb": prior_otb,
                "prior_final": prior_final,
                "projected_value": round(projected_value, 2),
                "actual_value": actual_value,
                "error": round(error, 2),
                "abs_error": round(abs_error, 2),
                "pct_error": round(pct_error, 2) if pct_error is not None else None,
                "abs_pct_error": round(abs_pct_error, 2) if abs_pct_error is not None else None,
                "projection_method": projection_method
            }
            results.append(result_record)

            # Store in backtest_results table
            try:
                db.execute(
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
                        "current_otb": current_otb,
                        "prior_otb": prior_otb,
                        "prior_final": prior_final,
                        "projected_value": round(projected_value, 2),
                        "actual_value": actual_value,
                        "error": round(error, 2),
                        "abs_error": round(abs_error, 2),
                        "pct_error": round(pct_error, 2) if pct_error is not None else None,
                        "abs_pct_error": round(abs_pct_error, 2) if abs_pct_error is not None else None,
                        "projection_method": projection_method
                    }
                )
            except Exception as e:
                logger.warning(f"Could not store backtest result: {e}")

        current_date += timedelta(days=1)

    db.commit()

    # Calculate summary statistics
    summary = calculate_backtest_summary(results, lead_times)

    logger.info(f"Backtest complete: {len(results)} forecasts evaluated")

    return {
        "metric_code": metric_code,
        "backtest_from": str(backtest_from),
        "backtest_to": str(backtest_to),
        "lead_times": lead_times,
        "total_forecasts": len(results),
        "results": results,
        "summary": summary
    }


def calculate_backtest_summary(results: List[dict], lead_times: List[int]) -> Dict:
    """
    Calculate summary accuracy metrics from backtest results.
    """
    if not results:
        return {}

    summary = {
        "overall": {},
        "by_lead_time": {}
    }

    # Overall metrics
    all_errors = [r['abs_error'] for r in results if r['abs_error'] is not None]
    all_pct_errors = [r['abs_pct_error'] for r in results if r['abs_pct_error'] is not None]

    if all_errors:
        summary["overall"] = {
            "mae": round(sum(all_errors) / len(all_errors), 2),  # Mean Absolute Error
            "mape": round(sum(all_pct_errors) / len(all_pct_errors), 2) if all_pct_errors else None,  # Mean Absolute Percentage Error
            "count": len(all_errors)
        }

    # By lead time
    for lt in lead_times:
        lt_results = [r for r in results if r['lead_time'] == lt]
        lt_errors = [r['abs_error'] for r in lt_results if r['abs_error'] is not None]
        lt_pct_errors = [r['abs_pct_error'] for r in lt_results if r['abs_pct_error'] is not None]

        if lt_errors:
            summary["by_lead_time"][lt] = {
                "mae": round(sum(lt_errors) / len(lt_errors), 2),
                "mape": round(sum(lt_pct_errors) / len(lt_pct_errors), 2) if lt_pct_errors else None,
                "count": len(lt_errors)
            }

    # By projection method
    methods = set(r['projection_method'] for r in results)
    summary["by_method"] = {}
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


async def get_backtest_results(
    db,
    metric_code: str,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    lead_time: Optional[int] = None
) -> List[dict]:
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

    result = db.execute(text(query), params)

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
        for row in result.fetchall()
    ]
