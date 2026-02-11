"""
Booking.com Rate Scraper Service

Main service for scraping competitor rates from booking.com.
Uses pluggable backends (Playwright local, proxy, Apify) via factory pattern.

Features:
- Location-based search (1 query = 40+ hotels)
- Hotel discovery and tier management
- Rate extraction with availability status
- Anti-scrape detection and pause/resume
"""

import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .scraper_backends import ScraperBackend, PlaywrightLocalBackend, HotelData, RateData, AvailabilityStatus

logger = logging.getLogger(__name__)


def get_scraper_backend(db: Session) -> ScraperBackend:
    """
    Factory to get configured scraper backend.

    Reads backend type from system_config and returns appropriate instance.
    """
    # Get backend configuration
    result = db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'booking_scraper_backend'")
    ).fetchone()

    backend_type = result.config_value if result and result.config_value else 'playwright_local'

    if backend_type == 'playwright_local':
        return PlaywrightLocalBackend()

    elif backend_type == 'playwright_proxy':
        # Get proxy config
        proxy_result = db.execute(
            text("""
                SELECT config_key, config_value FROM system_config
                WHERE config_key IN ('booking_scraper_proxy_url', 'booking_scraper_proxy_username', 'booking_scraper_proxy_password')
            """)
        )
        proxy_config = {row.config_key: row.config_value for row in proxy_result.fetchall()}
        return PlaywrightLocalBackend(proxy_config=proxy_config)

    elif backend_type == 'apify':
        # Future: Apify backend
        raise NotImplementedError("Apify backend not yet implemented")

    else:
        logger.warning(f"Unknown backend type '{backend_type}', falling back to playwright_local")
        return PlaywrightLocalBackend()


def get_scrape_config(db: Session) -> Optional[Dict[str, Any]]:
    """Get the active scrape location configuration."""
    result = db.execute(
        text("""
            SELECT id, location_name, location_search_url, pages_to_scrape, adults
            FROM booking_scrape_config
            WHERE is_active = TRUE
            ORDER BY id
            LIMIT 1
        """)
    ).fetchone()

    if not result:
        return None

    return {
        'id': result.id,
        'location_name': result.location_name,
        'location_search_url': result.location_search_url,
        'pages_to_scrape': result.pages_to_scrape or 2,
        'adults': result.adults or 2,
    }


async def is_scraper_paused(db: Session) -> bool:
    """Check if scraper is currently paused due to blocking."""
    result = db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'booking_scraper_paused'")
    ).fetchone()

    if not result or result.config_value != 'true':
        return False

    # Check if pause period has expired
    pause_until_result = db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'booking_scraper_pause_until'")
    ).fetchone()

    if pause_until_result and pause_until_result.config_value:
        try:
            pause_until = datetime.fromisoformat(pause_until_result.config_value)
            if datetime.now() >= pause_until:
                # Pause expired, reset
                db.execute(
                    text("UPDATE system_config SET config_value = 'false' WHERE config_key = 'booking_scraper_paused'")
                )
                db.commit()
                return False
        except ValueError:
            pass

    return True


async def set_scraper_paused(db: Session, paused: bool, hours: int = 2):
    """Set scraper pause status."""
    db.execute(
        text("UPDATE system_config SET config_value = :val WHERE config_key = 'booking_scraper_paused'"),
        {'val': 'true' if paused else 'false'}
    )
    if paused:
        pause_until = (datetime.now() + timedelta(hours=hours)).isoformat()
        db.execute(
            text("UPDATE system_config SET config_value = :val WHERE config_key = 'booking_scraper_pause_until'"),
            {'val': pause_until}
        )
    db.commit()


def save_hotel(db: Session, hotel: HotelData) -> int:
    """
    Save or update a hotel in the database.

    Returns the hotel's database ID.
    """
    # Check if hotel exists
    existing = db.execute(
        text("SELECT id FROM booking_com_hotels WHERE booking_com_id = :bid"),
        {'bid': hotel.booking_com_id}
    ).fetchone()

    if existing:
        # Update last_seen_at and any changed fields
        db.execute(
            text("""
                UPDATE booking_com_hotels SET
                    name = COALESCE(:name, name),
                    booking_com_url = COALESCE(:url, booking_com_url),
                    star_rating = COALESCE(:stars, star_rating),
                    review_score = COALESCE(:score, review_score),
                    review_count = COALESCE(:count, review_count),
                    last_seen_at = NOW()
                WHERE booking_com_id = :bid
            """),
            {
                'bid': hotel.booking_com_id,
                'name': hotel.name,
                'url': hotel.booking_com_url,
                'stars': float(hotel.star_rating) if hotel.star_rating else None,
                'score': float(hotel.review_score) if hotel.review_score else None,
                'count': hotel.review_count,
            }
        )
        return existing.id
    else:
        # Insert new hotel (default tier is 'market')
        result = db.execute(
            text("""
                INSERT INTO booking_com_hotels
                (booking_com_id, name, booking_com_url, star_rating, review_score, review_count, tier)
                VALUES (:bid, :name, :url, :stars, :score, :count, 'market')
                RETURNING id
            """),
            {
                'bid': hotel.booking_com_id,
                'name': hotel.name,
                'url': hotel.booking_com_url,
                'stars': float(hotel.star_rating) if hotel.star_rating else None,
                'score': float(hotel.review_score) if hotel.review_score else None,
                'count': hotel.review_count,
            }
        )
        return result.fetchone().id


def save_rate(db: Session, rate: RateData, hotel_id: int, batch_id: uuid.UUID):
    """Save a rate to the database."""
    db.execute(
        text("""
            INSERT INTO booking_com_rates
            (hotel_id, rate_date, availability_status, rate_gross, currency, room_type,
             breakfast_included, free_cancellation, no_prepayment, rooms_left, scrape_batch_id)
            VALUES (:hotel_id, :rate_date, :status, :rate, :currency, :room_type,
                    :breakfast, :cancel, :prepay, :rooms_left, :batch_id)
        """),
        {
            'hotel_id': hotel_id,
            'rate_date': rate.rate_date,
            'status': rate.availability_status.value,
            'rate': float(rate.rate_gross) if rate.rate_gross else None,
            'currency': rate.currency,
            'room_type': rate.room_type,
            'breakfast': rate.breakfast_included,
            'cancel': rate.free_cancellation,
            'prepay': rate.no_prepayment,
            'rooms_left': rate.rooms_left,
            'batch_id': str(batch_id),
        }
    )


def create_scrape_batch(db: Session, scrape_type: str) -> uuid.UUID:
    """Create a new scrape batch log entry."""
    batch_id = uuid.uuid4()
    db.execute(
        text("""
            INSERT INTO booking_scrape_log
            (batch_id, scrape_type, started_at, status)
            VALUES (:batch_id, :scrape_type, NOW(), 'running')
        """),
        {'batch_id': str(batch_id), 'scrape_type': scrape_type}
    )
    db.commit()
    return batch_id


def update_scrape_batch(
    db: Session,
    batch_id: uuid.UUID,
    status: str,
    hotels_found: int = 0,
    rates_scraped: int = 0,
    error_message: str = None,
    blocked: bool = False
):
    """Update scrape batch log with results."""
    db.execute(
        text("""
            UPDATE booking_scrape_log SET
                completed_at = CASE WHEN :status IN ('completed', 'failed', 'blocked') THEN NOW() ELSE NULL END,
                status = :status,
                hotels_found = :hotels,
                rates_scraped = :rates,
                error_message = :error,
                blocked_at = CASE WHEN :blocked THEN NOW() ELSE NULL END,
                resume_after = CASE WHEN :blocked THEN NOW() + INTERVAL '2 hours' ELSE NULL END
            WHERE batch_id = :batch_id
        """),
        {
            'batch_id': str(batch_id),
            'status': status,
            'hotels': hotels_found,
            'rates': rates_scraped,
            'error': error_message,
            'blocked': blocked,
        }
    )
    db.commit()


def cleanup_stale_batches(db: Session, max_age_minutes: int = 60):
    """
    Mark any 'running' scrape batches as 'failed' if they've been running
    longer than max_age_minutes. This handles orphaned batches from
    container restarts or crashes.
    """
    result = db.execute(
        text("""
            UPDATE booking_scrape_log SET
                status = 'failed',
                completed_at = NOW(),
                error_message = 'Interrupted (container restart or timeout)'
            WHERE status = 'running'
              AND started_at < NOW() - INTERVAL ':mins minutes'
            RETURNING batch_id
        """.replace(':mins', str(int(max_age_minutes))))
    )
    cleaned = result.fetchall()
    db.commit()
    if cleaned:
        logger.info(f"Cleaned up {len(cleaned)} stale running scrape batch(es)")
    return len(cleaned)


async def scrape_date(
    db: Session,
    rate_date: date,
    backend: ScraperBackend,
    config: Dict[str, Any],
    batch_id: uuid.UUID
) -> Dict[str, Any]:
    """
    Scrape rates for a single date.

    Args:
        db: Database session
        rate_date: Date to scrape rates for
        backend: Scraper backend instance
        config: Scrape configuration
        batch_id: Current batch ID

    Returns:
        Dict with 'success', 'blocked', 'hotels_count', 'rates_count'
    """
    check_in = rate_date
    check_out = rate_date + timedelta(days=1)  # Single night

    result = await backend.scrape_location_search(
        location=config['location_name'],
        check_in=check_in,
        check_out=check_out,
        adults=config['adults'],
        pages=config['pages_to_scrape']
    )

    if result.blocked:
        return {
            'success': False,
            'blocked': True,
            'block_reason': result.block_reason,
            'hotels_count': 0,
            'rates_count': 0,
        }

    if not result.success:
        return {
            'success': False,
            'blocked': False,
            'error': result.error_message,
            'hotels_count': 0,
            'rates_count': 0,
        }

    # Save hotels and rates
    hotels_saved = 0
    rates_saved = 0

    for hotel, rate in zip(result.hotels, result.rates):
        if not hotel.booking_com_id:
            continue

        try:
            hotel_id = save_hotel(db, hotel)
            save_rate(db, rate, hotel_id, batch_id)
            hotels_saved += 1
            rates_saved += 1
        except Exception as e:
            logger.warning(f"Error saving hotel/rate: {e}")
            continue

    db.commit()

    return {
        'success': True,
        'blocked': False,
        'hotels_count': hotels_saved,
        'rates_count': rates_saved,
    }


async def run_manual_scrape(
    db: Session,
    from_date: date,
    to_date: date = None
) -> Dict[str, Any]:
    """
    Run a manual scrape for testing/on-demand use.

    Args:
        db: Database session
        from_date: Start date
        to_date: End date (defaults to from_date for single day)

    Returns:
        Dict with scrape results summary
    """
    if to_date is None:
        to_date = from_date

    # Check if paused
    if await is_scraper_paused(db):
        return {
            'success': False,
            'error': 'Scraper is currently paused due to blocking. Try again later.',
        }

    # Get config
    config = get_scrape_config(db)
    if not config:
        return {
            'success': False,
            'error': 'No scrape location configured. Add a location in settings.',
        }

    # Create batch
    batch_id = create_scrape_batch(db, 'manual')

    # Get backend
    backend = get_scraper_backend(db)

    total_hotels = 0
    total_rates = 0
    dates_completed = 0
    dates_failed = 0

    try:
        current_date = from_date
        while current_date <= to_date:
            logger.info(f"Scraping date: {current_date}")

            result = await scrape_date(db, current_date, backend, config, batch_id)

            if result['blocked']:
                # Blocking detected - pause and exit
                await set_scraper_paused(db, True, hours=2)
                update_scrape_batch(
                    db, batch_id,
                    status='blocked',
                    hotels_found=total_hotels,
                    rates_scraped=total_rates,
                    error_message=f"Blocked: {result.get('block_reason', 'unknown')}",
                    blocked=True
                )
                return {
                    'success': False,
                    'blocked': True,
                    'block_reason': result.get('block_reason'),
                    'dates_completed': dates_completed,
                    'dates_failed': dates_failed,
                    'hotels_found': total_hotels,
                    'rates_scraped': total_rates,
                }

            if result['success']:
                total_hotels += result['hotels_count']
                total_rates += result['rates_count']
                dates_completed += 1
            else:
                dates_failed += 1
                logger.warning(f"Failed to scrape {current_date}: {result.get('error')}")

            current_date += timedelta(days=1)

        # Update batch as completed
        update_scrape_batch(
            db, batch_id,
            status='completed',
            hotels_found=total_hotels,
            rates_scraped=total_rates
        )

        return {
            'success': True,
            'blocked': False,
            'dates_completed': dates_completed,
            'dates_failed': dates_failed,
            'hotels_found': total_hotels,
            'rates_scraped': total_rates,
        }

    except Exception as e:
        logger.error(f"Scrape error: {e}")
        update_scrape_batch(
            db, batch_id,
            status='failed',
            hotels_found=total_hotels,
            rates_scraped=total_rates,
            error_message=str(e)
        )
        return {
            'success': False,
            'error': str(e),
            'dates_completed': dates_completed,
            'dates_failed': dates_failed,
            'hotels_found': total_hotels,
            'rates_scraped': total_rates,
        }
    finally:
        await backend.close()


# ============================================
# QUEUE MANAGEMENT
# ============================================

def populate_queue(db: Session, dates: List[date], priorities: Dict[date, int] = None):
    """
    Add dates to the scrape queue, skipping any already pending/processing.

    Args:
        db: Database session
        dates: Dates to add to the queue
        priorities: Optional priority map (higher = scraped first). Default: 0
    """
    if not dates:
        return 0

    added = 0
    for rate_date in dates:
        priority = (priorities or {}).get(rate_date, 0)
        try:
            db.execute(
                text("""
                    INSERT INTO booking_scrape_queue (rate_date, status, priority)
                    VALUES (:rate_date, 'pending', :priority)
                    ON CONFLICT (rate_date, status) DO UPDATE SET
                        priority = GREATEST(booking_scrape_queue.priority, :priority)
                """),
                {'rate_date': rate_date, 'priority': priority}
            )
            added += 1
        except Exception:
            # Ignore duplicates or constraint issues
            pass

    db.commit()
    logger.info(f"Queue: added/updated {added} dates")
    return added


def get_pending_queue_items(db: Session, limit: int = 50) -> List[Dict[str, Any]]:
    """Get pending queue items ordered by priority (highest first), then date."""
    result = db.execute(
        text("""
            SELECT id, rate_date, priority, attempts, max_attempts
            FROM booking_scrape_queue
            WHERE status = 'pending' AND attempts < max_attempts
            ORDER BY priority DESC, rate_date ASC
            LIMIT :limit
        """),
        {'limit': limit}
    )
    return [dict(row._mapping) for row in result.fetchall()]


def mark_queue_item(db: Session, queue_id: int, status: str, error_message: str = None):
    """Update a queue item's status."""
    if status == 'completed':
        db.execute(
            text("""
                UPDATE booking_scrape_queue SET
                    status = 'completed',
                    completed_at = NOW(),
                    last_attempt_at = NOW(),
                    attempts = attempts + 1
                WHERE id = :id
            """),
            {'id': queue_id}
        )
    elif status == 'failed':
        db.execute(
            text("""
                UPDATE booking_scrape_queue SET
                    status = CASE
                        WHEN attempts + 1 >= max_attempts THEN 'failed'
                        ELSE 'pending'
                    END,
                    last_attempt_at = NOW(),
                    attempts = attempts + 1,
                    error_message = :error
                WHERE id = :id
            """),
            {'id': queue_id, 'error': error_message}
        )
    db.commit()


def clear_old_queue_items(db: Session, days: int = 7):
    """Remove completed/failed queue items older than N days."""
    db.execute(
        text("""
            DELETE FROM booking_scrape_queue
            WHERE status IN ('completed', 'failed')
              AND created_at < NOW() - INTERVAL ':days days'
        """.replace(':days', str(int(days))))
    )
    db.commit()


async def process_queue(db: Session) -> Dict[str, Any]:
    """
    Process pending items from the scrape queue.

    Picks up pending items in priority order, scrapes each date,
    and handles blocking/retries.

    Returns:
        Dict with processing results
    """
    # Check if paused
    if await is_scraper_paused(db):
        return {
            'success': False,
            'error': 'Scraper is currently paused due to blocking.',
        }

    # Get config
    config = get_scrape_config(db)
    if not config:
        return {
            'success': False,
            'error': 'No scrape location configured.',
        }

    # Get pending items
    items = get_pending_queue_items(db, limit=50)
    if not items:
        return {'success': True, 'dates_completed': 0, 'message': 'Queue empty'}

    # Create batch
    batch_id = create_scrape_batch(db, 'scheduled')

    # Update batch with queue count
    db.execute(
        text("UPDATE booking_scrape_log SET dates_queued = :count WHERE batch_id = :bid"),
        {'count': len(items), 'bid': str(batch_id)}
    )
    db.commit()

    # Get backend
    backend = get_scraper_backend(db)

    total_hotels = 0
    total_rates = 0
    dates_completed = 0
    dates_failed = 0

    try:
        for item in items:
            rate_date = item['rate_date']
            queue_id = item['id']

            logger.info(f"Queue processing: {rate_date} (priority={item['priority']}, attempt={item['attempts']+1})")

            result = await scrape_date(db, rate_date, backend, config, batch_id)

            if result['blocked']:
                # Mark this item as failed, pause, and stop
                mark_queue_item(db, queue_id, 'failed', f"Blocked: {result.get('block_reason')}")
                await set_scraper_paused(db, True, hours=2)
                update_scrape_batch(
                    db, batch_id,
                    status='blocked',
                    hotels_found=total_hotels,
                    rates_scraped=total_rates,
                    error_message=f"Blocked: {result.get('block_reason', 'unknown')}",
                    blocked=True
                )
                # Update dates counters
                db.execute(
                    text("""
                        UPDATE booking_scrape_log SET
                            dates_completed = :completed,
                            dates_failed = :failed
                        WHERE batch_id = :bid
                    """),
                    {'completed': dates_completed, 'failed': dates_failed + 1, 'bid': str(batch_id)}
                )
                db.commit()
                return {
                    'success': False,
                    'blocked': True,
                    'block_reason': result.get('block_reason'),
                    'dates_completed': dates_completed,
                    'dates_failed': dates_failed + 1,
                    'hotels_found': total_hotels,
                    'rates_scraped': total_rates,
                }

            if result['success']:
                mark_queue_item(db, queue_id, 'completed')
                total_hotels += result['hotels_count']
                total_rates += result['rates_count']
                dates_completed += 1
            else:
                mark_queue_item(db, queue_id, 'failed', result.get('error'))
                dates_failed += 1
                logger.warning(f"Queue: failed to scrape {rate_date}: {result.get('error')}")

        # Update batch as completed
        update_scrape_batch(
            db, batch_id,
            status='completed',
            hotels_found=total_hotels,
            rates_scraped=total_rates
        )
        db.execute(
            text("""
                UPDATE booking_scrape_log SET
                    dates_completed = :completed,
                    dates_failed = :failed
                WHERE batch_id = :bid
            """),
            {'completed': dates_completed, 'failed': dates_failed, 'bid': str(batch_id)}
        )
        db.commit()

        return {
            'success': True,
            'blocked': False,
            'dates_completed': dates_completed,
            'dates_failed': dates_failed,
            'hotels_found': total_hotels,
            'rates_scraped': total_rates,
        }

    except Exception as e:
        logger.error(f"Queue processing error: {e}")
        update_scrape_batch(
            db, batch_id,
            status='failed',
            hotels_found=total_hotels,
            rates_scraped=total_rates,
            error_message=str(e)
        )
        return {
            'success': False,
            'error': str(e),
            'dates_completed': dates_completed,
            'dates_failed': dates_failed,
        }
    finally:
        await backend.close()


def get_competitor_matrix(
    db: Session,
    from_date: date,
    to_date: date,
    include_market: bool = False
) -> List[Dict[str, Any]]:
    """
    Get rate comparison matrix for competitors.

    Args:
        db: Database session
        from_date: Start date
        to_date: End date
        include_market: Include market tier hotels

    Returns:
        List of rate records for matrix display
    """
    tier_filter = "h.tier IN ('own', 'competitor')"
    if include_market:
        tier_filter = "h.tier IN ('own', 'competitor', 'market')"

    result = db.execute(
        text(f"""
            SELECT
                r.rate_date,
                h.id AS hotel_id,
                h.name AS hotel_name,
                h.tier,
                h.display_order,
                h.star_rating,
                h.review_score,
                r.availability_status,
                r.rate_gross,
                r.room_type,
                r.breakfast_included,
                r.free_cancellation,
                r.no_prepayment,
                r.rooms_left,
                r.scraped_at
            FROM booking_latest_rates r
            JOIN booking_com_hotels h ON r.hotel_id = h.id
            WHERE {tier_filter}
              AND h.is_active = TRUE
              AND r.rate_date BETWEEN :from_date AND :to_date
            ORDER BY r.rate_date, h.display_order, h.name
        """),
        {'from_date': from_date, 'to_date': to_date}
    )

    return [dict(row._mapping) for row in result.fetchall()]


def get_hotels_list(db: Session, tier: str = None) -> List[Dict[str, Any]]:
    """
    Get list of discovered hotels.

    Args:
        db: Database session
        tier: Filter by tier ('own', 'competitor', 'market') or None for all

    Returns:
        List of hotel records
    """
    where_clause = "WHERE is_active = TRUE"
    if tier:
        where_clause += f" AND tier = '{tier}'"

    result = db.execute(
        text(f"""
            SELECT
                id, booking_com_id, name, booking_com_url,
                star_rating, review_score, review_count,
                tier, display_order, notes,
                first_seen_at, last_seen_at
            FROM booking_com_hotels
            {where_clause}
            ORDER BY display_order, name
        """)
    )

    return [dict(row._mapping) for row in result.fetchall()]


def update_hotel_tier(db: Session, hotel_id: int, tier: str, display_order: int = None):
    """Update a hotel's tier and display order."""
    if tier not in ('own', 'competitor', 'market'):
        raise ValueError(f"Invalid tier: {tier}")

    params = {'hotel_id': hotel_id, 'tier': tier}
    set_clause = "tier = :tier"

    if display_order is not None:
        set_clause += ", display_order = :order"
        params['order'] = display_order

    db.execute(
        text(f"UPDATE booking_com_hotels SET {set_clause} WHERE id = :hotel_id"),
        params
    )
    db.commit()
