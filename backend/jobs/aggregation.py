"""
Aggregation job - calculates daily summaries from raw booking data

Processes dates from aggregation_queue and updates:
- daily_occupancy (from newbook_bookings)
- daily_covers (from resos_bookings)
"""
import json
import logging
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import text
from database import SyncSessionLocal

logger = logging.getLogger(__name__)


async def run_aggregation(source: Optional[str] = None):
    """
    Process pending aggregation queue and update daily summary tables.

    Args:
        source: Optional filter - 'newbook' or 'resos'. If None, processes both.
    """
    logger.info(f"Starting aggregation job (source={source or 'all'})")

    db = next(iter([SyncSessionLocal()]))

    try:
        # Get pending dates from queue
        query = """
            SELECT DISTINCT date, source
            FROM aggregation_queue
            WHERE aggregated_at IS NULL
        """

        if source:
            query += " AND source = :source"

        query += " ORDER BY date"

        result = db.execute(text(query), {"source": source} if source else {})
        pending = result.fetchall()

        if not pending:
            logger.info("No pending dates to aggregate")
            return

        logger.info(f"Found {len(pending)} date/source combinations to aggregate")

        # Group by source
        newbook_dates = [row.date for row in pending if row.source == 'newbook']
        resos_dates = [row.date for row in pending if row.source == 'resos']

        # Process Newbook dates
        if newbook_dates:
            await aggregate_newbook_dates(db, newbook_dates)

        # Process Resos dates
        if resos_dates:
            await aggregate_resos_dates(db, resos_dates)

        # Populate daily_metrics from aggregated data (for forecasting models)
        all_dates = list(set(newbook_dates + resos_dates))
        if all_dates:
            await populate_daily_metrics(db, all_dates)

        logger.info("Aggregation completed successfully")

    except Exception as e:
        logger.error(f"Aggregation failed: {e}")
        raise
    finally:
        db.close()


async def aggregate_newbook_dates(db, dates: List[date]):
    """
    Aggregate newbook_bookings into daily_occupancy for specified dates.

    Room availability is sourced from newbook_occupancy_report table (preferred)
    which provides accurate available rooms accounting for maintenance/offline rooms.
    Falls back to system config total_rooms if no occupancy report data exists.

    Revenue metrics:
    - room_revenue, adr, revpar = NET values (after VAT)
    - agr = Actual Guest Rate (gross rate guest paid, from calculated_amount)
    """
    logger.info(f"Aggregating {len(dates)} Newbook dates")

    # Get fallback total_rooms from system config (used when no occupancy report data)
    result = db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'total_rooms'")
    )
    row = result.fetchone()
    fallback_total_rooms = int(row.config_value) if row and row.config_value else 80

    # Get accommodation VAT rate from config (default 20%)
    result = db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'accommodation_vat_rate'")
    )
    row = result.fetchone()
    accommodation_vat = float(row.config_value) if row and row.config_value else 0.20

    # Statuses that count as "occupied" (case-insensitive check in query)
    # Includes: Confirmed, Unconfirmed, Arrived, Departed, In-House, etc.
    # Excludes: Cancelled, No Show, Quote, Waitlist
    excluded_statuses = "('cancelled', 'no show', 'no_show', 'quote', 'waitlist')"

    # Overflow room category (category_id=5) is used for chargeable no-shows/cancellations
    # and should be excluded from room night counts
    overflow_category_id = '5'

    for d in dates:
        # Get room availability from daily_occupancy (pre-calculated by occupancy report sync)
        # These values account for maintenance/offline rooms
        # Revenue comes from booking data, not occupancy report
        result = db.execute(
            text("""
            SELECT
                total_rooms, available_rooms, maintenance_rooms,
                newbook_occupied, newbook_occupancy_pct
            FROM daily_occupancy
            WHERE date = :date
            """),
            {"date": d}
        )
        existing = result.fetchone()

        # Use existing availability values if present, else fallback to config
        if existing and existing.available_rooms and existing.available_rooms > 0:
            total_rooms = existing.total_rooms
            available_rooms = existing.available_rooms
            maintenance_rooms = existing.maintenance_rooms or 0
            newbook_occupied = existing.newbook_occupied
            newbook_occupancy_pct = float(existing.newbook_occupancy_pct or 0)
        else:
            # No occupancy data yet - fall back to config
            total_rooms = fallback_total_rooms
            available_rooms = fallback_total_rooms  # Assume all rooms available
            maintenance_rooms = 0
            newbook_occupied = None
            newbook_occupancy_pct = None

        # Calculate occupancy stats for this date from booking data
        # A booking is "in house" if: arrival_date <= date < departure_date
        # AND status is not cancelled/no-show/quote/waitlist
        # EXCLUDES overflow room category (used for chargeable no-shows)
        result = db.execute(
            text(f"""
            SELECT
                COUNT(*) as occupied_rooms,
                COALESCE(SUM(total_guests), 0) as total_guests,
                COALESCE(SUM(adults), 0) as total_adults,
                COALESCE(SUM(children), 0) as total_children,
                COALESCE(SUM(infants), 0) as total_infants
            FROM newbook_bookings
            WHERE arrival_date <= :date
              AND departure_date > :date
              AND LOWER(status) NOT IN {excluded_statuses}
              AND (category_id IS NULL OR category_id != :overflow_cat)
            """),
            {"date": d, "overflow_cat": overflow_category_id}
        )
        stats = result.fetchone()

        # Count arrivals for this date (active bookings only, excluding overflow)
        result = db.execute(
            text(f"""
            SELECT COUNT(*) as arrival_count
            FROM newbook_bookings
            WHERE arrival_date = :date
              AND LOWER(status) NOT IN {excluded_statuses}
              AND (category_id IS NULL OR category_id != :overflow_cat)
            """),
            {"date": d, "overflow_cat": overflow_category_id}
        )
        arrivals = result.fetchone()

        # Calculate room revenue, breakfast/dinner allocations from booking_nights
        # charge_amount = room rate (net of inventory items, but includes VAT)
        # calculated_amount = gross rate guest paid (for AGR)
        # GL code matching is done during sync for meal allocations
        # EXCLUDES overflow category (chargeable no-shows are not actual room stays)
        result = db.execute(
            text(f"""
            SELECT
                COALESCE(SUM(bn.charge_amount), 0) as charge_amount_total,
                COALESCE(SUM(bn.calculated_amount), 0) as calculated_amount_total,
                COALESCE(SUM(CASE WHEN bn.breakfast_gross > 0 THEN 1 ELSE 0 END), 0) as breakfast_qty,
                COALESCE(SUM(bn.breakfast_net), 0) as breakfast_value,
                COALESCE(SUM(CASE WHEN bn.dinner_gross > 0 THEN 1 ELSE 0 END), 0) as dinner_qty,
                COALESCE(SUM(bn.dinner_net), 0) as dinner_value
            FROM newbook_booking_nights bn
            JOIN newbook_bookings b ON bn.booking_id = b.id
            WHERE bn.stay_date = :date
              AND LOWER(b.status) NOT IN {excluded_statuses}
              AND (b.category_id IS NULL OR b.category_id != :overflow_cat)
            """),
            {"date": d, "overflow_cat": overflow_category_id}
        )
        revenue_and_meals = result.fetchone()

        # Revenue breakdown by room category (for revenue_by_room_type JSON)
        # EXCLUDES overflow category from breakdown
        result = db.execute(
            text(f"""
            SELECT
                COALESCE(b.category_id, 'unknown') as category_id,
                COUNT(DISTINCT b.id) as rooms,
                COALESCE(SUM(bn.charge_amount), 0) as charge_amount,
                COALESCE(SUM(bn.calculated_amount), 0) as calculated_amount
            FROM newbook_booking_nights bn
            JOIN newbook_bookings b ON bn.booking_id = b.id
            WHERE bn.stay_date = :date
              AND LOWER(b.status) NOT IN {excluded_statuses}
              AND (b.category_id IS NULL OR b.category_id != :overflow_cat)
            GROUP BY b.category_id
            """),
            {"date": d, "overflow_cat": overflow_category_id}
        )
        revenue_by_category_rows = result.fetchall()

        # Booking movement stats - count by status category
        result = db.execute(
            text("""
            SELECT
                COUNT(*) FILTER (WHERE LOWER(status) NOT IN ('cancelled', 'no show', 'no_show', 'quote', 'waitlist')) as total_bookings,
                COUNT(*) FILTER (WHERE LOWER(status) IN ('cancelled')) as cancelled_bookings,
                COUNT(*) FILTER (WHERE LOWER(status) IN ('no show', 'no_show')) as no_show_bookings
            FROM newbook_bookings
            WHERE arrival_date <= :date
              AND departure_date > :date
            """),
            {"date": d}
        )
        movement = result.fetchone()

        # Breakdown by room category (keyed by category_id for stability)
        # EXCLUDES overflow category
        result = db.execute(
            text(f"""
            SELECT
                COALESCE(category_id, 'unknown') as category_id,
                COUNT(*) as rooms,
                COALESCE(SUM(total_guests), 0) as guests,
                COALESCE(SUM(adults), 0) as adults,
                COALESCE(SUM(children), 0) as children,
                COALESCE(SUM(infants), 0) as infants
            FROM newbook_bookings
            WHERE arrival_date <= :date
              AND departure_date > :date
              AND LOWER(status) NOT IN {excluded_statuses}
              AND (category_id IS NULL OR category_id != :overflow_cat)
            GROUP BY category_id
            """),
            {"date": d, "overflow_cat": overflow_category_id}
        )
        room_type_rows = result.fetchall()

        # Keyed by category_id - use room_categories table to get names in UI
        by_room_type = {}
        for row in room_type_rows:
            by_room_type[row.category_id] = {
                "rooms": row.rooms,
                "guests": row.guests,
                "adults": row.adults,
                "children": row.children,
                "infants": row.infants
            }

        occupied_rooms = stats.occupied_rooms or 0
        # Use available_rooms (accounts for maintenance) for accurate occupancy %
        occupancy_pct = (occupied_rooms / available_rooms * 100) if available_rooms > 0 else 0

        # Calculate revenue metrics
        # charge_amount is the room rate (includes VAT), convert to NET
        charge_amount_total = float(revenue_and_meals.charge_amount_total or 0)
        room_revenue = charge_amount_total / (1 + accommodation_vat)  # NET room revenue

        # ADR and RevPAR are NET values
        # ADR uses occupied rooms, RevPAR uses available rooms
        adr = (room_revenue / occupied_rooms) if occupied_rooms > 0 else 0
        revpar = (room_revenue / available_rooms) if available_rooms > 0 else 0

        # AGR (Actual Guest Rate) = gross rate guest paid (from calculated_amount)
        calculated_amount_total = float(revenue_and_meals.calculated_amount_total or 0)
        agr = (calculated_amount_total / occupied_rooms) if occupied_rooms > 0 else 0

        # Build revenue_by_room_type JSON with net revenue, ADR, AGR per category
        revenue_by_room_type = {}
        for row in revenue_by_category_rows:
            cat_charge = float(row.charge_amount or 0)
            cat_calculated = float(row.calculated_amount or 0)
            cat_rooms = row.rooms or 0
            cat_revenue_net = cat_charge / (1 + accommodation_vat)

            revenue_by_room_type[row.category_id] = {
                "rooms": cat_rooms,
                "revenue_net": round(cat_revenue_net, 2),
                "adr_net": round(cat_revenue_net / cat_rooms, 2) if cat_rooms > 0 else 0,
                "agr_total": round(cat_calculated, 2),
                "agr_avg": round(cat_calculated / cat_rooms, 2) if cat_rooms > 0 else 0
            }

        # Upsert into daily_occupancy
        # Revenue comes from booking data (room_revenue, adr, revpar, agr)
        db.execute(
            text("""
            INSERT INTO daily_occupancy (
                date, total_rooms, available_rooms, maintenance_rooms, occupied_rooms, occupancy_pct,
                newbook_occupied, newbook_occupancy_pct,
                total_guests, total_adults, total_children, total_infants,
                arrival_count, total_bookings, cancelled_bookings, no_show_bookings,
                room_revenue, adr, revpar, agr,
                breakfast_allocation_qty, breakfast_allocation_value,
                dinner_allocation_qty, dinner_allocation_value,
                by_room_type, revenue_by_room_type, fetched_at
            ) VALUES (
                :date, :total_rooms, :available_rooms, :maintenance_rooms, :occupied_rooms, :occupancy_pct,
                :newbook_occupied, :newbook_occupancy_pct,
                :total_guests, :total_adults, :total_children, :total_infants,
                :arrival_count, :total_bookings, :cancelled_bookings, :no_show_bookings,
                :room_revenue, :adr, :revpar, :agr,
                :breakfast_qty, :breakfast_value,
                :dinner_qty, :dinner_value,
                :by_room_type, :revenue_by_room_type, NOW()
            )
            ON CONFLICT (date) DO UPDATE SET
                total_rooms = :total_rooms,
                available_rooms = :available_rooms,
                maintenance_rooms = :maintenance_rooms,
                occupied_rooms = :occupied_rooms,
                occupancy_pct = :occupancy_pct,
                newbook_occupied = :newbook_occupied,
                newbook_occupancy_pct = :newbook_occupancy_pct,
                total_guests = :total_guests,
                total_adults = :total_adults,
                total_children = :total_children,
                total_infants = :total_infants,
                arrival_count = :arrival_count,
                total_bookings = :total_bookings,
                cancelled_bookings = :cancelled_bookings,
                no_show_bookings = :no_show_bookings,
                room_revenue = :room_revenue,
                adr = :adr,
                revpar = :revpar,
                agr = :agr,
                breakfast_allocation_qty = :breakfast_qty,
                breakfast_allocation_value = :breakfast_value,
                dinner_allocation_qty = :dinner_qty,
                dinner_allocation_value = :dinner_value,
                by_room_type = :by_room_type,
                revenue_by_room_type = :revenue_by_room_type,
                fetched_at = NOW()
            """),
            {
                "date": d,
                "total_rooms": total_rooms,
                "available_rooms": available_rooms,
                "maintenance_rooms": maintenance_rooms,
                "occupied_rooms": occupied_rooms,
                "occupancy_pct": round(occupancy_pct, 2),
                "newbook_occupied": newbook_occupied,
                "newbook_occupancy_pct": round(newbook_occupancy_pct, 2) if newbook_occupancy_pct is not None else None,
                "total_guests": stats.total_guests,
                "total_adults": stats.total_adults,
                "total_children": stats.total_children,
                "total_infants": stats.total_infants,
                "arrival_count": arrivals.arrival_count or 0,
                "total_bookings": movement.total_bookings or 0,
                "cancelled_bookings": movement.cancelled_bookings or 0,
                "no_show_bookings": movement.no_show_bookings or 0,
                "room_revenue": round(room_revenue, 2),
                "adr": round(adr, 2),
                "revpar": round(revpar, 2),
                "agr": round(agr, 2),
                "breakfast_qty": revenue_and_meals.breakfast_qty or 0,
                "breakfast_value": revenue_and_meals.breakfast_value or 0,
                "dinner_qty": revenue_and_meals.dinner_qty or 0,
                "dinner_value": revenue_and_meals.dinner_value or 0,
                "by_room_type": json.dumps(by_room_type),
                "revenue_by_room_type": json.dumps(revenue_by_room_type)
            }
        )

        # Mark queue entries as processed
        db.execute(
            text("""
            UPDATE aggregation_queue
            SET aggregated_at = NOW()
            WHERE date = :date AND source = 'newbook' AND aggregated_at IS NULL
            """),
            {"date": d}
        )

    db.commit()
    logger.info(f"Aggregated {len(dates)} Newbook dates into daily_occupancy")


def load_opening_hours_mappings(db) -> dict:
    """
    Load opening hours to period type mappings from resos_opening_hours_mapping table.

    Returns dict: {opening_hour_id: period_type}
    Where period_type is one of: 'lunch', 'afternoon', 'dinner', 'ignore'
    """
    result = db.execute(text("""
        SELECT opening_hour_id, period_type
        FROM resos_opening_hours_mapping
        WHERE period_type != 'ignore'
    """))
    mappings = {}
    for row in result.fetchall():
        mappings[row.opening_hour_id] = row.period_type
    return mappings


async def aggregate_resos_dates(db, dates: List[date]):
    """
    Aggregate resos_bookings into daily_covers for specified dates.

    Uses opening hours mapping to determine service periods (lunch, afternoon, dinner).
    Falls back to time-based logic if no mappings configured.
    """
    logger.info(f"Aggregating {len(dates)} Resos dates")

    # Load opening hours to period type mappings
    oh_mappings = load_opening_hours_mappings(db)
    use_oh_mapping = len(oh_mappings) > 0
    if use_oh_mapping:
        logger.info(f"Using {len(oh_mappings)} opening hours mappings for period detection")
    else:
        logger.info("No opening hours mappings configured, using time-based period detection")

    # Status values that count as "active" (case-insensitive check in query)
    # Excludes: Cancelled, No Show
    excluded_statuses = "('cancelled', 'no show', 'no_show')"

    for d in dates:
        # Get hotel occupancy data for this date (for dining rate calculation)
        occ_result = db.execute(
            text("""
            SELECT total_guests FROM daily_occupancy WHERE date = :date
            """),
            {"date": d}
        )
        occ_row = occ_result.fetchone()
        total_hotel_residents = occ_row.total_guests if occ_row and occ_row.total_guests else None

        # Calculate covers by service period
        # If we have opening hours mappings, aggregate by mapped period_type
        # Otherwise fall back to simple time-based logic
        for period in ['lunch', 'afternoon', 'dinner']:
            if use_oh_mapping:
                # Get the opening_hour_ids that map to this period
                period_oh_ids = [oh_id for oh_id, pt in oh_mappings.items() if pt == period]

                if not period_oh_ids:
                    # No mappings for this period, skip
                    continue

                # Build SQL placeholders for opening_hour_ids
                oh_placeholders = ", ".join([f":oh_{i}" for i in range(len(period_oh_ids))])
                oh_params = {f"oh_{i}": oh_id for i, oh_id in enumerate(period_oh_ids)}
                oh_params["date"] = d

                period_filter = f"opening_hour_id IN ({oh_placeholders})"

                # Get active booking stats
                result = db.execute(
                    text(f"""
                    SELECT
                        COUNT(*) as total_bookings,
                        COALESCE(SUM(covers), 0) as total_covers,
                        COALESCE(SUM(CASE WHEN is_hotel_guest THEN covers ELSE 0 END), 0) as hotel_guest_covers,
                        COALESCE(SUM(CASE WHEN NOT is_hotel_guest OR is_hotel_guest IS NULL THEN covers ELSE 0 END), 0) as external_covers,
                        COALESCE(SUM(CASE WHEN is_dbb THEN covers ELSE 0 END), 0) as dbb_covers,
                        COALESCE(SUM(CASE WHEN is_package THEN covers ELSE 0 END), 0) as package_covers
                    FROM resos_bookings
                    WHERE booking_date = :date
                      AND {period_filter}
                      AND LOWER(status) NOT IN {excluded_statuses}
                    """),
                    oh_params
                )
                stats = result.fetchone()

                # Get cancelled/no-show stats separately
                result = db.execute(
                    text(f"""
                    SELECT
                        COUNT(*) FILTER (WHERE LOWER(status) = 'cancelled') as cancelled_bookings,
                        COALESCE(SUM(covers) FILTER (WHERE LOWER(status) = 'cancelled'), 0) as cancelled_covers,
                        COUNT(*) FILTER (WHERE LOWER(status) IN ('no show', 'no_show')) as no_show_bookings,
                        COALESCE(SUM(covers) FILTER (WHERE LOWER(status) IN ('no show', 'no_show')), 0) as no_show_covers
                    FROM resos_bookings
                    WHERE booking_date = :date
                      AND {period_filter}
                    """),
                    oh_params
                )
                movement = result.fetchone()

                # Get source breakdown as JSON
                result = db.execute(
                    text(f"""
                    SELECT
                        COALESCE(source, 'unknown') as source,
                        COUNT(*) as bookings,
                        COALESCE(SUM(covers), 0) as covers
                    FROM resos_bookings
                    WHERE booking_date = :date
                      AND {period_filter}
                      AND LOWER(status) NOT IN {excluded_statuses}
                    GROUP BY source
                    """),
                    oh_params
                )
                source_rows = result.fetchall()
                by_source = {row.source: {"bookings": row.bookings, "covers": row.covers} for row in source_rows}

            else:
                # Fallback: time-based logic (skip afternoon if using fallback)
                if period == 'afternoon':
                    continue

                if period == 'lunch':
                    time_filter = "booking_time < '15:00'"
                else:  # dinner
                    time_filter = "booking_time >= '15:00'"

                # Get active booking stats
                result = db.execute(
                    text(f"""
                    SELECT
                        COUNT(*) as total_bookings,
                        COALESCE(SUM(covers), 0) as total_covers,
                        COALESCE(SUM(CASE WHEN is_hotel_guest THEN covers ELSE 0 END), 0) as hotel_guest_covers,
                        COALESCE(SUM(CASE WHEN NOT is_hotel_guest OR is_hotel_guest IS NULL THEN covers ELSE 0 END), 0) as external_covers,
                        COALESCE(SUM(CASE WHEN is_dbb THEN covers ELSE 0 END), 0) as dbb_covers,
                        COALESCE(SUM(CASE WHEN is_package THEN covers ELSE 0 END), 0) as package_covers
                    FROM resos_bookings
                    WHERE booking_date = :date
                      AND {time_filter}
                      AND LOWER(status) NOT IN {excluded_statuses}
                    """),
                    {"date": d}
                )
                stats = result.fetchone()

                # Get cancelled/no-show stats separately
                result = db.execute(
                    text(f"""
                    SELECT
                        COUNT(*) FILTER (WHERE LOWER(status) = 'cancelled') as cancelled_bookings,
                        COALESCE(SUM(covers) FILTER (WHERE LOWER(status) = 'cancelled'), 0) as cancelled_covers,
                        COUNT(*) FILTER (WHERE LOWER(status) IN ('no show', 'no_show')) as no_show_bookings,
                        COALESCE(SUM(covers) FILTER (WHERE LOWER(status) IN ('no show', 'no_show')), 0) as no_show_covers
                    FROM resos_bookings
                    WHERE booking_date = :date
                      AND {time_filter}
                    """),
                    {"date": d}
                )
                movement = result.fetchone()

                # Get source breakdown as JSON
                result = db.execute(
                    text(f"""
                    SELECT
                        COALESCE(source, 'unknown') as source,
                        COUNT(*) as bookings,
                        COALESCE(SUM(covers), 0) as covers
                    FROM resos_bookings
                    WHERE booking_date = :date
                      AND {time_filter}
                      AND LOWER(status) NOT IN {excluded_statuses}
                    GROUP BY source
                    """),
                    {"date": d}
                )
                source_rows = result.fetchall()
                by_source = {row.source: {"bookings": row.bookings, "covers": row.covers} for row in source_rows}

            total_bookings = stats.total_bookings or 0
            total_covers = stats.total_covers or 0
            avg_party_size = (total_covers / total_bookings) if total_bookings > 0 else 0
            hotel_guest_covers = stats.hotel_guest_covers or 0

            # Calculate hotel guest dining rate (% of hotel residents who dined this period)
            # This enables forecasting: forecast occupancy → apply dining rate → predict hotel guest covers
            hotel_guest_dining_rate = None
            if total_hotel_residents and total_hotel_residents > 0 and hotel_guest_covers > 0:
                hotel_guest_dining_rate = round((hotel_guest_covers / total_hotel_residents) * 100, 2)

            # Upsert into daily_covers
            db.execute(
                text("""
                INSERT INTO daily_covers (
                    date, service_period, total_bookings, total_covers, avg_party_size,
                    hotel_guest_covers, external_covers, dbb_covers, package_covers,
                    total_hotel_residents, hotel_guest_dining_rate,
                    cancelled_bookings, cancelled_covers, no_show_bookings, no_show_covers,
                    by_source, fetched_at
                ) VALUES (
                    :date, :service_period, :total_bookings, :total_covers, :avg_party_size,
                    :hotel_guest_covers, :external_covers, :dbb_covers, :package_covers,
                    :total_hotel_residents, :hotel_guest_dining_rate,
                    :cancelled_bookings, :cancelled_covers, :no_show_bookings, :no_show_covers,
                    :by_source, NOW()
                )
                ON CONFLICT (date, service_period) DO UPDATE SET
                    total_bookings = :total_bookings,
                    total_covers = :total_covers,
                    avg_party_size = :avg_party_size,
                    hotel_guest_covers = :hotel_guest_covers,
                    external_covers = :external_covers,
                    dbb_covers = :dbb_covers,
                    package_covers = :package_covers,
                    total_hotel_residents = :total_hotel_residents,
                    hotel_guest_dining_rate = :hotel_guest_dining_rate,
                    cancelled_bookings = :cancelled_bookings,
                    cancelled_covers = :cancelled_covers,
                    no_show_bookings = :no_show_bookings,
                    no_show_covers = :no_show_covers,
                    by_source = :by_source,
                    fetched_at = NOW()
                """),
                {
                    "date": d,
                    "service_period": period,
                    "total_bookings": total_bookings,
                    "total_covers": total_covers,
                    "avg_party_size": round(avg_party_size, 2),
                    "hotel_guest_covers": hotel_guest_covers,
                    "external_covers": stats.external_covers or 0,
                    "dbb_covers": stats.dbb_covers or 0,
                    "package_covers": stats.package_covers or 0,
                    "total_hotel_residents": total_hotel_residents,
                    "hotel_guest_dining_rate": hotel_guest_dining_rate,
                    "cancelled_bookings": movement.cancelled_bookings or 0,
                    "cancelled_covers": movement.cancelled_covers or 0,
                    "no_show_bookings": movement.no_show_bookings or 0,
                    "no_show_covers": movement.no_show_covers or 0,
                    "by_source": json.dumps(by_source)
                }
            )

        # Mark queue entries as processed
        db.execute(
            text("""
            UPDATE aggregation_queue
            SET aggregated_at = NOW()
            WHERE date = :date AND source = 'resos' AND aggregated_at IS NULL
            """),
            {"date": d}
        )

    db.commit()
    logger.info(f"Aggregated {len(dates)} Resos dates into daily_covers")


async def populate_daily_metrics(db, dates: List[date]):
    """
    Populate daily_metrics table from daily_occupancy and daily_covers.
    This table is the source for forecasting models.
    """
    logger.info(f"Populating daily_metrics for {len(dates)} dates")

    for d in dates:
        # Get daily_occupancy data
        result = db.execute(
            text("""
            SELECT
                occupied_rooms, total_guests, total_adults, total_children,
                arrival_count, occupancy_pct, adr, revpar,
                breakfast_allocation_qty, dinner_allocation_qty,
                room_revenue, available_rooms
            FROM daily_occupancy
            WHERE date = :date
            """),
            {"date": d}
        )
        occupancy = result.fetchone()

        # Get daily_covers data (lunch and dinner)
        result = db.execute(
            text("""
            SELECT
                service_period, total_bookings, total_covers, avg_party_size
            FROM daily_covers
            WHERE date = :date
            """),
            {"date": d}
        )
        covers_rows = result.fetchall()

        # Build covers data by period
        covers_data = {}
        for row in covers_rows:
            covers_data[row.service_period] = {
                "bookings": row.total_bookings,
                "covers": row.total_covers,
                "party_size": float(row.avg_party_size or 0)
            }

        # Define metrics to populate
        metrics_to_insert = []

        if occupancy:
            # Hotel metrics
            metrics_to_insert.extend([
                ("hotel_room_nights", occupancy.occupied_rooms, "newbook"),
                ("hotel_occupancy_pct", float(occupancy.occupancy_pct or 0), "newbook"),
                ("hotel_guests", occupancy.total_guests, "newbook"),
                ("hotel_arrivals", occupancy.arrival_count, "newbook"),
                ("hotel_adr", float(occupancy.adr or 0), "newbook"),
                ("hotel_revpar", float(occupancy.revpar or 0), "newbook"),
                ("hotel_breakfast_qty", occupancy.breakfast_allocation_qty, "newbook"),
                ("hotel_dinner_qty", occupancy.dinner_allocation_qty, "newbook"),
                ("revenue_rooms", float(occupancy.room_revenue or 0), "newbook"),
            ])

        # Restaurant metrics - lunch
        if "lunch" in covers_data:
            lunch = covers_data["lunch"]
            metrics_to_insert.extend([
                ("resos_lunch_bookings", lunch["bookings"], "resos"),
                ("resos_lunch_covers", lunch["covers"], "resos"),
                ("resos_lunch_party_size", lunch["party_size"], "resos"),
            ])

        # Restaurant metrics - dinner
        if "dinner" in covers_data:
            dinner = covers_data["dinner"]
            metrics_to_insert.extend([
                ("resos_dinner_bookings", dinner["bookings"], "resos"),
                ("resos_dinner_covers", dinner["covers"], "resos"),
                ("resos_dinner_party_size", dinner["party_size"], "resos"),
            ])

        # Insert/update all metrics
        for metric_code, actual_value, source in metrics_to_insert:
            if actual_value is not None:
                db.execute(
                    text("""
                    INSERT INTO daily_metrics (date, metric_code, actual_value, source, calculated_at)
                    VALUES (:date, :metric_code, :actual_value, :source, NOW())
                    ON CONFLICT (date, metric_code) DO UPDATE SET
                        actual_value = :actual_value,
                        source = :source,
                        calculated_at = NOW()
                    """),
                    {
                        "date": d,
                        "metric_code": metric_code,
                        "actual_value": actual_value,
                        "source": source
                    }
                )

    db.commit()
    logger.info(f"Populated daily_metrics for {len(dates)} dates")
