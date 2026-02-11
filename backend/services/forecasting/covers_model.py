"""
Restaurant Covers Forecast Model

Forecasts restaurant covers based on:
- Breakfast: Previous night's hotel occupancy (guests expected at breakfast)
- Lunch: OTB bookings + non-resident pickup based on lead time
- Dinner: OTB bookings split by hotel guest/non-resident + pickup for each segment

Key segments:
- Resident (hotel guest): Based on hotel occupancy, booking patterns, DBB packages
- Non-resident: Based on historical pickup patterns at lead time
"""
import logging
import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.forecasting.pickup_v2_model import forecast_rooms_for_date, get_prior_year_date as get_py_date

logger = logging.getLogger(__name__)

# Valid booking statuses for counting
VALID_STATUSES = ('approved', 'arrived', 'seated', 'left')


async def get_hotel_bookings_with_dinner_reservation(
    db: AsyncSession,
    target_date: date
) -> Dict[str, int]:
    """
    Get actual count of hotel bookings that have dinner reservations for a date.

    Queries resos_bookings_data to find distinct hotel_booking_numbers
    that have dinner reservations, then compares to total hotel bookings.

    Returns:
        {
            "rooms_with_dinner": int,  # Hotel bookings with dinner reservation
            "total_hotel_rooms": int,   # Total hotel bookings for this date
            "rooms_without_dinner": int # Difference
        }
    """
    # Count distinct hotel bookings with dinner reservations
    result = await db.execute(
        text("""
            SELECT COUNT(DISTINCT hotel_booking_number) as rooms_with_dinner
            FROM resos_bookings_data
            WHERE booking_date = :target_date
            AND is_hotel_guest = true
            AND period_type = 'dinner'
            AND hotel_booking_number IS NOT NULL
            AND hotel_booking_number != ''
            AND status IN ('approved', 'arrived', 'seated', 'left')
        """),
        {"target_date": target_date}
    )
    row = result.fetchone()
    rooms_with_dinner = row.rooms_with_dinner if row else 0

    # Get total hotel bookings from stats
    result = await db.execute(
        text("""
            SELECT COALESCE(booking_count, 0) as total_rooms
            FROM newbook_bookings_stats
            WHERE date = :target_date
        """),
        {"target_date": target_date}
    )
    row = result.fetchone()
    total_hotel_rooms = row.total_rooms if row else 0

    rooms_without_dinner = max(0, total_hotel_rooms - rooms_with_dinner)

    return {
        "rooms_with_dinner": rooms_with_dinner,
        "total_hotel_rooms": total_hotel_rooms,
        "rooms_without_dinner": rooms_without_dinner,
    }


def get_prior_year_date(target_date: date) -> date:
    """
    Get prior year date with 364-day offset for day-of-week alignment.
    52 weeks = 364 days, so Monday aligns with Monday.
    """
    return target_date - timedelta(days=364)


async def get_hotel_occupancy_for_date(db: AsyncSession, stay_date: date) -> Dict[str, Any]:
    """
    Get hotel room occupancy for a specific date from aggregated stats.
    Returns occupied rooms, total capacity, and occupancy percentage.
    Uses newbook_bookings_stats which is pre-aggregated with is_included filtering.
    """
    # Query from aggregated stats table - more reliable and already filtered
    result = await db.execute(
        text("""
            SELECT
                COALESCE(booking_count, 0) as room_count,
                COALESCE(guests_count, 0) as guest_count,
                COALESCE(bookable_count, 0) as total_rooms,
                COALESCE(bookable_occupancy_pct, 0) as occupancy_pct
            FROM newbook_bookings_stats
            WHERE date = :stay_date
        """),
        {"stay_date": stay_date}
    )
    row = result.fetchone()

    if row:
        return {
            "occupied_rooms": row.room_count,
            "total_rooms": row.total_rooms,
            "occupancy_pct": round(float(row.occupancy_pct), 1) if row.occupancy_pct else 0,
            "guests": row.guest_count
        }

    # No stats for this date - return empty
    return {"occupied_rooms": 0, "total_rooms": 0, "occupancy_pct": 0, "guests": 0}


async def get_resos_covers_for_date(
    db: AsyncSession,
    target_date: date,
    period_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get restaurant booking covers for a specific date from aggregated stats table.
    Returns covers by period (breakfast, lunch, dinner, etc.)
    """
    # Query from aggregated stats table - more efficient and reliable
    result = await db.execute(
        text("""
            SELECT
                COALESCE(breakfast_covers, 0) as breakfast_covers,
                COALESCE(lunch_covers, 0) as lunch_covers,
                COALESCE(afternoon_covers, 0) as afternoon_covers,
                COALESCE(dinner_covers, 0) as dinner_covers,
                COALESCE(other_covers, 0) as other_covers,
                COALESCE(total_covers, 0) as total_covers,
                COALESCE(hotel_guest_covers, 0) as hotel_guest_covers,
                COALESCE(non_hotel_guest_covers, 0) as non_hotel_guest_covers,
                COALESCE(dbb_covers, 0) as dbb_covers,
                COALESCE(total_bookings, 0) as total_bookings
            FROM resos_bookings_stats
            WHERE date = :target_date
        """),
        {"target_date": target_date}
    )
    row = result.fetchone()

    if not row:
        # No data for this date - return empty structure
        return {
            "breakfast": {"total_covers": 0, "booking_count": 0, "resident_covers": 0, "non_resident_covers": 0, "dbb_covers": 0},
            "lunch": {"total_covers": 0, "booking_count": 0, "resident_covers": 0, "non_resident_covers": 0, "dbb_covers": 0},
            "dinner": {"total_covers": 0, "booking_count": 0, "resident_covers": 0, "non_resident_covers": 0, "dbb_covers": 0},
        }

    # Calculate resident/non-resident split proportionally for each period
    # (stats table has overall split but not per-period, so we estimate based on ratio)
    total = row.total_covers or 1  # Avoid division by zero
    hotel_ratio = row.hotel_guest_covers / total if total > 0 else 0
    non_hotel_ratio = row.non_hotel_guest_covers / total if total > 0 else 0

    covers_by_period = {
        "breakfast": {
            "total_covers": row.breakfast_covers,
            "booking_count": 0,  # Not tracked per period in stats
            "resident_covers": int(row.breakfast_covers * hotel_ratio),
            "non_resident_covers": int(row.breakfast_covers * non_hotel_ratio),
            "dbb_covers": 0
        },
        "lunch": {
            "total_covers": row.lunch_covers,
            "booking_count": 0,
            "resident_covers": int(row.lunch_covers * hotel_ratio),
            "non_resident_covers": int(row.lunch_covers * non_hotel_ratio),
            "dbb_covers": 0
        },
        "dinner": {
            "total_covers": row.dinner_covers,
            "booking_count": 0,
            "resident_covers": int(row.dinner_covers * hotel_ratio),
            "non_resident_covers": int(row.dinner_covers * non_hotel_ratio),
            "dbb_covers": row.dbb_covers
        },
    }

    return covers_by_period


async def get_historical_breakfast_rate(db: AsyncSession, lookback_days: int = 90) -> float:
    """
    Calculate historical breakfast attendance rate as covers per occupied room.
    Uses past data to determine typical breakfast covers per hotel room.
    Uses aggregated stats tables for reliability.
    """
    # Join resos stats with newbook stats to get breakfast covers and occupancy
    result = await db.execute(
        text("""
            SELECT
                SUM(rbs.breakfast_covers) as total_breakfast,
                SUM(nbs.booking_count) as total_room_nights
            FROM resos_bookings_stats rbs
            JOIN newbook_bookings_stats nbs ON rbs.date = nbs.date
            WHERE rbs.date >= CURRENT_DATE - CAST(:lookback_days AS INTEGER)
            AND rbs.date < CURRENT_DATE
            AND rbs.breakfast_covers > 0
            AND nbs.booking_count > 0
        """),
        {"lookback_days": lookback_days}
    )
    row = result.fetchone()

    if row and row.total_room_nights and row.total_room_nights > 0:
        # Calculate covers per room night
        rate = float(row.total_breakfast) / float(row.total_room_nights)
        return rate

    # Default: assume 1.8 covers per room (average party size for breakfast)
    return 1.8


async def get_lunch_pickup_by_lead_time(
    db: AsyncSession,
    target_date: date,
    lead_days: int,
    lookback_weeks: int = 8
) -> int:
    """
    Get the median pickup COUNT for lunch at a given lead time for the same DOW.

    Pickup = final_covers - otb_at_lead
    This tells us how many covers typically come in AFTER this lead time.

    More stable than ratio-based approach because it doesn't inflate
    when current OTB is higher than historical OTB.

    Args:
        db: Database session
        target_date: Date we're forecasting (to get DOW)
        lead_days: Days until the target date
        lookback_weeks: Weeks of history to use

    Returns:
        Median pickup count (integer), or 0 if no data
    """
    # Get day of week - convert Python (0=Mon) to PostgreSQL (0=Sun, 1=Mon...6=Sat)
    python_dow = target_date.weekday()
    pg_dow = (python_dow + 1) % 7

    # Determine which pace column to use based on lead days
    if lead_days <= 0:
        return 0  # No pickup for past dates
    elif lead_days <= 30:
        pace_col = f"d{lead_days}"
    elif lead_days <= 177:
        # Weekly intervals - find closest
        weekly_cols = [37, 44, 51, 58, 65, 72, 79, 86, 93, 100, 107, 114, 121, 128, 135, 142, 149, 156, 163, 170, 177]
        pace_col = f"d{min(weekly_cols, key=lambda x: abs(x - lead_days))}"
    else:
        pace_col = "d177"  # Cap at max tracked

    # Query pace data for same DOW to calculate pickup counts
    # pace_type 'total' gives us overall covers
    result = await db.execute(
        text(f"""
            SELECT
                COALESCE({pace_col}, 0) as otb_at_lead,
                COALESCE(d0, 0) as final_covers
            FROM resos_booking_pace
            WHERE EXTRACT(DOW FROM booking_date) = :dow
            AND booking_date >= CURRENT_DATE - CAST(:lookback_days AS INTEGER)
            AND booking_date < CURRENT_DATE
            AND d0 > 0
            AND pace_type = 'total'
            ORDER BY booking_date DESC
            LIMIT :max_weeks
        """),
        {
            "dow": pg_dow,
            "lookback_days": lookback_weeks * 7,
            "max_weeks": lookback_weeks
        }
    )
    rows = result.fetchall()

    if not rows:
        # No pace data - return 0 (no pickup estimate available)
        return 0

    # Calculate pickup counts for each historical day
    pickups = []
    for row in rows:
        otb_at_lead = row.otb_at_lead or 0
        final = row.final_covers or 0
        # Pickup = how many came in after this lead time
        pickup = max(0, final - otb_at_lead)  # Floor at 0 (cancellations shouldn't give negative)
        pickups.append(pickup)

    if not pickups:
        return 0

    # Calculate median pickup count
    pickups_sorted = sorted(pickups)
    n = len(pickups_sorted)
    if n % 2 == 0:
        median = (pickups_sorted[n // 2 - 1] + pickups_sorted[n // 2]) / 2
    else:
        median = pickups_sorted[n // 2]

    return math.ceil(median)  # Round up


async def get_dinner_non_resident_pickup_by_lead_time(
    db: AsyncSession,
    target_date: date,
    lead_days: int,
    lookback_weeks: int = 8
) -> int:
    """
    Get median pickup count for non-resident dinner at a given lead time.
    Same logic as lunch - straight pickup count based on historical pace data.
    """
    python_dow = target_date.weekday()
    pg_dow = (python_dow + 1) % 7

    if lead_days <= 0:
        return 0
    elif lead_days <= 30:
        pace_col = f"d{lead_days}"
    elif lead_days <= 177:
        weekly_cols = [37, 44, 51, 58, 65, 72, 79, 86, 93, 100, 107, 114, 121, 128, 135, 142, 149, 156, 163, 170, 177]
        pace_col = f"d{min(weekly_cols, key=lambda x: abs(x - lead_days))}"
    else:
        pace_col = "d177"

    # Query pace data for non_resident type
    result = await db.execute(
        text(f"""
            SELECT
                COALESCE({pace_col}, 0) as otb_at_lead,
                COALESCE(d0, 0) as final_covers
            FROM resos_booking_pace
            WHERE EXTRACT(DOW FROM booking_date) = :dow
            AND booking_date >= CURRENT_DATE - CAST(:lookback_days AS INTEGER)
            AND booking_date < CURRENT_DATE
            AND d0 > 0
            AND pace_type = 'non_resident'
            ORDER BY booking_date DESC
            LIMIT :max_weeks
        """),
        {
            "dow": pg_dow,
            "lookback_days": lookback_weeks * 7,
            "max_weeks": lookback_weeks
        }
    )
    rows = result.fetchall()

    if not rows:
        return 0

    pickups = []
    for row in rows:
        otb_at_lead = row.otb_at_lead or 0
        final = row.final_covers or 0
        pickup = max(0, final - otb_at_lead)
        pickups.append(pickup)

    if not pickups:
        return 0

    pickups_sorted = sorted(pickups)
    n = len(pickups_sorted)
    if n % 2 == 0:
        median = (pickups_sorted[n // 2 - 1] + pickups_sorted[n // 2]) / 2
    else:
        median = pickups_sorted[n // 2]

    return math.ceil(median)


async def get_resident_dining_rate(
    db: AsyncSession,
    target_date: date,
    lookback_weeks: int = 4
) -> float:
    """
    Calculate what % of hotel guests typically dine at the restaurant (resident covers).

    Simple approach: resident_covers / hotel_guests for same DOW over last N weeks.
    Returns median rate to apply to forecasted hotel guests.

    Args:
        db: Database session
        target_date: Date we're forecasting (to get DOW)
        lookback_weeks: Weeks of history to analyze

    Returns:
        Median dining rate (0.0 to 1.0)
    """
    python_dow = target_date.weekday()
    pg_dow = (python_dow + 1) % 7

    # Query resident covers and hotel guests for same DOW
    result = await db.execute(
        text("""
            SELECT
                nbs.date,
                COALESCE(nbs.guests_count, 0) as hotel_guests,
                COALESCE(rbs.hotel_guest_covers, 0) as resident_covers
            FROM newbook_bookings_stats nbs
            JOIN resos_bookings_stats rbs ON nbs.date = rbs.date
            WHERE EXTRACT(DOW FROM nbs.date) = :dow
            AND nbs.date >= CURRENT_DATE - CAST(:lookback_days AS INTEGER)
            AND nbs.date < CURRENT_DATE
            AND nbs.guests_count > 0
            ORDER BY nbs.date DESC
            LIMIT :max_weeks
        """),
        {
            "dow": pg_dow,
            "lookback_days": lookback_weeks * 7,
            "max_weeks": lookback_weeks
        }
    )
    rows = result.fetchall()

    if not rows:
        return 0.4  # Default 40% if no data

    # Calculate dining rate for each week
    dining_rates = []
    for row in rows:
        if row.hotel_guests > 0:
            rate = min(1.0, row.resident_covers / row.hotel_guests)
            dining_rates.append(rate)

    if not dining_rates:
        return 0.4

    # Return median
    sorted_rates = sorted(dining_rates)
    n = len(sorted_rates)
    if n % 2 == 0:
        return (sorted_rates[n // 2 - 1] + sorted_rates[n // 2]) / 2
    return sorted_rates[n // 2]


async def get_historical_pickup_by_lead_time(
    db: AsyncSession,
    period_type: str,
    is_resident: bool,
    lead_days: int,
    lookback_weeks: int = 12
) -> Dict[str, float]:
    """
    Calculate historical pickup patterns for a period/segment at a given lead time.
    Returns average pickup and pickup rate compared to final.
    """
    # Get column name for this lead time
    column = f"d{lead_days}" if lead_days <= 30 else f"d{lead_days}"  # Use same format for all

    # For lead times with pace data, use pace table
    pace_type = 'resident' if is_resident else 'non_resident'

    if lead_days <= 365:  # We have pace columns up to d365
        result = await db.execute(
            text(f"""
                SELECT
                    AVG(COALESCE({column}, 0)) as avg_at_lead,
                    AVG(COALESCE(d0, 0)) as avg_final
                FROM resos_booking_pace
                WHERE pace_type = :pace_type
                AND booking_date >= CURRENT_DATE - CAST(:lookback_days AS INTEGER)
                AND booking_date < CURRENT_DATE
            """),
            {"pace_type": pace_type, "lookback_days": lookback_weeks * 7}
        )
    else:
        # Use aggregated stats table for period-specific analysis
        result = await db.execute(
            text("""
                SELECT
                    AVG(CASE WHEN :is_resident THEN hotel_guest_covers ELSE non_hotel_guest_covers END) as avg_covers
                FROM resos_bookings_stats
                WHERE date >= CURRENT_DATE - CAST(:lookback_days AS INTEGER)
                AND date < CURRENT_DATE
            """),
            {"is_resident": is_resident, "lookback_days": lookback_weeks * 7}
        )

    row = result.fetchone()

    return {
        "avg_at_lead": row.avg_at_lead if row and row.avg_at_lead else 0,
        "avg_final": row.avg_final if row and row.avg_final else 0
    }


async def forecast_covers_for_date(
    db: AsyncSession,
    target_date: date,
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Generate covers forecast for a specific date.

    Returns breakdown by period and segment:
    - Breakfast: Based on previous night's occupancy
    - Lunch: OTB + non-resident pickup
    - Dinner: OTB (resident + non-resident) + pickup for each
    """
    today = date.today()
    lead_days = (target_date - today).days
    prior_year_date = get_prior_year_date(target_date)

    # Get current OTB covers
    current_covers = await get_resos_covers_for_date(db, target_date)

    # Get prior year covers
    prior_covers = await get_resos_covers_for_date(db, prior_year_date)

    # Get hotel occupancy for the night before (for breakfast)
    night_before = target_date - timedelta(days=1)
    prior_year_night_before = get_prior_year_date(night_before)

    # Get current hotel OTB for night before
    hotel_otb = await get_hotel_occupancy_for_date(db, night_before)
    # Get prior year hotel occupancy for night before (tells us expected final)
    hotel_prior = await get_hotel_occupancy_for_date(db, prior_year_night_before)

    # Get breakfast rate (covers per room)
    breakfast_rate = await get_historical_breakfast_rate(db)

    # Calculate forecasts by period
    result = {
        "date": target_date.isoformat(),
        "day_of_week": target_date.strftime("%a"),
        "lead_days": lead_days,
        "prior_year_date": prior_year_date.isoformat(),
    }

    # ============ BREAKFAST ============
    # Breakfast = hotel guests from night before (guests eat breakfast, not rooms)
    # Past: use actual hotel guest count
    # Future: OTB guests + pickup from pickupv2 hotel forecast

    hotel_guests_otb = hotel_otb["guests"]
    hotel_rooms_otb = hotel_otb["occupied_rooms"]
    hotel_guests_prior = hotel_prior["guests"]
    hotel_rooms_prior = hotel_prior["occupied_rooms"]

    # Calculate guests per room ratio for converting room forecast to guests
    # Use prior year ratio (more stable/representative of final state) with fallbacks
    if hotel_rooms_prior > 0:
        guests_per_room = hotel_guests_prior / hotel_rooms_prior
    elif hotel_rooms_otb > 0:
        guests_per_room = hotel_guests_otb / hotel_rooms_otb
    else:
        guests_per_room = 1.8  # Default fallback

    breakfast_calc = None
    if lead_days <= 0:
        # PAST: Use actual hotel guest count
        breakfast_otb = hotel_guests_otb
        breakfast_pickup = 0
        breakfast_forecast = breakfast_otb
    else:
        # FUTURE: Use pickupv2 model for room forecast
        breakfast_otb = hotel_guests_otb

        # Get pickupv2 room forecast for the night before
        # (night_before lead_days = lead_days for target_date since breakfast is next morning)
        night_before_lead_days = lead_days - 1  # Night before has 1 less lead day
        pickup_rooms = 0
        try:
            pickupv2_forecast = await forecast_rooms_for_date(
                db,
                night_before,
                night_before_lead_days,
                prior_year_night_before,
                'hotel_room_nights'
            )
            if pickupv2_forecast:
                # Get forecasted rooms and pickup from pickupv2
                forecasted_rooms = pickupv2_forecast.get('predicted_value', hotel_rooms_otb)
                pickup_rooms = pickupv2_forecast.get('pickup_rooms_total', 0)

                # Convert pickup rooms to guests using the ratio (round up)
                breakfast_pickup = math.ceil(pickup_rooms * guests_per_room)
                # Forecast = OTB + pickup (floor is always OTB guests)
                breakfast_forecast = breakfast_otb + breakfast_pickup

                # Store calculation details
                breakfast_calc = {
                    "night_before": night_before.isoformat(),
                    "hotel_rooms_otb": hotel_rooms_otb,
                    "hotel_guests_otb": hotel_guests_otb,
                    "pickup_rooms": round(pickup_rooms, 1),
                    "guests_per_room": round(guests_per_room, 2),
                    "source": "pickupv2",
                }
            else:
                # Fallback to prior year pattern
                breakfast_pickup = max(0, hotel_guests_prior - hotel_guests_otb)
                breakfast_forecast = breakfast_otb + breakfast_pickup
                breakfast_calc = {
                    "night_before": night_before.isoformat(),
                    "hotel_guests_prior": hotel_guests_prior,
                    "source": "prior_year_fallback",
                }
        except Exception as e:
            logger.warning(f"Pickupv2 forecast failed for {night_before}: {e}")
            # Fallback to prior year pattern
            breakfast_pickup = max(0, hotel_guests_prior - hotel_guests_otb)
            breakfast_forecast = breakfast_otb + breakfast_pickup
            breakfast_calc = {
                "night_before": night_before.isoformat(),
                "hotel_guests_prior": hotel_guests_prior,
                "source": "prior_year_fallback",
            }

    # Prior year breakfast (for comparison)
    prior_breakfast = hotel_guests_prior

    result["breakfast"] = {
        "otb": breakfast_otb,
        "pickup": breakfast_pickup,
        "forecast": breakfast_forecast,
        "prior_year": prior_breakfast,
        "hotel_guests_otb": hotel_guests_otb,
        "hotel_guests_prior": hotel_guests_prior,
        "calc": breakfast_calc,
    }

    # ============ LUNCH ============
    # Lunch: OTB + pickup based on median historical pickup at lead time
    # Uses straight pickup count (not ratio) for stability
    lunch_data = current_covers.get("lunch", {})
    lunch_otb = lunch_data.get("total_covers", 0)
    prior_lunch = prior_covers.get("lunch", {}).get("total_covers", 0)

    # Get median pickup count for this lead time and DOW
    lunch_pickup = await get_lunch_pickup_by_lead_time(db, target_date, lead_days)

    # Determine pace column for tooltip
    if lead_days <= 30:
        lunch_pace_col = f"d{lead_days}"
    elif lead_days <= 177:
        weekly_cols = [37, 44, 51, 58, 65, 72, 79, 86, 93, 100, 107, 114, 121, 128, 135, 142, 149, 156, 163, 170, 177]
        lunch_pace_col = f"d{min(weekly_cols, key=lambda x: abs(x - lead_days))}"
    else:
        lunch_pace_col = "d177"

    lunch_calc = None
    # For future dates, add pickup to OTB
    if lead_days > 0:
        lunch_forecast = lunch_otb + lunch_pickup
        lunch_calc = {
            "day_of_week": target_date.strftime("%A"),
            "lead_days": lead_days,
            "pace_column": lunch_pace_col,
            "lookback_weeks": 8,
            "median_pickup": lunch_pickup,
            "source": "resos_booking_pace (total)",
        }
    else:
        # Past date - no pickup
        lunch_pickup = 0
        lunch_forecast = lunch_otb

    result["lunch"] = {
        "otb": lunch_otb,
        "pickup": lunch_pickup,
        "forecast": lunch_forecast,
        "prior_year": prior_lunch,
        "calc": lunch_calc,
    }

    # ============ DINNER ============
    # Dinner: More sophisticated calculation
    # - Non-resident: Lead-time based median pickup (like lunch)
    # - Resident: Based on hotel guests without dinner reservations + conversion rate
    dinner_data = current_covers.get("dinner", {})
    dinner_otb = dinner_data.get("total_covers", 0)
    dinner_resident_otb = dinner_data.get("resident_covers", 0)
    dinner_non_resident_otb = dinner_data.get("non_resident_covers", 0)
    dinner_dbb_otb = dinner_data.get("dbb_covers", 0)

    prior_dinner = prior_covers.get("dinner", {}).get("total_covers", 0)
    prior_dinner_resident = prior_covers.get("dinner", {}).get("resident_covers", 0)
    prior_dinner_non_resident = prior_covers.get("dinner", {}).get("non_resident_covers", 0)

    # Determine pace column for non-resident tooltip
    if lead_days <= 30:
        dinner_pace_col = f"d{lead_days}"
    elif lead_days <= 177:
        weekly_cols = [37, 44, 51, 58, 65, 72, 79, 86, 93, 100, 107, 114, 121, 128, 135, 142, 149, 156, 163, 170, 177]
        dinner_pace_col = f"d{min(weekly_cols, key=lambda x: abs(x - lead_days))}"
    else:
        dinner_pace_col = "d177"

    non_resident_calc = None
    if lead_days > 0:
        # ---- NON-RESIDENT PICKUP ----
        # Use lead-time based median pickup (same logic as lunch)
        non_resident_pickup = await get_dinner_non_resident_pickup_by_lead_time(db, target_date, lead_days)
        non_resident_calc = {
            "day_of_week": target_date.strftime("%A"),
            "lead_days": lead_days,
            "pace_column": dinner_pace_col,
            "lookback_weeks": 8,
            "median_pickup": non_resident_pickup,
            "source": "resos_booking_pace (non_resident)",
        }

        # ---- RESIDENT PICKUP ----
        # Simple approach: % of hotel guests who dine, applied to forecasted guests
        # Get hotel occupancy for target_date (dinner is same night as stay)
        hotel_tonight = await get_hotel_occupancy_for_date(db, target_date)
        hotel_guests_otb = hotel_tonight["guests"]
        hotel_rooms_otb = hotel_tonight["occupied_rooms"]

        # Calculate guests per room (use prior year ratio if current is 0)
        prior_year_hotel = await get_hotel_occupancy_for_date(db, prior_year_date)
        if hotel_rooms_otb > 0:
            guests_per_room = hotel_guests_otb / hotel_rooms_otb
        elif prior_year_hotel["occupied_rooms"] > 0:
            guests_per_room = prior_year_hotel["guests"] / prior_year_hotel["occupied_rooms"]
        else:
            guests_per_room = 1.8  # Default

        # Get pickupv2 room forecast for tonight
        pickup_rooms = 0
        try:
            pickupv2_dinner = await forecast_rooms_for_date(
                db, target_date, lead_days, prior_year_date, 'hotel_room_nights'
            )
            if pickupv2_dinner:
                pickup_rooms = pickupv2_dinner.get('pickup_rooms_total', 0)
        except Exception as e:
            logger.warning(f"Pickupv2 forecast failed for dinner {target_date}: {e}")

        # Calculate forecasted hotel guests (OTB + pickup)
        pickup_guests = pickup_rooms * guests_per_room
        forecasted_guests = hotel_guests_otb + pickup_guests

        # Get historical resident dining rate (% of hotel guests who dine)
        dining_rate = await get_resident_dining_rate(db, target_date)

        # Calculate expected resident covers
        # forecasted_resident_covers = forecasted_guests × dining_rate
        forecasted_resident_covers = forecasted_guests * dining_rate

        # Resident pickup = expected total - current OTB resident covers
        resident_pickup = max(0, math.ceil(forecasted_resident_covers) - dinner_resident_otb)

        dinner_forecast = dinner_otb + resident_pickup + non_resident_pickup

        # Store calculation details for tooltip
        resident_calc = {
            "hotel_guests_otb": hotel_guests_otb,
            "pickup_rooms": round(pickup_rooms, 1),
            "guests_per_room": round(guests_per_room, 2),
            "pickup_guests": round(pickup_guests, 1),
            "forecasted_guests": round(forecasted_guests, 1),
            "dining_rate": round(dining_rate * 100, 1),  # As percentage
            "forecasted_resident_covers": round(forecasted_resident_covers, 1),
            "resident_otb": dinner_resident_otb,
            "source": "last 4 weeks same DOW",
        }
    else:
        # Past date - no pickup
        dinner_forecast = dinner_otb
        resident_pickup = 0
        non_resident_pickup = 0
        resident_calc = None
        non_resident_calc = None

    result["dinner"] = {
        "otb": dinner_otb,
        "resident_otb": dinner_resident_otb,
        "non_resident_otb": dinner_non_resident_otb,
        "dbb_otb": dinner_dbb_otb,
        "resident_pickup": resident_pickup,
        "non_resident_pickup": non_resident_pickup,
        "forecast": dinner_forecast,
        "prior_year": prior_dinner,
        "prior_resident": prior_dinner_resident,
        "prior_non_resident": prior_dinner_non_resident,
        "resident_calc": resident_calc,
        "non_resident_calc": non_resident_calc,
    }

    # Totals
    total_otb = breakfast_otb + lunch_otb + dinner_otb
    total_forecast = breakfast_forecast + lunch_forecast + dinner_forecast
    prior_total = prior_breakfast + prior_lunch + prior_dinner

    result["totals"] = {
        "otb": total_otb,
        "forecast": total_forecast,
        "prior_year": prior_total,
        "pace_vs_prior_pct": round((total_otb / prior_total * 100), 1) if prior_total > 0 else None
    }

    # Add hotel occupancy context
    result["hotel_context"] = {
        "night_before_occupancy": hotel_otb["occupancy_pct"],
        "night_before_rooms": hotel_otb["occupied_rooms"],
        "night_before_guests": hotel_otb["guests"]
    }

    return result


async def forecast_covers_range(
    db: AsyncSession,
    start_date: date,
    end_date: date,
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Generate covers forecast for a date range.
    """
    forecasts = []
    current = start_date

    while current <= end_date:
        try:
            day_forecast = await forecast_covers_for_date(db, current, include_details)
            forecasts.append(day_forecast)
        except Exception as e:
            logger.warning(f"Failed to forecast covers for {current}: {e}")

        current += timedelta(days=1)

    # Calculate summary
    summary = {
        "breakfast_otb": sum(f["breakfast"]["otb"] for f in forecasts),
        "breakfast_forecast": sum(f["breakfast"]["forecast"] for f in forecasts),
        "breakfast_prior": sum(f["breakfast"]["prior_year"] for f in forecasts),
        "lunch_otb": sum(f["lunch"]["otb"] for f in forecasts),
        "lunch_forecast": sum(f["lunch"]["forecast"] for f in forecasts),
        "lunch_prior": sum(f["lunch"]["prior_year"] for f in forecasts),
        "dinner_otb": sum(f["dinner"]["otb"] for f in forecasts),
        "dinner_forecast": sum(f["dinner"]["forecast"] for f in forecasts),
        "dinner_prior": sum(f["dinner"]["prior_year"] for f in forecasts),
        "total_otb": sum(f["totals"]["otb"] for f in forecasts),
        "total_forecast": sum(f["totals"]["forecast"] for f in forecasts),
        "total_prior": sum(f["totals"]["prior_year"] for f in forecasts),
        "days_count": len(forecasts)
    }

    return {
        "data": forecasts,
        "summary": summary
    }
