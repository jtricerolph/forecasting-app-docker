"""
Bookings aggregation job - aggregates newbook_bookings_data into:
- newbook_bookings_stats: daily aggregated stats with JSONB category breakdowns
- newbook_booking_pace: lead-time snapshots for forecasting pickup patterns

Triggered automatically after bookings sync completes.
"""
import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Set, Dict, Any, Optional

from sqlalchemy import text
from database import SyncSessionLocal

logger = logging.getLogger(__name__)

# Valid booking statuses for aggregation
VALID_STATUSES = ('Unconfirmed', 'Confirmed', 'Arrived', 'Departed')

# All tracked pace intervals
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


def get_config_value(db, key: str) -> Optional[str]:
    """Get a configuration value from system_config table."""
    result = db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = :key"),
        {"key": key}
    )
    row = result.fetchone()
    return row.config_value if row else None


async def run_bookings_aggregation(triggered_by: str = "manual"):
    """
    Aggregate bookings into newbook_bookings_stats.

    Flow:
    1. Find bookings changed since last_bookings_aggregation_at
    2. Calculate affected dates (arrival_date <= date < departure_date)
    3. Reaggregate each affected date
    4. Update booking pace table
    5. Update last_bookings_aggregation_at
    """
    logger.info(f"Starting bookings aggregation (triggered_by={triggered_by})")

    db = next(iter([SyncSessionLocal()]))

    try:
        # Get last aggregation timestamp
        last_aggregation = get_config_value(db, 'last_bookings_aggregation_at')
        if last_aggregation:
            try:
                last_ts = datetime.fromisoformat(last_aggregation)
            except ValueError:
                last_ts = datetime.min
        else:
            last_ts = datetime.min

        logger.info(f"Last aggregation: {last_ts}")

        # Find bookings changed since last aggregation
        result = db.execute(
            text("""
                SELECT newbook_id, arrival_date, departure_date
                FROM newbook_bookings_data
                WHERE fetched_at > :last_ts
            """),
            {"last_ts": last_ts}
        )
        changed_bookings = result.fetchall()

        if not changed_bookings:
            logger.info("No changed bookings to aggregate")
            # Still update pace table
            await update_booking_pace(db)
            db.commit()
            return

        logger.info(f"Found {len(changed_bookings)} changed bookings")

        # Calculate affected dates
        affected_dates: Set[date] = set()
        for booking in changed_bookings:
            if booking.arrival_date and booking.departure_date:
                current = booking.arrival_date
                # < not <= (departure is checkout day, guest not staying that night)
                while current < booking.departure_date:
                    affected_dates.add(current)
                    current += timedelta(days=1)

        logger.info(f"Reaggregating {len(affected_dates)} affected dates")

        # Get accommodation VAT rate
        vat_rate_str = get_config_value(db, 'accommodation_vat_rate')
        vat_rate = Decimal(vat_rate_str) if vat_rate_str else Decimal('0.20')

        # Aggregate each affected date
        for target_date in sorted(affected_dates):
            await aggregate_date(db, target_date, vat_rate)

        # Fill any dates with occupancy data but no bookings (e.g., closed periods)
        await fill_occupancy_only_dates(db, vat_rate)

        # Update booking pace table
        await update_booking_pace(db)

        # Update last aggregation timestamp
        db.execute(
            text("""
                INSERT INTO system_config (config_key, config_value, updated_at)
                VALUES ('last_bookings_aggregation_at', :now, NOW())
                ON CONFLICT (config_key) DO UPDATE SET
                    config_value = :now,
                    updated_at = NOW()
            """),
            {"now": datetime.now().isoformat()}
        )

        db.commit()
        logger.info(f"Bookings aggregation completed: {len(affected_dates)} dates processed")

    except Exception as e:
        logger.error(f"Bookings aggregation failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


async def aggregate_date(db, target_date: date, vat_rate: Decimal):
    """
    Aggregate all bookings for a specific date into newbook_bookings_stats.

    Includes room availability from newbook_occupancy_report_data and
    booking stats from newbook_bookings_data.
    """
    # Step 1: Get room availability from occupancy report (included categories only)
    result = db.execute(
        text("""
            SELECT
                o.category_id,
                COALESCE(o.available, 0) as available,
                COALESCE(o.maintenance, 0) as maintenance
            FROM newbook_occupancy_report_data o
            JOIN newbook_room_categories c ON o.category_id = c.site_id
            WHERE o.date = :target_date
            AND c.is_included = true
        """),
        {"target_date": target_date}
    )
    occupancy_rows = result.fetchall()

    # Build availability by category
    availability_by_category: Dict[str, Dict[str, Any]] = {}
    rooms_count = 0
    maintenance_count = 0

    for row in occupancy_rows:
        cat_id = row.category_id
        available = row.available or 0
        maintenance = row.maintenance or 0
        bookable = available - maintenance

        rooms_count += available
        maintenance_count += maintenance

        availability_by_category[cat_id] = {
            "rooms_count": available,
            "maintenance_count": maintenance,
            "bookable_count": bookable,
            "booking_count": 0,
            "total_occupancy_pct": None,
            "bookable_occupancy_pct": None
        }

    bookable_count = rooms_count - maintenance_count

    # Fallback: If no occupancy data (bookable_count=0), use last known bookable_count
    # This prevents division-by-zero issues in forecast models when occupancy report is missing
    if bookable_count <= 0:
        fallback_result = db.execute(
            text("""
                SELECT bookable_count
                FROM newbook_bookings_stats
                WHERE bookable_count > 5 AND date < :target_date
                ORDER BY date DESC
                LIMIT 1
            """),
            {"target_date": target_date}
        )
        fallback_row = fallback_result.fetchone()
        if fallback_row and fallback_row.bookable_count:
            bookable_count = fallback_row.bookable_count
            rooms_count = bookable_count  # Assume same for rooms_count
            logger.info(f"Using fallback bookable_count={bookable_count} for {target_date}")

    # Step 2: Get booking stats (bookings staying this night)
    # A booking is "in house" if: arrival_date <= date < departure_date
    # Only counts bookings for categories marked as is_included=true in settings
    result = db.execute(
        text("""
            SELECT
                b.newbook_id,
                b.category_id,
                COALESCE(b.adults, 0) + COALESCE(b.children, 0) + COALESCE(b.infants, 0) as guests,
                COALESCE(b.adults, 0) as adults,
                COALESCE(b.children, 0) as children,
                COALESCE(b.infants, 0) as infants,
                b.raw_json
            FROM newbook_bookings_data b
            JOIN newbook_room_categories c ON b.category_id = c.site_id
            WHERE b.arrival_date <= :target_date
            AND b.departure_date > :target_date
            AND b.status IN :valid_statuses
            AND c.is_included = true
        """),
        {"target_date": target_date, "valid_statuses": VALID_STATUSES}
    )
    bookings = result.fetchall()

    # Aggregate bookings
    booking_count = 0
    guests_count = 0
    adults_count = 0
    children_count = 0
    infants_count = 0
    guest_rate_total = Decimal('0')
    net_booking_rev_total = Decimal('0')

    occupancy_by_category: Dict[str, Dict[str, Any]] = {}
    revenue_by_category: Dict[str, Dict[str, Any]] = {}
    rate_stats_by_category: Dict[str, Dict[str, Any]] = {}  # Pickup-V2: min/max/adr per category

    for booking in bookings:
        booking_count += 1
        guests_count += booking.guests or 0
        adults_count += booking.adults or 0
        children_count += booking.children or 0
        infants_count += booking.infants or 0

        cat_id = booking.category_id or 'unknown'

        # Initialize category dicts if needed
        if cat_id not in occupancy_by_category:
            occupancy_by_category[cat_id] = {
                "booking_count": 0,
                "guests": 0,
                "adults": 0,
                "children": 0,
                "infants": 0
            }
        if cat_id not in revenue_by_category:
            revenue_by_category[cat_id] = {
                "guest_rate_total": Decimal('0'),
                "net_booking_rev_total": Decimal('0')
            }
        if cat_id not in rate_stats_by_category:
            rate_stats_by_category[cat_id] = {
                "rates": [],  # Collect all net rates for min/max/adr calculation
                "rooms": 0
            }

        # Update occupancy by category
        occupancy_by_category[cat_id]["booking_count"] += 1
        occupancy_by_category[cat_id]["guests"] += booking.guests or 0
        occupancy_by_category[cat_id]["adults"] += booking.adults or 0
        occupancy_by_category[cat_id]["children"] += booking.children or 0
        occupancy_by_category[cat_id]["infants"] += booking.infants or 0

        # Update availability by category booking count
        if cat_id in availability_by_category:
            availability_by_category[cat_id]["booking_count"] += 1

        # Get revenue from tariffs_quoted for this date
        calculated_amount, net_amount = get_rate_for_date(
            booking.raw_json, target_date, vat_rate
        )
        guest_rate_total += calculated_amount
        net_booking_rev_total += net_amount

        revenue_by_category[cat_id]["guest_rate_total"] += calculated_amount
        revenue_by_category[cat_id]["net_booking_rev_total"] += net_amount

        # Pickup-V2: Collect net rate for rate stats (only if rate > 0)
        if net_amount > 0:
            rate_stats_by_category[cat_id]["rates"].append(float(net_amount))
            rate_stats_by_category[cat_id]["rooms"] += 1

    # Calculate occupancy percentages
    total_occupancy_pct = None
    bookable_occupancy_pct = None

    if rooms_count > 0:
        total_occupancy_pct = round(float(booking_count) / rooms_count * 100, 2)
    if bookable_count > 0:
        bookable_occupancy_pct = round(float(booking_count) / bookable_count * 100, 2)

    # Calculate per-category occupancy percentages
    for cat_id, avail in availability_by_category.items():
        cat_bookings = avail["booking_count"]
        cat_rooms = avail["rooms_count"]
        cat_bookable = avail["bookable_count"]

        if cat_rooms > 0:
            avail["total_occupancy_pct"] = round(float(cat_bookings) / cat_rooms * 100, 2)
        if cat_bookable > 0:
            avail["bookable_occupancy_pct"] = round(float(cat_bookings) / cat_bookable * 100, 2)

    # Convert Decimal to float for JSON serialization
    def decimal_to_float(d: Dict) -> Dict:
        return {
            k: (float(v) if isinstance(v, Decimal) else v)
            for k, v in d.items()
        }

    # Pickup-V2: Calculate min/max/adr from collected rates
    rate_stats_final: Dict[str, Dict[str, Any]] = {}
    for cat_id, stats in rate_stats_by_category.items():
        rates = stats["rates"]
        if rates:
            rate_stats_final[cat_id] = {
                "min_net": round(min(rates), 2),
                "max_net": round(max(rates), 2),
                "adr_net": round(sum(rates) / len(rates), 2),
                "rooms": stats["rooms"]
            }

    occupancy_json = json.dumps({
        k: decimal_to_float(v) for k, v in occupancy_by_category.items()
    })
    revenue_json = json.dumps({
        k: decimal_to_float(v) for k, v in revenue_by_category.items()
    })
    availability_json = json.dumps(availability_by_category)
    rate_stats_json = json.dumps(rate_stats_final)

    # Upsert into newbook_bookings_stats
    db.execute(
        text("""
            INSERT INTO newbook_bookings_stats (
                date, rooms_count, maintenance_count, bookable_count,
                booking_count, guests_count, adults_count, children_count, infants_count,
                total_occupancy_pct, bookable_occupancy_pct,
                guest_rate_total, net_booking_rev_total,
                occupancy_by_category, revenue_by_category, availability_by_category,
                rate_stats_by_category,
                aggregated_at
            ) VALUES (
                :date, :rooms_count, :maintenance_count, :bookable_count,
                :booking_count, :guests_count, :adults_count, :children_count, :infants_count,
                :total_occupancy_pct, :bookable_occupancy_pct,
                :guest_rate_total, :net_booking_rev_total,
                :occupancy_by_category, :revenue_by_category, :availability_by_category,
                :rate_stats_by_category,
                NOW()
            )
            ON CONFLICT (date) DO UPDATE SET
                rooms_count = :rooms_count,
                maintenance_count = :maintenance_count,
                bookable_count = :bookable_count,
                booking_count = :booking_count,
                guests_count = :guests_count,
                adults_count = :adults_count,
                children_count = :children_count,
                infants_count = :infants_count,
                total_occupancy_pct = :total_occupancy_pct,
                bookable_occupancy_pct = :bookable_occupancy_pct,
                guest_rate_total = :guest_rate_total,
                net_booking_rev_total = :net_booking_rev_total,
                occupancy_by_category = :occupancy_by_category,
                revenue_by_category = :revenue_by_category,
                availability_by_category = :availability_by_category,
                rate_stats_by_category = :rate_stats_by_category,
                aggregated_at = NOW()
        """),
        {
            "date": target_date,
            "rooms_count": rooms_count,
            "maintenance_count": maintenance_count,
            "bookable_count": bookable_count,
            "booking_count": booking_count,
            "guests_count": guests_count,
            "adults_count": adults_count,
            "children_count": children_count,
            "infants_count": infants_count,
            "total_occupancy_pct": total_occupancy_pct,
            "bookable_occupancy_pct": bookable_occupancy_pct,
            "guest_rate_total": float(guest_rate_total),
            "net_booking_rev_total": float(net_booking_rev_total),
            "occupancy_by_category": occupancy_json,
            "revenue_by_category": revenue_json,
            "availability_by_category": availability_json,
            "rate_stats_by_category": rate_stats_json
        }
    )


def get_rate_for_date(raw_json: dict, target_date: date, vat_rate: Decimal) -> tuple:
    """
    Extract rate from tariffs_quoted for specific stay_date.

    Returns tuple of (calculated_amount, net_amount).
    calculated_amount = gross rate guest paid (for AGR)
    net_amount = amount after VAT deduction
    """
    if not raw_json:
        return Decimal('0'), Decimal('0')

    tariffs = raw_json.get("tariffs_quoted", [])
    target_str = target_date.strftime("%Y-%m-%d")

    for tariff in tariffs:
        if tariff.get("stay_date") == target_str:
            calculated_amount = Decimal(str(tariff.get("calculated_amount", 0) or 0))
            charge_amount = Decimal(str(tariff.get("charge_amount", 0) or 0))

            # Try to get net from taxes array if available
            taxes = tariff.get("taxes", [])
            if taxes and charge_amount > 0:
                tax_amount = sum(Decimal(str(t.get("tax_amount", 0) or 0)) for t in taxes)
                net_amount = charge_amount - tax_amount
            else:
                # Fallback: calculate net using VAT rate
                net_amount = charge_amount / (1 + vat_rate)

            return calculated_amount, net_amount

    return Decimal('0'), Decimal('0')


async def update_booking_pace(db):
    """
    Update booking pace table with current snapshots.

    For each tracked interval, snapshot the current OCCUPANCY count for that stay_date.
    Occupancy = arrivals + stayovers (guests already checked in from earlier dates).

    This counts bookings where: arrival_date <= stay_date < departure_date
    Also ensures all dates in the forecast window have rows (prevents gaps when job misses a day).
    """
    logger.info("Updating booking pace snapshots (occupancy-based)")

    today = date.today()
    updates = 0

    # Step 1: Update tracked interval columns
    for interval in PACE_INTERVALS:
        stay_date = today + timedelta(days=interval)

        # Count OCCUPANCY for this stay_date (arrivals + stayovers)
        # A booking occupies a date if: arrival_date <= stay_date < departure_date
        result = db.execute(
            text("""
                SELECT COUNT(*) as count
                FROM newbook_bookings_data b
                JOIN newbook_room_categories c ON b.category_id = c.site_id
                WHERE b.arrival_date <= :stay_date
                AND b.departure_date > :stay_date
                AND b.status IN :valid_statuses
                AND c.is_included = true
            """),
            {"stay_date": stay_date, "valid_statuses": VALID_STATUSES}
        )
        row = result.fetchone()
        booking_count = row.count if row else 0

        # Upsert to pace table (column still named arrival_date for backwards compat)
        column_name = f"d{interval}"

        # Build dynamic SQL for upsert
        db.execute(
            text(f"""
                INSERT INTO newbook_booking_pace (arrival_date, {column_name}, updated_at)
                VALUES (:stay_date, :count, NOW())
                ON CONFLICT (arrival_date) DO UPDATE
                SET {column_name} = :count, updated_at = NOW()
            """),
            {"stay_date": stay_date, "count": booking_count}
        )
        updates += 1

    # Step 2: Update gap dates (31-36, 38-43, etc.) with their bracketed column
    # These dates fall between tracked intervals and need their nearest column updated
    gap_updates = 0
    for days_out in range(31, 90):  # Cover the gap range where intervals are weekly
        if days_out in PACE_INTERVALS:
            continue  # Already handled in step 1

        stay_date = today + timedelta(days=days_out)

        # Find the bracketed column (round up to next interval)
        bracket_col = None
        for interval in sorted(PACE_INTERVALS):
            if interval >= days_out:
                bracket_col = f"d{interval}"
                break

        if not bracket_col:
            continue

        # Count OCCUPANCY (arrivals + stayovers)
        result = db.execute(
            text("""
                SELECT COUNT(*) as count
                FROM newbook_bookings_data b
                JOIN newbook_room_categories c ON b.category_id = c.site_id
                WHERE b.arrival_date <= :stay_date
                AND b.departure_date > :stay_date
                AND b.status IN :valid_statuses
                AND c.is_included = true
            """),
            {"stay_date": stay_date, "valid_statuses": VALID_STATUSES}
        )
        row = result.fetchone()
        booking_count = row.count if row else 0

        # Upsert with the bracketed column
        db.execute(
            text(f"""
                INSERT INTO newbook_booking_pace (arrival_date, {bracket_col}, updated_at)
                VALUES (:stay_date, :count, NOW())
                ON CONFLICT (arrival_date) DO UPDATE
                SET {bracket_col} = :count, updated_at = NOW()
            """),
            {"stay_date": stay_date, "count": booking_count}
        )
        gap_updates += 1

    logger.info(f"Updated {updates} pace snapshots + {gap_updates} gap dates (occupancy-based)")


async def fill_occupancy_only_dates(db, vat_rate: Decimal = None):
    """
    Create stats rows for dates that have occupancy data but no bookings.

    This ensures dates like closed periods (all rooms in maintenance) get proper
    stats rows with bookable_count=0, so forecasts can cap correctly.
    """
    if vat_rate is None:
        vat_rate_str = get_config_value(db, 'accommodation_vat_rate')
        vat_rate = Decimal(vat_rate_str) if vat_rate_str else Decimal('0.20')

    # Find dates with occupancy data but no stats row
    result = db.execute(
        text("""
            SELECT DISTINCT o.date
            FROM newbook_occupancy_report_data o
            JOIN newbook_room_categories c ON o.category_id = c.site_id
            WHERE c.is_included = true
            AND NOT EXISTS (
                SELECT 1 FROM newbook_bookings_stats s WHERE s.date = o.date
            )
            ORDER BY o.date
        """)
    )
    missing_dates = [row.date for row in result.fetchall()]

    if not missing_dates:
        logger.info("No occupancy-only dates to fill")
        return 0

    logger.info(f"Filling {len(missing_dates)} occupancy-only dates (no bookings)")

    for target_date in missing_dates:
        await aggregate_date(db, target_date, vat_rate)

    logger.info(f"Filled {len(missing_dates)} occupancy-only dates")
    return len(missing_dates)


async def backfill_aggregation(db=None):
    """
    Backfill historical data into newbook_bookings_stats and newbook_booking_pace.

    - Stats: Aggregates all dates that have bookings staying
    - Pace: Reconstructs historical snapshots using booking_placed timestamps
    """
    import sys
    print("[BACKFILL] Starting backfill aggregation...", flush=True)
    sys.stdout.flush()

    close_db = False
    if db is None:
        db = next(iter([SyncSessionLocal()]))
        close_db = True

    try:
        # Get VAT rate
        vat_rate_str = get_config_value(db, 'accommodation_vat_rate')
        vat_rate = Decimal(vat_rate_str) if vat_rate_str else Decimal('0.20')

        # Step 1: Get all unique stay dates from bookings
        print("[BACKFILL] Finding all stay dates...", flush=True)
        result = db.execute(
            text("""
                SELECT DISTINCT d::date as stay_date
                FROM newbook_bookings_data b,
                     generate_series(b.arrival_date, b.departure_date - interval '1 day', '1 day') d
                WHERE b.status IN :valid_statuses
                ORDER BY stay_date
            """),
            {"valid_statuses": VALID_STATUSES}
        )
        stay_dates = [row.stay_date for row in result.fetchall()]
        print(f"[BACKFILL] Found {len(stay_dates)} stay dates to aggregate", flush=True)

        # Step 2: Aggregate each stay date into stats
        for i, target_date in enumerate(stay_dates):
            if i % 100 == 0:
                print(f"[BACKFILL] Aggregating stats: {i}/{len(stay_dates)} dates...", flush=True)
                db.commit()  # Commit periodically
            await aggregate_date(db, target_date, vat_rate)

        db.commit()
        print(f"[BACKFILL] Stats aggregation complete: {len(stay_dates)} dates", flush=True)

        # Step 2b: Fill in dates with occupancy data but no bookings (e.g., closed periods)
        print("[BACKFILL] Filling occupancy-only dates (no bookings)...", flush=True)
        filled_count = await fill_occupancy_only_dates(db, vat_rate)
        db.commit()
        print(f"[BACKFILL] Filled {filled_count} occupancy-only dates", flush=True)

        # Step 3: Get ALL dates from stats for pace backfill
        # This includes dates with 0 bookings (closed periods, future dates)
        # Critical: Without pace entries, models may predict 100% occupancy
        print("[BACKFILL] Finding all stats dates for pace...", flush=True)
        result = db.execute(
            text("""
                SELECT date as stay_date
                FROM newbook_bookings_stats
                ORDER BY date
            """)
        )
        stay_dates_for_pace = [row.stay_date for row in result.fetchall()]
        print(f"[BACKFILL] Found {len(stay_dates_for_pace)} stats dates for pace backfill", flush=True)

        # Step 4: Backfill pace for each stay date (occupancy-based)
        today = date.today()
        for i, stay_date in enumerate(stay_dates_for_pace):
            if i % 100 == 0:
                print(f"[BACKFILL] Backfilling pace: {i}/{len(stay_dates_for_pace)} dates...", flush=True)
                db.commit()

            await backfill_pace_for_date(db, stay_date, today)

        db.commit()
        print(f"[BACKFILL] Pace backfill complete: {len(stay_dates_for_pace)} dates (occupancy-based)", flush=True)

        # Update last aggregation timestamp
        db.execute(
            text("""
                INSERT INTO system_config (config_key, config_value, updated_at)
                VALUES ('last_bookings_aggregation_at', :now, NOW())
                ON CONFLICT (config_key) DO UPDATE SET
                    config_value = :now,
                    updated_at = NOW()
            """),
            {"now": datetime.now().isoformat()}
        )
        db.commit()

        print("[BACKFILL] Backfill complete!", flush=True)
        logger.info("Backfill aggregation completed successfully")

    except Exception as e:
        print(f"[BACKFILL] FAILED: {e}", flush=True)
        logger.error(f"Backfill aggregation failed: {e}")
        db.rollback()
        raise
    finally:
        if close_db:
            db.close()


async def backfill_pace_for_date(db, stay_date: date, today: date):
    """
    Backfill pace snapshots for a single stay date using booking_placed timestamps.

    Tracks OCCUPANCY (arrivals + stayovers), not just arrivals.
    For historical stays: Reconstruct what occupancy would have been at each lead time
    For future stays: Use current count for today's lead time
    """
    # For each interval, calculate what the occupancy count was at that point
    # Using booking_placed to determine when each booking was created
    pace_values = {}

    for interval in PACE_INTERVALS:
        # The snapshot date is when we would have taken this measurement
        snapshot_date = stay_date - timedelta(days=interval)

        if snapshot_date > today:
            # This snapshot hasn't happened yet - skip
            continue

        if snapshot_date < date(2020, 1, 1):
            # Don't go too far back - skip ancient dates
            continue

        # Count OCCUPANCY that existed at the snapshot date
        # A booking contributes to occupancy if:
        #   - arrival_date <= stay_date < departure_date (booking spans this night)
        #   - booking_placed <= snapshot_date (booking existed at measurement time)
        # Only counts categories with is_included = true
        result = db.execute(
            text("""
                SELECT COUNT(*) as count
                FROM newbook_bookings_data b
                JOIN newbook_room_categories c ON b.category_id = c.site_id
                WHERE b.arrival_date <= :stay_date
                AND b.departure_date > :stay_date
                AND b.status IN :valid_statuses
                AND c.is_included = true
                AND b.booking_placed IS NOT NULL
                AND b.booking_placed::date <= :snapshot_date
            """),
            {
                "stay_date": stay_date,
                "valid_statuses": VALID_STATUSES,
                "snapshot_date": snapshot_date
            }
        )
        row = result.fetchone()
        pace_values[f"d{interval}"] = row.count if row else 0

    if not pace_values:
        return

    # Build dynamic upsert for all columns we have values for
    columns = list(pace_values.keys())
    set_clauses = ", ".join([f"{col} = :{col}" for col in columns])
    insert_cols = ", ".join(columns)
    insert_vals = ", ".join([f":{col}" for col in columns])

    db.execute(
        text(f"""
            INSERT INTO newbook_booking_pace (arrival_date, {insert_cols}, updated_at)
            VALUES (:stay_date, {insert_vals}, NOW())
            ON CONFLICT (arrival_date) DO UPDATE SET
                {set_clauses}, updated_at = NOW()
        """),
        {"stay_date": stay_date, **pace_values}
    )


async def fill_missing_pace_entries(db=None):
    """
    Fill pace entries for all stats dates that don't have pace rows.

    This fixes gaps where dates exist in stats (with 0 or more bookings)
    but have no pace data, causing models to predict incorrectly.
    """
    import sys
    print("[PACE-FILL] Finding dates missing pace entries...", flush=True)

    close_db = False
    if db is None:
        db = next(iter([SyncSessionLocal()]))
        close_db = True

    try:
        # Find dates in stats but not in pace
        result = db.execute(
            text("""
                SELECT s.date as stay_date
                FROM newbook_bookings_stats s
                LEFT JOIN newbook_booking_pace p ON s.date = p.arrival_date
                WHERE p.arrival_date IS NULL
                ORDER BY s.date
            """)
        )
        missing_dates = [row.stay_date for row in result.fetchall()]

        if not missing_dates:
            print("[PACE-FILL] No missing pace entries found", flush=True)
            return 0

        print(f"[PACE-FILL] Found {len(missing_dates)} dates missing pace entries", flush=True)

        today = date.today()
        for i, stay_date in enumerate(missing_dates):
            if i % 100 == 0:
                print(f"[PACE-FILL] Processing: {i}/{len(missing_dates)} dates...", flush=True)
                db.commit()

            await backfill_pace_for_date(db, stay_date, today)

        db.commit()
        print(f"[PACE-FILL] Filled {len(missing_dates)} missing pace entries", flush=True)
        return len(missing_dates)

    except Exception as e:
        print(f"[PACE-FILL] FAILED: {e}", flush=True)
        db.rollback()
        raise
    finally:
        if close_db:
            db.close()


def get_pace_interval(days_out: int) -> str:
    """
    Get the pace column to use for a given lead time.
    Uses round-up logic (next higher interval for conservative estimates).

    Examples:
      - 25 days out → d25 (exact daily match)
      - 35 days out → d37 (rounds up to next weekly)
      - 200 days out → d210 (rounds up to next monthly)
    """
    # Monthly thresholds (7-12 months)
    if days_out >= 365:
        return "d365"
    if days_out >= 330:
        return "d365"
    if days_out >= 300:
        return "d330"
    if days_out >= 270:
        return "d300"
    if days_out >= 240:
        return "d270"
    if days_out >= 210:
        return "d240"

    # Weekly thresholds (5-25 weeks)
    weekly = [177, 170, 163, 156, 149, 142, 135, 128, 121, 114,
              107, 100, 93, 86, 79, 72, 65, 58, 51, 44, 37]
    for i, threshold in enumerate(weekly):
        if days_out >= threshold:
            return f"d{weekly[i - 1]}" if i > 0 else "d210"

    # Daily (0-30 days) - exact match available
    if days_out > 30:
        return "d37"  # Round up to first weekly
    return f"d{days_out}"
