"""
Room capacity utilities

Functions for getting bookable room counts accounting for maintenance.
"""
from datetime import date
from sqlalchemy import text


def get_bookable_cap_sync(db, forecast_date: date = None, fallback_value: int = 25) -> int:
    """
    Get the bookable rooms cap for a specific date (synchronous version).

    Bookable = Total Rooms - Maintenance - Allotted

    Args:
        db: Synchronous database session
        forecast_date: Specific date to get cap for (optional)
        fallback_value: Default if no data found

    Returns:
        Bookable room count (cap for room forecasts)
    """
    # First try to get specific date's bookable count from stats
    if forecast_date:
        result = db.execute(text("""
            SELECT bookable_count
            FROM newbook_bookings_stats
            WHERE date = :target_date AND bookable_count IS NOT NULL
        """), {"target_date": forecast_date})
        row = result.fetchone()
        if row and row.bookable_count is not None:
            return int(row.bookable_count)

        # Try occupancy report data for future dates
        result = db.execute(text("""
            SELECT
                SUM(COALESCE(o.available, 0) - COALESCE(o.maintenance, 0)) as bookable
            FROM newbook_occupancy_report_data o
            JOIN newbook_room_categories c ON o.category_id = c.site_id
            WHERE o.date = :target_date AND c.is_included = true
        """), {"target_date": forecast_date})
        row = result.fetchone()
        if row and row.bookable is not None:
            return int(row.bookable)

    # Fall back to most recent bookable_count
    result = db.execute(text("""
        SELECT bookable_count
        FROM newbook_bookings_stats
        WHERE bookable_count IS NOT NULL
        ORDER BY date DESC
        LIMIT 1
    """))
    row = result.fetchone()
    if row and row.bookable_count:
        return int(row.bookable_count)

    return fallback_value


async def get_bookable_cap(db, forecast_date: date = None, fallback_value: int = 25) -> int:
    """
    Get the bookable rooms cap for a specific date.

    Bookable = Total Rooms - Maintenance - Allotted

    For future dates without stats data, tries occupancy report data first,
    then falls back to most recent bookable_count from stats.

    Args:
        db: Database session
        forecast_date: Specific date to get cap for (optional)
        fallback_value: Default if no data found

    Returns:
        Bookable room count (cap for room forecasts)
    """
    # First try to get specific date's bookable count from stats
    if forecast_date:
        result = await db.execute(text("""
            SELECT bookable_count
            FROM newbook_bookings_stats
            WHERE date = :target_date AND bookable_count IS NOT NULL
        """), {"target_date": forecast_date})
        row = result.fetchone()
        # Accept 0 as valid (all rooms in maintenance)
        if row and row.bookable_count is not None:
            return int(row.bookable_count)

        # Try occupancy report data for future dates
        result = await db.execute(text("""
            SELECT
                SUM(COALESCE(o.available, 0) - COALESCE(o.maintenance, 0)) as bookable
            FROM newbook_occupancy_report_data o
            JOIN newbook_room_categories c ON o.category_id = c.site_id
            WHERE o.date = :target_date AND c.is_included = true
        """), {"target_date": forecast_date})
        row = result.fetchone()
        # Accept 0 as valid bookable count (all rooms in maintenance)
        if row and row.bookable is not None:
            return int(row.bookable)

    # Fall back to most recent bookable_count
    result = await db.execute(text("""
        SELECT bookable_count
        FROM newbook_bookings_stats
        WHERE bookable_count IS NOT NULL
        ORDER BY date DESC
        LIMIT 1
    """))
    row = result.fetchone()
    if row and row.bookable_count:
        return int(row.bookable_count)

    return fallback_value
