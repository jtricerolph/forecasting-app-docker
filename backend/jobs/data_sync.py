"""
Data sync job - pulls data from Newbook and Resos APIs
"""
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Set

from sqlalchemy import text
from database import SyncSessionLocal
from services.newbook_client import NewbookClient
from services.resos_client import ResosClient

logger = logging.getLogger(__name__)


def get_config_value(db, key: str) -> Optional[str]:
    """Get a configuration value from system_config table."""
    result = db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = :key"),
        {"key": key}
    )
    row = result.fetchone()
    return row.config_value if row else None


def load_newbook_credentials(db) -> dict:
    """Load Newbook API credentials from database config."""
    import base64

    def decrypt(value: str) -> str:
        """Decrypt base64 encoded value"""
        if not value:
            return None
        try:
            return base64.b64decode(value.encode()).decode()
        except:
            return value

    # Get credentials (some are encrypted)
    api_key_result = db.execute(
        text("SELECT config_value, is_encrypted FROM system_config WHERE config_key = 'newbook_api_key'")
    )
    api_key_row = api_key_result.fetchone()

    password_result = db.execute(
        text("SELECT config_value, is_encrypted FROM system_config WHERE config_key = 'newbook_password'")
    )
    password_row = password_result.fetchone()

    username = get_config_value(db, 'newbook_username')
    region = get_config_value(db, 'newbook_region')

    api_key = None
    if api_key_row and api_key_row.config_value:
        api_key = decrypt(api_key_row.config_value) if api_key_row.is_encrypted else api_key_row.config_value

    password = None
    if password_row and password_row.config_value:
        password = decrypt(password_row.config_value) if password_row.is_encrypted else password_row.config_value

    return {
        'api_key': api_key,
        'username': username,
        'password': password,
        'region': region
    }


def load_resos_credentials(db) -> dict:
    """Load Resos API credentials from database config."""
    import base64

    def decrypt(value: str) -> str:
        """Decrypt base64 encoded value"""
        if not value:
            return None
        try:
            return base64.b64decode(value.encode()).decode()
        except:
            return value

    # Get API key (may be encrypted)
    api_key_result = db.execute(
        text("SELECT config_value, is_encrypted FROM system_config WHERE config_key = 'resos_api_key'")
    )
    api_key_row = api_key_result.fetchone()

    api_key = None
    if api_key_row and api_key_row.config_value:
        api_key = decrypt(api_key_row.config_value) if api_key_row.is_encrypted else api_key_row.config_value

    return {'api_key': api_key}


def load_gl_config(db) -> tuple:
    """
    Load GL code configuration for identifying breakfast/dinner items.

    Returns:
        tuple: (breakfast_codes, dinner_codes, breakfast_vat, dinner_vat, gl_mapping)
    """
    # Load configured GL codes
    breakfast_gl_codes = get_config_value(db, 'newbook_breakfast_gl_codes') or ''
    dinner_gl_codes = get_config_value(db, 'newbook_dinner_gl_codes') or ''

    # Parse into sets
    breakfast_codes = set(c.strip() for c in breakfast_gl_codes.split(',') if c.strip())
    dinner_codes = set(c.strip() for c in dinner_gl_codes.split(',') if c.strip())

    # Load VAT rates
    breakfast_vat = float(get_config_value(db, 'newbook_breakfast_vat_rate') or 0.20)
    dinner_vat = float(get_config_value(db, 'newbook_dinner_vat_rate') or 0.20)

    # Build GL account ID → GL code mapping from cached lookup table
    gl_mapping: Dict[str, str] = {}
    result = db.execute(text("SELECT gl_account_id, gl_code FROM newbook_gl_accounts"))
    for row in result.fetchall():
        if row.gl_account_id and row.gl_code:
            gl_mapping[row.gl_account_id] = row.gl_code

    logger.info(f"Loaded GL config: {len(breakfast_codes)} breakfast codes, {len(dinner_codes)} dinner codes, {len(gl_mapping)} mappings")

    return breakfast_codes, dinner_codes, breakfast_vat, dinner_vat, gl_mapping


def process_inventory_items(
    inventory_items: list,
    gl_mapping: Dict[str, str],
    breakfast_codes: Set[str],
    dinner_codes: Set[str],
    breakfast_vat: float,
    dinner_vat: float
) -> dict:
    """
    Process inventory items and categorize by GL code.

    Returns dict with keys: breakfast_gross, breakfast_net, dinner_gross, dinner_net, other_items
    """
    breakfast_gross = 0.0
    dinner_gross = 0.0
    other_items = []

    for item in inventory_items:
        gl_account_id = item.get('gl_account_id')
        # Try to get GL code from mapping, fall back to gl_account_code in the item
        gl_code = gl_mapping.get(gl_account_id) or item.get('gl_account_code') or ''
        amount = float(item.get('amount', 0) or 0)

        if gl_code in breakfast_codes:
            breakfast_gross += amount
        elif gl_code in dinner_codes:
            dinner_gross += amount
        else:
            # Store non-breakfast/dinner items for reference
            other_items.append({
                'item_name': item.get('item_name'),
                'gl_account_id': gl_account_id,
                'gl_code': gl_code,
                'amount': amount
            })

    # Calculate net values (gross / (1 + VAT rate))
    breakfast_net = breakfast_gross / (1 + breakfast_vat) if breakfast_vat else breakfast_gross
    dinner_net = dinner_gross / (1 + dinner_vat) if dinner_vat else dinner_gross

    return {
        'breakfast_gross': round(breakfast_gross, 2),
        'breakfast_net': round(breakfast_net, 2),
        'dinner_gross': round(dinner_gross, 2),
        'dinner_net': round(dinner_net, 2),
        'other_items': other_items if other_items else None
    }


async def run_data_sync(
    full_sync: bool = False,
    triggered_by: str = "scheduler"
):
    """
    Main data sync job - runs Newbook bookings, Newbook occupancy report, and Resos sync.

    Args:
        full_sync: If True, pulls all bookings. If False, only pulls changes since last sync.
        triggered_by: Who/what triggered this sync
    """
    logger.info(f"Starting data sync (full_sync={full_sync})")

    try:
        # Sync Newbook booking data
        await sync_newbook_data(full_sync=full_sync, triggered_by=triggered_by)

        # Sync Newbook occupancy report (provides available rooms, maintenance, official revenue)
        # Daily sync: -7 days (catch corrections) to +365 days (future availability for forecasting)
        # Can't forecast beyond what's available - need to know maintenance/blocked rooms
        occ_from_date = date.today() - timedelta(days=7)
        occ_to_date = date.today() + timedelta(days=365)
        await sync_newbook_occupancy_report(occ_from_date, occ_to_date, triggered_by)

        # Sync Resos data (still uses date range for now)
        from_date = date.today() - timedelta(days=7)
        to_date = date.today() + timedelta(days=365)
        await sync_resos_data(from_date, to_date, triggered_by)

        logger.info("Data sync completed successfully")
    except Exception as e:
        logger.error(f"Data sync failed: {e}")
        raise


async def sync_newbook_data(
    full_sync: bool = False,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    triggered_by: str = "scheduler"
):
    """
    Sync hotel bookings from Newbook.

    Uses list_type="all" which returns all bookings including cancelled.
    - full_sync=True: Fetches entire booking database (initial backfill)
    - full_sync=False: Fetches only bookings modified since last successful sync
    - from_date/to_date: If provided, fetches bookings staying during this period
    """
    import sys
    print(f"[SYNC] Starting Newbook sync (full_sync={full_sync})", flush=True)
    sys.stdout.flush()

    if from_date and to_date:
        logger.info(f"Starting Newbook sync for stay dates {from_date} to {to_date}")
    else:
        logger.info(f"Starting Newbook sync (full_sync={full_sync})")

    db = next(iter([SyncSessionLocal()]))

    # Load credentials from database
    creds = load_newbook_credentials(db)
    print(f"[SYNC] Loaded credentials: api_key={'set' if creds['api_key'] else 'empty'}, username={creds['username']}, region={creds['region']}", flush=True)
    logger.info(f"Loaded Newbook credentials: api_key={'set' if creds['api_key'] else 'empty'}, username={creds['username']}, region={creds['region']}")

    # Load GL configuration for inventory item categorization
    breakfast_codes, dinner_codes, breakfast_vat, dinner_vat, gl_mapping = load_gl_config(db)

    try:
        # Get last successful sync timestamp for incremental sync
        modified_since = None
        if not full_sync:
            result = db.execute(
                text("""
                SELECT completed_at FROM sync_log
                WHERE source = 'newbook' AND status = 'success'
                ORDER BY completed_at DESC LIMIT 1
                """)
            )
            row = result.fetchone()
            if row and row.completed_at:
                modified_since = row.completed_at.isoformat()
                logger.info(f"Incremental sync: fetching bookings modified since {modified_since}")
            else:
                logger.info("No previous successful sync found, performing full sync")

        # Log sync start
        db.execute(
            text("""
            INSERT INTO sync_log (sync_type, source, started_at, status, triggered_by)
            VALUES ('bookings', 'newbook', NOW(), 'running', :triggered_by)
            RETURNING id
            """),
            {"triggered_by": triggered_by}
        )
        db.commit()

        print("[SYNC] Creating NewbookClient...", flush=True)
        async with NewbookClient(
            api_key=creds['api_key'],
            username=creds['username'],
            password=creds['password'],
            region=creds['region']
        ) as client:
            # Test connection
            print("[SYNC] Testing connection...", flush=True)
            if not await client.test_connection():
                print("[SYNC] Connection test FAILED!", flush=True)
                raise Exception("Newbook connection failed")
            print("[SYNC] Connection test passed", flush=True)

            # Fetch bookings based on sync mode
            print(f"[SYNC] Fetching bookings (modified_since={modified_since})...", flush=True)
            if from_date and to_date:
                # Date range sync - fetch bookings staying during this period
                # This is useful for testing or targeted syncs
                bookings = await client.get_bookings_by_stay_dates(
                    from_date=from_date,
                    to_date=to_date,
                    list_type="staying"  # Gets all bookings staying during this period
                )
                print(f"[SYNC] Fetched {len(bookings)} bookings (stay dates: {from_date} to {to_date})", flush=True)
                logger.info(f"Fetched {len(bookings)} bookings from Newbook (stay dates: {from_date} to {to_date})")
            else:
                # Standard sync - all bookings (optionally filtered by modification date)
                bookings = await client.get_bookings(modified_since=modified_since)
                print(f"[SYNC] Fetched {len(bookings)} bookings from Newbook", flush=True)
                logger.info(f"Fetched {len(bookings)} bookings from Newbook")

            records_created = 0
            records_updated = 0

            print(f"[SYNC] Starting to process {len(bookings)} bookings...", flush=True)
            for i, booking in enumerate(bookings):
                newbook_id = booking.get("booking_id")

                # Progress every 100 bookings
                if i > 0 and i % 100 == 0:
                    print(f"[SYNC] Processed {i}/{len(bookings)} bookings, {records_created} created", flush=True)

                # Skip bookings without a valid ID
                if not newbook_id:
                    logger.warning(f"Skipping booking without booking_id: {booking.get('booking_reference_id', 'unknown')}")
                    continue

                # Convert to string for VARCHAR column
                newbook_id = str(newbook_id)

                try:
                    # Create sanitized copy of raw JSON (remove guest PII)
                    raw_booking = {k: v for k, v in booking.items() if k != "guests"}
                    raw_json_str = json.dumps(raw_booking)

                    # Parse arrival/departure - API returns "2026-02-16 15:00:00" format
                    arrival_raw = booking.get("booking_arrival")
                    departure_raw = booking.get("booking_departure")
                    arrival = arrival_raw.split(" ")[0] if arrival_raw else None  # Extract date part only
                    departure = departure_raw.split(" ")[0] if departure_raw else None

                    status = booking.get("booking_status")
                    category_id = str(booking.get("category_id")) if booking.get("category_id") else None
                    category_name = booking.get("category_name")

                    # Upsert room category to lookup table
                    if category_id:
                        db.execute(
                            text("""
                            INSERT INTO room_categories (category_id, category_name)
                            VALUES (:category_id, :category_name)
                            ON CONFLICT (category_id) DO UPDATE SET
                                category_name = COALESCE(:category_name, room_categories.category_name),
                                updated_at = NOW()
                            """),
                            {"category_id": category_id, "category_name": category_name}
                        )

                    # Upsert booking
                    result = db.execute(
                        text("""
                        INSERT INTO newbook_bookings (
                            newbook_id, booking_reference, arrival_date, departure_date,
                            nights, adults, children, infants, total_guests,
                            category_id, room_type, status, total_amount, tariff_name,
                            booking_source_name, raw_json, fetched_at
                        ) VALUES (
                            :newbook_id, :reference, :arrival, :departure,
                            :nights, :adults, :children, :infants, :total_guests,
                            :category_id, :room_type, :status, :total, :tariff_name,
                            :source, :raw_json, NOW()
                        )
                        ON CONFLICT (newbook_id) DO UPDATE SET
                            status = :status,
                            total_amount = :total,
                            raw_json = :raw_json,
                            fetched_at = NOW()
                        """),
                        {
                            "newbook_id": newbook_id,
                            "reference": booking.get("booking_reference_id"),
                            "arrival": arrival,
                            "departure": departure,
                            "nights": booking.get("booking_length"),
                            "adults": int(booking.get("booking_adults") or 0),
                            "children": int(booking.get("booking_children") or 0),
                            "infants": int(booking.get("booking_infants") or 0),
                            "total_guests": int(booking.get("booking_adults") or 0) + int(booking.get("booking_children") or 0),
                            "category_id": category_id,
                            "room_type": category_name,
                            "status": status,
                            "total": booking.get("booking_total"),
                            "tariff_name": booking.get("tariff_name"),
                            "source": booking.get("booking_source_name"),
                            "raw_json": raw_json_str
                        }
                    )

                    if result.rowcount > 0:
                        records_created += 1

                    # Get the booking's internal ID for child table references
                    booking_db_id = None
                    id_result = db.execute(
                        text("SELECT id FROM newbook_bookings WHERE newbook_id = :newbook_id"),
                        {"newbook_id": newbook_id}
                    )
                    id_row = id_result.fetchone()
                    if id_row:
                        booking_db_id = id_row.id

                    # Get inventory items and group by stay_date
                    inventory_items = booking.get("inventory_items", [])
                    inventory_by_date = {}
                    for item in inventory_items:
                        stay_date = item.get("stay_date")
                        if stay_date:
                            if stay_date not in inventory_by_date:
                                inventory_by_date[stay_date] = []
                            inventory_by_date[stay_date].append(item)

                    # Extract and store per-night tariff breakdown + inventory data
                    tariffs_quoted = booking.get("tariffs_quoted", [])
                    if booking_db_id and tariffs_quoted:
                        for tariff in tariffs_quoted:
                            stay_date = tariff.get("stay_date")
                            if stay_date:
                                # Process inventory items for this night using GL code matching
                                date_inventory = inventory_by_date.get(stay_date, [])
                                inv_data = process_inventory_items(
                                    date_inventory,
                                    gl_mapping,
                                    breakfast_codes,
                                    dinner_codes,
                                    breakfast_vat,
                                    dinner_vat
                                )

                                db.execute(
                                    text("""
                                    INSERT INTO newbook_booking_nights (
                                        booking_id, stay_date, tariff_quoted_id, tariff_label,
                                        tariff_type_id, tariff_applied_id, original_amount,
                                        calculated_amount, charge_amount, taxes, occupant_charges,
                                        breakfast_gross, breakfast_net, dinner_gross, dinner_net,
                                        other_items, fetched_at
                                    ) VALUES (
                                        :booking_id, :stay_date, :tariff_quoted_id, :tariff_label,
                                        :tariff_type_id, :tariff_applied_id, :original_amount,
                                        :calculated_amount, :charge_amount, :taxes, :occupant_charges,
                                        :breakfast_gross, :breakfast_net, :dinner_gross, :dinner_net,
                                        :other_items, NOW()
                                    )
                                    ON CONFLICT (booking_id, stay_date) DO UPDATE SET
                                        tariff_label = :tariff_label,
                                        original_amount = :original_amount,
                                        calculated_amount = :calculated_amount,
                                        charge_amount = :charge_amount,
                                        taxes = :taxes,
                                        occupant_charges = :occupant_charges,
                                        breakfast_gross = :breakfast_gross,
                                        breakfast_net = :breakfast_net,
                                        dinner_gross = :dinner_gross,
                                        dinner_net = :dinner_net,
                                        other_items = :other_items,
                                        fetched_at = NOW()
                                    """),
                                    {
                                        "booking_id": booking_db_id,
                                        "stay_date": stay_date,
                                        "tariff_quoted_id": tariff.get("tariff_quoted_id"),
                                        "tariff_label": tariff.get("label"),
                                        "tariff_type_id": tariff.get("type_id"),
                                        "tariff_applied_id": tariff.get("tariff_applied_id"),
                                        "original_amount": tariff.get("original_amount"),
                                        "calculated_amount": tariff.get("calculated_amount"),
                                        "charge_amount": tariff.get("charge_amount"),
                                        "taxes": json.dumps(tariff.get("taxes", [])),
                                        "occupant_charges": json.dumps(tariff.get("occupant_charges", [])),
                                        "breakfast_gross": inv_data['breakfast_gross'],
                                        "breakfast_net": inv_data['breakfast_net'],
                                        "dinner_gross": inv_data['dinner_gross'],
                                        "dinner_net": inv_data['dinner_net'],
                                        "other_items": json.dumps(inv_data['other_items']) if inv_data['other_items'] else None
                                    }
                                )

                    # Queue all stay dates for aggregation (arrival to departure-1)
                    # Each night the guest is "in house" needs recalculating
                    if arrival and departure:
                        arrival_date = date.fromisoformat(arrival) if isinstance(arrival, str) else arrival
                        departure_date = date.fromisoformat(departure) if isinstance(departure, str) else departure

                        current = arrival_date
                        while current < departure_date:
                            db.execute(
                                text("""
                                INSERT INTO aggregation_queue (date, source, reason, booking_id)
                                VALUES (:date, 'newbook', :reason, :booking_id)
                                ON CONFLICT (date, source, booking_id) DO UPDATE SET
                                    queued_at = NOW(),
                                    aggregated_at = NULL
                                """),
                                {
                                    "date": current,
                                    "reason": f"booking_{status.lower() if status else 'modified'}",
                                    "booking_id": str(newbook_id)
                                }
                            )
                            current += timedelta(days=1)

                    # Commit this booking immediately
                    db.commit()

                except Exception as booking_error:
                    print(f"[SYNC] ERROR processing booking {newbook_id}: {booking_error}", flush=True)
                    logger.error(f"Error processing booking {newbook_id}: {booking_error}")
                    db.rollback()  # Rollback only this booking's changes
                    continue  # Skip this booking and continue with the next

            # Update sync log
            db.execute(
                text("""
                UPDATE sync_log
                SET completed_at = NOW(), status = 'success',
                    records_fetched = :fetched, records_created = :created
                WHERE id = (
                    SELECT id FROM sync_log
                    WHERE source = 'newbook' AND status = 'running'
                    ORDER BY started_at DESC LIMIT 1
                )
                """),
                {"fetched": len(bookings), "created": records_created}
            )
            db.commit()

        print(f"[SYNC] Sync completed: {records_created} records processed", flush=True)
        logger.info(f"Newbook sync completed: {records_created} records processed")

    except Exception as e:
        print(f"[SYNC] SYNC FAILED: {e}", flush=True)
        import traceback
        traceback.print_exc()
        logger.error(f"Newbook sync failed: {e}")
        try:
            db.rollback()  # Rollback any failed transaction first
            db.execute(
                text("""
                UPDATE sync_log
                SET completed_at = NOW(), status = 'failed', error_message = :error
                WHERE id = (
                    SELECT id FROM sync_log
                    WHERE source = 'newbook' AND status = 'running'
                    ORDER BY started_at DESC LIMIT 1
                )
                """),
                {"error": str(e)[:500]}  # Truncate error message to avoid issues
            )
            db.commit()
        except Exception as log_error:
            logger.error(f"Failed to update sync_log: {log_error}")
        raise
    finally:
        db.close()


def load_resos_custom_field_mappings(db) -> Dict[str, dict]:
    """
    Load custom field mappings from resos_custom_field_mapping table.

    Returns dict: {field_id: {"maps_to": "hotel_guest", "value_for_true": "Yes"}}
    """
    result = db.execute(text("""
        SELECT field_id, maps_to, value_for_true
        FROM resos_custom_field_mapping
        WHERE maps_to != 'ignore'
    """))
    mappings = {}
    for row in result.fetchall():
        mappings[row.field_id] = {
            "maps_to": row.maps_to,
            "value_for_true": row.value_for_true
        }
    return mappings


async def sync_resos_data(
    from_date: date,
    to_date: date,
    triggered_by: str = "scheduler"
):
    """
    Sync restaurant bookings from Resos.
    """
    logger.info(f"Starting Resos sync from {from_date} to {to_date}")

    db = next(iter([SyncSessionLocal()]))

    try:
        # Log sync start
        db.execute(
            text("""
            INSERT INTO sync_log (sync_type, source, started_at, status, date_from, date_to, triggered_by)
            VALUES ('bookings', 'resos', NOW(), 'running', :from_date, :to_date, :triggered_by)
            """),
            {"from_date": from_date, "to_date": to_date, "triggered_by": triggered_by}
        )
        db.commit()

        # Load Resos credentials from database
        resos_creds = load_resos_credentials(db)
        if not resos_creds.get('api_key'):
            raise Exception("Resos API key not configured in database")

        # Load custom field mappings from database
        cf_mappings = load_resos_custom_field_mappings(db)
        logger.info(f"Loaded {len(cf_mappings)} Resos custom field mappings")

        async with ResosClient(api_key=resos_creds['api_key']) as client:
            # Test connection
            if not await client.test_connection():
                raise Exception("Resos connection failed")

            # Fetch bookings
            bookings = await client.get_bookings(from_date, to_date)
            logger.info(f"Fetched {len(bookings)} bookings from Resos")

            records_created = 0

            for booking in bookings:
                # Parse guest info
                guest = booking.get("guest", {})
                resos_id = booking.get("_id")
                booking_date = booking.get("date")
                status = booking.get("status")

                # Extract custom fields using configured mappings
                custom_fields = booking.get("customFields", [])
                is_hotel_guest = None
                is_dbb = None
                is_package = None
                hotel_booking_number = None
                allergies = None

                for cf in custom_fields:
                    # Get field ID - Resos may use 'id' or '_id'
                    field_id = cf.get("id") or cf.get("_id") or cf.get("fieldId")
                    # For radio/checkbox fields, use multipleChoiceValueName (human-readable label)
                    # Fall back to value field for text fields
                    field_value_label = cf.get("multipleChoiceValueName") or cf.get("value")
                    field_value = cf.get("value")

                    # Check if this field has a configured mapping
                    if field_id and field_id in cf_mappings:
                        mapping = cf_mappings[field_id]
                        maps_to = mapping["maps_to"]
                        value_for_true = mapping.get("value_for_true")

                        # Debug logging for matched mappings (first 5 records only)
                        if records_created < 5:
                            logger.info(f"Matched mapping: field_id={field_id}, maps_to={maps_to}, label={field_value_label}, value_for_true={value_for_true}")

                        if maps_to == "hotel_guest":
                            # For boolean fields, check label against value_for_true
                            if value_for_true:
                                is_hotel_guest = str(field_value_label) == str(value_for_true)
                            else:
                                is_hotel_guest = str(field_value_label).lower() in ("yes", "true", "1")
                        elif maps_to == "dbb":
                            if value_for_true:
                                is_dbb = str(field_value_label) == str(value_for_true)
                            else:
                                is_dbb = str(field_value_label).lower() in ("yes", "true", "1")
                        elif maps_to == "package":
                            if value_for_true:
                                is_package = str(field_value) == str(value_for_true)
                            else:
                                is_package = str(field_value).lower() in ("yes", "true", "1")
                        elif maps_to == "booking_number":
                            hotel_booking_number = str(field_value) if field_value else None
                        elif maps_to == "allergies":
                            allergies = str(field_value) if field_value else None

                    # Fallback to keyword matching if no mapping configured
                    elif not cf_mappings:
                        field_name = cf.get("name", "").lower()
                        if "hotel" in field_name and "guest" in field_name:
                            is_hotel_guest = str(field_value).lower() in ("yes", "true", "1")
                        elif "dbb" in field_name or "dinner bed breakfast" in field_name:
                            is_dbb = str(field_value).lower() in ("yes", "true", "1")
                        elif "package" in field_name:
                            is_package = str(field_value).lower() in ("yes", "true", "1")
                        elif "booking" in field_name and "number" in field_name:
                            hotel_booking_number = str(field_value) if field_value else None
                        elif "allerg" in field_name:
                            allergies = str(field_value) if field_value else None

                # Upsert booking with full data
                db.execute(
                    text("""
                    INSERT INTO resos_bookings (
                        resos_id, booking_date, booking_time, covers,
                        status, source, opening_hour_id, table_name, table_area,
                        is_hotel_guest, is_dbb, is_package, hotel_booking_number, allergies,
                        notes, fetched_at
                    ) VALUES (
                        :resos_id, :booking_date, :booking_time, :covers,
                        :status, :source, :opening_hour_id, :table_name, :table_area,
                        :is_hotel_guest, :is_dbb, :is_package, :hotel_booking_number, :allergies,
                        :notes, NOW()
                    )
                    ON CONFLICT (resos_id) DO UPDATE SET
                        status = :status,
                        covers = :covers,
                        is_hotel_guest = COALESCE(:is_hotel_guest, resos_bookings.is_hotel_guest),
                        is_dbb = COALESCE(:is_dbb, resos_bookings.is_dbb),
                        is_package = COALESCE(:is_package, resos_bookings.is_package),
                        fetched_at = NOW()
                    """),
                    {
                        "resos_id": resos_id,
                        "booking_date": booking_date,
                        "booking_time": booking.get("time"),
                        "covers": booking.get("people"),
                        "status": status,
                        "source": booking.get("source"),
                        "opening_hour_id": booking.get("openingHourId"),
                        "table_name": booking.get("tables", [{}])[0].get("name") if booking.get("tables") else None,
                        "table_area": booking.get("tables", [{}])[0].get("area", {}).get("name") if booking.get("tables") else None,
                        "is_hotel_guest": is_hotel_guest,
                        "is_dbb": is_dbb,
                        "is_package": is_package,
                        "hotel_booking_number": hotel_booking_number,
                        "allergies": allergies,
                        "notes": str(booking.get("restaurantNotes", []))
                    }
                )
                records_created += 1

                # Queue date for aggregation
                if booking_date:
                    db.execute(
                        text("""
                        INSERT INTO aggregation_queue (date, source, reason, booking_id)
                        VALUES (:date, 'resos', :reason, :booking_id)
                        ON CONFLICT (date, source, booking_id) DO UPDATE SET
                            queued_at = NOW(),
                            aggregated_at = NULL
                        """),
                        {
                            "date": booking_date,
                            "reason": f"booking_{status.lower() if status else 'modified'}",
                            "booking_id": str(resos_id)
                        }
                    )

            db.commit()

            # Update sync log
            db.execute(
                text("""
                UPDATE sync_log
                SET completed_at = NOW(), status = 'success',
                    records_fetched = :fetched, records_created = :created
                WHERE id = (
                    SELECT id FROM sync_log
                    WHERE source = 'resos' AND status = 'running'
                    ORDER BY started_at DESC LIMIT 1
                )
                """),
                {"fetched": len(bookings), "created": records_created}
            )
            db.commit()

        logger.info(f"Resos sync completed: {records_created} records processed")

    except Exception as e:
        logger.error(f"Resos sync failed: {e}")
        db.execute(
            text("""
            UPDATE sync_log
            SET completed_at = NOW(), status = 'failed', error_message = :error
            WHERE id = (
                SELECT id FROM sync_log
                WHERE source = 'resos' AND status = 'running'
                ORDER BY started_at DESC LIMIT 1
            )
            """),
            {"error": str(e)}
        )
        db.commit()
        raise
    finally:
        db.close()


async def sync_newbook_occupancy_report(
    from_date: date,
    to_date: date,
    triggered_by: str = "scheduler"
):
    """
    Sync occupancy report from Newbook's reports_occupancy endpoint.

    This provides:
    - Available rooms per category (total capacity minus maintenance/offline)
    - Official occupied rooms
    - Maintenance/offline room counts
    - Official revenue figures (gross)

    The 'available' field is crucial for accurate occupancy % calculations
    as it accounts for rooms taken offline for maintenance.

    API returns all categories with all dates in a single response (no pagination).
    """
    import sys

    print(f"[SYNC] Starting Newbook occupancy report sync ({from_date} to {to_date})", flush=True)
    sys.stdout.flush()

    logger.info(f"Starting Newbook occupancy report sync from {from_date} to {to_date}")

    db = next(iter([SyncSessionLocal()]))

    # Load credentials
    creds = load_newbook_credentials(db)

    # Get accommodation VAT rate for calculating net revenue
    result = db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'accommodation_vat_rate'")
    )
    row = result.fetchone()
    accommodation_vat = float(row.config_value) if row and row.config_value else 0.20

    try:
        # Log sync start
        db.execute(
            text("""
            INSERT INTO sync_log (sync_type, source, started_at, status, date_from, date_to, triggered_by)
            VALUES ('occupancy_report', 'newbook', NOW(), 'running', :from_date, :to_date, :triggered_by)
            """),
            {"from_date": from_date, "to_date": to_date, "triggered_by": triggered_by}
        )
        db.commit()

        print("[SYNC] Creating NewbookClient for occupancy report...", flush=True)
        async with NewbookClient(
            api_key=creds['api_key'],
            username=creds['username'],
            password=creds['password'],
            region=creds['region']
        ) as client:
            # Test connection
            if not await client.test_connection():
                raise Exception("Newbook connection failed")

            records_created = 0

            # Track daily totals as we process categories
            # {date: {available: X, occupied: X, maintenance: X, revenue_gross: X, revenue_net: X}}
            daily_totals = {}

            print(f"[SYNC] Fetching occupancy report: {from_date} to {to_date}...", flush=True)
            report_data = await client.get_occupancy_report(from_date, to_date)
            print(f"[SYNC] Received {len(report_data)} categories", flush=True)

            # Response format is a list of categories, each with nested occupancy by date
            for category in report_data:
                category_id = str(category.get("category_id", ""))
                category_name = category.get("category_name", "")
                occupancy_data = category.get("occupancy", {})

                if not category_id:
                    logger.warning(f"Skipping category without ID: {category}")
                    continue

                # Process each date in the occupancy data
                for date_str, day_data in occupancy_data.items():
                    try:
                        # Parse date (could be "2024-08-01" format)
                        report_date = date.fromisoformat(date_str) if isinstance(date_str, str) else date_str

                        available = int(day_data.get("available", 0) or 0)
                        occupied = int(day_data.get("occupied", 0) or 0)
                        maintenance = int(day_data.get("maintenance", 0) or 0)
                        allotted = int(day_data.get("allotted", 0) or 0)
                        revenue_gross = float(day_data.get("revenue_gross", 0) or 0)

                        # Calculate net revenue (gross / (1 + VAT rate))
                        # Use provided revenue_net if available, otherwise calculate
                        revenue_net = day_data.get("revenue_net")
                        if revenue_net is None:
                            revenue_net = revenue_gross / (1 + accommodation_vat) if accommodation_vat else revenue_gross
                        else:
                            revenue_net = float(revenue_net)

                        # Calculate occupancy percentage
                        occupancy_pct = (occupied / available * 100) if available > 0 else 0

                        # Upsert into newbook_occupancy_report_data
                        db.execute(
                            text("""
                            INSERT INTO newbook_occupancy_report_data (
                                date, category_id, category_name,
                                available, occupied, maintenance, allotted,
                                revenue_gross, revenue_net, occupancy_pct, fetched_at
                            ) VALUES (
                                :date, :category_id, :category_name,
                                :available, :occupied, :maintenance, :allotted,
                                :revenue_gross, :revenue_net, :occupancy_pct, NOW()
                            )
                            ON CONFLICT (date, category_id) DO UPDATE SET
                                category_name = :category_name,
                                available = :available,
                                occupied = :occupied,
                                maintenance = :maintenance,
                                allotted = :allotted,
                                revenue_gross = :revenue_gross,
                                revenue_net = :revenue_net,
                                occupancy_pct = :occupancy_pct,
                                fetched_at = NOW()
                            """),
                            {
                                "date": report_date,
                                "category_id": category_id,
                                "category_name": category_name,
                                "available": available,
                                "occupied": occupied,
                                "maintenance": maintenance,
                                "allotted": allotted,
                                "revenue_gross": round(revenue_gross, 2),
                                "revenue_net": round(revenue_net, 2),
                                "occupancy_pct": round(occupancy_pct, 2)
                            }
                        )
                        records_created += 1

                        # Accumulate daily totals
                        if report_date not in daily_totals:
                            daily_totals[report_date] = {
                                "available": 0,
                                "occupied": 0,
                                "maintenance": 0,
                                "revenue_gross": 0.0,
                                "revenue_net": 0.0
                            }
                        daily_totals[report_date]["available"] += available
                        daily_totals[report_date]["occupied"] += occupied
                        daily_totals[report_date]["maintenance"] += maintenance
                        daily_totals[report_date]["revenue_gross"] += revenue_gross
                        daily_totals[report_date]["revenue_net"] += revenue_net

                    except Exception as day_error:
                        logger.error(f"Error processing occupancy for {category_id} on {date_str}: {day_error}")
                        continue

            db.commit()

            # Update sync log
            db.execute(
                text("""
                UPDATE sync_log
                SET completed_at = NOW(), status = 'success',
                    records_fetched = :fetched, records_created = :created
                WHERE id = (
                    SELECT id FROM sync_log
                    WHERE source = 'newbook' AND sync_type = 'occupancy_report' AND status = 'running'
                    ORDER BY started_at DESC LIMIT 1
                )
                """),
                {"fetched": records_created, "created": records_created}
            )
            db.commit()

        print(f"[SYNC] Occupancy report sync completed: {records_created} category records, {len(daily_totals)} daily totals", flush=True)
        logger.info(f"Newbook occupancy report sync completed: {records_created} category records, {len(daily_totals)} daily totals")

    except Exception as e:
        print(f"[SYNC] Occupancy report sync FAILED: {e}", flush=True)
        import traceback
        traceback.print_exc()
        logger.error(f"Newbook occupancy report sync failed: {e}")
        try:
            db.rollback()
            db.execute(
                text("""
                UPDATE sync_log
                SET completed_at = NOW(), status = 'failed', error_message = :error
                WHERE id = (
                    SELECT id FROM sync_log
                    WHERE source = 'newbook' AND sync_type = 'occupancy_report' AND status = 'running'
                    ORDER BY started_at DESC LIMIT 1
                )
                """),
                {"error": str(e)[:500]}
            )
            db.commit()
        except Exception as log_error:
            logger.error(f"Failed to update sync_log: {log_error}")
        raise
    finally:
        db.close()


async def sync_newbook_earned_revenue(
    from_date: date,
    to_date: date,
    triggered_by: str = "scheduler"
):
    """
    Sync earned revenue from Newbook's report_earned_revenue endpoint.

    This provides official financial figures by GL account - the declared
    accounting revenue that flows into the books.

    Uses accommodation_gl_codes config to identify which GL accounts are
    room revenue vs other types (F&B, etc.).

    Fetches day-by-day (API only returns daily breakdown when requesting single days).
    Schedule: Historical backfill + daily last 7 days to catch adjustments.
    """
    import sys

    print(f"[SYNC] Starting Newbook earned revenue sync ({from_date} to {to_date})", flush=True)
    sys.stdout.flush()

    logger.info(f"Starting Newbook earned revenue sync from {from_date} to {to_date}")

    db = next(iter([SyncSessionLocal()]))

    # Load credentials
    creds = load_newbook_credentials(db)

    # Load accommodation GL codes configuration
    result = db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'accommodation_gl_codes'")
    )
    row = result.fetchone()
    accommodation_gl_codes_str = row.config_value if row and row.config_value else ""
    accommodation_gl_codes = set(c.strip() for c in accommodation_gl_codes_str.split(',') if c.strip())

    if not accommodation_gl_codes:
        logger.warning("No accommodation_gl_codes configured - all revenue will be marked as 'other'")
        print("[SYNC] WARNING: No accommodation_gl_codes configured", flush=True)

    # Get accommodation VAT rate for calculating net if not provided
    result = db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'accommodation_vat_rate'")
    )
    row = result.fetchone()
    accommodation_vat = float(row.config_value) if row and row.config_value else 0.20

    try:
        # Log sync start
        db.execute(
            text("""
            INSERT INTO sync_log (sync_type, source, started_at, status, date_from, date_to, triggered_by)
            VALUES ('earned_revenue', 'newbook', NOW(), 'running', :from_date, :to_date, :triggered_by)
            """),
            {"from_date": from_date, "to_date": to_date, "triggered_by": triggered_by}
        )
        db.commit()

        print("[SYNC] Creating NewbookClient for earned revenue...", flush=True)
        async with NewbookClient(
            api_key=creds['api_key'],
            username=creds['username'],
            password=creds['password'],
            region=creds['region']
        ) as client:
            # Test connection
            if not await client.test_connection():
                raise Exception("Newbook connection failed")

            records_created = 0
            days_processed = 0

            # Track daily accommodation totals for updating daily_occupancy
            daily_accommodation = {}  # {date: {gross: X, net: X}}

            # Track unique GL accounts for caching (for Settings page reference)
            gl_accounts_seen = {}  # {gl_account_id: {gl_code, gl_name, last_date, total}}

            # Fetch earned revenue (returns dict keyed by date)
            print(f"[SYNC] Fetching earned revenue: {from_date} to {to_date}...", flush=True)
            revenue_data = await client.get_earned_revenue(from_date, to_date)
            print(f"[SYNC] Received data for {len(revenue_data)} days", flush=True)

            for date_str, day_data in revenue_data.items():
                try:
                    revenue_date = date.fromisoformat(date_str)
                    days_processed += 1

                    # Initialize daily totals
                    if revenue_date not in daily_accommodation:
                        daily_accommodation[revenue_date] = {"gross": 0.0, "net": 0.0}

                    # Process GL accounts
                    # API may return list directly or nested in dict
                    if isinstance(day_data, list):
                        gl_accounts = day_data
                    elif isinstance(day_data, dict):
                        gl_accounts = day_data.get("gl_accounts", []) or day_data.get("data", [])
                    else:
                        gl_accounts = []

                    for gl_item in gl_accounts:
                        # API field mapping (Newbook reports_earned_revenue response):
                        # - gl_account_id: internal ID
                        # - gl_account_code: actual GL code (e.g., "7001")
                        # - gl_account_description: human-readable name
                        # - earned_revenue: gross amount (inc. tax)
                        # - earned_revenue_ex: net amount (exc. tax)
                        # - earned_revenue_tax: tax amount
                        gl_account_id = str(gl_item.get("gl_account_id", ""))
                        gl_code = str(gl_item.get("gl_account_code", ""))
                        gl_name = gl_item.get("gl_account_description", "")
                        amount_gross = float(gl_item.get("earned_revenue", 0) or 0)
                        amount_net = float(gl_item.get("earned_revenue_ex", 0) or 0)

                        # Determine revenue type based on GL code
                        if gl_code in accommodation_gl_codes:
                            revenue_type = "accommodation"
                            daily_accommodation[revenue_date]["gross"] += amount_gross
                            daily_accommodation[revenue_date]["net"] += amount_net
                        else:
                            # Future: add food_gl_codes, beverage_gl_codes config
                            revenue_type = "other"

                        # Upsert into newbook_earned_revenue_data
                        db.execute(
                            text("""
                            INSERT INTO newbook_earned_revenue_data (
                                date, gl_account_id, gl_code, gl_name,
                                amount_gross, amount_net, revenue_type, fetched_at
                            ) VALUES (
                                :date, :gl_account_id, :gl_code, :gl_name,
                                :amount_gross, :amount_net, :revenue_type, NOW()
                            )
                            ON CONFLICT (date, gl_account_id) DO UPDATE SET
                                gl_code = :gl_code,
                                gl_name = :gl_name,
                                amount_gross = :amount_gross,
                                amount_net = :amount_net,
                                revenue_type = :revenue_type,
                                fetched_at = NOW()
                            """),
                            {
                                "date": revenue_date,
                                "gl_account_id": gl_account_id,
                                "gl_code": gl_code,
                                "gl_name": gl_name,
                                "amount_gross": round(amount_gross, 2),
                                "amount_net": round(amount_net, 2),
                                "revenue_type": revenue_type
                            }
                        )
                        records_created += 1

                        # Track GL account for caching
                        if gl_account_id and gl_account_id not in gl_accounts_seen:
                            gl_accounts_seen[gl_account_id] = {
                                "gl_code": gl_code,
                                "gl_name": gl_name,
                                "last_date": revenue_date,
                                "total": amount_gross
                            }
                        elif gl_account_id:
                            gl_accounts_seen[gl_account_id]["total"] += amount_gross
                            if revenue_date > gl_accounts_seen[gl_account_id]["last_date"]:
                                gl_accounts_seen[gl_account_id]["last_date"] = revenue_date

                except Exception as day_error:
                    logger.error(f"Error processing earned revenue for {date_str}: {day_error}")
                    continue

            db.commit()

            # Cache GL accounts for Settings page reference
            print(f"[SYNC] Caching {len(gl_accounts_seen)} GL accounts...", flush=True)
            for gl_id, gl_info in gl_accounts_seen.items():
                db.execute(
                    text("""
                    INSERT INTO newbook_gl_accounts (
                        gl_account_id, gl_code, gl_name, last_seen_date, total_amount, fetched_at
                    ) VALUES (
                        :gl_account_id, :gl_code, :gl_name, :last_date, :total, NOW()
                    )
                    ON CONFLICT (gl_account_id) DO UPDATE SET
                        gl_code = :gl_code,
                        gl_name = :gl_name,
                        last_seen_date = GREATEST(newbook_gl_accounts.last_seen_date, :last_date),
                        total_amount = newbook_gl_accounts.total_amount + :total,
                        fetched_at = NOW()
                    """),
                    {
                        "gl_account_id": gl_id,
                        "gl_code": gl_info["gl_code"],
                        "gl_name": gl_info["gl_name"],
                        "last_date": gl_info["last_date"],
                        "total": round(gl_info["total"], 2)
                    }
                )
            db.commit()

            # Update sync log
            db.execute(
                text("""
                UPDATE sync_log
                SET completed_at = NOW(), status = 'success',
                    records_fetched = :fetched, records_created = :created
                WHERE id = (
                    SELECT id FROM sync_log
                    WHERE source = 'newbook' AND sync_type = 'earned_revenue' AND status = 'running'
                    ORDER BY started_at DESC LIMIT 1
                )
                """),
                {"fetched": days_processed, "created": records_created}
            )
            db.commit()

        print(f"[SYNC] Earned revenue sync completed: {records_created} GL records, {days_processed} days", flush=True)
        logger.info(f"Newbook earned revenue sync completed: {records_created} GL records, {days_processed} days")

        # Trigger revenue aggregation after successful sync
        try:
            from jobs.revenue_aggregation import aggregate_revenue
            print("[SYNC] Running revenue aggregation...", flush=True)
            result = await aggregate_revenue()
            print(f"[SYNC] Revenue aggregation complete: {result.get('dates_processed', 0)} dates", flush=True)
        except Exception as agg_err:
            print(f"[SYNC] Revenue aggregation failed (non-fatal): {agg_err}", flush=True)
            logger.warning(f"Revenue aggregation failed after sync: {agg_err}")

    except Exception as e:
        print(f"[SYNC] Earned revenue sync FAILED: {e}", flush=True)
        import traceback
        traceback.print_exc()
        logger.error(f"Newbook earned revenue sync failed: {e}")
        try:
            db.rollback()
            db.execute(
                text("""
                UPDATE sync_log
                SET completed_at = NOW(), status = 'failed', error_message = :error
                WHERE id = (
                    SELECT id FROM sync_log
                    WHERE source = 'newbook' AND sync_type = 'earned_revenue' AND status = 'running'
                    ORDER BY started_at DESC LIMIT 1
                )
                """),
                {"error": str(e)[:500]}
            )
            db.commit()
        except Exception as log_error:
            logger.error(f"Failed to update sync_log: {log_error}")
        raise
    finally:
        db.close()