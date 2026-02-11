"""
Budget distribution service
Distributes monthly budgets to daily values using prior year patterns
"""
import logging
from datetime import date, timedelta
from calendar import monthrange
from typing import Optional, Dict, List
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Map budget_type to column name in newbook_net_revenue_data
BUDGET_TYPE_TO_COLUMN = {
    'net_accom': 'accommodation',
    'net_dry': 'dry',
    'net_wet': 'wet',
}


async def distribute_budget(
    db,
    year: int,
    month: int,
    budget_type: Optional[str] = None
) -> dict:
    """
    Distribute monthly budget to daily values using DOW-aligned prior year patterns.

    Uses 364-day offset (52 weeks) so that days of week align between years.
    This ensures weekday/weekend patterns are preserved in the distribution.

    Logic:
    1. Get monthly budget from FD-provided values
    2. For each day in target month, find DOW-aligned date 364 days prior
    3. Get prior year actual values for those DOW-aligned dates
    4. Calculate percentages and distribute budget accordingly

    Example:
    - Feb 1, 2026 (Sunday) - 364 days = Feb 2, 2025 (Sunday)
    - If Feb 2, 2025 was 4% of the DOW-aligned period total
    - Feb 1, 2026 daily budget = monthly_budget × 4%

    Args:
        db: Database session
        year: Year to distribute for
        month: Month to distribute (1-12)
        budget_type: Optional specific budget type, or all if None

    Returns:
        Dict with distribution results
    """
    logger.info(f"Distributing budget for {year}-{month:02d} using DOW-aligned prior year patterns")

    # Get monthly budgets
    query = """
        SELECT id, budget_type, budget_value
        FROM monthly_budgets
        WHERE year = :year AND month = :month
    """
    params = {"year": year, "month": month}

    if budget_type:
        query += " AND budget_type = :budget_type"
        params["budget_type"] = budget_type

    result = await db.execute(text(query), params)
    monthly_budgets = result.fetchall()

    if not monthly_budgets:
        logger.warning(f"No monthly budgets found for {year}-{month:02d}")
        return {"days_distributed": 0, "status": "no_budgets_found"}

    # Get days in target month
    _, days_in_month = monthrange(year, month)

    days_distributed = 0

    for budget in monthly_budgets:
        budget_id = budget.id
        btype = budget.budget_type
        monthly_value = float(budget.budget_value)

        # Get column name for this budget type
        column_name = BUDGET_TYPE_TO_COLUMN.get(btype)
        if not column_name:
            logger.warning(f"Unknown budget type: {btype}, skipping")
            continue

        logger.info(f"Distributing {btype}: £{monthly_value:,.2f}")

        # Build list of target dates and their DOW-aligned prior year dates
        target_dates = []
        prior_dates = []
        for day in range(1, days_in_month + 1):
            target_date = date(year, month, day)
            prior_date = target_date - timedelta(days=364)  # 52 weeks back, DOW aligned
            target_dates.append(target_date)
            prior_dates.append(prior_date)

        # Get prior year actual values for the DOW-aligned dates from newbook_net_revenue_data
        prior_result = await db.execute(
            text(f"""
                SELECT date, {column_name} as value
                FROM newbook_net_revenue_data
                WHERE date = ANY(:dates)
                    AND {column_name} IS NOT NULL
                ORDER BY date
            """),
            {"dates": prior_dates}
        )
        prior_rows = prior_result.fetchall()
        prior_values = {row.date: float(row.value) for row in prior_rows}

        # Calculate total of prior year values for percentage calculation
        total_prior = sum(prior_values.get(d, 0) for d in prior_dates)

        logger.info(f"Prior year DOW-aligned total for {btype}: £{total_prior:,.2f} ({len(prior_values)} days with data)")

        if total_prior > 0:
            # Distribute using DOW-aligned prior year percentages
            for target_date, prior_date in zip(target_dates, prior_dates):
                prior_value = prior_values.get(prior_date, 0)
                pct_of_total = prior_value / total_prior if total_prior > 0 else (1 / days_in_month)
                daily_budget = monthly_value * pct_of_total

                await db.execute(
                    text("""
                        INSERT INTO daily_budgets (
                            date, budget_type, budget_value, distribution_method,
                            prior_year_pct, monthly_budget_id, calculated_at
                        ) VALUES (
                            :date, :btype, :value, 'dow_aligned',
                            :pct, :budget_id, NOW()
                        )
                        ON CONFLICT (date, budget_type) DO UPDATE SET
                            budget_value = :value,
                            distribution_method = 'dow_aligned',
                            prior_year_pct = :pct,
                            calculated_at = NOW()
                    """),
                    {
                        "date": target_date,
                        "btype": btype,
                        "value": round(daily_budget, 2),
                        "pct": round(pct_of_total, 6),
                        "budget_id": budget_id
                    }
                )
                days_distributed += 1

            logger.info(f"Distributed {btype} using DOW-aligned prior year patterns")
        else:
            # No prior year data - distribute evenly
            logger.warning(f"No prior year DOW-aligned data for {btype}, using even distribution")
            daily_budget = monthly_value / days_in_month

            for target_date in target_dates:
                await db.execute(
                    text("""
                        INSERT INTO daily_budgets (
                            date, budget_type, budget_value, distribution_method,
                            prior_year_pct, monthly_budget_id, calculated_at
                        ) VALUES (
                            :date, :btype, :value, 'even',
                            :pct, :budget_id, NOW()
                        )
                        ON CONFLICT (date, budget_type) DO UPDATE SET
                            budget_value = :value,
                            distribution_method = 'even',
                            prior_year_pct = :pct,
                            calculated_at = NOW()
                    """),
                    {
                        "date": target_date,
                        "btype": btype,
                        "value": round(daily_budget, 2),
                        "pct": round(1 / days_in_month, 6),
                        "budget_id": budget_id
                    }
                )
                days_distributed += 1

    await db.commit()
    logger.info(f"Budget distribution complete: {days_distributed} days")
    return {"days_distributed": days_distributed, "status": "success"}


async def calculate_prior_year_percentages(db, metric_type: str):
    """
    Calculate and store prior year daily percentages for budget distribution

    For each month, calculates what percentage each day was of the monthly total
    """
    logger.info(f"Calculating prior year percentages for {metric_type}")

    # Get all daily values from prior year
    result = await db.execute(
        text("""
        WITH monthly_totals AS (
            SELECT
                EXTRACT(YEAR FROM date) as year,
                EXTRACT(MONTH FROM date) as month,
                SUM(actual_value) as month_total
            FROM daily_metrics
            WHERE metric_code = :metric_type
                AND date >= CURRENT_DATE - INTERVAL '2 years'
                AND actual_value IS NOT NULL
            GROUP BY EXTRACT(YEAR FROM date), EXTRACT(MONTH FROM date)
        )
        SELECT
            dm.date,
            dm.actual_value,
            mt.month_total,
            dm.actual_value / NULLIF(mt.month_total, 0) as pct_of_month
        FROM daily_metrics dm
        JOIN monthly_totals mt ON
            EXTRACT(YEAR FROM dm.date) = mt.year AND
            EXTRACT(MONTH FROM dm.date) = mt.month
        WHERE dm.metric_code = :metric_type
            AND dm.actual_value IS NOT NULL
        ORDER BY dm.date
        """),
        {"metric_type": metric_type}
    )

    count = 0
    for row in result.fetchall():
        await db.execute(
            text("""
            INSERT INTO prior_year_daily (
                date, metric_type, actual_value, month_total, pct_of_month, fetched_at
            ) VALUES (
                :date, :metric, :actual, :month_total, :pct, NOW()
            )
            ON CONFLICT (date, metric_type) DO UPDATE SET
                actual_value = :actual,
                month_total = :month_total,
                pct_of_month = :pct,
                fetched_at = NOW()
            """),
            {
                "date": row.date,
                "metric": metric_type,
                "actual": row.actual_value,
                "month_total": row.month_total,
                "pct": row.pct_of_month
            }
        )
        count += 1

    await db.commit()
    logger.info(f"Prior year percentages calculated: {count} records for {metric_type}")
    return count
