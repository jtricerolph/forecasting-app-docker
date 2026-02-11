"""
Resos Bookings Aggregation Job
Aggregates resos_bookings_data into:
- resos_bookings_stats: daily aggregated stats with period/source breakdowns
- resos_booking_pace: lead-time snapshots for pickup forecasting (3 types)
"""
import json
import logging
from datetime import date, datetime, timedelta
from typing import Set, Dict, Any, Optional, Tuple, List
from collections import defaultdict

from sqlalchemy import text
from database import SyncSessionLocal

logger = logging.getLogger(__name__)

# Valid booking statuses for aggregation
# Note: Resos uses 'approved' for confirmed future reservations, 'left' for completed meals
VALID_STATUSES = ('approved', 'arrived', 'seated', 'left')

# All tracked pace intervals (same as Newbook)
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


def parse_group_exclude_field(group_exclude_field: Optional[str], primary_booking_number: Optional[str]) -> Tuple[List[str], List[str]]:
    """
    Parse group_exclude_field to extract linked bookings and exclude markers.
    Returns: (all_booking_numbers, exclude_numbers)
    """
    all_booking_numbers = []
    exclude_numbers = []

    # Always include primary booking number
    if primary_booking_number:
        all_booking_numbers.append(primary_booking_number)

    if not group_exclude_field:
        return all_booking_numbers, exclude_numbers

    # Parse comma-separated entries
    parts = group_exclude_field.split(',')
    for part in parts:
        part = part.strip()

        if part.upper().startswith('NOT-#'):
            # Exclude marker: NOT-#56748 → NB56748
            booking_num = part[5:]  # Remove "NOT-#"
            exclude_numbers.append(f"NB{booking_num}")

        elif part.startswith('#'):
            # Additional booking: #12346 → NB12346
            booking_num = part[1:]  # Remove "#"
            all_booking_numbers.append(f"NB{booking_num}")

    return all_booking_numbers, exclude_numbers


async def aggregate_resos_bookings(triggered_by: str = "manual"):
    """
    Aggregate Resos bookings into resos_bookings_stats.

    Flow:
    1. Find bookings changed since last_resos_aggregation_at
    2. Calculate affected dates
    3. Reaggregate each affected date
    4. Update booking pace table (3 types)
    5. Update last_resos_aggregation_at
    """
    logger.info(f"Starting Resos bookings aggregation (triggered_by={triggered_by})")

    db = SyncSessionLocal()

    try:
        # Get last aggregation timestamp
        result = db.execute(
            text("SELECT config_value FROM system_config WHERE config_key = 'last_resos_aggregation_at'")
        )
        row = result.fetchone()
        if row and row.config_value:
            try:
                last_ts = datetime.fromisoformat(row.config_value)
            except ValueError:
                last_ts = datetime.min
        else:
            last_ts = datetime.min

        logger.info(f"Last aggregation: {last_ts}")

        # Find bookings changed since last aggregation
        result = db.execute(
            text("""
                SELECT resos_id, booking_date
                FROM resos_bookings_data
                WHERE fetched_at > :last_ts
            """),
            {"last_ts": last_ts}
        )
        changed_bookings = result.fetchall()

        if not changed_bookings:
            logger.info("No changed bookings to aggregate")
            # Still update pace table
            await update_resos_booking_pace(db)
            db.commit()

            # Update timestamp
            db.execute(
                text("""
                    INSERT INTO system_config (config_key, config_value, updated_at)
                    VALUES ('last_resos_aggregation_at', :now, NOW())
                    ON CONFLICT (config_key) DO UPDATE SET
                        config_value = :now,
                        updated_at = NOW()
                """),
                {"now": datetime.now().isoformat()}
            )
            db.commit()
            return

        logger.info(f"Found {len(changed_bookings)} changed bookings")

        # Calculate affected dates
        affected_dates: Set[date] = set()
        for booking in changed_bookings:
            if booking.booking_date:
                affected_dates.add(booking.booking_date)

        logger.info(f"Reaggregating {len(affected_dates)} affected dates")

        # Aggregate each affected date
        for target_date in sorted(affected_dates):
            await aggregate_date(db, target_date)

        # Update booking pace table (3 types)
        await update_resos_booking_pace(db)

        # Update last aggregation timestamp
        db.execute(
            text("""
                INSERT INTO system_config (config_key, config_value, updated_at)
                VALUES ('last_resos_aggregation_at', :now, NOW())
                ON CONFLICT (config_key) DO UPDATE SET
                    config_value = :now,
                    updated_at = NOW()
            """),
            {"now": datetime.now().isoformat()}
        )

        db.commit()
        logger.info(f"Resos bookings aggregation completed: {len(affected_dates)} dates processed")

    except Exception as e:
        logger.error(f"Resos bookings aggregation failed: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


async def aggregate_date(db, target_date: date):
    """
    Aggregate all Resos bookings for a specific date into resos_bookings_stats.
    """
    # Get all valid bookings for this date
    result = db.execute(
        text("""
            SELECT
                resos_id,
                period_type,
                covers,
                source,
                opening_hour_id,
                is_hotel_guest,
                is_dbb,
                is_package,
                total_guests,
                hotel_booking_number,
                group_exclude_field
            FROM resos_bookings_data
            WHERE booking_date = :target_date
            AND status IN :valid_statuses
        """),
        {"target_date": target_date, "valid_statuses": VALID_STATUSES}
    )
    bookings = result.fetchall()

    # Initialize counters
    breakfast_covers = 0
    lunch_covers = 0
    afternoon_covers = 0
    dinner_covers = 0
    other_covers = 0

    breakfast_bookings = 0
    lunch_bookings = 0
    afternoon_bookings = 0
    dinner_bookings = 0
    other_bookings = 0

    hotel_guest_covers = 0
    non_hotel_guest_covers = 0
    dbb_covers = 0
    package_covers = 0

    covers_by_source: Dict[str, int] = defaultdict(int)
    covers_by_period: Dict[str, Dict[str, Any]] = {}

    total_party_sizes = []
    party_sizes_by_period: Dict[str, list] = defaultdict(list)

    # Build hotel_booking_numbers mapping
    hotel_booking_numbers: Dict[str, str] = {}  # hotel_booking_number -> resos_id
    bookings_with_hotel_link = 0

    for booking in bookings:
        period = booking.period_type or 'other'
        covers = booking.covers or 0
        source = booking.source or 'unknown'
        opening_hour_id = booking.opening_hour_id
        resos_id = booking.resos_id

        # Count by period
        if period == 'breakfast':
            breakfast_covers += covers
            breakfast_bookings += 1
        elif period == 'lunch':
            lunch_covers += covers
            lunch_bookings += 1
        elif period == 'afternoon':
            afternoon_covers += covers
            afternoon_bookings += 1
        elif period == 'dinner':
            dinner_covers += covers
            dinner_bookings += 1
        else:
            other_covers += covers
            other_bookings += 1

        # Count by source
        covers_by_source[source] += covers

        # Count by period (detailed)
        if opening_hour_id:
            if opening_hour_id not in covers_by_period:
                covers_by_period[opening_hour_id] = {
                    "period_type": period,
                    "covers": 0,
                    "bookings": 0
                }
            covers_by_period[opening_hour_id]["covers"] += covers
            covers_by_period[opening_hour_id]["bookings"] += 1

        # Count business segments
        if booking.is_hotel_guest:
            hotel_guest_covers += covers
        else:
            non_hotel_guest_covers += covers

        if booking.is_dbb:
            dbb_covers += covers
        if booking.is_package:
            package_covers += covers

        # Track party sizes
        if covers > 0:
            total_party_sizes.append(covers)
            party_sizes_by_period[period].append(covers)

        # Build hotel booking numbers mapping
        all_booking_numbers, _ = parse_group_exclude_field(
            booking.group_exclude_field,
            booking.hotel_booking_number
        )

        if all_booking_numbers:
            bookings_with_hotel_link += 1
            for hotel_number in all_booking_numbers:
                hotel_booking_numbers[hotel_number] = resos_id

    # Calculate averages
    avg_party_size = sum(total_party_sizes) / len(total_party_sizes) if total_party_sizes else None

    avg_by_period = {}
    for period, sizes in party_sizes_by_period.items():
        avg_by_period[period] = sum(sizes) / len(sizes) if sizes else None

    total_covers = breakfast_covers + lunch_covers + afternoon_covers + dinner_covers + other_covers
    total_bookings = breakfast_bookings + lunch_bookings + afternoon_bookings + dinner_bookings + other_bookings
    distinct_hotel_bookings = len(hotel_booking_numbers)

    # Upsert stats
    db.execute(
        text("""
            INSERT INTO resos_bookings_stats (
                date,
                breakfast_covers, lunch_covers, afternoon_covers, dinner_covers, other_covers, total_covers,
                breakfast_bookings, lunch_bookings, afternoon_bookings, dinner_bookings, other_bookings, total_bookings,
                covers_by_source, covers_by_period,
                hotel_guest_covers, non_hotel_guest_covers, dbb_covers, package_covers,
                hotel_booking_numbers, distinct_hotel_bookings, bookings_with_hotel_link,
                avg_party_size, avg_party_size_by_period,
                aggregated_at
            ) VALUES (
                :date,
                :breakfast_covers, :lunch_covers, :afternoon_covers, :dinner_covers, :other_covers, :total_covers,
                :breakfast_bookings, :lunch_bookings, :afternoon_bookings, :dinner_bookings, :other_bookings, :total_bookings,
                :covers_by_source, :covers_by_period,
                :hotel_guest_covers, :non_hotel_guest_covers, :dbb_covers, :package_covers,
                :hotel_booking_numbers, :distinct_hotel_bookings, :bookings_with_hotel_link,
                :avg_party_size, :avg_party_size_by_period,
                NOW()
            )
            ON CONFLICT (date) DO UPDATE SET
                breakfast_covers = :breakfast_covers,
                lunch_covers = :lunch_covers,
                afternoon_covers = :afternoon_covers,
                dinner_covers = :dinner_covers,
                other_covers = :other_covers,
                total_covers = :total_covers,
                breakfast_bookings = :breakfast_bookings,
                lunch_bookings = :lunch_bookings,
                afternoon_bookings = :afternoon_bookings,
                dinner_bookings = :dinner_bookings,
                other_bookings = :other_bookings,
                total_bookings = :total_bookings,
                covers_by_source = :covers_by_source,
                covers_by_period = :covers_by_period,
                hotel_guest_covers = :hotel_guest_covers,
                non_hotel_guest_covers = :non_hotel_guest_covers,
                dbb_covers = :dbb_covers,
                package_covers = :package_covers,
                hotel_booking_numbers = :hotel_booking_numbers,
                distinct_hotel_bookings = :distinct_hotel_bookings,
                bookings_with_hotel_link = :bookings_with_hotel_link,
                avg_party_size = :avg_party_size,
                avg_party_size_by_period = :avg_party_size_by_period,
                aggregated_at = NOW()
        """),
        {
            "date": target_date,
            "breakfast_covers": breakfast_covers,
            "lunch_covers": lunch_covers,
            "afternoon_covers": afternoon_covers,
            "dinner_covers": dinner_covers,
            "other_covers": other_covers,
            "total_covers": total_covers,
            "breakfast_bookings": breakfast_bookings,
            "lunch_bookings": lunch_bookings,
            "afternoon_bookings": afternoon_bookings,
            "dinner_bookings": dinner_bookings,
            "other_bookings": other_bookings,
            "total_bookings": total_bookings,
            "covers_by_source": json.dumps(dict(covers_by_source)),
            "covers_by_period": json.dumps(covers_by_period),
            "hotel_guest_covers": hotel_guest_covers,
            "non_hotel_guest_covers": non_hotel_guest_covers,
            "dbb_covers": dbb_covers,
            "package_covers": package_covers,
            "hotel_booking_numbers": json.dumps(hotel_booking_numbers),
            "distinct_hotel_bookings": distinct_hotel_bookings,
            "bookings_with_hotel_link": bookings_with_hotel_link,
            "avg_party_size": avg_party_size,
            "avg_party_size_by_period": json.dumps(avg_by_period)
        }
    )
    db.commit()


async def update_resos_booking_pace(db):
    """
    Update resos_booking_pace table with lead-time snapshots.
    Creates 3 rows per date: total, resident, non_resident
    """
    logger.info("Updating Resos booking pace table...")

    today = date.today()

    # Process dates from -30 to +365 (historical + forecast window)
    from_date = today - timedelta(days=30)
    to_date = today + timedelta(days=365)

    current = from_date
    while current <= to_date:
        # Calculate pace for each type
        for pace_type in ['total', 'resident', 'non_resident']:
            pace_values = {}

            for days_out in PACE_INTERVALS:
                snapshot_date = current - timedelta(days=days_out)

                # Build query based on pace_type
                if pace_type == 'total':
                    # All valid bookings
                    result = db.execute(
                        text("""
                            SELECT COALESCE(SUM(covers), 0) as total_covers
                            FROM resos_bookings_data
                            WHERE booking_date = :target_date
                            AND status IN :valid_statuses
                            AND booking_placed <= :snapshot_date
                        """),
                        {
                            "target_date": current,
                            "valid_statuses": VALID_STATUSES,
                            "snapshot_date": snapshot_date
                        }
                    )
                elif pace_type == 'resident':
                    # Hotel guests only
                    result = db.execute(
                        text("""
                            SELECT COALESCE(SUM(covers), 0) as total_covers
                            FROM resos_bookings_data
                            WHERE booking_date = :target_date
                            AND status IN :valid_statuses
                            AND booking_placed <= :snapshot_date
                            AND is_hotel_guest = true
                        """),
                        {
                            "target_date": current,
                            "valid_statuses": VALID_STATUSES,
                            "snapshot_date": snapshot_date
                        }
                    )
                else:  # non_resident
                    # Non-hotel guests
                    result = db.execute(
                        text("""
                            SELECT COALESCE(SUM(covers), 0) as total_covers
                            FROM resos_bookings_data
                            WHERE booking_date = :target_date
                            AND status IN :valid_statuses
                            AND booking_placed <= :snapshot_date
                            AND (is_hotel_guest = false OR is_hotel_guest IS NULL)
                        """),
                        {
                            "target_date": current,
                            "valid_statuses": VALID_STATUSES,
                            "snapshot_date": snapshot_date
                        }
                    )

                row = result.fetchone()
                pace_values[f"d{days_out}"] = row.total_covers if row else 0

            # Upsert pace record
            columns = ", ".join(pace_values.keys())
            placeholders = ", ".join([f":{k}" for k in pace_values.keys()])
            updates = ", ".join([f"{k} = :{k}" for k in pace_values.keys()])

            db.execute(
                text(f"""
                    INSERT INTO resos_booking_pace (booking_date, pace_type, {columns}, updated_at)
                    VALUES (:booking_date, :pace_type, {placeholders}, NOW())
                    ON CONFLICT (booking_date, pace_type) DO UPDATE SET
                        {updates},
                        updated_at = NOW()
                """),
                {"booking_date": current, "pace_type": pace_type, **pace_values}
            )

        current += timedelta(days=1)

    db.commit()
    logger.info("Resos booking pace table updated (3 types: total, resident, non_resident)")
