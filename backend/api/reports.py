"""
Reports API endpoints
Provide aggregated data for frontend reports and visualizations
"""
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
import calendar

from database import get_db
from auth import get_current_user

router = APIRouter()


# ============================================
# RESPONSE MODELS
# ============================================

class OccupancyDataPoint(BaseModel):
    date: str
    total_occupancy_pct: Optional[float] = None
    bookable_occupancy_pct: Optional[float] = None
    booking_count: int = 0
    rooms_count: int = 0
    bookable_count: int = 0


class BookingsDataPoint(BaseModel):
    date: str
    booking_count: int = 0
    guests_count: int = 0
    rooms_count: int = 0


class RatesDataPoint(BaseModel):
    date: str
    guest_rate_total: float = 0.0
    net_booking_rev_total: float = 0.0
    booking_count: int = 0
    avg_guest_rate: Optional[float] = None
    avg_net_rate: Optional[float] = None


class RevenueDataPoint(BaseModel):
    date: str
    accommodation: float = 0.0
    dry: float = 0.0
    wet: float = 0.0
    total: float = 0.0


# ============================================
# OCCUPANCY REPORT ENDPOINT
# ============================================

@router.get("/occupancy", response_model=List[OccupancyDataPoint])
async def get_occupancy_report(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    consolidation: str = Query("day", description="Consolidation period: day, week, or month"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get occupancy data for the specified date range with optional consolidation.

    - **day**: Returns daily data points
    - **week**: Aggregates by week (Monday start)
    - **month**: Aggregates by month
    """
    # Validate dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    if consolidation not in ["day", "week", "month"]:
        raise HTTPException(status_code=400, detail="Consolidation must be 'day', 'week', or 'month'")

    # Build the query based on consolidation type
    # Use generate_series to include all dates in range, even those without data
    if consolidation == "day":
        query = text("""
            SELECT
                to_char(d, 'YYYY-MM-DD') as period_date,
                COALESCE(s.total_occupancy_pct, 0) as total_occupancy_pct,
                COALESCE(s.bookable_occupancy_pct, 0) as bookable_occupancy_pct,
                COALESCE(s.booking_count, 0) as booking_count,
                COALESCE(s.rooms_count, 0) as rooms_count,
                COALESCE(s.bookable_count, 0) as bookable_count
            FROM generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) d
            LEFT JOIN newbook_bookings_stats s ON s.date = d
            ORDER BY d
        """)
    elif consolidation == "week":
        query = text("""
            WITH date_range AS (
                SELECT CAST(generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) AS date) as d
            ),
            weekly_data AS (
                SELECT
                    CAST(date_trunc('week', d) AS date) as week_start,
                    ROUND(CAST(AVG(COALESCE(s.total_occupancy_pct, 0)) AS numeric), 2) as total_occupancy_pct,
                    ROUND(CAST(AVG(COALESCE(s.bookable_occupancy_pct, 0)) AS numeric), 2) as bookable_occupancy_pct,
                    CAST(SUM(COALESCE(s.booking_count, 0)) AS integer) as booking_count,
                    CAST(ROUND(AVG(COALESCE(s.rooms_count, 0))) AS integer) as rooms_count,
                    CAST(ROUND(AVG(COALESCE(s.bookable_count, 0))) AS integer) as bookable_count
                FROM date_range dr
                LEFT JOIN newbook_bookings_stats s ON s.date = dr.d
                GROUP BY date_trunc('week', d)
            )
            SELECT
                to_char(week_start, 'YYYY-MM-DD') as period_date,
                total_occupancy_pct,
                bookable_occupancy_pct,
                booking_count,
                rooms_count,
                bookable_count
            FROM weekly_data
            ORDER BY week_start
        """)
    else:  # month
        query = text("""
            WITH date_range AS (
                SELECT CAST(generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) AS date) as d
            ),
            monthly_data AS (
                SELECT
                    CAST(date_trunc('month', d) AS date) as month_start,
                    ROUND(CAST(AVG(COALESCE(s.total_occupancy_pct, 0)) AS numeric), 2) as total_occupancy_pct,
                    ROUND(CAST(AVG(COALESCE(s.bookable_occupancy_pct, 0)) AS numeric), 2) as bookable_occupancy_pct,
                    CAST(SUM(COALESCE(s.booking_count, 0)) AS integer) as booking_count,
                    CAST(ROUND(AVG(COALESCE(s.rooms_count, 0))) AS integer) as rooms_count,
                    CAST(ROUND(AVG(COALESCE(s.bookable_count, 0))) AS integer) as bookable_count
                FROM date_range dr
                LEFT JOIN newbook_bookings_stats s ON s.date = dr.d
                GROUP BY date_trunc('month', d)
            )
            SELECT
                to_char(month_start, 'YYYY-MM-DD') as period_date,
                total_occupancy_pct,
                bookable_occupancy_pct,
                booking_count,
                rooms_count,
                bookable_count
            FROM monthly_data
            ORDER BY month_start
        """)

    result = await db.execute(query, {"start_date": start, "end_date": end})
    rows = result.fetchall()

    data_points = []
    for row in rows:
        data_points.append(OccupancyDataPoint(
            date=row.period_date,
            total_occupancy_pct=float(row.total_occupancy_pct) if row.total_occupancy_pct else None,
            bookable_occupancy_pct=float(row.bookable_occupancy_pct) if row.bookable_occupancy_pct else None,
            booking_count=row.booking_count or 0,
            rooms_count=row.rooms_count or 0,
            bookable_count=row.bookable_count or 0,
        ))

    return data_points


# ============================================
# BOOKINGS REPORT ENDPOINT
# ============================================

@router.get("/bookings", response_model=List[BookingsDataPoint])
async def get_bookings_report(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    consolidation: str = Query("day", description="Consolidation period: day, week, or month"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get bookings and guests data for the specified date range with optional consolidation.
    """
    # Validate dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    if consolidation not in ["day", "week", "month"]:
        raise HTTPException(status_code=400, detail="Consolidation must be 'day', 'week', or 'month'")

    if consolidation == "day":
        query = text("""
            SELECT
                to_char(d, 'YYYY-MM-DD') as period_date,
                COALESCE(s.booking_count, 0) as booking_count,
                COALESCE(s.guests_count, 0) as guests_count,
                COALESCE(s.rooms_count, 0) as rooms_count
            FROM generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) d
            LEFT JOIN newbook_bookings_stats s ON s.date = d
            ORDER BY d
        """)
    elif consolidation == "week":
        query = text("""
            WITH date_range AS (
                SELECT CAST(generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) AS date) as d
            ),
            weekly_data AS (
                SELECT
                    CAST(date_trunc('week', d) AS date) as week_start,
                    CAST(SUM(COALESCE(s.booking_count, 0)) AS integer) as booking_count,
                    CAST(SUM(COALESCE(s.guests_count, 0)) AS integer) as guests_count,
                    CAST(ROUND(AVG(COALESCE(s.rooms_count, 0))) AS integer) as rooms_count
                FROM date_range dr
                LEFT JOIN newbook_bookings_stats s ON s.date = dr.d
                GROUP BY date_trunc('week', d)
            )
            SELECT
                to_char(week_start, 'YYYY-MM-DD') as period_date,
                booking_count,
                guests_count,
                rooms_count
            FROM weekly_data
            ORDER BY week_start
        """)
    else:  # month
        query = text("""
            WITH date_range AS (
                SELECT CAST(generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) AS date) as d
            ),
            monthly_data AS (
                SELECT
                    CAST(date_trunc('month', d) AS date) as month_start,
                    CAST(SUM(COALESCE(s.booking_count, 0)) AS integer) as booking_count,
                    CAST(SUM(COALESCE(s.guests_count, 0)) AS integer) as guests_count,
                    CAST(ROUND(AVG(COALESCE(s.rooms_count, 0))) AS integer) as rooms_count
                FROM date_range dr
                LEFT JOIN newbook_bookings_stats s ON s.date = dr.d
                GROUP BY date_trunc('month', d)
            )
            SELECT
                to_char(month_start, 'YYYY-MM-DD') as period_date,
                booking_count,
                guests_count,
                rooms_count
            FROM monthly_data
            ORDER BY month_start
        """)

    result = await db.execute(query, {"start_date": start, "end_date": end})
    rows = result.fetchall()

    data_points = []
    for row in rows:
        data_points.append(BookingsDataPoint(
            date=row.period_date,
            booking_count=row.booking_count or 0,
            guests_count=row.guests_count or 0,
            rooms_count=row.rooms_count or 0,
        ))

    return data_points


# ============================================
# RATES REPORT ENDPOINT
# ============================================

@router.get("/rates", response_model=List[RatesDataPoint])
async def get_rates_report(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    consolidation: str = Query("day", description="Consolidation period: day, week, or month"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get guest rates data (gross tariff / calculated amount) for the specified date range.
    """
    # Validate dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    if consolidation not in ["day", "week", "month"]:
        raise HTTPException(status_code=400, detail="Consolidation must be 'day', 'week', or 'month'")

    if consolidation == "day":
        query = text("""
            SELECT
                to_char(d, 'YYYY-MM-DD') as period_date,
                COALESCE(s.guest_rate_total, 0) as guest_rate_total,
                COALESCE(s.net_booking_rev_total, 0) as net_booking_rev_total,
                COALESCE(s.booking_count, 0) as booking_count
            FROM generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) d
            LEFT JOIN newbook_bookings_stats s ON s.date = d
            ORDER BY d
        """)
    elif consolidation == "week":
        query = text("""
            WITH date_range AS (
                SELECT CAST(generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) AS date) as d
            ),
            weekly_data AS (
                SELECT
                    CAST(date_trunc('week', d) AS date) as week_start,
                    ROUND(CAST(SUM(COALESCE(s.guest_rate_total, 0)) AS numeric), 2) as guest_rate_total,
                    ROUND(CAST(SUM(COALESCE(s.net_booking_rev_total, 0)) AS numeric), 2) as net_booking_rev_total,
                    CAST(SUM(COALESCE(s.booking_count, 0)) AS integer) as booking_count
                FROM date_range dr
                LEFT JOIN newbook_bookings_stats s ON s.date = dr.d
                GROUP BY date_trunc('week', d)
            )
            SELECT
                to_char(week_start, 'YYYY-MM-DD') as period_date,
                guest_rate_total,
                net_booking_rev_total,
                booking_count
            FROM weekly_data
            ORDER BY week_start
        """)
    else:  # month
        query = text("""
            WITH date_range AS (
                SELECT CAST(generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) AS date) as d
            ),
            monthly_data AS (
                SELECT
                    CAST(date_trunc('month', d) AS date) as month_start,
                    ROUND(CAST(SUM(COALESCE(s.guest_rate_total, 0)) AS numeric), 2) as guest_rate_total,
                    ROUND(CAST(SUM(COALESCE(s.net_booking_rev_total, 0)) AS numeric), 2) as net_booking_rev_total,
                    CAST(SUM(COALESCE(s.booking_count, 0)) AS integer) as booking_count
                FROM date_range dr
                LEFT JOIN newbook_bookings_stats s ON s.date = dr.d
                GROUP BY date_trunc('month', d)
            )
            SELECT
                to_char(month_start, 'YYYY-MM-DD') as period_date,
                guest_rate_total,
                net_booking_rev_total,
                booking_count
            FROM monthly_data
            ORDER BY month_start
        """)

    result = await db.execute(query, {"start_date": start, "end_date": end})
    rows = result.fetchall()

    data_points = []
    for row in rows:
        guest_rate = float(row.guest_rate_total) if row.guest_rate_total else 0.0
        net_rate = float(row.net_booking_rev_total) if row.net_booking_rev_total else 0.0
        bookings = row.booking_count or 0

        data_points.append(RatesDataPoint(
            date=row.period_date,
            guest_rate_total=guest_rate,
            net_booking_rev_total=net_rate,
            booking_count=bookings,
            avg_guest_rate=round(guest_rate / bookings, 2) if bookings > 0 else None,
            avg_net_rate=round(net_rate / bookings, 2) if bookings > 0 else None,
        ))

    return data_points


# ============================================
# REVENUE REPORT ENDPOINT
# ============================================

@router.get("/revenue", response_model=List[RevenueDataPoint])
async def get_revenue_report(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    consolidation: str = Query("day", description="Consolidation period: day, week, or month"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get net revenue data (accommodation, dry, wet) for the specified date range.
    """
    # Validate dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    if consolidation not in ["day", "week", "month"]:
        raise HTTPException(status_code=400, detail="Consolidation must be 'day', 'week', or 'month'")

    if consolidation == "day":
        query = text("""
            SELECT
                to_char(d, 'YYYY-MM-DD') as period_date,
                COALESCE(r.accommodation, 0) as accommodation,
                COALESCE(r.dry, 0) as dry,
                COALESCE(r.wet, 0) as wet
            FROM generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) d
            LEFT JOIN newbook_net_revenue_data r ON r.date = d
            ORDER BY d
        """)
    elif consolidation == "week":
        query = text("""
            WITH date_range AS (
                SELECT CAST(generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) AS date) as d
            ),
            weekly_data AS (
                SELECT
                    CAST(date_trunc('week', d) AS date) as week_start,
                    ROUND(CAST(SUM(COALESCE(r.accommodation, 0)) AS numeric), 2) as accommodation,
                    ROUND(CAST(SUM(COALESCE(r.dry, 0)) AS numeric), 2) as dry,
                    ROUND(CAST(SUM(COALESCE(r.wet, 0)) AS numeric), 2) as wet
                FROM date_range dr
                LEFT JOIN newbook_net_revenue_data r ON r.date = dr.d
                GROUP BY date_trunc('week', d)
            )
            SELECT
                to_char(week_start, 'YYYY-MM-DD') as period_date,
                accommodation,
                dry,
                wet
            FROM weekly_data
            ORDER BY week_start
        """)
    else:  # month
        query = text("""
            WITH date_range AS (
                SELECT CAST(generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) AS date) as d
            ),
            monthly_data AS (
                SELECT
                    CAST(date_trunc('month', d) AS date) as month_start,
                    ROUND(CAST(SUM(COALESCE(r.accommodation, 0)) AS numeric), 2) as accommodation,
                    ROUND(CAST(SUM(COALESCE(r.dry, 0)) AS numeric), 2) as dry,
                    ROUND(CAST(SUM(COALESCE(r.wet, 0)) AS numeric), 2) as wet
                FROM date_range dr
                LEFT JOIN newbook_net_revenue_data r ON r.date = dr.d
                GROUP BY date_trunc('month', d)
            )
            SELECT
                to_char(month_start, 'YYYY-MM-DD') as period_date,
                accommodation,
                dry,
                wet
            FROM monthly_data
            ORDER BY month_start
        """)

    result = await db.execute(query, {"start_date": start, "end_date": end})
    rows = result.fetchall()

    data_points = []
    for row in rows:
        accom = float(row.accommodation) if row.accommodation else 0.0
        dry = float(row.dry) if row.dry else 0.0
        wet = float(row.wet) if row.wet else 0.0

        data_points.append(RevenueDataPoint(
            date=row.period_date,
            accommodation=accom,
            dry=dry,
            wet=wet,
            total=round(accom + dry + wet, 2),
        ))

    return data_points


# ============================================
# RESTAURANT REPORTS
# ============================================

class ResosBookingsDataPoint(BaseModel):
    date: str
    total_bookings: int = 0
    breakfast_bookings: int = 0
    lunch_bookings: int = 0
    afternoon_bookings: int = 0
    dinner_bookings: int = 0
    other_bookings: int = 0


class ResosCoversDataPoint(BaseModel):
    date: str
    total_covers: int = 0
    breakfast_covers: int = 0
    lunch_covers: int = 0
    afternoon_covers: int = 0
    dinner_covers: int = 0
    other_covers: int = 0
    hotel_guest_covers: int = 0
    non_hotel_guest_covers: int = 0


@router.get("/restaurant-bookings", response_model=List[ResosBookingsDataPoint])
async def get_restaurant_bookings_report(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    consolidation: str = Query("day", description="Consolidation period: day, week, or month"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get restaurant bookings data for the specified date range with optional consolidation.
    """
    # Validate dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    if consolidation not in ["day", "week", "month"]:
        raise HTTPException(status_code=400, detail="Consolidation must be 'day', 'week', or 'month'")

    if consolidation == "day":
        query = text("""
            SELECT
                to_char(d, 'YYYY-MM-DD') as period_date,
                COALESCE(s.total_bookings, 0) as total_bookings,
                COALESCE(s.breakfast_bookings, 0) as breakfast_bookings,
                COALESCE(s.lunch_bookings, 0) as lunch_bookings,
                COALESCE(s.afternoon_bookings, 0) as afternoon_bookings,
                COALESCE(s.dinner_bookings, 0) as dinner_bookings,
                COALESCE(s.other_bookings, 0) as other_bookings
            FROM generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) d
            LEFT JOIN resos_bookings_stats s ON s.date = d
            ORDER BY d
        """)
    elif consolidation == "week":
        query = text("""
            WITH date_range AS (
                SELECT CAST(generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) AS date) as d
            ),
            weekly_data AS (
                SELECT
                    CAST(date_trunc('week', d) AS date) as week_start,
                    CAST(SUM(COALESCE(s.total_bookings, 0)) AS integer) as total_bookings,
                    CAST(SUM(COALESCE(s.breakfast_bookings, 0)) AS integer) as breakfast_bookings,
                    CAST(SUM(COALESCE(s.lunch_bookings, 0)) AS integer) as lunch_bookings,
                    CAST(SUM(COALESCE(s.afternoon_bookings, 0)) AS integer) as afternoon_bookings,
                    CAST(SUM(COALESCE(s.dinner_bookings, 0)) AS integer) as dinner_bookings,
                    CAST(SUM(COALESCE(s.other_bookings, 0)) AS integer) as other_bookings
                FROM date_range dr
                LEFT JOIN resos_bookings_stats s ON s.date = dr.d
                GROUP BY date_trunc('week', d)
            )
            SELECT
                to_char(week_start, 'YYYY-MM-DD') as period_date,
                total_bookings, breakfast_bookings, lunch_bookings,
                afternoon_bookings, dinner_bookings, other_bookings
            FROM weekly_data
            ORDER BY week_start
        """)
    else:  # month
        query = text("""
            WITH date_range AS (
                SELECT CAST(generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) AS date) as d
            ),
            monthly_data AS (
                SELECT
                    CAST(date_trunc('month', d) AS date) as month_start,
                    CAST(SUM(COALESCE(s.total_bookings, 0)) AS integer) as total_bookings,
                    CAST(SUM(COALESCE(s.breakfast_bookings, 0)) AS integer) as breakfast_bookings,
                    CAST(SUM(COALESCE(s.lunch_bookings, 0)) AS integer) as lunch_bookings,
                    CAST(SUM(COALESCE(s.afternoon_bookings, 0)) AS integer) as afternoon_bookings,
                    CAST(SUM(COALESCE(s.dinner_bookings, 0)) AS integer) as dinner_bookings,
                    CAST(SUM(COALESCE(s.other_bookings, 0)) AS integer) as other_bookings
                FROM date_range dr
                LEFT JOIN resos_bookings_stats s ON s.date = dr.d
                GROUP BY date_trunc('month', d)
            )
            SELECT
                to_char(month_start, 'YYYY-MM-DD') as period_date,
                total_bookings, breakfast_bookings, lunch_bookings,
                afternoon_bookings, dinner_bookings, other_bookings
            FROM monthly_data
            ORDER BY month_start
        """)

    result = await db.execute(query, {"start_date": start, "end_date": end})
    rows = result.fetchall()

    data_points = []
    for row in rows:
        data_points.append(ResosBookingsDataPoint(
            date=row.period_date,
            total_bookings=row.total_bookings or 0,
            breakfast_bookings=row.breakfast_bookings or 0,
            lunch_bookings=row.lunch_bookings or 0,
            afternoon_bookings=row.afternoon_bookings or 0,
            dinner_bookings=row.dinner_bookings or 0,
            other_bookings=row.other_bookings or 0,
        ))

    return data_points


@router.get("/restaurant-covers", response_model=List[ResosCoversDataPoint])
async def get_restaurant_covers_report(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    consolidation: str = Query("day", description="Consolidation period: day, week, or month"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get restaurant covers (guests) data for the specified date range with optional consolidation.
    """
    # Validate dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    if consolidation not in ["day", "week", "month"]:
        raise HTTPException(status_code=400, detail="Consolidation must be 'day', 'week', or 'month'")

    if consolidation == "day":
        query = text("""
            SELECT
                to_char(d, 'YYYY-MM-DD') as period_date,
                COALESCE(s.total_covers, 0) as total_covers,
                COALESCE(s.breakfast_covers, 0) as breakfast_covers,
                COALESCE(s.lunch_covers, 0) as lunch_covers,
                COALESCE(s.afternoon_covers, 0) as afternoon_covers,
                COALESCE(s.dinner_covers, 0) as dinner_covers,
                COALESCE(s.other_covers, 0) as other_covers,
                COALESCE(s.hotel_guest_covers, 0) as hotel_guest_covers,
                COALESCE(s.non_hotel_guest_covers, 0) as non_hotel_guest_covers
            FROM generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) d
            LEFT JOIN resos_bookings_stats s ON s.date = d
            ORDER BY d
        """)
    elif consolidation == "week":
        query = text("""
            WITH date_range AS (
                SELECT CAST(generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) AS date) as d
            ),
            weekly_data AS (
                SELECT
                    CAST(date_trunc('week', d) AS date) as week_start,
                    CAST(SUM(COALESCE(s.total_covers, 0)) AS integer) as total_covers,
                    CAST(SUM(COALESCE(s.breakfast_covers, 0)) AS integer) as breakfast_covers,
                    CAST(SUM(COALESCE(s.lunch_covers, 0)) AS integer) as lunch_covers,
                    CAST(SUM(COALESCE(s.afternoon_covers, 0)) AS integer) as afternoon_covers,
                    CAST(SUM(COALESCE(s.dinner_covers, 0)) AS integer) as dinner_covers,
                    CAST(SUM(COALESCE(s.other_covers, 0)) AS integer) as other_covers,
                    CAST(SUM(COALESCE(s.hotel_guest_covers, 0)) AS integer) as hotel_guest_covers,
                    CAST(SUM(COALESCE(s.non_hotel_guest_covers, 0)) AS integer) as non_hotel_guest_covers
                FROM date_range dr
                LEFT JOIN resos_bookings_stats s ON s.date = dr.d
                GROUP BY date_trunc('week', d)
            )
            SELECT
                to_char(week_start, 'YYYY-MM-DD') as period_date,
                total_covers, breakfast_covers, lunch_covers,
                afternoon_covers, dinner_covers, other_covers,
                hotel_guest_covers, non_hotel_guest_covers
            FROM weekly_data
            ORDER BY week_start
        """)
    else:  # month
        query = text("""
            WITH date_range AS (
                SELECT CAST(generate_series(CAST(:start_date AS date), CAST(:end_date AS date), CAST('1 day' AS interval)) AS date) as d
            ),
            monthly_data AS (
                SELECT
                    CAST(date_trunc('month', d) AS date) as month_start,
                    CAST(SUM(COALESCE(s.total_covers, 0)) AS integer) as total_covers,
                    CAST(SUM(COALESCE(s.breakfast_covers, 0)) AS integer) as breakfast_covers,
                    CAST(SUM(COALESCE(s.lunch_covers, 0)) AS integer) as lunch_covers,
                    CAST(SUM(COALESCE(s.afternoon_covers, 0)) AS integer) as afternoon_covers,
                    CAST(SUM(COALESCE(s.dinner_covers, 0)) AS integer) as dinner_covers,
                    CAST(SUM(COALESCE(s.other_covers, 0)) AS integer) as other_covers,
                    CAST(SUM(COALESCE(s.hotel_guest_covers, 0)) AS integer) as hotel_guest_covers,
                    CAST(SUM(COALESCE(s.non_hotel_guest_covers, 0)) AS integer) as non_hotel_guest_covers
                FROM date_range dr
                LEFT JOIN resos_bookings_stats s ON s.date = dr.d
                GROUP BY date_trunc('month', d)
            )
            SELECT
                to_char(month_start, 'YYYY-MM-DD') as period_date,
                total_covers, breakfast_covers, lunch_covers,
                afternoon_covers, dinner_covers, other_covers,
                hotel_guest_covers, non_hotel_guest_covers
            FROM monthly_data
            ORDER BY month_start
        """)

    result = await db.execute(query, {"start_date": start, "end_date": end})
    rows = result.fetchall()

    data_points = []
    for row in rows:
        data_points.append(ResosCoversDataPoint(
            date=row.period_date,
            total_covers=row.total_covers or 0,
            breakfast_covers=row.breakfast_covers or 0,
            lunch_covers=row.lunch_covers or 0,
            afternoon_covers=row.afternoon_covers or 0,
            dinner_covers=row.dinner_covers or 0,
            other_covers=row.other_covers or 0,
            hotel_guest_covers=row.hotel_guest_covers or 0,
            non_hotel_guest_covers=row.non_hotel_guest_covers or 0,
        ))

    return data_points


# ============================================
# 3D PICKUP VISUALIZATION ENDPOINT
# ============================================

class Pickup3DResponse(BaseModel):
    """Response model for 3D pickup visualization data"""
    start_date: str
    end_date: str
    metric: str
    consolidation: str
    arrival_dates: List[str]  # X-axis: dates in range
    lead_times: List[int]     # Y-axis: lead times (days out)
    surface_data: List[List[Optional[float]]]  # Z-axis: [lead_time][arrival_date] values
    final_values: List[Optional[float]]  # Final values (d0) for each arrival date


@router.get("/pickup-3d", response_model=Pickup3DResponse)
async def get_pickup_3d_data(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    metric: str = Query("rooms", description="Metric: rooms or occupancy"),
    consolidation: str = Query("day", description="Consolidation: day or week"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get 3D pickup visualization data for a date range.

    Returns booking pace data structured for a 3D surface plot:
    - X-axis: Arrival dates in the range
    - Y-axis: Lead time (days before arrival when booking count was recorded)
    - Z-axis: Room count or occupancy percentage

    This visualizes how bookings accumulated over time for each arrival date.
    """
    if metric not in ["rooms", "occupancy"]:
        raise HTTPException(status_code=400, detail="Metric must be 'rooms' or 'occupancy'")

    if consolidation not in ["day", "week"]:
        raise HTTPException(status_code=400, detail="Consolidation must be 'day' or 'week'")

    # Parse dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    # Define the lead times we want to show
    # We'll show a reasonable subset to keep the visualization manageable
    # Daily for d0-d30, weekly for d30-d90, monthly beyond that
    lead_time_columns = [
        # Daily (0-30 days)
        'd0', 'd1', 'd2', 'd3', 'd4', 'd5', 'd6', 'd7',
        'd8', 'd9', 'd10', 'd11', 'd12', 'd13', 'd14',
        'd15', 'd16', 'd17', 'd18', 'd19', 'd20', 'd21',
        'd22', 'd23', 'd24', 'd25', 'd26', 'd27', 'd28', 'd29', 'd30',
        # Weekly (37-93 days)
        'd37', 'd44', 'd51', 'd58', 'd65', 'd72', 'd79', 'd86', 'd93',
        # Further out (100+ days)
        'd100', 'd107', 'd114', 'd121', 'd128', 'd135', 'd142', 'd149',
        'd156', 'd163', 'd170', 'd177',
        # Monthly intervals
        'd210', 'd240', 'd270', 'd300', 'd330', 'd365',
    ]

    # Build select clause for available columns
    select_cols = ", ".join([f"COALESCE({col}, 0) as {col}" for col in lead_time_columns])

    query = text(f"""
        SELECT
            arrival_date,
            {select_cols}
        FROM newbook_booking_pace
        WHERE arrival_date >= :start_date AND arrival_date <= :end_date
        ORDER BY arrival_date
    """)

    result = await db.execute(query, {"start_date": start, "end_date": end})
    rows = result.fetchall()

    # Generate all dates in range
    all_dates = []
    current = start
    while current <= end:
        all_dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    if not rows:
        # Return empty structure if no data
        lead_times = [int(col[1:]) for col in lead_time_columns]
        return Pickup3DResponse(
            start_date=start_date,
            end_date=end_date,
            metric=metric,
            consolidation=consolidation,
            arrival_dates=all_dates,
            lead_times=lead_times,
            surface_data=[[None] * len(all_dates) for _ in lead_times],
            final_values=[None] * len(all_dates)
        )

    # Get total rooms for occupancy calculation
    total_rooms = 27  # Hotel Number Four has 27 rooms

    # Build the surface data
    row_data_dict = {}
    for row in rows:
        arr_date = row.arrival_date.strftime("%Y-%m-%d")
        row_data_dict[arr_date] = {col: getattr(row, col, 0) or 0 for col in lead_time_columns}

    # Handle weekly consolidation
    if consolidation == "week":
        # Group dates by week (Monday start)
        weekly_dates = []
        weekly_data = {}
        current = start
        week_start = None

        while current <= end:
            # Get Monday of this week
            days_since_monday = current.weekday()
            monday = current - timedelta(days=days_since_monday)
            week_label = monday.strftime("%Y-%m-%d")

            if week_label not in weekly_data:
                weekly_dates.append(week_label)
                weekly_data[week_label] = {col: [] for col in lead_time_columns}

            date_str = current.strftime("%Y-%m-%d")
            if date_str in row_data_dict:
                for col in lead_time_columns:
                    weekly_data[week_label][col].append(row_data_dict[date_str].get(col, 0) or 0)

            current += timedelta(days=1)

        # Average the weekly data
        all_dates = weekly_dates
        row_data_dict = {}
        for week_label in weekly_dates:
            row_data_dict[week_label] = {}
            for col in lead_time_columns:
                values = weekly_data[week_label][col]
                if values:
                    row_data_dict[week_label][col] = sum(values) / len(values)
                else:
                    row_data_dict[week_label][col] = 0

    # Build surface_data: [lead_time_index][arrival_date_index]
    lead_times = [int(col[1:]) for col in lead_time_columns]
    surface_data = []

    for col in lead_time_columns:
        lead_row = []
        for arr_date in all_dates:
            if arr_date in row_data_dict:
                value = row_data_dict[arr_date].get(col, 0) or 0
                if metric == "occupancy":
                    # Convert to occupancy percentage
                    value = round((value / total_rooms) * 100, 1) if total_rooms > 0 else 0
                lead_row.append(value)
            else:
                lead_row.append(None)
        surface_data.append(lead_row)

    # Get final values (d0) for each arrival date
    final_values = []
    for arr_date in all_dates:
        if arr_date in row_data_dict:
            value = row_data_dict[arr_date].get('d0', 0) or 0
            if metric == "occupancy":
                value = round((value / total_rooms) * 100, 1) if total_rooms > 0 else 0
            final_values.append(value)
        else:
            final_values.append(None)

    return Pickup3DResponse(
        start_date=start_date,
        end_date=end_date,
        metric=metric,
        consolidation=consolidation,
        arrival_dates=all_dates,
        lead_times=lead_times,
        surface_data=surface_data,
        final_values=final_values
    )
