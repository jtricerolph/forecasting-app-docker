"""
Reports API endpoints
Provide aggregated data for frontend reports and visualizations
"""
from datetime import date, datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

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
