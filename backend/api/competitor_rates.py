"""
Competitor Rates API endpoints
Booking.com rate scraping, hotel management, and competitor comparison
"""
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
import logging

from database import get_db, SyncSessionLocal
from auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class ScrapeRequest(BaseModel):
    from_date: str
    to_date: Optional[str] = None


class LocationConfigRequest(BaseModel):
    location_name: str
    pages_to_scrape: int = 2
    adults: int = 2


class HotelTierUpdate(BaseModel):
    tier: str  # 'own', 'competitor', 'market'
    display_order: Optional[int] = None


class HotelResponse(BaseModel):
    id: int
    booking_com_id: str
    name: str
    booking_com_url: Optional[str]
    star_rating: Optional[float]
    review_score: Optional[float]
    review_count: Optional[int]
    tier: str
    display_order: int
    notes: Optional[str]
    first_seen_at: Optional[datetime]
    last_seen_at: Optional[datetime]


class RateResponse(BaseModel):
    rate_date: str
    hotel_id: int
    hotel_name: str
    tier: str
    star_rating: Optional[float]
    review_score: Optional[float]
    availability_status: str
    rate_gross: Optional[float]
    room_type: Optional[str]
    breakfast_included: Optional[bool]
    free_cancellation: Optional[bool]
    no_prepayment: Optional[bool]
    rooms_left: Optional[int]
    scraped_at: Optional[datetime]


class ScraperStatusResponse(BaseModel):
    enabled: bool
    paused: bool
    pause_until: Optional[str]
    backend: str
    location_configured: bool
    location_name: Optional[str]
    last_scrape: Optional[dict]


# ============================================
# SCRAPER STATUS & CONFIGURATION
# ============================================

@router.get("/status", response_model=ScraperStatusResponse)
async def get_scraper_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get current scraper status and configuration."""
    # Get config values
    config_result = await db.execute(
        text("""
            SELECT config_key, config_value FROM system_config
            WHERE config_key IN (
                'booking_scraper_enabled',
                'booking_scraper_paused',
                'booking_scraper_pause_until',
                'booking_scraper_backend'
            )
        """)
    )
    config = {row.config_key: row.config_value for row in config_result.fetchall()}

    # Get location config
    location_result = await db.execute(
        text("SELECT location_name FROM booking_scrape_config WHERE is_active = TRUE LIMIT 1")
    )
    location_row = location_result.fetchone()

    # Get last scrape info
    last_scrape_result = await db.execute(
        text("""
            SELECT batch_id, scrape_type, started_at, completed_at, status,
                   hotels_found, rates_scraped, error_message
            FROM booking_scrape_log
            ORDER BY started_at DESC
            LIMIT 1
        """)
    )
    last_scrape_row = last_scrape_result.fetchone()
    last_scrape = None
    if last_scrape_row:
        last_scrape = {
            'batch_id': str(last_scrape_row.batch_id),
            'scrape_type': last_scrape_row.scrape_type,
            'started_at': last_scrape_row.started_at.isoformat() if last_scrape_row.started_at else None,
            'completed_at': last_scrape_row.completed_at.isoformat() if last_scrape_row.completed_at else None,
            'status': last_scrape_row.status,
            'hotels_found': last_scrape_row.hotels_found,
            'rates_scraped': last_scrape_row.rates_scraped,
            'error_message': last_scrape_row.error_message,
        }

    return ScraperStatusResponse(
        enabled=config.get('booking_scraper_enabled', 'false') == 'true',
        paused=config.get('booking_scraper_paused', 'false') == 'true',
        pause_until=config.get('booking_scraper_pause_until'),
        backend=config.get('booking_scraper_backend', 'playwright_local'),
        location_configured=location_row is not None,
        location_name=location_row.location_name if location_row else None,
        last_scrape=last_scrape
    )


@router.post("/config/location")
async def set_location_config(
    config: LocationConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Set the location to scrape for competitor rates."""
    # Deactivate existing configs
    await db.execute(
        text("UPDATE booking_scrape_config SET is_active = FALSE")
    )

    # Insert new config
    await db.execute(
        text("""
            INSERT INTO booking_scrape_config (location_name, pages_to_scrape, adults, is_active)
            VALUES (:location, :pages, :adults, TRUE)
        """),
        {'location': config.location_name, 'pages': config.pages_to_scrape, 'adults': config.adults}
    )
    await db.commit()

    return {"status": "success", "location": config.location_name}


@router.post("/config/enable")
async def enable_scraper(
    enabled: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Enable or disable the booking.com scraper."""
    await db.execute(
        text("UPDATE system_config SET config_value = :val WHERE config_key = 'booking_scraper_enabled'"),
        {'val': 'true' if enabled else 'false'}
    )
    await db.commit()
    return {"status": "success", "enabled": enabled}


@router.post("/config/unpause")
async def unpause_scraper(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Manually unpause the scraper (clears blocking pause)."""
    await db.execute(
        text("UPDATE system_config SET config_value = 'false' WHERE config_key = 'booking_scraper_paused'")
    )
    await db.commit()
    return {"status": "success", "message": "Scraper unpaused"}


# ============================================
# MANUAL SCRAPE TRIGGER
# ============================================

def run_scrape_sync(from_date: date, to_date: date):
    """Run scrape in sync context for background task."""
    import asyncio
    from services.booking_scraper import run_manual_scrape, cleanup_stale_batches

    db = SyncSessionLocal()
    try:
        # Clean up any stale batches before starting
        cleanup_stale_batches(db, max_age_minutes=60)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_manual_scrape(db, from_date, to_date))
            logger.info(f"Background scrape completed: {result}")
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Background scrape failed: {e}", exc_info=True)
    finally:
        db.close()


@router.post("/scrape")
async def trigger_manual_scrape(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger a manual scrape for the specified date range.

    Runs in background - check /status for progress.
    """
    try:
        from_date = date.fromisoformat(request.from_date)
        to_date = date.fromisoformat(request.to_date) if request.to_date else from_date
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")

    if to_date < from_date:
        raise HTTPException(status_code=400, detail="to_date must be after from_date")

    if (to_date - from_date).days > 30:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 30 days for manual scrape")

    # Check if location is configured
    location_result = await db.execute(
        text("SELECT id FROM booking_scrape_config WHERE is_active = TRUE LIMIT 1")
    )
    if not location_result.fetchone():
        raise HTTPException(status_code=400, detail="No scrape location configured. Set location first.")

    # Check if paused
    paused_result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'booking_scraper_paused'")
    )
    paused_row = paused_result.fetchone()
    if paused_row and paused_row.config_value == 'true':
        raise HTTPException(status_code=400, detail="Scraper is currently paused. Use /unpause first or wait for cooldown.")

    # Start background task
    background_tasks.add_task(run_scrape_sync, from_date, to_date)

    return {
        "status": "started",
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "message": "Scrape started in background. Check /status for progress."
    }


# ============================================
# HOTELS MANAGEMENT
# ============================================

@router.get("/hotels", response_model=List[HotelResponse])
async def list_hotels(
    tier: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all discovered hotels.

    Filter by tier: 'own', 'competitor', 'market', or None for all.
    """
    query = """
        SELECT id, booking_com_id, name, booking_com_url,
               star_rating, review_score, review_count,
               tier, display_order, notes, first_seen_at, last_seen_at
        FROM booking_com_hotels
        WHERE is_active = TRUE
    """
    params = {}

    if tier:
        if tier not in ('own', 'competitor', 'market'):
            raise HTTPException(status_code=400, detail="Invalid tier. Must be 'own', 'competitor', or 'market'")
        query += " AND tier = :tier"
        params['tier'] = tier

    query += " ORDER BY display_order, name"

    result = await db.execute(text(query), params)

    return [
        HotelResponse(
            id=row.id,
            booking_com_id=row.booking_com_id or '',
            name=row.name,
            booking_com_url=row.booking_com_url,
            star_rating=float(row.star_rating) if row.star_rating else None,
            review_score=float(row.review_score) if row.review_score else None,
            review_count=row.review_count,
            tier=row.tier,
            display_order=row.display_order,
            notes=row.notes,
            first_seen_at=row.first_seen_at,
            last_seen_at=row.last_seen_at
        )
        for row in result.fetchall()
    ]


@router.put("/hotels/{hotel_id}/tier")
async def update_hotel_tier(
    hotel_id: int,
    update: HotelTierUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update a hotel's tier and display order.

    Tiers:
    - 'own': Your hotel (for parity checking)
    - 'competitor': Main competitors (full tracking)
    - 'market': Other hotels (context only)
    """
    if update.tier not in ('own', 'competitor', 'market'):
        raise HTTPException(status_code=400, detail="Invalid tier")

    # If setting as 'own', clear any existing 'own' hotel
    if update.tier == 'own':
        await db.execute(
            text("UPDATE booking_com_hotels SET tier = 'market' WHERE tier = 'own'")
        )

    # Update the hotel
    set_clause = "tier = :tier"
    params = {'hotel_id': hotel_id, 'tier': update.tier}

    if update.display_order is not None:
        set_clause += ", display_order = :order"
        params['order'] = update.display_order

    result = await db.execute(
        text(f"UPDATE booking_com_hotels SET {set_clause} WHERE id = :hotel_id RETURNING id"),
        params
    )

    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Hotel not found")

    await db.commit()

    # If this is now the own hotel, update system config
    if update.tier == 'own':
        await db.execute(
            text("UPDATE system_config SET config_value = :val WHERE config_key = 'booking_scraper_own_hotel_id'"),
            {'val': str(hotel_id)}
        )
        await db.commit()

    return {"status": "success", "hotel_id": hotel_id, "tier": update.tier}


@router.put("/hotels/{hotel_id}/notes")
async def update_hotel_notes(
    hotel_id: int,
    notes: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update notes for a hotel."""
    result = await db.execute(
        text("UPDATE booking_com_hotels SET notes = :notes WHERE id = :hotel_id RETURNING id"),
        {'hotel_id': hotel_id, 'notes': notes}
    )

    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Hotel not found")

    await db.commit()
    return {"status": "success"}


# ============================================
# COMPETITOR RATES MATRIX
# ============================================

@router.get("/matrix")
async def get_competitor_matrix(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    include_market: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get rate comparison matrix for competitors.

    Returns rates for own hotel and competitors, organized by date.
    Set include_market=true to also include market tier hotels.
    """
    today = date.today()
    start = date.fromisoformat(from_date) if from_date else today
    end = date.fromisoformat(to_date) if to_date else today + timedelta(days=30)

    if end < start:
        raise HTTPException(status_code=400, detail="to_date must be after from_date")
    if (end - start).days > 90:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 90 days")

    tier_filter = "h.tier IN ('own', 'competitor')"
    if include_market:
        tier_filter = "h.tier IN ('own', 'competitor', 'market')"

    # Get hotels
    hotels_result = await db.execute(
        text(f"""
            SELECT id, name, tier, display_order, star_rating, review_score, booking_com_url
            FROM booking_com_hotels
            WHERE is_active = TRUE AND {tier_filter.replace('h.', '')}
            ORDER BY display_order, name
        """)
    )
    hotels = [dict(row._mapping) for row in hotels_result.fetchall()]

    # Get latest rates using the view
    rates_result = await db.execute(
        text(f"""
            SELECT DISTINCT ON (r.hotel_id, r.rate_date)
                r.hotel_id,
                r.rate_date,
                r.availability_status,
                r.rate_gross,
                r.room_type,
                r.breakfast_included,
                r.free_cancellation,
                r.no_prepayment,
                r.rooms_left,
                r.scraped_at
            FROM booking_com_rates r
            JOIN booking_com_hotels h ON r.hotel_id = h.id
            WHERE {tier_filter}
              AND h.is_active = TRUE
              AND r.rate_date >= :from_date AND r.rate_date <= :to_date
            ORDER BY r.hotel_id, r.rate_date, r.scraped_at DESC
        """),
        {'from_date': start, 'to_date': end}
    )

    # Build matrix: hotel_id -> date -> rate data
    rates_by_hotel: Dict[int, Dict[str, dict]] = {}
    for row in rates_result.fetchall():
        hotel_id = row.hotel_id
        rate_date = row.rate_date.isoformat()

        if hotel_id not in rates_by_hotel:
            rates_by_hotel[hotel_id] = {}

        rates_by_hotel[hotel_id][rate_date] = {
            'availability_status': row.availability_status,
            'rate_gross': float(row.rate_gross) if row.rate_gross else None,
            'room_type': row.room_type,
            'breakfast_included': row.breakfast_included,
            'free_cancellation': row.free_cancellation,
            'no_prepayment': row.no_prepayment,
            'rooms_left': row.rooms_left,
            'scraped_at': row.scraped_at.isoformat() if row.scraped_at else None,
        }

    # Build date list
    dates = []
    current = start
    while current <= end:
        dates.append(current.isoformat())
        current += timedelta(days=1)

    return {
        'from_date': start.isoformat(),
        'to_date': end.isoformat(),
        'dates': dates,
        'hotels': hotels,
        'rates': rates_by_hotel
    }


# ============================================
# RATE PARITY (OWN HOTEL VS NEWBOOK)
# ============================================

@router.get("/parity")
async def get_rate_parity(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get rate parity comparison between booking.com and Newbook rates.

    Compares scraped booking.com rates for own hotel against Newbook current rates.
    """
    today = date.today()
    start = date.fromisoformat(from_date) if from_date else today
    end = date.fromisoformat(to_date) if to_date else today + timedelta(days=30)

    # Get own hotel's booking.com rates
    booking_rates_result = await db.execute(
        text("""
            SELECT DISTINCT ON (r.rate_date)
                r.rate_date,
                r.rate_gross as booking_rate,
                r.availability_status,
                r.room_type as booking_room_type,
                r.scraped_at
            FROM booking_com_rates r
            JOIN booking_com_hotels h ON r.hotel_id = h.id
            WHERE h.tier = 'own'
              AND r.rate_date >= :from_date AND r.rate_date <= :to_date
            ORDER BY r.rate_date, r.scraped_at DESC
        """),
        {'from_date': start, 'to_date': end}
    )
    booking_rates = {row.rate_date: dict(row._mapping) for row in booking_rates_result.fetchall()}

    # Get Newbook rates (best rate per date across categories)
    newbook_rates_result = await db.execute(
        text("""
            SELECT DISTINCT ON (rate_date)
                rate_date,
                rate_gross as newbook_rate,
                category_id
            FROM newbook_current_rates
            WHERE rate_date >= :from_date AND rate_date <= :to_date
            ORDER BY rate_date, valid_from DESC
        """),
        {'from_date': start, 'to_date': end}
    )
    newbook_rates = {row.rate_date: dict(row._mapping) for row in newbook_rates_result.fetchall()}

    # Compare rates
    parity_issues = []
    all_dates = set(booking_rates.keys()) | set(newbook_rates.keys())

    for rate_date in sorted(all_dates):
        booking = booking_rates.get(rate_date)
        newbook = newbook_rates.get(rate_date)

        if not booking or not newbook:
            continue

        booking_rate = booking.get('booking_rate')
        newbook_rate = newbook.get('newbook_rate')

        if not booking_rate or not newbook_rate:
            continue

        diff_pct = ((float(booking_rate) - float(newbook_rate)) / float(newbook_rate)) * 100

        if abs(diff_pct) > 1:  # More than 1% difference
            parity_issues.append({
                'rate_date': rate_date.isoformat(),
                'booking_rate': float(booking_rate),
                'newbook_rate': float(newbook_rate),
                'difference_pct': round(diff_pct, 2),
                'alert_type': 'higher' if diff_pct > 0 else 'lower',
                'booking_room_type': booking.get('booking_room_type'),
                'availability_status': booking.get('availability_status'),
            })

    return {
        'from_date': start.isoformat(),
        'to_date': end.isoformat(),
        'issues_count': len(parity_issues),
        'issues': parity_issues
    }


# ============================================
# PARITY ALERTS
# ============================================

@router.get("/parity/alerts")
async def get_parity_alerts(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get rate parity alerts."""
    query = """
        SELECT id, rate_date, room_category, newbook_rate, booking_com_rate,
               difference_pct, alert_type, alert_status, created_at,
               acknowledged_at, acknowledged_by, notes
        FROM rate_parity_alerts
    """
    params = {}

    if status:
        query += " WHERE alert_status = :status"
        params['status'] = status

    query += " ORDER BY rate_date DESC, created_at DESC LIMIT 100"

    result = await db.execute(text(query), params)

    return [
        {
            'id': row.id,
            'rate_date': row.rate_date.isoformat(),
            'room_category': row.room_category,
            'newbook_rate': float(row.newbook_rate) if row.newbook_rate else None,
            'booking_com_rate': float(row.booking_com_rate) if row.booking_com_rate else None,
            'difference_pct': float(row.difference_pct) if row.difference_pct else None,
            'alert_type': row.alert_type,
            'alert_status': row.alert_status,
            'created_at': row.created_at.isoformat() if row.created_at else None,
            'acknowledged_at': row.acknowledged_at.isoformat() if row.acknowledged_at else None,
            'acknowledged_by': row.acknowledged_by,
            'notes': row.notes,
        }
        for row in result.fetchall()
    ]


@router.put("/parity/alerts/{alert_id}/acknowledge")
async def acknowledge_parity_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Acknowledge a parity alert."""
    result = await db.execute(
        text("""
            UPDATE rate_parity_alerts
            SET alert_status = 'acknowledged',
                acknowledged_at = NOW(),
                acknowledged_by = :username
            WHERE id = :alert_id
            RETURNING id
        """),
        {'alert_id': alert_id, 'username': current_user.get('username', 'unknown')}
    )

    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Alert not found")

    await db.commit()
    return {"status": "success"}


# ============================================
# QUEUE STATUS
# ============================================

@router.get("/queue-status")
async def get_queue_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get current scrape queue status."""
    result = await db.execute(
        text("""
            SELECT
                status,
                COUNT(*) as count,
                MIN(rate_date) as earliest_date,
                MAX(rate_date) as latest_date
            FROM booking_scrape_queue
            GROUP BY status
        """)
    )
    status_counts = {row.status: {
        'count': row.count,
        'earliest': row.earliest_date.isoformat() if row.earliest_date else None,
        'latest': row.latest_date.isoformat() if row.latest_date else None,
    } for row in result.fetchall()}

    # Get retry items (failed but under max_attempts)
    retry_result = await db.execute(
        text("""
            SELECT COUNT(*) as count
            FROM booking_scrape_queue
            WHERE status = 'pending' AND attempts > 0
        """)
    )
    retry_count = retry_result.fetchone().count

    return {
        'statuses': status_counts,
        'retries_pending': retry_count,
        'total_pending': status_counts.get('pending', {}).get('count', 0),
        'total_completed': status_counts.get('completed', {}).get('count', 0),
        'total_failed': status_counts.get('failed', {}).get('count', 0),
    }


# ============================================
# SCHEDULE INFO
# ============================================

@router.get("/schedule-info")
async def get_schedule_info(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get information about the scraping schedule."""
    # Get configured time
    time_result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'booking_scraper_daily_time'")
    )
    time_row = time_result.fetchone()
    daily_time = time_row.config_value if time_row and time_row.config_value else '05:30'

    # Calculate what today's schedule would look like
    from jobs.scrape_booking_rates import get_high_priority_dates, get_medium_priority_dates, get_low_priority_dates
    high = get_high_priority_dates()
    medium = get_medium_priority_dates()
    low = get_low_priority_dates()

    today = date.today()
    weekday_name = today.strftime('%A')

    return {
        'daily_time': daily_time,
        'today': today.isoformat(),
        'weekday': weekday_name,
        'tiers': {
            'high': {
                'description': 'Next 30 days (scraped first)',
                'dates_today': len(high),
                'range': f'{high[0].isoformat()} to {high[-1].isoformat()}' if high else None,
            },
            'medium': {
                'description': 'Days 31-180 (scraped after high priority)',
                'dates_today': len(medium),
                'range': f'{medium[0].isoformat()} to {medium[-1].isoformat()}' if medium else None,
            },
            'low': {
                'description': 'Days 181-365 (scraped last, or until rate limit)',
                'dates_today': len(low),
                'range': f'{low[0].isoformat()} to {low[-1].isoformat()}' if low else None,
            },
        },
        'total_dates_today': len(set(high + medium + low)),
    }


# ============================================
# SCRAPE COVERAGE (365-day view)
# ============================================

@router.get("/scrape-coverage")
async def get_scrape_coverage(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get 365-day scrape coverage showing last scraped time
    and next expected scrape for every date.
    """
    today = date.today()
    end = today + timedelta(days=365)

    # Get latest scraped_at per date (across all hotels)
    result = await db.execute(
        text("""
            SELECT rate_date, MAX(scraped_at) as last_scraped
            FROM booking_com_rates
            WHERE rate_date >= :from_date AND rate_date <= :to_date
            GROUP BY rate_date
        """),
        {'from_date': today, 'to_date': end}
    )
    scraped_map = {row.rate_date: row.last_scraped for row in result.fetchall()}

    # Compute tier and next scrape for each date
    from jobs.scrape_booking_rates import compute_next_scrape_for_date

    coverage = []
    for offset in range(366):
        d = today + timedelta(days=offset)
        tier, next_scrape = compute_next_scrape_for_date(d)
        last_scraped = scraped_map.get(d)

        coverage.append({
            'date': d.isoformat(),
            'tier': tier,
            'last_scraped': last_scraped.isoformat() if last_scraped else None,
            'next_expected': next_scrape.isoformat() if next_scrape else None,
        })

    return {
        'today': today.isoformat(),
        'coverage': coverage,
    }


# ============================================
# BOOKING.COM AVAILABILITY CHECK (for Bookability page)
# ============================================

@router.get("/booking-availability")
async def get_booking_availability(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Check own hotel's availability on booking.com.

    Returns a simple summary: for each date in the range, whether the own hotel
    appears available on booking.com based on the latest scrape data.
    """
    today = date.today()
    start = date.fromisoformat(from_date) if from_date else today
    end = date.fromisoformat(to_date) if to_date else today + timedelta(days=30)

    # Get own hotel's latest scraped availability
    result = await db.execute(
        text("""
            SELECT DISTINCT ON (r.rate_date)
                r.rate_date,
                r.availability_status,
                r.rate_gross,
                r.scraped_at
            FROM booking_com_rates r
            JOIN booking_com_hotels h ON r.hotel_id = h.id
            WHERE h.tier = 'own'
              AND r.rate_date >= :from_date AND r.rate_date <= :to_date
            ORDER BY r.rate_date, r.scraped_at DESC
        """),
        {'from_date': start, 'to_date': end}
    )
    rows = result.fetchall()

    if not rows:
        return {
            'has_own_hotel': False,
            'dates_checked': 0,
            'dates_available': 0,
            'dates_sold_out': 0,
            'dates_no_data': 0,
            'latest_scrape': None,
            'dates': {},
        }

    dates_map = {}
    dates_available = 0
    dates_sold_out = 0
    dates_no_data = 0
    latest_scrape = None

    for row in rows:
        status = row.availability_status
        dates_map[row.rate_date.isoformat()] = {
            'status': status,
            'rate': float(row.rate_gross) if row.rate_gross else None,
        }
        if status == 'available':
            dates_available += 1
        elif status == 'sold_out':
            dates_sold_out += 1
        else:
            dates_no_data += 1

        if row.scraped_at and (not latest_scrape or row.scraped_at > latest_scrape):
            latest_scrape = row.scraped_at

    return {
        'has_own_hotel': True,
        'dates_checked': len(rows),
        'dates_available': dates_available,
        'dates_sold_out': dates_sold_out,
        'dates_no_data': dates_no_data,
        'latest_scrape': latest_scrape.isoformat() if latest_scrape else None,
        'dates': dates_map,
    }


# ============================================
# SCRAPE HISTORY
# ============================================

@router.get("/scrape-history")
async def get_scrape_history(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get recent scrape batch history."""
    result = await db.execute(
        text("""
            SELECT batch_id, scrape_type, started_at, completed_at, status,
                   dates_queued, dates_completed, dates_failed,
                   hotels_found, rates_scraped, error_message,
                   blocked_at, resume_after
            FROM booking_scrape_log
            ORDER BY started_at DESC
            LIMIT :limit
        """),
        {'limit': limit}
    )

    return [
        {
            'batch_id': str(row.batch_id),
            'scrape_type': row.scrape_type,
            'started_at': row.started_at.isoformat() if row.started_at else None,
            'completed_at': row.completed_at.isoformat() if row.completed_at else None,
            'status': row.status,
            'dates_queued': row.dates_queued,
            'dates_completed': row.dates_completed,
            'dates_failed': row.dates_failed,
            'hotels_found': row.hotels_found,
            'rates_scraped': row.rates_scraped,
            'error_message': row.error_message,
            'blocked_at': row.blocked_at.isoformat() if row.blocked_at else None,
            'resume_after': row.resume_after.isoformat() if row.resume_after else None,
        }
        for row in result.fetchall()
    ]
