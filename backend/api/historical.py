"""
Historical data API endpoints
Provides access to aggregated actual data from daily_occupancy and daily_covers
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db
from auth import get_current_user

router = APIRouter()


@router.get("/occupancy")
async def get_occupancy_data(
    from_date: Optional[date] = Query(None, description="Start date"),
    to_date: Optional[date] = Query(None, description="End date"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get historical occupancy data from daily_occupancy table.
    """
    if from_date is None:
        from_date = date.today() - timedelta(days=30)
    if to_date is None:
        to_date = date.today()

    query = """
        SELECT
            date,
            total_rooms,
            occupied_rooms,
            occupancy_pct,
            total_guests,
            total_adults,
            total_children,
            total_infants,
            arrival_count,
            room_revenue,
            adr,
            revpar,
            agr,
            breakfast_allocation_qty,
            dinner_allocation_qty,
            by_room_type,
            revenue_by_room_type
        FROM daily_occupancy
        WHERE date BETWEEN :from_date AND :to_date
        ORDER BY date
    """

    result = await db.execute(text(query), {"from_date": from_date, "to_date": to_date})
    rows = result.fetchall()

    return [
        {
            "date": row.date,
            "total_rooms": row.total_rooms,
            "occupied_rooms": row.occupied_rooms,
            "occupancy_pct": float(row.occupancy_pct) if row.occupancy_pct else 0,
            "total_guests": row.total_guests,
            "total_adults": row.total_adults,
            "total_children": row.total_children,
            "total_infants": row.total_infants,
            "arrival_count": row.arrival_count,
            "room_revenue": float(row.room_revenue) if row.room_revenue else 0,
            "adr": float(row.adr) if row.adr else 0,
            "revpar": float(row.revpar) if row.revpar else 0,
            "agr": float(row.agr) if row.agr else 0,
            "breakfast_allocation_qty": row.breakfast_allocation_qty,
            "dinner_allocation_qty": row.dinner_allocation_qty,
            "by_room_type": row.by_room_type,
            "revenue_by_room_type": row.revenue_by_room_type
        }
        for row in rows
    ]


@router.get("/covers")
async def get_covers_data(
    from_date: Optional[date] = Query(None, description="Start date"),
    to_date: Optional[date] = Query(None, description="End date"),
    service_period: Optional[str] = Query(None, description="Filter by: lunch, dinner"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get historical covers data from daily_covers table.
    """
    if from_date is None:
        from_date = date.today() - timedelta(days=30)
    if to_date is None:
        to_date = date.today()

    query = """
        SELECT
            date,
            service_period,
            total_bookings,
            total_covers,
            avg_party_size,
            hotel_guest_covers,
            external_covers,
            dbb_covers,
            package_covers,
            cancelled_bookings,
            cancelled_covers,
            no_show_bookings,
            no_show_covers,
            by_source
        FROM daily_covers
        WHERE date BETWEEN :from_date AND :to_date
    """

    params = {"from_date": from_date, "to_date": to_date}

    if service_period:
        query += " AND service_period = :service_period"
        params["service_period"] = service_period

    query += " ORDER BY date, service_period"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "date": row.date,
            "service_period": row.service_period,
            "total_bookings": row.total_bookings,
            "total_covers": row.total_covers,
            "avg_party_size": float(row.avg_party_size) if row.avg_party_size else 0,
            "hotel_guest_covers": row.hotel_guest_covers,
            "external_covers": row.external_covers,
            "dbb_covers": row.dbb_covers,
            "package_covers": row.package_covers,
            "cancelled_bookings": row.cancelled_bookings,
            "cancelled_covers": row.cancelled_covers,
            "no_show_bookings": row.no_show_bookings,
            "no_show_covers": row.no_show_covers,
            "by_source": row.by_source
        }
        for row in rows
    ]


@router.get("/summary")
async def get_daily_summary(
    from_date: Optional[date] = Query(None, description="Start date"),
    to_date: Optional[date] = Query(None, description="End date"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get combined daily summary with occupancy and covers data.
    """
    if from_date is None:
        from_date = date.today() - timedelta(days=30)
    if to_date is None:
        to_date = date.today()

    query = """
        SELECT
            o.date,
            EXTRACT(DOW FROM o.date) as day_of_week,
            o.total_rooms,
            o.available_rooms,
            o.occupied_rooms,
            o.occupancy_pct,
            o.total_guests,
            o.room_revenue,
            o.adr,
            o.revpar,
            o.agr,
            o.arrival_count,
            o.breakfast_allocation_qty,
            o.dinner_allocation_qty,
            COALESCE(cl.total_covers, 0) as lunch_covers,
            COALESCE(cd.total_covers, 0) as dinner_covers,
            COALESCE(cl.total_bookings, 0) as lunch_bookings,
            COALESCE(cd.total_bookings, 0) as dinner_bookings
        FROM daily_occupancy o
        LEFT JOIN daily_covers cl ON o.date = cl.date AND cl.service_period = 'lunch'
        LEFT JOIN daily_covers cd ON o.date = cd.date AND cd.service_period = 'dinner'
        WHERE o.date BETWEEN :from_date AND :to_date
        ORDER BY o.date
    """

    result = await db.execute(text(query), {"from_date": from_date, "to_date": to_date})
    rows = result.fetchall()

    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    return [
        {
            "date": row.date,
            "day_of_week": day_names[int(row.day_of_week)],
            "total_rooms": row.total_rooms,
            "available_rooms": row.available_rooms,
            "occupied_rooms": row.occupied_rooms,
            "occupancy_pct": float(row.occupancy_pct) if row.occupancy_pct else 0,
            "total_guests": row.total_guests,
            "room_revenue": float(row.room_revenue) if row.room_revenue else 0,
            "adr": float(row.adr) if row.adr else 0,
            "revpar": float(row.revpar) if row.revpar else 0,
            "agr": float(row.agr) if row.agr else 0,
            "arrival_count": row.arrival_count,
            "breakfast_allocation_qty": row.breakfast_allocation_qty,
            "dinner_allocation_qty": row.dinner_allocation_qty,
            "lunch_covers": row.lunch_covers,
            "dinner_covers": row.dinner_covers,
            "lunch_bookings": row.lunch_bookings,
            "dinner_bookings": row.dinner_bookings
        }
        for row in rows
    ]
