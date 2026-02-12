"""
Fetch Current Rates Job

Fetches current rack rates from Newbook API and populates newbook_current_rates table.
These rates are used by pickup-v2 model for upper bound calculations in confidence shading.

Uses a snapshot model - only inserts new rows when rates change, otherwise updates last_verified_at.
This allows tracking rate history over time.

Schedule: Daily at 5:20 AM (before pace snapshot runs)

Processing: Day-by-day with progressive DB commits. Each date is fully processed
(single-night fetch + inline multi-night verification) and saved before moving to the next.
If the job fails partway, all previously processed dates are preserved.
"""
import json
import logging
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, Set

import asyncio
from sqlalchemy import text
from database import SyncSessionLocal

logger = logging.getLogger(__name__)

COMMIT_BATCH_SIZE = 10  # Commit to DB every N days


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


def needs_multi_night_check(tariff: Dict, days_ahead: int) -> Optional[int]:
    """
    Check if a tariff needs multi-night verification.

    Returns the min_stay value if a multi-night check is needed, None otherwise.
    Skips tariffs with advance booking restrictions that aren't met.
    """
    min_stay = tariff.get('min_stay')
    if not min_stay or min_stay <= 1:
        return None
    if tariff.get('success', False):
        return None  # Already available as single-night, no recheck needed

    # Check for advance booking requirement
    message = tariff.get('message', '') or ''
    advance_match = re.search(r'(\d+)\s*days?\s*in\s*advance', message, re.IGNORECASE)
    if advance_match:
        min_advance_days = int(advance_match.group(1))
        if days_ahead < min_advance_days:
            return None  # Within advance period - recheck won't help

    return min_stay


async def run_fetch_current_rates(horizon_days: int = 720, start_date: date = None):
    """
    Fetch current rates for all included categories and store in database.

    Args:
        horizon_days: Number of days ahead to fetch (default 720 for scheduled, configurable for manual)
        start_date: Start date for fetch (default today)

    Processing: Day-by-day with progressive commits.
    For each date:
      1. Fetch single-night rates (all categories in one API call)
      2. Check if any tariffs need multi-night verification
      3. If so, run multi-night check immediately for that date
      4. Save all rates for that date to DB
      5. Commit every COMMIT_BATCH_SIZE days

    This means if the job fails at day 400, the first 390+ days are already saved.
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
            inserted_total = 0
            verified_total = 0
            multi_night_checks = 0
            skipped_advance = 0
            current_date = today
            day_count = 0

            while current_date <= today + timedelta(days=horizon_days):
                day_count += 1
                days_ahead = (current_date - today).days

                try:
                    # Step 1: Fetch single-night rates for all categories on this date
                    day_rates = await client.fetch_single_date_all_categories(
                        current_date, guests_adults=2, guests_children=0
                    )

                    # Step 2: Check for multi-night verification needs and run inline
                    # Collect unique min_stay values needed for this date
                    nights_needed: Set[int] = set()
                    for cat_id, rates in day_rates.items():
                        if cat_id not in included_categories:
                            continue
                        for rate in rates:
                            for tariff in rate.get('tariffs_data', {}).get('tariffs', []):
                                check = needs_multi_night_check(tariff, days_ahead)
                                if check:
                                    nights_needed.add(check)
                                elif tariff.get('min_stay') and tariff['min_stay'] > 1 and not tariff.get('success', False):
                                    skipped_advance += 1

                    # Step 3: Run multi-night checks for this date if needed
                    multi_night_results: Dict[int, Dict[str, Dict[str, bool]]] = {}
                    for nights in sorted(nights_needed):
                        try:
                            result = await client.fetch_multi_night_for_date(
                                current_date, nights
                            )
                            multi_night_results[nights] = result
                            multi_night_checks += 1
                            await asyncio.sleep(1.0)  # Rate limiting
                        except Exception as e:
                            logger.warning(f"Multi-night check failed for {current_date} ({nights}n): {e}")

                    # Step 4: Update tariffs with multi-night results and save to DB
                    for cat_id, rates in day_rates.items():
                        if cat_id not in included_categories:
                            continue
                        for rate in rates:
                            tariffs_data = rate.get('tariffs_data', {})
                            # Apply multi-night results to tariffs
                            for tariff in tariffs_data.get('tariffs', []):
                                min_stay = tariff.get('min_stay')
                                if min_stay and min_stay > 1 and min_stay in multi_night_results:
                                    cat_availability = multi_night_results[min_stay].get(cat_id, {})
                                    tariff_name = tariff.get('name', '')
                                    tariff['available_for_min_stay'] = cat_availability.get(tariff_name, False)

                            # Save to DB
                            result = save_rate_snapshot(db, cat_id, current_date, rate)
                            if result == 'inserted':
                                inserted_total += 1
                            elif result == 'verified':
                                verified_total += 1

                    if day_count % 50 == 0 or nights_needed:
                        logger.info(
                            f"Day {day_count}/{horizon_days}: {current_date}"
                            f" | {inserted_total} new, {verified_total} verified"
                            f"{f' | {len(nights_needed)} multi-night checks' if nights_needed else ''}"
                        )

                except Exception as e:
                    logger.warning(f"Failed to fetch rates for {current_date}: {e}")

                # Step 5: Commit periodically
                if day_count % COMMIT_BATCH_SIZE == 0:
                    db.commit()

                current_date += timedelta(days=1)
                await asyncio.sleep(1.0)  # Rate limiting between days

            # Final commit for remaining days
            db.commit()

            if skipped_advance > 0:
                logger.info(f"Skipped {skipped_advance} multi-night checks (advance booking restriction)")
            logger.info(
                f"Complete: {inserted_total} new snapshots, {verified_total} verified unchanged, "
                f"{multi_night_checks} multi-night checks"
            )

        logger.info("Current rates fetch completed successfully")

    except Exception as e:
        logger.error(f"Current rates fetch failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()
