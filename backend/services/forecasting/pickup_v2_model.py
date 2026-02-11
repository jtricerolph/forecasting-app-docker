"""
Pickup-V2 Forecasting Model - Self-contained revenue forecasting with confidence bands

This model runs alongside the existing pickup model, adding:
1. Revenue forecasting for accommodation using per-category rate tracking
2. Confidence bands based on rate range analysis (ADR position between min/max)
3. Per-category breakdown for detailed analysis

Uses 364-day offset for prior year comparison (52 weeks = day-of-week alignment).
"""
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple

from sqlalchemy import text

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


def get_prior_year_date(target_date: date) -> date:
    """
    Get prior year date with 364-day offset for day-of-week alignment.
    52 weeks = 364 days, so Monday aligns with Monday.
    """
    return target_date - timedelta(days=364)


async def get_current_otb_revenue(db, stay_date: date) -> Decimal:
    """
    Get current on-the-books revenue for a stay date.

    For current state, calculate from actual bookings directly (more accurate than pace snapshots).
    Sums net accommodation revenue for all bookings spanning the stay_date.
    """
    # Get VAT rate for net calculation
    vat_result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'accommodation_vat_rate'")
    )
    row = vat_result.fetchone()
    vat_rate = Decimal(row.config_value) if row and row.config_value else Decimal('0.20')

    # Get included categories
    cat_result = await db.execute(
        text("SELECT site_id FROM newbook_room_categories WHERE is_included = true")
    )
    included_categories = [row.site_id for row in cat_result.fetchall()]

    if not included_categories:
        return Decimal('0')

    # Query actual bookings for real-time OTB revenue
    result = await db.execute(
        text("""
            SELECT raw_json
            FROM newbook_bookings_data
            WHERE arrival_date <= :stay_date
            AND departure_date > :stay_date
            AND status IN ('Unconfirmed', 'Confirmed', 'Arrived', 'Departed')
            AND category_id = ANY(:categories)
        """),
        {
            "stay_date": stay_date,
            "categories": included_categories
        }
    )

    total_revenue = Decimal('0')
    for row in result.fetchall():
        if row.raw_json:
            revenue = _extract_day_rate_from_booking(row.raw_json, stay_date, vat_rate)
            total_revenue += revenue

    return total_revenue


async def get_revenue_at_lead_time(db, stay_date: date, lead_days: int) -> Decimal:
    """
    Get revenue snapshot at a specific lead time for a stay date.
    """
    column = get_lead_time_column(lead_days)

    result = await db.execute(
        text(f"""
            SELECT {column} as revenue
            FROM revenue_pace
            WHERE stay_date = :stay_date
        """),
        {"stay_date": stay_date}
    )
    row = result.fetchone()

    if row and row.revenue is not None:
        return Decimal(str(row.revenue))
    return Decimal('0')


async def get_actual_revenue(db, stay_date: date) -> Decimal:
    """
    Get actual final revenue for a stay date from newbook_net_revenue_data.
    """
    result = await db.execute(
        text("""
            SELECT accommodation
            FROM newbook_net_revenue_data
            WHERE date = :stay_date
        """),
        {"stay_date": stay_date}
    )
    row = result.fetchone()

    if row and row.accommodation is not None:
        return Decimal(str(row.accommodation))
    return Decimal('0')


async def get_prior_otb_revenue_from_bookings(
    db,
    prior_date: date,
    lead_days: int,
    vat_rate: Decimal
) -> Decimal:
    """
    Calculate prior year OTB revenue by looking at bookings that:
    1. Span the prior year date (arrival <= date < departure)
    2. Were placed BEFORE the equivalent lead time cutoff

    This gives us what was "on the books" at the same lead time last year.

    Args:
        prior_date: The prior year stay date (e.g., Feb 16, 2025)
        lead_days: Current lead days (e.g., 7 days out)
        vat_rate: VAT rate for net calculation

    Returns:
        Net accommodation revenue that was booked at same lead time
    """
    # Calculate the cutoff date - bookings must have been placed before this
    # This is "today" equivalent in the prior year
    cutoff_date = prior_date - timedelta(days=lead_days)

    # Get included categories
    cat_result = await db.execute(
        text("SELECT site_id FROM newbook_room_categories WHERE is_included = true")
    )
    included_categories = [row.site_id for row in cat_result.fetchall()]

    if not included_categories:
        return Decimal('0')

    # Query bookings that span the prior date and were placed before cutoff
    result = await db.execute(
        text("""
            SELECT raw_json
            FROM newbook_bookings_data
            WHERE arrival_date <= :prior_date
            AND departure_date > :prior_date
            AND booking_placed < :cutoff_date
            AND status IN ('Unconfirmed', 'Confirmed', 'Arrived', 'Departed')
            AND category_id = ANY(:categories)
        """),
        {
            "prior_date": prior_date,
            "cutoff_date": cutoff_date,
            "categories": included_categories
        }
    )

    total_revenue = Decimal('0')
    for row in result.fetchall():
        if row.raw_json:
            revenue = _extract_day_rate_from_booking(row.raw_json, prior_date, vat_rate)
            total_revenue += revenue

    return total_revenue


def _extract_day_rate_from_booking(raw_json: dict, target_date: date, vat_rate: Decimal) -> Decimal:
    """
    Extract net accommodation revenue from booking JSON for a specific stay date.
    Returns net rate only (for backward compatibility).
    """
    net, _ = _extract_day_rates_from_booking(raw_json, target_date, vat_rate)
    return net


def _extract_day_rates_from_booking(raw_json: dict, target_date: date, vat_rate: Decimal) -> Tuple[Decimal, Decimal]:
    """
    Extract both net and gross rates from booking JSON for a specific stay date.

    Returns:
        (net_rate, gross_rate) tuple

    Net includes:
    - Room tariff from tariffs_quoted (net of VAT)
    - Inventory items like breakfast allocations (net of VAT)
    - Commission deductions (negative amounts, no VAT)

    Gross is the actual guest-facing tariff:
    - Room tariff charge_amount
    - Inventory items amounts
    """
    if not raw_json:
        return Decimal('0'), Decimal('0')

    target_str = target_date.strftime("%Y-%m-%d")
    total_net = Decimal('0')
    total_gross = Decimal('0')

    # 1. Get room tariff for this stay date
    tariffs = raw_json.get("tariffs_quoted", [])
    for tariff in tariffs:
        if tariff.get("stay_date") == target_str:
            charge_amount = Decimal(str(tariff.get("charge_amount", 0) or 0))
            total_gross += charge_amount

            # Try to get net from taxes array if available
            taxes = tariff.get("taxes", [])
            if taxes and charge_amount > 0:
                tax_amount = sum(Decimal(str(t.get("tax_amount", 0) or 0)) for t in taxes)
                net_amount = charge_amount - tax_amount
            else:
                # Fallback: calculate net using VAT rate
                net_amount = charge_amount / (1 + vat_rate)

            total_net += net_amount
            break  # Only one tariff per date

    # 2. Add inventory items for this date (breakfast, commissions, etc.)
    inventory_items = raw_json.get("inventory_items", [])
    for item in inventory_items:
        if item.get("stay_date") == target_str:
            amount = Decimal(str(item.get("amount", 0) or 0))

            if amount > 0:
                # Positive amounts (breakfast, extras)
                total_gross += amount  # Guest pays this
                net_amount = amount / (1 + vat_rate)
            else:
                # Negative amounts (commissions) - reduce both, no VAT
                total_gross += amount  # Reduces guest charge if visible
                net_amount = amount

            total_net += net_amount

    return total_net, total_gross


async def get_current_otb_rooms_by_category(db, stay_date: date) -> Dict[str, int]:
    """
    Get current on-the-books room counts by category.

    For current state, query actual bookings directly (more accurate than pace snapshots).
    This counts bookings that span the stay_date and have valid status.
    """
    # Get included categories
    cat_result = await db.execute(
        text("SELECT site_id FROM newbook_room_categories WHERE is_included = true")
    )
    included_categories = [row.site_id for row in cat_result.fetchall()]

    if not included_categories:
        return {}

    # Query actual bookings for real-time OTB count
    result = await db.execute(
        text("""
            SELECT category_id, COUNT(*) as room_count
            FROM newbook_bookings_data
            WHERE arrival_date <= :stay_date
            AND departure_date > :stay_date
            AND status IN ('Unconfirmed', 'Confirmed', 'Arrived', 'Departed')
            AND category_id = ANY(:categories)
            GROUP BY category_id
        """),
        {
            "stay_date": stay_date,
            "categories": included_categories
        }
    )

    return {str(row.category_id): row.room_count for row in result.fetchall()}


async def get_rooms_at_lead_time_by_category(db, stay_date: date, lead_days: int) -> Dict[str, int]:
    """
    Get room count snapshot at a specific lead time by category.
    """
    column = get_lead_time_column(lead_days)

    result = await db.execute(
        text(f"""
            SELECT category_id, {column} as rooms
            FROM category_booking_pace
            WHERE arrival_date = :stay_date
        """),
        {"stay_date": stay_date}
    )

    return {row.category_id: row.rooms or 0 for row in result.fetchall()}


async def get_rate_stats_by_category(db, stay_date: date) -> Dict[str, Dict[str, Any]]:
    """
    Get rate statistics (min/max/adr) per category from newbook_bookings_stats.
    """
    result = await db.execute(
        text("""
            SELECT rate_stats_by_category
            FROM newbook_bookings_stats
            WHERE date = :stay_date
        """),
        {"stay_date": stay_date}
    )
    row = result.fetchone()

    if row and row.rate_stats_by_category:
        return row.rate_stats_by_category
    return {}


async def get_current_rates_by_category(db, stay_date: date) -> Dict[str, Dict[str, Decimal]]:
    """
    Get current rack rates per category from newbook_current_rates.
    Returns dict with 'net' and 'gross' rates per category.
    Falls back to historical ADR if no current rate available.
    """
    result = await db.execute(
        text("""
            SELECT category_id, rate_net, rate_gross
            FROM newbook_current_rates
            WHERE rate_date = :stay_date
        """),
        {"stay_date": stay_date}
    )

    rates = {}
    for row in result.fetchall():
        rates[row.category_id] = {
            'net': Decimal(str(row.rate_net)) if row.rate_net else Decimal('0'),
            'gross': Decimal(str(row.rate_gross)) if row.rate_gross else Decimal('0')
        }

    # Fallback to historical ADR for categories without current rates
    if not rates:
        rate_stats = await get_rate_stats_by_category(db, stay_date)
        for cat_id, stats in rate_stats.items():
            if cat_id not in rates and 'adr_net' in stats:
                net = Decimal(str(stats['adr_net']))
                # Estimate gross as net * 1.2 (20% VAT) as fallback
                rates[cat_id] = {
                    'net': net,
                    'gross': net * Decimal('1.2')
                }

    return rates


async def get_prior_year_pickup_rooms_by_category(
    db,
    prior_date: date,
    lead_days: int
) -> Dict[str, int]:
    """
    Get prior year pickup rooms by category from bookings data.

    Pickup = Final rooms - OTB rooms at same lead time.
    OTB rooms = bookings placed BEFORE the cutoff date
    Final rooms = all valid bookings (status in valid statuses)

    Returns per-category pickup counts.
    """
    cutoff_date = prior_date - timedelta(days=lead_days)

    # Get included categories
    cat_result = await db.execute(
        text("SELECT site_id FROM newbook_room_categories WHERE is_included = true")
    )
    included_categories = [row.site_id for row in cat_result.fetchall()]

    if not included_categories:
        return {}

    # Count OTB rooms by category (bookings placed BEFORE cutoff)
    otb_result = await db.execute(
        text("""
            SELECT category_id, COUNT(*) as room_count
            FROM newbook_bookings_data
            WHERE arrival_date <= :prior_date
            AND departure_date > :prior_date
            AND booking_placed < :cutoff_date
            AND status IN ('Unconfirmed', 'Confirmed', 'Arrived', 'Departed')
            AND category_id = ANY(:categories)
            GROUP BY category_id
        """),
        {
            "prior_date": prior_date,
            "cutoff_date": cutoff_date,
            "categories": included_categories
        }
    )
    otb_by_cat = {str(row.category_id): row.room_count for row in otb_result.fetchall()}

    # Count final rooms by category (all valid bookings for that date)
    final_result = await db.execute(
        text("""
            SELECT category_id, COUNT(*) as room_count
            FROM newbook_bookings_data
            WHERE arrival_date <= :prior_date
            AND departure_date > :prior_date
            AND status IN ('Confirmed', 'Arrived', 'Departed')
            AND category_id = ANY(:categories)
            GROUP BY category_id
        """),
        {
            "prior_date": prior_date,
            "categories": included_categories
        }
    )
    final_by_cat = {str(row.category_id): row.room_count for row in final_result.fetchall()}

    # Calculate pickup per category
    pickup_by_category = {}
    all_categories = set(list(otb_by_cat.keys()) + list(final_by_cat.keys()))

    for cat_id in all_categories:
        otb = otb_by_cat.get(cat_id, 0)
        final = final_by_cat.get(cat_id, 0)
        pickup = max(0, final - otb)  # Only positive pickup (ignore cancellations)
        if pickup > 0:
            pickup_by_category[cat_id] = pickup

    return pickup_by_category


async def get_prior_year_pickup_rates_by_category(
    db,
    prior_date: date,
    lead_days: int,
    vat_rate: Decimal
) -> Dict[str, Dict[str, Decimal]]:
    """
    Get prior year rates for picked-up bookings by category.

    Uses the EARLIEST pickup booking(s) to estimate the listed rate at that lead time,
    rather than averaging all pickup bookings (which gets diluted by last-minute discounts).

    Returns dict per category with:
    - avg_rate: Rate from earliest pickup booking(s) - represents listed rate at this lead time
    - cheaper_50_avg / expensive_50_avg: For bounds calculation

    Pickup bookings = bookings placed AFTER the cutoff date (late bookers).
    """
    # Calculate the cutoff date - bookings placed AFTER this are "pickup"
    cutoff_date = prior_date - timedelta(days=lead_days)

    # Get included categories
    cat_result = await db.execute(
        text("SELECT site_id FROM newbook_room_categories WHERE is_included = true")
    )
    included_categories = [row.site_id for row in cat_result.fetchall()]

    if not included_categories:
        return {}

    # Query bookings ordered by booking_placed to get earliest first
    # This lets us use the first booking(s) as the "listed rate at this lead time"
    result = await db.execute(
        text("""
            SELECT category_id, raw_json, booking_placed
            FROM newbook_bookings_data
            WHERE arrival_date <= :prior_date
            AND departure_date > :prior_date
            AND booking_placed >= :cutoff_date
            AND status IN ('Unconfirmed', 'Confirmed', 'Arrived', 'Departed')
            AND category_id = ANY(:categories)
            ORDER BY booking_placed ASC
        """),
        {
            "prior_date": prior_date,
            "cutoff_date": cutoff_date,
            "categories": included_categories
        }
    )

    # Collect rates per category with booking order preserved
    # Format: List of (net, gross, booking_placed) tuples
    rates_by_category: Dict[str, List[Tuple[Decimal, Decimal, date]]] = {}

    for row in result.fetchall():
        cat_id = str(row.category_id)
        if row.raw_json:
            net_rate, gross_rate = _extract_day_rates_from_booking(row.raw_json, prior_date, vat_rate)
            if net_rate > 0:
                if cat_id not in rates_by_category:
                    rates_by_category[cat_id] = []
                booking_date = row.booking_placed.date() if hasattr(row.booking_placed, 'date') else row.booking_placed
                rates_by_category[cat_id].append((net_rate, gross_rate, booking_date))

    # Calculate TWO sets of rates:
    # 1. Average of ALL pickup bookings - for realistic revenue forecasting
    # 2. Earliest booking(s) rate - represents "listed rate at this lead time" for rate comparison
    result_rates: Dict[str, Dict[str, Decimal]] = {}

    for cat_id, rate_tuples in rates_by_category.items():
        if rate_tuples:
            all_net_rates = [(r[0], r[1]) for r in rate_tuples]

            # Average of ALL pickup bookings - for forecast revenue calculation
            avg_rate = sum(r[0] for r in all_net_rates) / len(all_net_rates)
            avg_rate_gross = sum(r[1] for r in all_net_rates) / len(all_net_rates)

            # Earliest 1-3 bookings = "listed rate at this lead time" for rate comparison
            earliest_count = min(3, len(rate_tuples))
            earliest_bookings = rate_tuples[:earliest_count]
            listed_rate = sum(r[0] for r in earliest_bookings) / len(earliest_bookings)
            listed_rate_gross = sum(r[1] for r in earliest_bookings) / len(earliest_bookings)

            # For 50% splits, use all bookings sorted by rate
            sorted_pairs = sorted(all_net_rates, key=lambda x: x[0])
            mid_point = len(sorted_pairs) // 2
            if mid_point == 0:
                mid_point = 1

            cheaper_half = sorted_pairs[:mid_point]
            expensive_half = sorted_pairs[mid_point:] if mid_point < len(sorted_pairs) else sorted_pairs

            cheaper_50_avg = sum(r[0] for r in cheaper_half) / len(cheaper_half)
            cheaper_50_avg_gross = sum(r[1] for r in cheaper_half) / len(cheaper_half)
            expensive_50_avg = sum(r[0] for r in expensive_half) / len(expensive_half) if expensive_half else avg_rate
            expensive_50_avg_gross = sum(r[1] for r in expensive_half) / len(expensive_half) if expensive_half else avg_rate_gross

            result_rates[cat_id] = {
                'avg_rate': avg_rate,                    # For forecast calculation
                'avg_rate_gross': avg_rate_gross,
                'listed_rate': listed_rate,              # For rate comparison (earliest bookings)
                'listed_rate_gross': listed_rate_gross,
                'cheaper_50_avg': cheaper_50_avg,
                'cheaper_50_avg_gross': cheaper_50_avg_gross,
                'expensive_50_avg': expensive_50_avg,
                'expensive_50_avg_gross': expensive_50_avg_gross,
                'booking_count': len(rate_tuples),
                'earliest_booking_count': earliest_count
            }

    return result_rates


async def get_prior_year_otb_rooms_by_category(
    db,
    prior_date: date,
    lead_days: int
) -> Dict[str, int]:
    """
    Get prior year OTB rooms by category (bookings placed before cutoff).
    """
    cutoff_date = prior_date - timedelta(days=lead_days)

    cat_result = await db.execute(
        text("SELECT site_id FROM newbook_room_categories WHERE is_included = true")
    )
    included_categories = [row.site_id for row in cat_result.fetchall()]

    if not included_categories:
        return {}

    result = await db.execute(
        text("""
            SELECT category_id, COUNT(*) as room_count
            FROM newbook_bookings_data
            WHERE arrival_date <= :prior_date
            AND departure_date > :prior_date
            AND booking_placed < :cutoff_date
            AND status IN ('Unconfirmed', 'Confirmed', 'Arrived', 'Departed')
            AND category_id = ANY(:categories)
            GROUP BY category_id
        """),
        {
            "prior_date": prior_date,
            "cutoff_date": cutoff_date,
            "categories": included_categories
        }
    )

    return {str(row.category_id): row.room_count for row in result.fetchall()}


async def get_prior_year_final_rooms_by_category(
    db,
    prior_date: date
) -> Dict[str, int]:
    """
    Get prior year final rooms by category (all valid bookings).
    """
    cat_result = await db.execute(
        text("SELECT site_id FROM newbook_room_categories WHERE is_included = true")
    )
    included_categories = [row.site_id for row in cat_result.fetchall()]

    if not included_categories:
        return {}

    result = await db.execute(
        text("""
            SELECT category_id, COUNT(*) as room_count
            FROM newbook_bookings_data
            WHERE arrival_date <= :prior_date
            AND departure_date > :prior_date
            AND status IN ('Confirmed', 'Arrived', 'Departed')
            AND category_id = ANY(:categories)
            GROUP BY category_id
        """),
        {
            "prior_date": prior_date,
            "categories": included_categories
        }
    )

    return {str(row.category_id): row.room_count for row in result.fetchall()}


async def get_category_availability(db, stay_date: date) -> Dict[str, int]:
    """
    Get available room capacity per category for a date.
    Uses room inventory minus OTB.
    """
    # Get included categories with their room counts
    result = await db.execute(
        text("""
            SELECT site_id, room_count
            FROM newbook_room_categories
            WHERE is_included = true
        """)
    )

    capacity = {row.site_id: row.room_count or 0 for row in result.fetchall()}
    return capacity


async def get_bookable_rooms(db, stay_date: date) -> int:
    """
    Get total bookable room capacity for a date.
    """
    result = await db.execute(
        text("""
            SELECT bookable_count
            FROM newbook_bookings_stats
            WHERE date = :stay_date
        """),
        {"stay_date": stay_date}
    )
    row = result.fetchone()

    if row and row.bookable_count:
        return row.bookable_count

    # Fallback: sum of all included category rooms
    result = await db.execute(
        text("""
            SELECT COALESCE(SUM(room_count), 0) as total
            FROM newbook_room_categories
            WHERE is_included = true
        """)
    )
    row = result.fetchone()

    return row.total if row else 0


async def calculate_revenue_bounds(
    db,
    stay_date: date,
    current_otb_rev: Decimal,
    current_otb_rooms: Dict[str, int],
    expected_pickup_rev: Decimal
) -> Tuple[Decimal, Decimal, Decimal, float, Dict[str, Dict[str, Any]]]:
    """
    Calculate forecast with confidence bounds based on rate analysis.

    Returns:
        (forecast, upper_bound, lower_bound, adr_position, category_breakdown)

    Upper bound: current OTB + (pickup rooms × current rack rate per category)
    Lower bound: current OTB + (pickup rooms × min historical rate per category)
    ADR position: where current ADR falls between min/max (0-1 scale)
    """
    capacity = await get_category_availability(db, stay_date)
    rate_stats = await get_rate_stats_by_category(db, stay_date)
    current_rates = await get_current_rates_by_category(db, stay_date)

    # Get prior year data for expected pickup calculation
    prior_date = get_prior_year_date(stay_date)
    prior_otb_rooms = await get_current_otb_rooms_by_category(db, prior_date)

    category_breakdown: Dict[str, Dict[str, Any]] = {}
    total_upper_pickup = Decimal('0')
    total_lower_pickup = Decimal('0')
    total_expected_pickup = Decimal('0')

    weighted_adr_position = Decimal('0')
    total_weight = Decimal('0')

    for cat_id, cat_capacity in capacity.items():
        otb_rooms = current_otb_rooms.get(cat_id, 0)
        remaining = cat_capacity - otb_rooms

        if remaining <= 0:
            category_breakdown[cat_id] = {
                'otb_rooms': otb_rooms,
                'capacity': cat_capacity,
                'remaining': 0,
                'pickup_rooms': 0,
                'upper_pickup_rev': 0,
                'lower_pickup_rev': 0,
                'expected_pickup_rev': 0
            }
            continue

        # Get rate bounds for this category
        cat_stats = rate_stats.get(cat_id, {})
        min_rate = Decimal(str(cat_stats.get('min_net', 100)))  # Default fallback
        max_rate = Decimal(str(cat_stats.get('max_net', 200)))
        adr = Decimal(str(cat_stats.get('adr_net', 150)))
        # Handle new dict format for current_rates
        current_rate_data = current_rates.get(cat_id, {})
        if isinstance(current_rate_data, dict):
            current_rate = current_rate_data.get('net', adr)
        else:
            current_rate = current_rate_data if current_rate_data else adr

        # Expected pickup rooms based on prior year pattern
        prior_otb = prior_otb_rooms.get(cat_id, 0)
        # Assume similar pickup ratio to prior year
        # This is simplified - ideally would use actual prior final rooms
        expected_pickup_rooms = min(remaining, max(0, prior_otb - otb_rooms) if prior_otb > otb_rooms else int(remaining * 0.3))

        # Calculate revenue bounds
        upper_pickup_rev = Decimal(remaining) * current_rate
        lower_pickup_rev = Decimal(remaining) * min_rate
        expected_pickup_rev_cat = Decimal(expected_pickup_rooms) * adr

        total_upper_pickup += upper_pickup_rev
        total_lower_pickup += lower_pickup_rev
        total_expected_pickup += expected_pickup_rev_cat

        # Calculate ADR position for this category
        if max_rate > min_rate:
            cat_adr_position = (adr - min_rate) / (max_rate - min_rate)
            weighted_adr_position += cat_adr_position * Decimal(otb_rooms) if otb_rooms > 0 else Decimal('0')
            total_weight += Decimal(otb_rooms) if otb_rooms > 0 else Decimal('0')

        category_breakdown[cat_id] = {
            'otb_rooms': otb_rooms,
            'capacity': cat_capacity,
            'remaining': remaining,
            'pickup_rooms': expected_pickup_rooms,
            'min_rate': float(min_rate),
            'max_rate': float(max_rate),
            'adr': float(adr),
            'current_rate': float(current_rate),
            'upper_pickup_rev': float(upper_pickup_rev),
            'lower_pickup_rev': float(lower_pickup_rev),
            'expected_pickup_rev': float(expected_pickup_rev_cat)
        }

    # Use expected pickup from prior year pattern (even if negative - indicates cancellations)
    # Only fall back to room-based calculation if we have no prior data at all
    if expected_pickup_rev != 0:
        forecast = current_otb_rev + expected_pickup_rev
    else:
        forecast = current_otb_rev + total_expected_pickup

    # Floor: can't go below current OTB (negative pickup still respects current bookings)
    forecast = max(forecast, current_otb_rev)

    # Calculate bounds using rate-based variance
    # Use min/max rate ratios from rate_stats if available, otherwise use default variance
    total_min_rate = Decimal('0')
    total_max_rate = Decimal('0')
    total_adr = Decimal('0')
    rate_count = 0

    for cat_id, stats in rate_stats.items():
        if 'min_net' in stats and 'max_net' in stats and 'adr_net' in stats:
            total_min_rate += Decimal(str(stats['min_net']))
            total_max_rate += Decimal(str(stats['max_net']))
            total_adr += Decimal(str(stats['adr_net']))
            rate_count += 1

    if rate_count > 0 and total_adr > 0:
        # Use actual rate ratios for bounds
        avg_min = total_min_rate / rate_count
        avg_max = total_max_rate / rate_count
        avg_adr = total_adr / rate_count

        # Rate multipliers: how much pickup could vary based on rate changes
        lower_ratio = avg_min / avg_adr if avg_adr > 0 else Decimal('0.85')
        upper_ratio = avg_max / avg_adr if avg_adr > 0 else Decimal('1.15')
    else:
        # No rate stats - use default variance
        lower_ratio = Decimal('0.85')
        upper_ratio = Decimal('1.15')

    if expected_pickup_rev > 0:
        # Positive pickup: apply rate variance to pickup amount
        upper_bound = current_otb_rev + (expected_pickup_rev * upper_ratio)
        lower_bound = max(current_otb_rev, current_otb_rev + (expected_pickup_rev * lower_ratio))
    else:
        # Negative or zero pickup: forecast is already floored to OTB
        # Upper: could get some late bookings (small % upside)
        # Lower: OTB is the floor
        upside_pct = Decimal('0.10')
        upper_bound = forecast + (current_otb_rev * upside_pct)
        lower_bound = current_otb_rev

    # Calculate weighted ADR position
    adr_position = float(weighted_adr_position / total_weight) if total_weight > 0 else 0.5

    return forecast, upper_bound, lower_bound, adr_position, category_breakdown


async def run_pickup_v2_forecast(
    db,
    metric_code: str,
    start_date: date,
    end_date: date,
    include_details: bool = False
) -> List[Dict[str, Any]]:
    """
    Generate pickup-v2 forecast for a date range.

    Supports metrics:
    - net_accom: Accommodation revenue forecast with confidence bands
    - hotel_room_nights: Room count forecast (uses same pickup logic)
    - hotel_occupancy_pct: Occupancy percentage forecast

    Args:
        db: Database session
        metric_code: Metric to forecast
        start_date: Start date for forecast
        end_date: End date for forecast
        include_details: If True, includes category breakdown and explanations

    Returns:
        List of forecast dicts with predicted values and confidence bounds
    """
    logger.info(f"Running pickup-v2 forecast for {metric_code}: {start_date} to {end_date}")

    forecasts = []
    today = date.today()
    current_date = start_date

    while current_date <= end_date:
        lead_days = (current_date - today).days
        day_of_week = current_date.strftime("%a")
        prior_date = get_prior_year_date(current_date)

        if metric_code == 'net_accom':
            # Revenue forecasting with confidence bands
            forecast_data = await forecast_revenue_for_date(
                db, current_date, lead_days, prior_date, include_details
            )
        elif metric_code in ('hotel_room_nights', 'hotel_occupancy_pct'):
            # Room-based forecasting
            forecast_data = await forecast_rooms_for_date(
                db, current_date, lead_days, prior_date, metric_code, include_details
            )
        else:
            logger.warning(f"Unsupported metric: {metric_code}")
            current_date += timedelta(days=1)
            continue

        if forecast_data:
            forecast_data['date'] = str(current_date)
            forecast_data['day_of_week'] = day_of_week
            forecast_data['lead_days'] = lead_days
            forecast_data['prior_year_date'] = str(prior_date)
            forecasts.append(forecast_data)

        current_date += timedelta(days=1)

    logger.info(f"Generated {len(forecasts)} pickup-v2 forecasts for {metric_code}")
    return forecasts


async def forecast_revenue_for_date(
    db,
    stay_date: date,
    lead_days: int,
    prior_date: date,
    include_details: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Generate revenue forecast for a single date using room-based per-category pickup.

    Four scenarios calculated:
    a) At prior ADR = OTB + Σ(pickup_rooms[cat] × prior_adr[cat]) - what prior year achieved
    b) At current rate = OTB + Σ(pickup_rooms[cat] × current_rate[cat]) - achievable now
    c) Cheaper 50% = OTB + Σ(pickup_rooms[cat] × cheaper_half_avg[cat])
    d) Expensive 50% = OTB + Σ(pickup_rooms[cat] × expensive_half_avg[cat])

    Forecast = min(at_prior_adr, at_current_rate) - can't exceed what's achievable at current prices
    Bounds: Upper = max of all 4, Lower = min of all 4
    Ceiling: OTB + remaining_rooms × expensive_50_rate (physical capacity limit)
    """
    # Get VAT rate for revenue calculations
    vat_result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'accommodation_vat_rate'")
    )
    row = vat_result.fetchone()
    vat_rate = Decimal(row.config_value) if row and row.config_value else Decimal('0.20')

    # Get current OTB revenue (net accommodation)
    current_otb_rev = await get_current_otb_revenue(db, stay_date)

    # Get prior year data for comparison (still useful for pace metrics)
    prior_otb_rev = await get_prior_otb_revenue_from_bookings(db, prior_date, lead_days, vat_rate)
    prior_final_rev = await get_actual_revenue(db, prior_date)

    # NEW: Room-based per-category pickup calculation
    # Get prior year pickup rooms by category
    pickup_rooms_by_cat = await get_prior_year_pickup_rooms_by_category(db, prior_date, lead_days)

    # Get prior year pickup rates (avg rate and cheapest 3 avg) per category
    pickup_rates_by_cat = await get_prior_year_pickup_rates_by_category(db, prior_date, lead_days, vat_rate)

    # Get current rates for upper bound calculation
    current_rates = await get_current_rates_by_category(db, stay_date)

    # Get rate stats for fallback rates
    rate_stats = await get_rate_stats_by_category(db, prior_date)

    # Get current OTB rooms and capacity for ceiling calculation
    current_otb_rooms_by_cat = await get_current_otb_rooms_by_category(db, stay_date)
    current_otb_rooms_total = sum(current_otb_rooms_by_cat.values())
    capacity_by_cat = await get_category_availability(db, stay_date)

    # Calculate 4 scenarios per category
    category_breakdown: Dict[str, Dict[str, Any]] = {}
    # a) Forecast: pickup × ADR of prior year pickups (net and gross)
    forecast_pickup = Decimal('0')
    forecast_pickup_gross = Decimal('0')
    # b) At current rate: pickup × current rack rate (net and gross)
    current_rate_pickup = Decimal('0')
    current_rate_pickup_gross = Decimal('0')
    # c) Cheaper 50%: pickup × avg of cheaper half of prior pickups
    cheaper_50_pickup = Decimal('0')
    # d) Expensive 50%: pickup × avg of more expensive half of prior pickups
    expensive_50_pickup = Decimal('0')
    # Listed rate at lead time (earliest bookings) - for rate comparison
    listed_rate_pickup = Decimal('0')
    listed_rate_pickup_gross = Decimal('0')
    # Ceiling: max revenue if all remaining rooms sell at expensive 50% rate
    max_remaining_revenue = Decimal('0')
    total_pickup_rooms = 0

    for cat_id, pickup_rooms in pickup_rooms_by_cat.items():
        total_pickup_rooms += pickup_rooms
        cat_rates = pickup_rates_by_cat.get(cat_id, {})

        # Prior year average rate for picked up bookings (for forecast) - net and gross
        avg_rate = cat_rates.get('avg_rate')
        avg_rate_gross = cat_rates.get('avg_rate_gross')
        # Listed rate = earliest bookings (for rate comparison at this lead time)
        listed_rate = cat_rates.get('listed_rate')
        listed_rate_gross = cat_rates.get('listed_rate_gross')
        if avg_rate is None:
            # Fallback to rate_stats ADR if no pickup bookings found
            cat_stats = rate_stats.get(cat_id, {})
            avg_rate = Decimal(str(cat_stats.get('adr_net', 150)))
            avg_rate_gross = avg_rate * Decimal('1.2')  # Estimate gross
            listed_rate = avg_rate
            listed_rate_gross = avg_rate_gross

        # Cheaper 50% avg rate
        cheaper_50_rate = cat_rates.get('cheaper_50_avg')
        if cheaper_50_rate is None:
            cat_stats = rate_stats.get(cat_id, {})
            cheaper_50_rate = Decimal(str(cat_stats.get('min_net', avg_rate * Decimal('0.85'))))

        # Expensive 50% avg rate
        expensive_50_rate = cat_rates.get('expensive_50_avg')
        if expensive_50_rate is None:
            cat_stats = rate_stats.get(cat_id, {})
            expensive_50_rate = Decimal(str(cat_stats.get('max_net', avg_rate * Decimal('1.15'))))

        # Current rack rate (net and gross from newbook_current_rates)
        current_rate_data = current_rates.get(cat_id, {})
        if isinstance(current_rate_data, dict):
            current_rate = current_rate_data.get('net')
            current_rate_gross = current_rate_data.get('gross')
        else:
            # Backward compatibility if old format
            current_rate = current_rate_data
            current_rate_gross = current_rate * Decimal('1.2') if current_rate else None

        if current_rate is None:
            cat_stats = rate_stats.get(cat_id, {})
            current_rate = Decimal(str(cat_stats.get('adr_net', avg_rate)))
            current_rate_gross = current_rate * Decimal('1.2')

        # Calculate pickup revenue contributions for all 4 scenarios
        cat_forecast_pickup = Decimal(pickup_rooms) * avg_rate
        cat_forecast_pickup_gross = Decimal(pickup_rooms) * (avg_rate_gross or avg_rate * Decimal('1.2'))
        cat_current_pickup = Decimal(pickup_rooms) * current_rate
        cat_current_pickup_gross = Decimal(pickup_rooms) * (current_rate_gross or current_rate * Decimal('1.2'))
        cat_cheaper_50_pickup = Decimal(pickup_rooms) * cheaper_50_rate
        cat_expensive_50_pickup = Decimal(pickup_rooms) * expensive_50_rate
        # Listed rate contribution (for rate comparison)
        cat_listed_rate_pickup = Decimal(pickup_rooms) * (listed_rate or avg_rate)
        cat_listed_rate_pickup_gross = Decimal(pickup_rooms) * (listed_rate_gross or avg_rate_gross or avg_rate * Decimal('1.2'))

        forecast_pickup += cat_forecast_pickup
        forecast_pickup_gross += cat_forecast_pickup_gross
        current_rate_pickup += cat_current_pickup
        current_rate_pickup_gross += cat_current_pickup_gross
        cheaper_50_pickup += cat_cheaper_50_pickup
        expensive_50_pickup += cat_expensive_50_pickup
        listed_rate_pickup += cat_listed_rate_pickup
        listed_rate_pickup_gross += cat_listed_rate_pickup_gross

        # Calculate remaining capacity for ceiling
        cat_otb_rooms = current_otb_rooms_by_cat.get(cat_id, 0)
        cat_capacity = capacity_by_cat.get(cat_id, 0)
        remaining_rooms = max(0, cat_capacity - cat_otb_rooms)

        # Cap pickup rooms at remaining capacity
        capped_pickup_rooms = min(pickup_rooms, remaining_rooms)

        # Ceiling contribution: remaining rooms × expensive 50% rate
        max_remaining_revenue += Decimal(remaining_rooms) * expensive_50_rate

        category_breakdown[cat_id] = {
            'pickup_rooms': pickup_rooms,
            'capped_pickup_rooms': capped_pickup_rooms,
            'remaining_capacity': remaining_rooms,
            'prior_avg_rate': float(avg_rate),
            'prior_avg_rate_gross': float(avg_rate_gross or avg_rate * Decimal('1.2')),
            'cheaper_50_rate': float(cheaper_50_rate),
            'expensive_50_rate': float(expensive_50_rate),
            'current_rate': float(current_rate),
            'current_rate_gross': float(current_rate_gross or current_rate * Decimal('1.2')),
            'forecast_pickup_rev': float(cat_forecast_pickup),
            'current_rate_pickup_rev': float(cat_current_pickup),
            'cheaper_50_pickup_rev': float(cat_cheaper_50_pickup),
            'expensive_50_pickup_rev': float(cat_expensive_50_pickup),
            'booking_count': cat_rates.get('booking_count', 0)
        }

    # Ceiling: OTB + max possible from remaining rooms at expensive 50% rate
    revenue_ceiling = current_otb_rev + max_remaining_revenue

    # Calculate 4 scenarios (floored at OTB, capped at ceiling)
    # a) Forecast: at prior year ADR (what actually happened)
    at_prior_adr = min(max(current_otb_rev + forecast_pickup, current_otb_rev), revenue_ceiling)
    # b) At current rack rate
    at_current_rate = min(max(current_otb_rev + current_rate_pickup, current_otb_rev), revenue_ceiling)
    # c) Cheaper 50%: if bookings come in at lower end of prior distribution
    at_cheaper_50 = min(max(current_otb_rev + cheaper_50_pickup, current_otb_rev), revenue_ceiling)
    # d) Expensive 50%: if bookings come in at higher end of prior distribution
    at_expensive_50 = min(max(current_otb_rev + expensive_50_pickup, current_otb_rev), revenue_ceiling)

    # Forecast = prior year ADR, but capped at current rate (can't exceed what's achievable)
    # If current rates are lower than prior, we're limited to current rate
    forecast = min(at_prior_adr, at_current_rate)

    # Bounds = min/max of all 4 scenarios (forecast will naturally fall in between)
    all_scenarios = [at_prior_adr, at_current_rate, at_cheaper_50, at_expensive_50]
    upper_bound = max(all_scenarios)
    lower_bound = min(all_scenarios)

    # Rate gap: current rate vs prior ADR (negative = opportunity)
    rate_gap = at_current_rate - at_prior_adr

    # Calculate weighted average rates (per room) for display
    # Uses actual gross rates from tariffs (including breakfast, VAT, etc.)
    weighted_avg_prior_rate = 0.0
    weighted_avg_current_rate = 0.0
    weighted_avg_prior_rate_gross = 0.0
    weighted_avg_current_rate_gross = 0.0
    # Listed rate = earliest bookings, for rate comparison at same lead time
    weighted_avg_listed_rate = 0.0
    weighted_avg_listed_rate_gross = 0.0
    # Effective rate = rate actually used in forecast (min of prior and current)
    effective_rate = 0.0
    effective_rate_gross = 0.0
    if total_pickup_rooms > 0:
        weighted_avg_prior_rate = float(forecast_pickup / Decimal(total_pickup_rooms))
        weighted_avg_current_rate = float(current_rate_pickup / Decimal(total_pickup_rooms))
        # Use actual gross rates from booking tariffs, not calculated
        weighted_avg_prior_rate_gross = float(forecast_pickup_gross / Decimal(total_pickup_rooms))
        weighted_avg_current_rate_gross = float(current_rate_pickup_gross / Decimal(total_pickup_rooms))
        # Listed rate (earliest bookings) for rate comparison
        weighted_avg_listed_rate = float(listed_rate_pickup / Decimal(total_pickup_rooms))
        weighted_avg_listed_rate_gross = float(listed_rate_pickup_gross / Decimal(total_pickup_rooms))
        # Effective rate: the rate actually used in forecast = min(prior, current)
        # If current rate is lower, forecast is capped at what's achievable at current prices
        if current_rate_pickup < forecast_pickup:
            effective_rate = weighted_avg_current_rate
            effective_rate_gross = weighted_avg_current_rate_gross
        else:
            effective_rate = weighted_avg_prior_rate
            effective_rate_gross = weighted_avg_prior_rate_gross

    # Lost potential: compare current rate vs LISTED rate per room
    # Only show lost potential if current rate is LOWER than what was offered at this lead time
    # If current rate is higher, there's no lost potential - we're doing better!
    if current_rate_pickup < listed_rate_pickup:
        lost_potential = listed_rate_pickup - current_rate_pickup
    else:
        lost_potential = Decimal('0')
    has_pricing_opportunity = lost_potential > 0

    # Rate position vs listed rate (what was being offered at this lead time)
    # Positive = current rate is higher (good), Negative = current rate is lower (opportunity)
    rate_vs_prior_pct = 0.0
    if listed_rate_pickup > 0:
        rate_vs_prior_pct = float((current_rate_pickup - listed_rate_pickup) / listed_rate_pickup * 100)

    # Calculate pace vs prior year
    pace_vs_prior_pct = 0.0
    if prior_otb_rev > 0:
        pace_vs_prior_pct = float((current_otb_rev - prior_otb_rev) / prior_otb_rev * 100)

    # Legacy pickup calc for comparison
    expected_pickup_rev = prior_final_rev - prior_otb_rev if prior_final_rev > 0 else Decimal('0')

    result = {
        'current_otb_rev': float(current_otb_rev),
        'current_otb': current_otb_rooms_total,  # Room count for display
        'current_otb_rooms': current_otb_rooms_total,  # Alias for compatibility
        'prior_year_otb_rev': float(prior_otb_rev),
        'prior_year_final_rev': float(prior_final_rev),
        'expected_pickup_rev': float(expected_pickup_rev),  # Legacy revenue-based pickup
        'pickup_rooms_total': total_pickup_rooms,
        'forecast_pickup_rev': float(forecast_pickup),  # Pickup revenue at prior ADR
        'forecast': float(forecast),
        'predicted_value': float(forecast),  # For compatibility with blended model
        # 4 scenarios
        'at_prior_adr': float(at_prior_adr),            # a) Pickup at prior year ADR (forecast)
        'at_current_rate': float(at_current_rate),      # b) Pickup at current rack rates
        'at_cheaper_50': float(at_cheaper_50),          # c) Pickup at cheaper 50% of prior rates
        'at_expensive_50': float(at_expensive_50),      # d) Pickup at expensive 50% of prior rates
        # Bounds (min/max of all scenarios)
        'upper_bound': float(upper_bound),
        'lower_bound': float(lower_bound),
        'ceiling': float(revenue_ceiling),  # Max if all remaining rooms sell at expensive 50%
        'rate_gap': float(rate_gap),                    # Negative = current rate below prior ADR
        'lost_potential': float(lost_potential),        # Revenue left on table (0 if none)
        'has_pricing_opportunity': has_pricing_opportunity,  # True if current < prior ADR
        'rate_vs_prior_pct': round(rate_vs_prior_pct, 1),
        'pace_vs_prior_pct': round(pace_vs_prior_pct, 1),
        # Weighted average rates per room for display (net) - avg of all pickups for forecast
        'weighted_avg_prior_rate': round(weighted_avg_prior_rate, 2),
        'weighted_avg_current_rate': round(weighted_avg_current_rate, 2),
        # Gross rates (inc VAT) for UI reference when adjusting rates
        'weighted_avg_prior_rate_gross': round(weighted_avg_prior_rate_gross, 2),
        'weighted_avg_current_rate_gross': round(weighted_avg_current_rate_gross, 2),
        # Listed rate at lead time (earliest bookings) - for rate comparison
        'weighted_avg_listed_rate': round(weighted_avg_listed_rate, 2),
        'weighted_avg_listed_rate_gross': round(weighted_avg_listed_rate_gross, 2),
        # Effective rate = rate actually used in forecast (min of prior and current)
        'effective_rate': round(effective_rate, 2),
        'effective_rate_gross': round(effective_rate_gross, 2)
    }

    if include_details:
        result['category_breakdown'] = category_breakdown
        result['explanation'] = {
            'method': 'room_based_category_pickup',
            'formula': 'Forecast = min(at_prior_adr, at_current_rate) - capped at achievable',
            'scenarios': {
                'a_prior_adr': 'OTB + pickup × prior year ADR (what actually happened)',
                'b_current': 'OTB + pickup × current rack rate (what we can achieve now)',
                'c_cheaper_50': 'OTB + pickup × avg of cheaper 50% of prior bookings',
                'd_expensive_50': 'OTB + pickup × avg of expensive 50% of prior bookings'
            },
            'bounds': 'Upper = max of all 4 scenarios, Lower = min of all 4',
            'ceiling': 'OTB + (remaining_rooms × expensive_50_rate) - physical capacity limit',
            'rate_gap': 'at_current_rate - at_prior_adr (negative = opportunity to raise rates)'
        }

    return result


async def forecast_rooms_for_date(
    db,
    stay_date: date,
    lead_days: int,
    prior_date: date,
    metric_code: str,
    include_details: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Generate room/occupancy forecast for a single date using category-based pickup.

    Uses same bookings-based approach as revenue forecast for consistency.
    Formula: Forecast = Current OTB Rooms + Σ(pickup_rooms[cat])
    Floor: Current OTB
    Ceiling: Bookable capacity
    """
    # Get current OTB rooms by category
    current_otb_by_cat = await get_current_otb_rooms_by_category(db, stay_date)
    current_otb_rooms = sum(current_otb_by_cat.values())

    # Get prior year pickup rooms by category (from bookings data)
    pickup_rooms_by_cat = await get_prior_year_pickup_rooms_by_category(db, prior_date, lead_days)
    total_pickup_rooms = sum(pickup_rooms_by_cat.values())

    # Get prior year totals for comparison (from bookings data)
    prior_otb_by_cat = await get_prior_year_otb_rooms_by_category(db, prior_date, lead_days)
    prior_otb_rooms = sum(prior_otb_by_cat.values())
    prior_final_by_cat = await get_prior_year_final_rooms_by_category(db, prior_date)
    prior_final_rooms = sum(prior_final_by_cat.values())

    # Get bookable capacity
    bookable = await get_bookable_rooms(db, stay_date)
    capacity_by_cat = await get_category_availability(db, stay_date)

    # Build category breakdown
    category_breakdown: Dict[str, Dict[str, Any]] = {}
    all_categories = set(
        list(current_otb_by_cat.keys()) +
        list(pickup_rooms_by_cat.keys()) +
        list(capacity_by_cat.keys())
    )

    for cat_id in all_categories:
        cat_otb = current_otb_by_cat.get(cat_id, 0)
        cat_pickup = pickup_rooms_by_cat.get(cat_id, 0)
        cat_capacity = capacity_by_cat.get(cat_id, 0)
        cat_forecast = min(cat_otb + cat_pickup, cat_capacity) if cat_capacity > 0 else cat_otb + cat_pickup

        category_breakdown[cat_id] = {
            'current_otb': cat_otb,
            'pickup_rooms': cat_pickup,
            'forecast': cat_forecast,
            'capacity': cat_capacity,
            'prior_otb': prior_otb_by_cat.get(cat_id, 0),
            'prior_final': prior_final_by_cat.get(cat_id, 0)
        }

    # Base forecast
    forecast_rooms = current_otb_rooms + total_pickup_rooms

    # Apply floor and ceiling
    forecast_rooms = max(forecast_rooms, current_otb_rooms)  # Floor: current OTB
    forecast_rooms = min(forecast_rooms, bookable) if bookable > 0 else forecast_rooms  # Ceiling: capacity

    # Calculate pace vs prior year
    pace_vs_prior_pct = 0.0
    if prior_otb_rooms > 0:
        pace_vs_prior_pct = float((current_otb_rooms - prior_otb_rooms) / prior_otb_rooms * 100)

    # Convert to appropriate metric
    if metric_code == 'hotel_occupancy_pct':
        predicted_value = (forecast_rooms / bookable * 100) if bookable > 0 else 0
        current_otb_val = (current_otb_rooms / bookable * 100) if bookable > 0 else 0
        ceiling_val = 100.0
    else:
        predicted_value = forecast_rooms
        current_otb_val = current_otb_rooms
        ceiling_val = bookable

    result = {
        'current_otb': current_otb_val,
        'current_otb_rooms': current_otb_rooms,
        'prior_year_otb': prior_otb_rooms,
        'prior_year_final': prior_final_rooms,
        'pickup_rooms_total': total_pickup_rooms,
        'expected_pickup': total_pickup_rooms,  # For compatibility
        'forecast': predicted_value,
        'predicted_value': predicted_value,
        'ceiling': ceiling_val,
        'floor': current_otb_val,
        'pace_vs_prior_pct': round(pace_vs_prior_pct, 1)
    }

    if include_details:
        result['category_breakdown'] = category_breakdown
        result['explanation'] = {
            'method': 'category_based_pickup',
            'formula': 'Current OTB + Σ(pickup_rooms[cat])',
            'floor': 'Current OTB rooms',
            'ceiling': 'Bookable room capacity'
        }

    return result


async def get_pickup_v2_summary(
    db,
    start_date: date,
    end_date: date,
    metric_code: str = 'net_accom'
) -> Dict[str, Any]:
    """
    Get summary statistics for a pickup-v2 forecast range.
    """
    forecasts = await run_pickup_v2_forecast(db, metric_code, start_date, end_date)

    if not forecasts:
        return {
            'days_count': 0,
            'message': 'No forecast data available'
        }

    if metric_code == 'net_accom':
        return {
            'otb_rev_total': sum(f.get('current_otb_rev', 0) for f in forecasts),
            'forecast_total': sum(f.get('forecast', 0) for f in forecasts),
            'upper_total': sum(f.get('upper_bound', 0) for f in forecasts),
            'lower_total': sum(f.get('lower_bound', 0) for f in forecasts),
            'prior_final_total': sum(f.get('prior_year_final_rev', 0) for f in forecasts),
            'avg_adr_position': sum(f.get('adr_position', 0.5) for f in forecasts) / len(forecasts),
            'avg_pace_pct': sum(f.get('pace_vs_prior_pct', 0) for f in forecasts) / len(forecasts),
            'days_count': len(forecasts)
        }
    else:
        return {
            'otb_total': sum(f.get('current_otb', 0) for f in forecasts),
            'forecast_total': sum(f.get('forecast', 0) for f in forecasts),
            'prior_final_total': sum(f.get('prior_year_final', 0) for f in forecasts),
            'avg_pace_pct': sum(f.get('pace_vs_prior_pct', 0) for f in forecasts) / len(forecasts),
            'days_count': len(forecasts)
        }
