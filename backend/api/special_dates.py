"""
Special Dates API - Configure custom holidays/events for Prophet forecasting
"""
from datetime import date, datetime, timedelta
from typing import Optional, List
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from database import get_db
from auth import get_current_user

router = APIRouter()


# ============================================
# MODELS
# ============================================

class DatePatternType(str, Enum):
    FIXED = "fixed"  # Fixed date each year (e.g., Feb 14)
    NTH_WEEKDAY = "nth_weekday"  # Nth weekday of month (e.g., 2nd Monday of Feb)
    RELATIVE_TO_DATE = "relative_to_date"  # Weekday before/after a fixed date


class SpecialDateBase(BaseModel):
    name: str
    pattern_type: DatePatternType
    # For FIXED pattern
    fixed_month: Optional[int] = None  # 1-12
    fixed_day: Optional[int] = None  # 1-31
    # For NTH_WEEKDAY pattern
    nth_week: Optional[int] = None  # 1-5 or -1 for last
    weekday: Optional[int] = None  # 0=Mon, 6=Sun
    month: Optional[int] = None  # 1-12
    # For RELATIVE_TO_DATE pattern
    relative_to_month: Optional[int] = None
    relative_to_day: Optional[int] = None
    relative_weekday: Optional[int] = None  # Which weekday to find
    relative_direction: Optional[str] = None  # 'before' or 'after'
    # Common fields
    duration_days: int = 1
    is_recurring: bool = True
    one_off_year: Optional[int] = None  # Only if is_recurring = False
    is_active: bool = True


class SpecialDateCreate(SpecialDateBase):
    pass


class SpecialDateUpdate(SpecialDateBase):
    pass


class SpecialDateResponse(SpecialDateBase):
    id: int
    created_at: str


class ResolvedDate(BaseModel):
    name: str
    date: str
    day_of_week: str


# ============================================
# TABLE CREATION
# ============================================

async def ensure_table_exists(db: AsyncSession):
    """Create the special_dates table if it doesn't exist"""
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS special_dates (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            pattern_type VARCHAR(20) NOT NULL,
            fixed_month INTEGER,
            fixed_day INTEGER,
            nth_week INTEGER,
            weekday INTEGER,
            month INTEGER,
            relative_to_month INTEGER,
            relative_to_day INTEGER,
            relative_weekday INTEGER,
            relative_direction VARCHAR(10),
            duration_days INTEGER DEFAULT 1,
            is_recurring BOOLEAN DEFAULT TRUE,
            one_off_year INTEGER,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """))
    await db.commit()


# ============================================
# DATE RESOLUTION HELPERS
# ============================================

def get_nth_weekday_of_month(year: int, month: int, weekday: int, nth: int) -> Optional[date]:
    """
    Get the nth occurrence of a weekday in a month.
    nth: 1-5 for first through fifth, -1 for last
    weekday: 0=Monday, 6=Sunday
    """
    if nth == -1:
        # Last occurrence - start from end of month
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        last_day = next_month - timedelta(days=1)

        # Find the last occurrence of the weekday
        days_back = (last_day.weekday() - weekday) % 7
        return last_day - timedelta(days=days_back)
    else:
        # Nth occurrence from start
        first_of_month = date(year, month, 1)
        # Find the first occurrence of the weekday
        days_ahead = (weekday - first_of_month.weekday()) % 7
        first_occurrence = first_of_month + timedelta(days=days_ahead)
        # Add weeks to get to nth occurrence
        result = first_occurrence + timedelta(weeks=nth - 1)
        # Verify it's still in the same month
        if result.month != month:
            return None
        return result


def get_weekday_relative_to_date(year: int, month: int, day: int,
                                  target_weekday: int, direction: str) -> Optional[date]:
    """
    Get a specific weekday before or after a fixed date.
    target_weekday: 0=Monday, 6=Sunday
    direction: 'before' or 'after'
    """
    try:
        base_date = date(year, month, day)
    except ValueError:
        return None

    if direction == 'before':
        # Find the weekday before (or on) the base date
        days_back = (base_date.weekday() - target_weekday) % 7
        if days_back == 0:
            days_back = 7  # If same weekday, go back a week
        return base_date - timedelta(days=days_back)
    else:  # after
        # Find the weekday after the base date
        days_ahead = (target_weekday - base_date.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7  # If same weekday, go forward a week
        return base_date + timedelta(days=days_ahead)


def resolve_special_date(sd: dict, year: int) -> List[date]:
    """Resolve a special date pattern to actual dates for a given year"""
    if not sd['is_recurring'] and sd.get('one_off_year') and sd['one_off_year'] != year:
        return []

    base_date = None
    pattern_type = sd['pattern_type']

    if pattern_type == 'fixed':
        try:
            base_date = date(year, sd['fixed_month'], sd['fixed_day'])
        except (ValueError, TypeError):
            return []

    elif pattern_type == 'nth_weekday':
        base_date = get_nth_weekday_of_month(
            year, sd['month'], sd['weekday'], sd['nth_week']
        )

    elif pattern_type == 'relative_to_date':
        base_date = get_weekday_relative_to_date(
            year, sd['relative_to_month'], sd['relative_to_day'],
            sd['relative_weekday'], sd['relative_direction']
        )

    if base_date is None:
        return []

    # Generate dates for duration
    duration = sd.get('duration_days', 1) or 1
    return [base_date + timedelta(days=i) for i in range(duration)]


# ============================================
# CRUD ENDPOINTS
# ============================================

@router.get("/special-dates", response_model=List[SpecialDateResponse])
async def list_special_dates(
    active_only: bool = Query(False, description="Only return active dates"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List all special date configurations"""
    await ensure_table_exists(db)

    query = "SELECT * FROM special_dates"
    if active_only:
        query += " WHERE is_active = TRUE"
    query += " ORDER BY name"

    result = await db.execute(text(query))
    rows = result.fetchall()

    return [
        SpecialDateResponse(
            id=row.id,
            name=row.name,
            pattern_type=row.pattern_type,
            fixed_month=row.fixed_month,
            fixed_day=row.fixed_day,
            nth_week=row.nth_week,
            weekday=row.weekday,
            month=row.month,
            relative_to_month=row.relative_to_month,
            relative_to_day=row.relative_to_day,
            relative_weekday=row.relative_weekday,
            relative_direction=row.relative_direction,
            duration_days=row.duration_days or 1,
            is_recurring=row.is_recurring,
            one_off_year=row.one_off_year,
            is_active=row.is_active,
            created_at=str(row.created_at)
        )
        for row in rows
    ]


@router.post("/special-dates", response_model=SpecialDateResponse)
async def create_special_date(
    data: SpecialDateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new special date configuration"""
    await ensure_table_exists(db)

    result = await db.execute(text("""
        INSERT INTO special_dates (
            name, pattern_type, fixed_month, fixed_day, nth_week, weekday, month,
            relative_to_month, relative_to_day, relative_weekday, relative_direction,
            duration_days, is_recurring, one_off_year, is_active
        ) VALUES (
            :name, :pattern_type, :fixed_month, :fixed_day, :nth_week, :weekday, :month,
            :relative_to_month, :relative_to_day, :relative_weekday, :relative_direction,
            :duration_days, :is_recurring, :one_off_year, :is_active
        ) RETURNING id, created_at
    """), {
        "name": data.name,
        "pattern_type": data.pattern_type.value,
        "fixed_month": data.fixed_month,
        "fixed_day": data.fixed_day,
        "nth_week": data.nth_week,
        "weekday": data.weekday,
        "month": data.month,
        "relative_to_month": data.relative_to_month,
        "relative_to_day": data.relative_to_day,
        "relative_weekday": data.relative_weekday,
        "relative_direction": data.relative_direction,
        "duration_days": data.duration_days,
        "is_recurring": data.is_recurring,
        "one_off_year": data.one_off_year,
        "is_active": data.is_active
    })

    row = result.fetchone()
    await db.commit()

    return SpecialDateResponse(
        id=row.id,
        created_at=str(row.created_at),
        **data.dict()
    )


@router.put("/special-dates/{date_id}", response_model=SpecialDateResponse)
async def update_special_date(
    date_id: int,
    data: SpecialDateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update a special date configuration"""
    result = await db.execute(text("""
        UPDATE special_dates SET
            name = :name,
            pattern_type = :pattern_type,
            fixed_month = :fixed_month,
            fixed_day = :fixed_day,
            nth_week = :nth_week,
            weekday = :weekday,
            month = :month,
            relative_to_month = :relative_to_month,
            relative_to_day = :relative_to_day,
            relative_weekday = :relative_weekday,
            relative_direction = :relative_direction,
            duration_days = :duration_days,
            is_recurring = :is_recurring,
            one_off_year = :one_off_year,
            is_active = :is_active,
            updated_at = NOW()
        WHERE id = :id
        RETURNING id, created_at
    """), {
        "id": date_id,
        "name": data.name,
        "pattern_type": data.pattern_type.value,
        "fixed_month": data.fixed_month,
        "fixed_day": data.fixed_day,
        "nth_week": data.nth_week,
        "weekday": data.weekday,
        "month": data.month,
        "relative_to_month": data.relative_to_month,
        "relative_to_day": data.relative_to_day,
        "relative_weekday": data.relative_weekday,
        "relative_direction": data.relative_direction,
        "duration_days": data.duration_days,
        "is_recurring": data.is_recurring,
        "one_off_year": data.one_off_year,
        "is_active": data.is_active
    })

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Special date not found")

    await db.commit()

    return SpecialDateResponse(
        id=row.id,
        created_at=str(row.created_at),
        **data.dict()
    )


@router.delete("/special-dates/{date_id}")
async def delete_special_date(
    date_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete a special date configuration"""
    result = await db.execute(
        text("DELETE FROM special_dates WHERE id = :id RETURNING id"),
        {"id": date_id}
    )

    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Special date not found")

    await db.commit()
    return {"message": "Special date deleted successfully"}


@router.get("/special-dates/preview", response_model=List[ResolvedDate])
async def preview_special_dates(
    year: int = Query(..., description="Year to preview dates for"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Preview resolved dates for a given year"""
    await ensure_table_exists(db)

    result = await db.execute(text(
        "SELECT * FROM special_dates WHERE is_active = TRUE ORDER BY name"
    ))
    rows = result.fetchall()

    resolved = []
    for row in rows:
        sd = {
            'pattern_type': row.pattern_type,
            'fixed_month': row.fixed_month,
            'fixed_day': row.fixed_day,
            'nth_week': row.nth_week,
            'weekday': row.weekday,
            'month': row.month,
            'relative_to_month': row.relative_to_month,
            'relative_to_day': row.relative_to_day,
            'relative_weekday': row.relative_weekday,
            'relative_direction': row.relative_direction,
            'duration_days': row.duration_days,
            'is_recurring': row.is_recurring,
            'one_off_year': row.one_off_year
        }

        dates = resolve_special_date(sd, year)
        for d in dates:
            resolved.append(ResolvedDate(
                name=row.name,
                date=str(d),
                day_of_week=d.strftime("%a")
            ))

    # Sort by date
    resolved.sort(key=lambda x: x.date)
    return resolved


@router.post("/special-dates/seed-defaults")
async def seed_default_dates(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Seed default special dates (Valentine's, Christmas Eve, NYE, Bank Holiday weekends)"""
    await ensure_table_exists(db)

    # Check if already seeded
    result = await db.execute(text("SELECT COUNT(*) as count FROM special_dates"))
    if result.fetchone().count > 0:
        return {"message": "Special dates already exist. Delete existing to re-seed."}

    defaults = [
        # Valentine's Day
        {
            "name": "Valentine's Day",
            "pattern_type": "fixed",
            "fixed_month": 2,
            "fixed_day": 14,
            "duration_days": 1
        },
        # Christmas Eve
        {
            "name": "Christmas Eve",
            "pattern_type": "fixed",
            "fixed_month": 12,
            "fixed_day": 24,
            "duration_days": 1
        },
        # New Year's Eve
        {
            "name": "New Year's Eve",
            "pattern_type": "fixed",
            "fixed_month": 12,
            "fixed_day": 31,
            "duration_days": 1
        },
        # Friday before Christmas (if Christmas is Sat-Tue)
        {
            "name": "Friday Before Christmas",
            "pattern_type": "relative_to_date",
            "relative_to_month": 12,
            "relative_to_day": 25,
            "relative_weekday": 4,  # Friday
            "relative_direction": "before",
            "duration_days": 1
        },
        # Saturday before Christmas
        {
            "name": "Saturday Before Christmas",
            "pattern_type": "relative_to_date",
            "relative_to_month": 12,
            "relative_to_day": 25,
            "relative_weekday": 5,  # Saturday
            "relative_direction": "before",
            "duration_days": 1
        },
        # Early May Bank Holiday Weekend (Fri-Sat of first Monday in May)
        {
            "name": "Early May BH Friday",
            "pattern_type": "nth_weekday",
            "month": 5,
            "nth_week": 1,
            "weekday": 4,  # Friday (before the Monday)
            "duration_days": 1
        },
        # Spring Bank Holiday Weekend (last Monday of May)
        {
            "name": "Spring BH Weekend",
            "pattern_type": "nth_weekday",
            "month": 5,
            "nth_week": -1,  # Last week
            "weekday": 5,  # Saturday
            "duration_days": 2  # Sat + Sun (Mon is the bank holiday itself)
        },
        # August Bank Holiday Weekend (last Monday of August)
        {
            "name": "August BH Weekend",
            "pattern_type": "nth_weekday",
            "month": 8,
            "nth_week": -1,
            "weekday": 5,  # Saturday
            "duration_days": 2
        },
    ]

    for d in defaults:
        await db.execute(text("""
            INSERT INTO special_dates (
                name, pattern_type, fixed_month, fixed_day, nth_week, weekday, month,
                relative_to_month, relative_to_day, relative_weekday, relative_direction,
                duration_days, is_recurring, is_active
            ) VALUES (
                :name, :pattern_type, :fixed_month, :fixed_day, :nth_week, :weekday, :month,
                :relative_to_month, :relative_to_day, :relative_weekday, :relative_direction,
                :duration_days, TRUE, TRUE
            )
        """), {
            "name": d["name"],
            "pattern_type": d["pattern_type"],
            "fixed_month": d.get("fixed_month"),
            "fixed_day": d.get("fixed_day"),
            "nth_week": d.get("nth_week"),
            "weekday": d.get("weekday"),
            "month": d.get("month"),
            "relative_to_month": d.get("relative_to_month"),
            "relative_to_day": d.get("relative_to_day"),
            "relative_weekday": d.get("relative_weekday"),
            "relative_direction": d.get("relative_direction"),
            "duration_days": d.get("duration_days", 1)
        })

    await db.commit()
    return {"message": f"Seeded {len(defaults)} default special dates"}


# ============================================
# HELPER FOR PROPHET INTEGRATION
# ============================================

async def get_special_dates_for_prophet(db: AsyncSession, start_year: int, end_year: int) -> List[dict]:
    """
    Get all special dates resolved for a range of years, formatted for Prophet.
    Returns list of dicts with 'ds' (date) and 'holiday' (name) columns.
    """
    await ensure_table_exists(db)

    result = await db.execute(text(
        "SELECT * FROM special_dates WHERE is_active = TRUE"
    ))
    rows = result.fetchall()

    prophet_holidays = []
    for year in range(start_year, end_year + 1):
        for row in rows:
            sd = {
                'pattern_type': row.pattern_type,
                'fixed_month': row.fixed_month,
                'fixed_day': row.fixed_day,
                'nth_week': row.nth_week,
                'weekday': row.weekday,
                'month': row.month,
                'relative_to_month': row.relative_to_month,
                'relative_to_day': row.relative_to_day,
                'relative_weekday': row.relative_weekday,
                'relative_direction': row.relative_direction,
                'duration_days': row.duration_days,
                'is_recurring': row.is_recurring,
                'one_off_year': row.one_off_year
            }

            dates = resolve_special_date(sd, year)
            for d in dates:
                # Prophet expects datetime objects, not date objects
                prophet_holidays.append({
                    'ds': datetime.combine(d, datetime.min.time()),
                    'holiday': row.name
                })

    return prophet_holidays
