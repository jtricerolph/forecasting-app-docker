"""
Resos Bookings Data Sync Job
Syncs restaurant bookings to resos_bookings_data table
Pattern: Replicates newbook bookings sync but adapted for Resos covers/stats
"""
import json
import logging
import base64
from datetime import date, datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any

from sqlalchemy import text
from database import SyncSessionLocal
from services.resos_client import ResosClient

logger = logging.getLogger(__name__)

# Valid booking statuses for aggregation
# Note: Resos uses 'approved' for confirmed future reservations, 'left' for completed meals
VALID_STATUSES = ('approved', 'arrived', 'seated', 'left')


def get_config_value(db, key: str) -> Optional[str]:
    """Get a configuration value from system_config table."""
    result = db.execute(
        text("SELECT config_value, is_encrypted FROM system_config WHERE config_key = :key"),
        {"key": key}
    )
    row = result.fetchone()
    if not row or not row.config_value:
        return None

    # Decrypt if encrypted
    if row.is_encrypted:
        try:
            return base64.b64decode(row.config_value.encode()).decode()
        except Exception as e:
            logger.warning(f"Failed to decrypt {key}: {e}")
            return row.config_value

    return row.config_value


def load_resos_custom_field_mappings(db) -> Dict[str, Dict[str, Any]]:
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
    logger.info(f"Loaded {len(mappings)} custom field mappings")
    return mappings


def load_resos_opening_hours_mappings(db) -> Dict[str, Dict[str, str]]:
    """
    Load opening hours mappings from resos_opening_hours_mapping table.
    Returns dict: {opening_hour_id: {"period_type": "dinner", "display_name": "..."}}
    """
    result = db.execute(text("""
        SELECT opening_hour_id, period_type, display_name
        FROM resos_opening_hours_mapping
        WHERE period_type != 'ignore'
    """))
    mappings = {}
    for row in result.fetchall():
        mappings[row.opening_hour_id] = {
            "period_type": row.period_type,
            "display_name": row.display_name
        }
    logger.info(f"Loaded {len(mappings)} opening hours mappings")
    return mappings


def parse_group_exclude_field(group_exclude_field: Optional[str], primary_booking_number: Optional[str]) -> Tuple[List[str], List[str]]:
    """
    Parse group_exclude_field to extract linked bookings and exclude markers.

    Args:
        group_exclude_field: Raw field like "#12346,#12347,NOT-#56748"
        primary_booking_number: Primary booking from hotel_booking_number field

    Returns:
        (all_booking_numbers, exclude_numbers)

    Example:
        Input: "#12346,#12347,NOT-#56748", "NB12345"
        Returns: (["NB12345", "NB12346", "NB12347"], ["NB56748"])
    """
    all_booking_numbers = []
    exclude_numbers = []

    # Always include primary booking number
    if primary_booking_number:
        all_booking_numbers.append(primary_booking_number)

    if not group_exclude_field:
        return all_booking_numbers, exclude_numbers

    # Parse comma-separated entries
    parts = group_exclude_field.split(',')
    for part in parts:
        part = part.strip()

        if part.upper().startswith('NOT-#'):
            # Exclude marker: NOT-#56748 → NB56748
            booking_num = part[5:]  # Remove "NOT-#"
            exclude_numbers.append(f"NB{booking_num}")

        elif part.startswith('#'):
            # Additional booking: #12346 → NB12346
            booking_num = part[1:]  # Remove "#"
            all_booking_numbers.append(f"NB{booking_num}")

    return all_booking_numbers, exclude_numbers


def extract_custom_field_value(custom_fields: List[Dict[str, Any]], field_id: str, cf_mappings: Dict[str, Dict[str, Any]]) -> Optional[Any]:
    """
    Extract value from Resos custom fields array.

    Args:
        custom_fields: Array of custom field objects from Resos API
        field_id: The field ID to look for
        cf_mappings: Mapping configuration

    Returns:
        Extracted value (boolean for hotel_guest/dbb/package, string for booking_number, etc.)
    """
    if field_id not in cf_mappings:
        return None

    mapping = cf_mappings[field_id]
    maps_to = mapping["maps_to"]
    value_for_true = mapping.get("value_for_true")

    # Find the field in custom_fields array
    field_value = None
    field_value_label = None
    for cf in custom_fields:
        cf_id = cf.get("id") or cf.get("_id") or cf.get("fieldId")
        if cf_id == field_id:
            field_value = cf.get("value")
            field_value_label = cf.get("multipleChoiceValueName") or cf.get("value")
            break

    if field_value is None and field_value_label is None:
        return None

    # For boolean mappings (hotel_guest, dbb, package)
    if maps_to in ("hotel_guest", "dbb", "package"):
        if value_for_true:
            return str(field_value_label) == str(value_for_true)
        else:
            # Auto-detect: check for "yes", "true", "1"
            return str(field_value_label).lower() in ("yes", "true", "1")

    # For string mappings (booking_number, group_exclude, allergies)
    return str(field_value) if field_value else str(field_value_label) if field_value_label else None


async def sync_resos_bookings_data(
    from_date: date,
    to_date: date,
    triggered_by: str = "scheduler"
):
    """
    Sync Resos bookings to resos_bookings_data.

    Date range: Historical -365 days + Forecast +365 days (daily sync)
    PII handling: Remove guest details, store only aggregate covers
    """
    logger.info(f"Starting Resos bookings sync from {from_date} to {to_date} (triggered by {triggered_by})")

    db = SyncSessionLocal()

    try:
        # Log sync start
        db.execute(
            text("""
            INSERT INTO sync_log (sync_type, source, started_at, status, date_from, date_to, triggered_by)
            VALUES ('bookings_data', 'resos', NOW(), 'running', :from_date, :to_date, :triggered_by)
            """),
            {"from_date": from_date, "to_date": to_date, "triggered_by": triggered_by}
        )
        db.commit()

        # Load Resos API key
        api_key = get_config_value(db, 'resos_api_key')

        if not api_key:
            raise Exception("Resos API key not configured")

        # Load mappings
        cf_mappings = load_resos_custom_field_mappings(db)
        oh_mappings = load_resos_opening_hours_mappings(db)

        async with ResosClient(api_key=api_key) as client:
            # Test connection
            if not await client.test_connection():
                raise Exception("Resos connection failed")

            # Fetch bookings
            logger.info(f"Fetching bookings from Resos API for {from_date} to {to_date}")
            bookings = await client.get_bookings(from_date, to_date)
            logger.info(f"Fetched {len(bookings)} bookings from Resos")

            records_created = 0
            records_updated = 0

            for booking in bookings:
                resos_id = booking.get("_id")
                if not resos_id:
                    continue

                booking_date_str = booking.get("date")
                booking_date_obj = date.fromisoformat(booking_date_str) if booking_date_str else None

                if not booking_date_obj:
                    continue

                # Extract opening hour ID and map to period type
                opening_hour_id = booking.get("openingHourId")
                period_type = None
                if opening_hour_id and opening_hour_id in oh_mappings:
                    period_type = oh_mappings[opening_hour_id]["period_type"]

                # Extract custom fields using mappings
                custom_fields = booking.get("customFields", [])

                is_hotel_guest = None
                is_dbb = None
                is_package = None
                hotel_booking_number = None
                group_exclude_field = None

                for field_id, mapping in cf_mappings.items():
                    maps_to = mapping["maps_to"]

                    if maps_to == "hotel_guest":
                        is_hotel_guest = extract_custom_field_value(custom_fields, field_id, cf_mappings)
                    elif maps_to == "dbb":
                        is_dbb = extract_custom_field_value(custom_fields, field_id, cf_mappings)
                    elif maps_to == "package":
                        is_package = extract_custom_field_value(custom_fields, field_id, cf_mappings)
                    elif maps_to == "booking_number":
                        hotel_booking_number = extract_custom_field_value(custom_fields, field_id, cf_mappings)
                    elif maps_to == "group_exclude":
                        group_exclude_field = extract_custom_field_value(custom_fields, field_id, cf_mappings)

                # Remove PII from raw JSON (remove guest object)
                raw_booking = {k: v for k, v in booking.items() if k != "guest"}
                raw_json_str = json.dumps(raw_booking)

                # Extract other booking details
                covers = booking.get("people", 0)
                status = booking.get("status")
                source = booking.get("source")
                booking_time_str = booking.get("time")

                # Parse table information
                tables = booking.get("tables", [])
                table_name = tables[0].get("name") if tables else None
                table_area = None
                if tables and tables[0].get("area"):
                    table_area = tables[0]["area"].get("name")

                # Parse booking placed timestamp
                booking_placed_str = booking.get("createdAt")
                booking_placed = None
                if booking_placed_str:
                    try:
                        booking_placed = datetime.fromisoformat(booking_placed_str.replace('Z', '+00:00'))
                    except:
                        pass

                # Parse notes (sanitized - no PII)
                notes_array = booking.get("restaurantNotes", [])
                notes = ', '.join([str(note) for note in notes_array]) if notes_array else None

                # Check if record exists
                existing = db.execute(
                    text("SELECT id FROM resos_bookings_data WHERE resos_id = :rid"),
                    {"rid": resos_id}
                ).fetchone()

                # Upsert booking
                db.execute(
                    text("""
                    INSERT INTO resos_bookings_data (
                        resos_id, booking_date, booking_time, opening_hour_id, period_type,
                        covers, status, source, table_name, table_area,
                        is_hotel_guest, is_dbb, is_package, hotel_booking_number, group_exclude_field,
                        total_guests, booking_placed, notes, raw_json, fetched_at
                    ) VALUES (
                        :resos_id, :booking_date, :booking_time, :opening_hour_id, :period_type,
                        :covers, :status, :source, :table_name, :table_area,
                        :is_hotel_guest, :is_dbb, :is_package, :hotel_booking_number, :group_exclude_field,
                        :total_guests, :booking_placed, :notes, :raw_json, NOW()
                    )
                    ON CONFLICT (resos_id) DO UPDATE SET
                        status = :status,
                        covers = :covers,
                        period_type = :period_type,
                        is_hotel_guest = COALESCE(:is_hotel_guest, resos_bookings_data.is_hotel_guest),
                        is_dbb = COALESCE(:is_dbb, resos_bookings_data.is_dbb),
                        is_package = COALESCE(:is_package, resos_bookings_data.is_package),
                        hotel_booking_number = COALESCE(:hotel_booking_number, resos_bookings_data.hotel_booking_number),
                        group_exclude_field = COALESCE(:group_exclude_field, resos_bookings_data.group_exclude_field),
                        raw_json = :raw_json,
                        fetched_at = NOW()
                    """),
                    {
                        "resos_id": resos_id,
                        "booking_date": booking_date_obj,
                        "booking_time": booking_time_str,
                        "opening_hour_id": opening_hour_id,
                        "period_type": period_type,
                        "covers": covers,
                        "status": status,
                        "source": source,
                        "table_name": table_name,
                        "table_area": table_area,
                        "is_hotel_guest": is_hotel_guest,
                        "is_dbb": is_dbb,
                        "is_package": is_package,
                        "hotel_booking_number": hotel_booking_number,
                        "group_exclude_field": group_exclude_field,
                        "total_guests": covers,  # Same as covers for restaurants
                        "booking_placed": booking_placed,
                        "notes": notes,
                        "raw_json": raw_json_str
                    }
                )

                if existing:
                    records_updated += 1
                else:
                    records_created += 1

                db.commit()

            # Update sync log
            db.execute(
                text("""
                UPDATE sync_log
                SET completed_at = NOW(), status = 'success',
                    records_fetched = :fetched, records_created = :created, records_updated = :updated
                WHERE id = (
                    SELECT id FROM sync_log
                    WHERE source = 'resos' AND sync_type = 'bookings_data' AND status = 'running'
                    ORDER BY started_at DESC LIMIT 1
                )
                """),
                {"fetched": len(bookings), "created": records_created, "updated": records_updated}
            )
            db.commit()

            logger.info(f"Resos bookings sync completed: {records_created} created, {records_updated} updated")

            # Trigger aggregation
            logger.info("Triggering Resos bookings aggregation...")
            try:
                import asyncio
                from jobs.resos_aggregation import aggregate_resos_bookings
                await aggregate_resos_bookings(triggered_by=triggered_by)
                logger.info("Resos bookings aggregation completed")
            except Exception as agg_error:
                logger.warning(f"Resos aggregation failed (non-fatal): {agg_error}")

    except Exception as e:
        logger.error(f"Resos bookings sync failed: {e}", exc_info=True)
        db.execute(
            text("""
            UPDATE sync_log
            SET completed_at = NOW(), status = 'failed', error_message = :error
            WHERE id = (
                SELECT id FROM sync_log
                WHERE source = 'resos' AND sync_type = 'bookings_data' AND status = 'running'
                ORDER BY started_at DESC LIMIT 1
            )
            """),
            {"error": str(e)[:500]}
        )
        db.commit()
        raise
    finally:
        db.close()
