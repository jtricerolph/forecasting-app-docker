"""
Budget distribution service
Distributes monthly budgets to daily values using prior year patterns
"""
import logging
from datetime import date
from calendar import monthrange
from typing import Optional

logger = logging.getLogger(__name__)


async def distribute_budget(
    db,
    year: int,
    month: int,
    budget_type: Optional[str] = None
) -> dict:
    """
    Distribute monthly budget to daily values using prior year patterns

    Logic:
    1. Get monthly budget from FD-provided values
    2. Get prior year daily values for the same month
    3. Calculate each day's percentage of the month total
    4. Apply those percentages to distribute this year's budget

    Example:
    - Feb 2026 budget: £100,000
    - Feb 14, 2025 was 5% of Feb 2025 total
    - Feb 14, 2026 daily budget = £100,000 × 5% = £5,000

    Args:
        db: Database session
        year: Year to distribute for
        month: Month to distribute (1-12)
        budget_type: Optional specific budget type, or all if None

    Returns:
        Dict with distribution results
    """
    logger.info(f"Distributing budget for {year}-{month:02d}")

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

    result = db.execute(query, params)
    monthly_budgets = result.fetchall()

    if not monthly_budgets:
        logger.warning(f"No monthly budgets found for {year}-{month:02d}")
        return {"days_distributed": 0, "status": "no_budgets_found"}

    # Get days in month
    _, days_in_month = monthrange(year, month)
    prior_year = year - 1

    days_distributed = 0

    for budget in monthly_budgets:
        budget_id = budget.id
        btype = budget.budget_type
        monthly_value = float(budget.budget_value)

        logger.info(f"Distributing {btype}: £{monthly_value:,.2f}")

        # Get prior year daily values for percentage calculation
        prior_result = db.execute(
            """
            SELECT date, actual_value, pct_of_month
            FROM prior_year_daily
            WHERE EXTRACT(MONTH FROM date) = :month
                AND EXTRACT(YEAR FROM date) = :prior_year
                AND metric_type = :btype
            ORDER BY date
            """,
            {"month": month, "prior_year": prior_year, "btype": btype}
        )
        prior_days = result.fetchall()

        if prior_days:
            # Use prior year percentages
            for prior_day in prior_days:
                # Calculate this year's date
                day_num = prior_day.date.day
                try:
                    this_year_date = date(year, month, day_num)
                except ValueError:
                    continue  # Day doesn't exist this year (e.g., Feb 29)

                pct_of_month = float(prior_day.pct_of_month) if prior_day.pct_of_month else (1 / days_in_month)
                daily_budget = monthly_value * pct_of_month

                db.execute(
                    """
                    INSERT INTO daily_budgets (
                        date, budget_type, budget_value, distribution_method,
                        prior_year_pct, monthly_budget_id, calculated_at
                    ) VALUES (
                        :date, :btype, :value, 'prior_year',
                        :pct, :budget_id, NOW()
                    )
                    ON CONFLICT (date, budget_type) DO UPDATE SET
                        budget_value = :value,
                        prior_year_pct = :pct,
                        calculated_at = NOW()
                    """,
                    {
                        "date": this_year_date,
                        "btype": btype,
                        "value": round(daily_budget, 2),
                        "pct": pct_of_month,
                        "budget_id": budget_id
                    }
                )
                days_distributed += 1
        else:
            # No prior year data - distribute evenly
            logger.warning(f"No prior year data for {btype}, using even distribution")
            daily_budget = monthly_value / days_in_month

            for day in range(1, days_in_month + 1):
                this_year_date = date(year, month, day)

                db.execute(
                    """
                    INSERT INTO daily_budgets (
                        date, budget_type, budget_value, distribution_method,
                        prior_year_pct, monthly_budget_id, calculated_at
                    ) VALUES (
                        :date, :btype, :value, 'even',
                        :pct, :budget_id, NOW()
                    )
                    ON CONFLICT (date, budget_type) DO UPDATE SET
                        budget_value = :value,
                        calculated_at = NOW()
                    """,
                    {
                        "date": this_year_date,
                        "btype": btype,
                        "value": round(daily_budget, 2),
                        "pct": 1 / days_in_month,
                        "budget_id": budget_id
                    }
                )
                days_distributed += 1

    db.commit()
    logger.info(f"Budget distribution complete: {days_distributed} days")
    return {"days_distributed": days_distributed, "status": "success"}


async def calculate_prior_year_percentages(db, metric_type: str):
    """
    Calculate and store prior year daily percentages for budget distribution

    For each month, calculates what percentage each day was of the monthly total
    """
    logger.info(f"Calculating prior year percentages for {metric_type}")

    # Get all daily values from prior year
    result = db.execute(
        """
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
        """,
        {"metric_type": metric_type}
    )

    count = 0
    for row in result.fetchall():
        db.execute(
            """
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
            """,
            {
                "date": row.date,
                "metric": metric_type,
                "actual": row.actual_value,
                "month_total": row.month_total,
                "pct": row.pct_of_month
            }
        )
        count += 1

    db.commit()
    logger.info(f"Prior year percentages calculated: {count} records for {metric_type}")
    return count
