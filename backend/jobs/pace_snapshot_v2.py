"""
Pace Snapshot V2 - Enhanced pace capture for pickup-v2 model

Captures:
1. Per-category room counts at each lead time (category_booking_pace)
2. Total booked accommodation revenue at each lead time (revenue_pace)

This job runs alongside the existing pickup_snapshot job.
Uses 364-day offset for prior year comparison (52 weeks = day-of-week alignment).
"""
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import text
from database import SyncSessionLocal

logger = logging.getLogger(__name__)

# Valid booking statuses for aggregation
VALID_STATUSES = ('Unconfirmed', 'Confirmed', 'Arrived', 'Departed')

# All tracked pace intervals (same as booking_pace table structure)
PACE_INTERVALS = [
    # Monthly (months 7-12)
    365, 330, 300, 270, 240, 210,
    # Weekly (weeks 5-25)
    177, 170, 163, 156, 149, 142, 135, 128, 121, 114,
    107, 100, 93, 86, 79, 72, 65, 58, 51, 44, 37,
    # Daily (days 0-30)
    30, 29, 28, 27, 26, 25, 24, 23, 22, 21,
    20, 19, 18, 17, 16, 15, 14, 13, 12, 11,
    10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0
]


def get_lead_time_column(lead_days: int) -> str:
    """
    Map lead days to the appropriate column in pace tables.
    Uses round-up logic for days between tracked intervals.
    """
    if lead_days <= 0:
        return "d0"
    elif lead_days <= 30:
        return f"d{lead_days}"
    elif lead_days <= 177:
        # Weekly intervals - find next higher
        weekly_cols = [37, 44, 51, 58, 65, 72, 79, 86, 93, 100, 107, 114, 121, 128, 135, 142, 149, 156, 163, 170, 177]
        for col in weekly_cols:
            if lead_days <= col:
                return f"d{col}"
        return "d177"
    else:
        # Monthly intervals
        monthly_cols = [210, 240, 270, 300, 330, 365]
        for col in monthly_cols:
            if lead_days <= col:
                return f"d{col}"
        return "d365"


def get_rate_for_date(raw_json: dict, target_date: date, vat_rate: Decimal) -> Decimal:
    """
    Extract net accommodation rate from tariffs_quoted for a specific stay_date.
    Returns net amount (after VAT deduction).
    """
    if not raw_json:
        return Decimal('0')

    tariffs = raw_json.get("tariffs_quoted", [])
    target_str = target_date.strftime("%Y-%m-%d")

    for tariff in tariffs:
        if tariff.get("stay_date") == target_str:
            charge_amount = Decimal(str(tariff.get("charge_amount", 0) or 0))

            # Try to get net from taxes array if available
            taxes = tariff.get("taxes", [])
            if taxes and charge_amount > 0:
                tax_amount = sum(Decimal(str(t.get("amount", 0) or 0)) for t in taxes)
                net_amount = charge_amount - tax_amount
            else:
                # Fallback: calculate net using VAT rate
                net_amount = charge_amount / (1 + vat_rate)

            return net_amount

    return Decimal('0')


async def run_pace_snapshot_v2():
    """
    Capture per-category room counts and total revenue at each lead time.

    Updates:
    - category_booking_pace: room counts by category for each future date
    - revenue_pace: total booked accommodation revenue for each future date
    """
    logger.info("Starting pace snapshot v2 capture")

    db = next(iter([SyncSessionLocal()]))
    today = date.today()

    try:
        # Get accommodation VAT rate from config
        vat_result = db.execute(
            text("SELECT config_value FROM system_config WHERE config_key = 'accommodation_vat_rate'")
        ).fetchone()
        vat_rate = Decimal(vat_result.config_value) if vat_result and vat_result.config_value else Decimal('0.20')

        # Get all included room categories
        cat_result = db.execute(
            text("SELECT site_id FROM newbook_room_categories WHERE is_included = true")
        )
        included_categories = [row.site_id for row in cat_result.fetchall()]

        if not included_categories:
            logger.warning("No included room categories found")
            return

        # Process each tracked interval
        for interval in PACE_INTERVALS:
            stay_date = today + timedelta(days=interval)
            column_name = f"d{interval}"

            # === 1. Capture per-category room counts ===
            cat_counts = await capture_category_counts(db, stay_date, included_categories)

            for category_id, count in cat_counts.items():
                db.execute(
                    text(f"""
                        INSERT INTO category_booking_pace (arrival_date, category_id, {column_name}, updated_at)
                        VALUES (:stay_date, :category_id, :count, NOW())
                        ON CONFLICT (arrival_date, category_id) DO UPDATE
                        SET {column_name} = :count, updated_at = NOW()
                    """),
                    {"stay_date": stay_date, "category_id": category_id, "count": count}
                )

            # === 2. Capture total booked revenue ===
            total_revenue = await capture_booked_revenue(db, stay_date, vat_rate, included_categories)

            db.execute(
                text(f"""
                    INSERT INTO revenue_pace (stay_date, {column_name}, updated_at)
                    VALUES (:stay_date, :revenue, NOW())
                    ON CONFLICT (stay_date) DO UPDATE
                    SET {column_name} = :revenue, updated_at = NOW()
                """),
                {"stay_date": stay_date, "revenue": float(total_revenue)}
            )

        # Also fill gap dates (31-36, 38-43, etc.) with their bracketed column
        await fill_gap_dates(db, today, vat_rate, included_categories)

        db.commit()
        logger.info(f"Pace snapshot v2 completed for {today}")

    except Exception as e:
        logger.error(f"Pace snapshot v2 failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


async def capture_category_counts(db, stay_date: date, included_categories: List[str]) -> Dict[str, int]:
    """
    Count rooms booked per category for a given stay date.
    Returns dict of {category_id: count}
    """
    result = db.execute(
        text("""
            SELECT category_id, COUNT(*) as count
            FROM newbook_bookings_data
            WHERE arrival_date <= :stay_date
            AND departure_date > :stay_date
            AND status IN :valid_statuses
            AND category_id IN :categories
            GROUP BY category_id
        """),
        {"stay_date": stay_date, "valid_statuses": VALID_STATUSES, "categories": tuple(included_categories)}
    )

    counts = {cat: 0 for cat in included_categories}  # Initialize all categories with 0
    for row in result.fetchall():
        counts[row.category_id] = row.count

    return counts


async def capture_booked_revenue(db, stay_date: date, vat_rate: Decimal, included_categories: List[str]) -> Decimal:
    """
    Calculate total booked accommodation revenue (net) for a given stay date.
    Sums up tariffs from all active bookings that span this date.
    """
    result = db.execute(
        text("""
            SELECT raw_json
            FROM newbook_bookings_data
            WHERE arrival_date <= :stay_date
            AND departure_date > :stay_date
            AND status IN :valid_statuses
            AND category_id IN :categories
        """),
        {"stay_date": stay_date, "valid_statuses": VALID_STATUSES, "categories": tuple(included_categories)}
    )

    total_revenue = Decimal('0')
    for row in result.fetchall():
        if row.raw_json:
            revenue = get_rate_for_date(row.raw_json, stay_date, vat_rate)
            total_revenue += revenue

    return total_revenue


async def fill_gap_dates(db, today: date, vat_rate: Decimal, included_categories: List[str]):
    """
    Fill gap dates (between tracked intervals) with their bracketed column value.
    These dates fall between weekly intervals and need the next higher column updated.
    """
    gap_updates = 0

    for days_out in range(31, 90):  # Cover the gap range where intervals are weekly
        if days_out in PACE_INTERVALS:
            continue  # Already handled in main loop

        stay_date = today + timedelta(days=days_out)
        bracket_col = get_lead_time_column(days_out)

        # Capture category counts
        cat_counts = await capture_category_counts(db, stay_date, included_categories)
        for category_id, count in cat_counts.items():
            db.execute(
                text(f"""
                    INSERT INTO category_booking_pace (arrival_date, category_id, {bracket_col}, updated_at)
                    VALUES (:stay_date, :category_id, :count, NOW())
                    ON CONFLICT (arrival_date, category_id) DO UPDATE
                    SET {bracket_col} = :count, updated_at = NOW()
                """),
                {"stay_date": stay_date, "category_id": category_id, "count": count}
            )

        # Capture revenue
        total_revenue = await capture_booked_revenue(db, stay_date, vat_rate, included_categories)
        db.execute(
            text(f"""
                INSERT INTO revenue_pace (stay_date, {bracket_col}, updated_at)
                VALUES (:stay_date, :revenue, NOW())
                ON CONFLICT (stay_date) DO UPDATE
                SET {bracket_col} = :revenue, updated_at = NOW()
            """),
            {"stay_date": stay_date, "revenue": float(total_revenue)}
        )

        gap_updates += 1

    logger.info(f"Filled {gap_updates} gap dates for category pace and revenue pace")


async def backfill_pace_v2(db=None):
    """
    Backfill historical pace v2 data using booking_placed timestamps.

    Reconstructs what category counts and revenue would have been at each lead time
    for historical dates.
    """
    import sys
    print("[PACE-V2-BACKFILL] Starting backfill...", flush=True)

    close_db = False
    if db is None:
        db = next(iter([SyncSessionLocal()]))
        close_db = True

    try:
        # Get VAT rate
        vat_result = db.execute(
            text("SELECT config_value FROM system_config WHERE config_key = 'accommodation_vat_rate'")
        ).fetchone()
        vat_rate = Decimal(vat_result.config_value) if vat_result and vat_result.config_value else Decimal('0.20')

        # Get included categories
        cat_result = db.execute(
            text("SELECT site_id FROM newbook_room_categories WHERE is_included = true")
        )
        included_categories = [row.site_id for row in cat_result.fetchall()]

        if not included_categories:
            print("[PACE-V2-BACKFILL] No included categories found", flush=True)
            return

        # Get all unique stay dates from bookings_stats
        result = db.execute(
            text("""
                SELECT date as stay_date
                FROM newbook_bookings_stats
                WHERE date >= CURRENT_DATE - INTERVAL '2 years'
                ORDER BY date
            """)
        )
        stay_dates = [row.stay_date for row in result.fetchall()]
        print(f"[PACE-V2-BACKFILL] Found {len(stay_dates)} dates to process", flush=True)

        today = date.today()

        for i, stay_date in enumerate(stay_dates):
            if i % 100 == 0:
                print(f"[PACE-V2-BACKFILL] Processing: {i}/{len(stay_dates)} dates...", flush=True)
                db.commit()

            await backfill_pace_v2_for_date(db, stay_date, today, vat_rate, included_categories)

        db.commit()
        print(f"[PACE-V2-BACKFILL] Complete: {len(stay_dates)} dates processed", flush=True)

    except Exception as e:
        print(f"[PACE-V2-BACKFILL] FAILED: {e}", flush=True)
        db.rollback()
        raise
    finally:
        if close_db:
            db.close()


async def backfill_pace_v2_for_date(
    db,
    stay_date: date,
    today: date,
    vat_rate: Decimal,
    included_categories: List[str]
):
    """
    Backfill pace v2 data for a single date using booking_placed timestamps.
    """
    pace_category_values: Dict[str, Dict[str, int]] = {cat: {} for cat in included_categories}
    pace_revenue_values: Dict[str, Decimal] = {}

    for interval in PACE_INTERVALS:
        snapshot_date = stay_date - timedelta(days=interval)

        if snapshot_date > today:
            continue  # This snapshot hasn't happened yet
        if snapshot_date < date(2020, 1, 1):
            continue  # Don't go too far back

        column_name = f"d{interval}"

        # Count per-category bookings that existed at snapshot_date
        result = db.execute(
            text("""
                SELECT category_id, COUNT(*) as count
                FROM newbook_bookings_data
                WHERE arrival_date <= :stay_date
                AND departure_date > :stay_date
                AND status IN :valid_statuses
                AND category_id IN :categories
                AND booking_placed IS NOT NULL
                AND booking_placed::date <= :snapshot_date
                GROUP BY category_id
            """),
            {
                "stay_date": stay_date,
                "valid_statuses": VALID_STATUSES,
                "categories": tuple(included_categories),
                "snapshot_date": snapshot_date
            }
        )

        for row in result.fetchall():
            pace_category_values[row.category_id][column_name] = row.count

        # Calculate revenue that was booked at snapshot_date
        result = db.execute(
            text("""
                SELECT raw_json
                FROM newbook_bookings_data
                WHERE arrival_date <= :stay_date
                AND departure_date > :stay_date
                AND status IN :valid_statuses
                AND category_id IN :categories
                AND booking_placed IS NOT NULL
                AND booking_placed::date <= :snapshot_date
            """),
            {
                "stay_date": stay_date,
                "valid_statuses": VALID_STATUSES,
                "categories": tuple(included_categories),
                "snapshot_date": snapshot_date
            }
        )

        total_revenue = Decimal('0')
        for row in result.fetchall():
            if row.raw_json:
                revenue = get_rate_for_date(row.raw_json, stay_date, vat_rate)
                total_revenue += revenue

        pace_revenue_values[column_name] = total_revenue

    # Upsert category pace values
    for category_id, columns in pace_category_values.items():
        if not columns:
            continue

        col_names = list(columns.keys())
        set_clauses = ", ".join([f"{col} = :{col}" for col in col_names])
        insert_cols = ", ".join(col_names)
        insert_vals = ", ".join([f":{col}" for col in col_names])

        db.execute(
            text(f"""
                INSERT INTO category_booking_pace (arrival_date, category_id, {insert_cols}, updated_at)
                VALUES (:stay_date, :category_id, {insert_vals}, NOW())
                ON CONFLICT (arrival_date, category_id) DO UPDATE SET
                    {set_clauses}, updated_at = NOW()
            """),
            {"stay_date": stay_date, "category_id": category_id, **columns}
        )

    # Upsert revenue pace values
    if pace_revenue_values:
        col_names = list(pace_revenue_values.keys())
        float_values = {k: float(v) for k, v in pace_revenue_values.items()}
        set_clauses = ", ".join([f"{col} = :{col}" for col in col_names])
        insert_cols = ", ".join(col_names)
        insert_vals = ", ".join([f":{col}" for col in col_names])

        db.execute(
            text(f"""
                INSERT INTO revenue_pace (stay_date, {insert_cols}, updated_at)
                VALUES (:stay_date, {insert_vals}, NOW())
                ON CONFLICT (stay_date) DO UPDATE SET
                    {set_clauses}, updated_at = NOW()
            """),
            {"stay_date": stay_date, **float_values}
        )
