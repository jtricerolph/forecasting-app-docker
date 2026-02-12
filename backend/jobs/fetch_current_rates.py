"""
Fetch Current Rates Job

Fetches current rack rates from Newbook API and populates newbook_current_rates table.
These rates are used by pickup-v2 model for upper bound calculations in confidence shading.

Uses a snapshot model - only inserts new rows when rates change, otherwise updates last_verified_at.
This allows tracking rate history over time.

Schedule: Daily at 5:20 AM (before pace snapshot runs)
"""
import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional

from sqlalchemy import text
from database import SyncSessionLocal

logger = logging.getLogger(__name__)


def rates_changed(old_rate: Optional[Dict], new_rate: Dict) -> bool:
    """
    Compare old and new rates to determine if they've changed.

    Compares gross rate, net rate, and tariff availability status.
    Returns True if rates have changed, False if they're the same.
    """
    if old_rate is None:
        return True  # No existing rate, need to insert

    # Compare gross and net rates
    old_gross = float(old_rate.get('rate_gross') or 0)
    new_gross = float(new_rate.get('gross_rate') or 0)
    if abs(old_gross - new_gross) > 0.01:
        return True

    old_net = float(old_rate.get('rate_net') or 0)
    new_net = float(new_rate.get('net_rate') or 0)
    if abs(old_net - new_net) > 0.01:
        return True

    # Compare tariff availability
    old_tariffs = old_rate.get('tariffs_data', {})
    if isinstance(old_tariffs, str):
        try:
            old_tariffs = json.loads(old_tariffs)
        except json.JSONDecodeError:
            old_tariffs = {}

    new_tariffs = new_rate.get('tariffs_data', {})

    old_tariff_list = old_tariffs.get('tariffs', [])
    new_tariff_list = new_tariffs.get('tariffs', [])

    # Different number of tariffs
    if len(old_tariff_list) != len(new_tariff_list):
        return True

    # Compare each tariff's key attributes
    for old_t, new_t in zip(old_tariff_list, new_tariff_list):
        # Name changed
        if old_t.get('name') != new_t.get('name'):
            return True
        # Availability status changed
        if old_t.get('success') != new_t.get('success'):
            return True
        # Rate changed significantly
        old_rate_val = float(old_t.get('rate') or 0)
        new_rate_val = float(new_t.get('rate') or 0)
        if abs(old_rate_val - new_rate_val) > 0.01:
            return True
        # Min stay changed
        if old_t.get('min_stay') != new_t.get('min_stay'):
            return True
        # Multi-night availability changed
        if old_t.get('available_for_min_stay') != new_t.get('available_for_min_stay'):
            return True

    return False


def save_rate_snapshot(db, category_id: str, rate_date: date, rate: Dict) -> str:
    """
    Save rate to database using snapshot logic.

    If rate has changed from latest version, insert new row.
    If rate is the same, just update last_verified_at.

    Returns: 'inserted', 'verified', or 'error'
    """
    gross_rate = rate.get('gross_rate')
    net_rate = rate.get('net_rate')
    tariffs_data = rate.get('tariffs_data', {})

    # Get the latest rate for this category/date
    existing = db.execute(
        text("""
            SELECT id, rate_gross, rate_net, tariffs_data
            FROM newbook_current_rates
            WHERE category_id = :category_id AND rate_date = :rate_date
            ORDER BY valid_from DESC
            LIMIT 1
        """),
        {"category_id": category_id, "rate_date": rate_date}
    ).fetchone()

    if existing:
        existing_dict = {
            'rate_gross': existing.rate_gross,
            'rate_net': existing.rate_net,
            'tariffs_data': existing.tariffs_data
        }
    else:
        existing_dict = None

    if rates_changed(existing_dict, rate):
        # Rates changed - insert new snapshot
        db.execute(
            text("""
                INSERT INTO newbook_current_rates
                (category_id, rate_date, rate_gross, rate_net, tariffs_data, valid_from, last_verified_at)
                VALUES (:category_id, :rate_date, :rate_gross, :rate_net,
                        CAST(:tariffs_data AS jsonb), NOW(), NOW())
            """),
            {
                "category_id": category_id,
                "rate_date": rate_date,
                "rate_gross": gross_rate,
                "rate_net": net_rate,
                "tariffs_data": json.dumps(tariffs_data)
            }
        )
        return 'inserted'
    else:
        # Rates unchanged - just verify
        db.execute(
            text("""
                UPDATE newbook_current_rates
                SET last_verified_at = NOW()
                WHERE id = :id
            """),
            {"id": existing.id}
        )
        return 'verified'


async def run_fetch_current_rates(horizon_days: int = 720, start_date: date = None):
    """
    Fetch current rates for all included categories and store in database.

    Args:
        horizon_days: Number of days ahead to fetch (default 720 for scheduled, configurable for manual)
        start_date: Start date for fetch (default today)

    OPTIMIZED: Queries all categories in a single API call per date,
    reducing API calls from (categories × days) to just (days).

    Uses snapshot model - only stores new rows when rates change.
    """
    logger.info(f"Starting current rates fetch ({horizon_days} days)")

    db = next(iter([SyncSessionLocal()]))
    today = start_date or date.today()

    try:
        # Get VAT rate from config
        vat_result = db.execute(
            text("SELECT config_value FROM system_config WHERE config_key = 'accommodation_vat_rate'")
        ).fetchone()
        vat_rate_str = vat_result.config_value if vat_result and vat_result.config_value else '0.20'

        # Get all included room categories
        cat_result = db.execute(
            text("SELECT site_id FROM newbook_room_categories WHERE is_included = true")
        )
        included_categories = set(row.site_id for row in cat_result.fetchall())

        if not included_categories:
            logger.warning("No included room categories found")
            return

        logger.info(f"Fetching rates for {len(included_categories)} categories")

        # Import rates client
        import base64
        from services.newbook_rates_client import NewbookRatesClient

        # Get credentials from config (decrypt encrypted values)
        config_result = db.execute(
            text("""
                SELECT config_key, config_value, COALESCE(is_encrypted, false) as is_encrypted
                FROM system_config
                WHERE config_key IN ('newbook_api_key', 'newbook_username', 'newbook_password', 'newbook_region')
            """)
        )
        config = {}
        for row in config_result.fetchall():
            value = row.config_value
            if row.is_encrypted and value:
                try:
                    value = base64.b64decode(value.encode()).decode()
                except Exception:
                    pass  # Use raw value if decryption fails
            config[row.config_key] = value

        if not all(k in config for k in ['newbook_api_key', 'newbook_username', 'newbook_password', 'newbook_region']):
            logger.error("Newbook credentials not configured")
            return

        # Create client
        client = NewbookRatesClient(
            api_key=config['newbook_api_key'],
            username=config['newbook_username'],
            password=config['newbook_password'],
            region=config['newbook_region'],
            vat_rate=Decimal(vat_rate_str)
        )

        async with client:
            # OPTIMIZED: Use get_all_categories_single_night_rates for ALL 720 days
            # This queries all categories in ONE API call per date
            logger.info(f"Fetching single-night rates for {horizon_days} days (all categories per call)")
            all_rates = await client.get_all_categories_single_night_rates(
                today, today + timedelta(days=horizon_days)
            )

            # Collect dates needing multi-night verification
            # Group by min_stay value for efficient batching
            # Skip tariffs where failure is due to advance booking requirements
            # (e.g. "must be booked 365 days in advance" - 2-night recheck won't help)
            import re
            dates_by_nights: Dict[int, set] = {}
            skipped_advance = 0
            for category_id, rates in all_rates.items():
                if category_id not in included_categories:
                    continue
                for rate in rates:
                    tariffs_data = rate.get('tariffs_data', {})
                    rate_date = rate['date']
                    days_ahead = (rate_date - today).days if isinstance(rate_date, date) else 0
                    for tariff in tariffs_data.get('tariffs', []):
                        min_stay = tariff.get('min_stay')
                        # If unavailable and has min_stay > 1, we need to verify with multi-night query
                        if min_stay and min_stay > 1 and not tariff.get('success', False):
                            # Check if tariff has an advance booking requirement that isn't met
                            message = tariff.get('message', '') or ''
                            advance_match = re.search(r'(\d+)\s*days?\s*in\s*advance', message, re.IGNORECASE)
                            if advance_match:
                                min_advance_days = int(advance_match.group(1))
                                if days_ahead < min_advance_days:
                                    # Date is within advance period - recheck won't help
                                    skipped_advance += 1
                                    continue

                            if min_stay not in dates_by_nights:
                                dates_by_nights[min_stay] = set()
                            dates_by_nights[min_stay].add(rate_date)
            if skipped_advance > 0:
                logger.info(f"Skipped {skipped_advance} multi-night checks (advance booking restriction)")

            # Convert sets to sorted lists
            dates_by_nights_list = {nights: sorted(list(dates)) for nights, dates in dates_by_nights.items()}
            total_multi_night = sum(len(dates) for dates in dates_by_nights_list.values())

            if total_multi_night > 0:
                logger.info(f"Running multi-night verification for {total_multi_night} date(s)")
                for nights, dates in dates_by_nights_list.items():
                    logger.info(f"  {nights}-night check: {len(dates)} dates")

                # Fetch multi-night availability
                multi_night_results = await client.get_multi_night_availability(dates_by_nights_list)

                # Update tariffs_data with multi-night availability
                for category_id, rates in all_rates.items():
                    if category_id not in included_categories:
                        continue
                    for rate in rates:
                        rate_date = rate['date']
                        if rate_date in multi_night_results:
                            cat_availability = multi_night_results[rate_date].get(category_id, {})
                            tariffs_data = rate.get('tariffs_data', {})
                            for tariff in tariffs_data.get('tariffs', []):
                                tariff_name = tariff.get('name', '')
                                min_stay = tariff.get('min_stay')
                                if min_stay and min_stay > 1:
                                    # Update with multi-night availability result
                                    tariff['available_for_min_stay'] = cat_availability.get(tariff_name, False)

                logger.info(f"Multi-night verification complete")
            else:
                logger.info("No multi-night verification needed")

            # Save rates for included categories only
            inserted_total = 0
            verified_total = 0
            for category_id, rates in all_rates.items():
                if category_id not in included_categories:
                    continue  # Skip categories not in our included list

                for rate in rates:
                    rate_date = rate['date']
                    result = save_rate_snapshot(db, category_id, rate_date, rate)
                    if result == 'inserted':
                        inserted_total += 1
                    elif result == 'verified':
                        verified_total += 1

            logger.info(f"Complete: {inserted_total} new snapshots, {verified_total} verified unchanged")

        db.commit()
        logger.info("Current rates fetch completed successfully")

    except Exception as e:
        logger.error(f"Current rates fetch failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


