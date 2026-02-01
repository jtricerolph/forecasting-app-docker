"""
Newbook Bookings Data Sync API endpoints
Handles syncing booking data to newbook_bookings_data table
"""
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from database import get_db, SyncSessionLocal
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class SyncConfig(BaseModel):
    """Auto sync configuration for bookings"""
    enabled: bool
    sync_type: str = "incremental"  # "incremental" or "full"
    sync_time: str = "05:00"  # HH:MM format


class OccupancySyncConfig(BaseModel):
    """Auto sync configuration for occupancy data"""
    enabled: bool
    sync_time: str = "05:00"  # HH:MM format


class EarnedRevenueSyncConfig(BaseModel):
    """Auto sync configuration for earned revenue data"""
    enabled: bool
    sync_time: str = "05:10"  # HH:MM format


@router.get("/bookings-data/status")
async def get_bookings_sync_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get sync status for newbook bookings data including last sync info.
    """
    # Get last successful sync
    result = await db.execute(
        text("""
            SELECT id, sync_type, started_at, completed_at, status,
                   records_fetched, records_created, records_updated,
                   date_from, date_to, error_message, triggered_by
            FROM sync_log
            WHERE source = 'newbook' AND sync_type = 'bookings_data'
            AND status = 'success'
            ORDER BY completed_at DESC
            LIMIT 1
        """)
    )
    last_success = result.fetchone()

    # Get last sync (any status)
    result = await db.execute(
        text("""
            SELECT id, sync_type, started_at, completed_at, status,
                   records_fetched, records_created, records_updated,
                   date_from, date_to, error_message, triggered_by
            FROM sync_log
            WHERE source = 'newbook' AND sync_type = 'bookings_data'
            ORDER BY started_at DESC
            LIMIT 1
        """)
    )
    last_sync = result.fetchone()

    # Get auto sync config
    result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'sync_newbook_bookings_enabled'")
    )
    row = result.fetchone()
    auto_enabled = row.config_value.lower() == 'true' if row and row.config_value else False

    result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'sync_newbook_bookings_type'")
    )
    row = result.fetchone()
    sync_type = row.config_value if row and row.config_value else 'incremental'

    result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'sync_newbook_bookings_time'")
    )
    row = result.fetchone()
    sync_time = row.config_value if row and row.config_value else '05:00'

    # Get total records in table
    result = await db.execute(text("SELECT COUNT(*) as count FROM newbook_bookings_data"))
    total_records = result.fetchone().count

    return {
        "last_successful_sync": {
            "completed_at": last_success.completed_at if last_success else None,
            "records_fetched": last_success.records_fetched if last_success else None,
            "records_created": last_success.records_created if last_success else None,
            "triggered_by": last_success.triggered_by if last_success else None,
        } if last_success else None,
        "last_sync": {
            "started_at": last_sync.started_at if last_sync else None,
            "completed_at": last_sync.completed_at if last_sync else None,
            "status": last_sync.status if last_sync else None,
            "records_fetched": last_sync.records_fetched if last_sync else None,
            "error_message": last_sync.error_message if last_sync else None,
            "triggered_by": last_sync.triggered_by if last_sync else None,
        } if last_sync else None,
        "auto_sync": {
            "enabled": auto_enabled,
            "type": sync_type,
            "time": sync_time
        },
        "total_records": total_records
    }


@router.get("/bookings-data/logs")
async def get_bookings_sync_logs(
    limit: int = Query(5, description="Number of logs to return"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get recent sync logs for bookings data.
    """
    result = await db.execute(
        text("""
            SELECT id, sync_type, started_at, completed_at, status,
                   records_fetched, records_created, records_updated,
                   date_from, date_to, error_message, triggered_by
            FROM sync_log
            WHERE source = 'newbook' AND sync_type = 'bookings_data'
            ORDER BY started_at DESC
            LIMIT :limit
        """),
        {"limit": limit}
    )
    rows = result.fetchall()

    return [
        {
            "id": row.id,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "status": row.status,
            "records_fetched": row.records_fetched,
            "records_created": row.records_created,
            "date_from": row.date_from,
            "date_to": row.date_to,
            "error_message": row.error_message,
            "triggered_by": row.triggered_by
        }
        for row in rows
    ]


@router.post("/bookings-data/sync")
async def trigger_bookings_sync(
    background_tasks: BackgroundTasks,
    sync_mode: str = Query("incremental", description="Sync mode: 'incremental', 'staying_range', or 'full'"),
    from_date: Optional[date] = Query(None, description="Start date for staying range sync"),
    to_date: Optional[date] = Query(None, description="End date for staying range sync"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger a bookings data sync.

    Modes:
    - incremental: Fetch bookings modified since last successful sync (or last 7 days if no history)
    - staying_range: Fetch bookings staying during the specified date range
    - full: Fetch all bookings (warning: large dataset)
    """
    if sync_mode == "staying_range" and (not from_date or not to_date):
        raise HTTPException(status_code=400, detail="from_date and to_date required for staying_range mode")

    # Queue background task
    background_tasks.add_task(
        run_bookings_data_sync,
        sync_mode=sync_mode,
        from_date=from_date,
        to_date=to_date,
        triggered_by=f"user:{current_user['username']}"
    )

    msg = f"Bookings data sync started ({sync_mode})"
    if sync_mode == "staying_range":
        msg = f"Bookings data sync started for staying period {from_date} to {to_date}"

    return {
        "status": "started",
        "sync_mode": sync_mode,
        "from_date": from_date,
        "to_date": to_date,
        "message": msg
    }


@router.post("/bookings-data/config")
async def update_bookings_sync_config(
    config: SyncConfig,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update auto sync configuration for bookings data.
    """
    # Upsert enabled setting
    await db.execute(
        text("""
            INSERT INTO system_config (config_key, config_value, description, updated_at, updated_by)
            VALUES ('sync_newbook_bookings_enabled', :value, 'Enable automatic Newbook bookings sync', NOW(), :user)
            ON CONFLICT (config_key) DO UPDATE SET
                config_value = :value,
                updated_at = NOW(),
                updated_by = :user
        """),
        {"value": str(config.enabled).lower(), "user": current_user['username']}
    )

    # Upsert sync type setting
    await db.execute(
        text("""
            INSERT INTO system_config (config_key, config_value, description, updated_at, updated_by)
            VALUES ('sync_newbook_bookings_type', :value, 'Newbook bookings sync type (incremental/full)', NOW(), :user)
            ON CONFLICT (config_key) DO UPDATE SET
                config_value = :value,
                updated_at = NOW(),
                updated_by = :user
        """),
        {"value": config.sync_type, "user": current_user['username']}
    )

    # Upsert sync time setting
    await db.execute(
        text("""
            INSERT INTO system_config (config_key, config_value, description, updated_at, updated_by)
            VALUES ('sync_newbook_bookings_time', :value, 'Newbook bookings sync time (HH:MM)', NOW(), :user)
            ON CONFLICT (config_key) DO UPDATE SET
                config_value = :value,
                updated_at = NOW(),
                updated_by = :user
        """),
        {"value": config.sync_time, "user": current_user['username']}
    )

    await db.commit()

    return {
        "status": "success",
        "enabled": config.enabled,
        "sync_type": config.sync_type,
        "sync_time": config.sync_time
    }


def run_bookings_data_sync(
    sync_mode: str,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    triggered_by: str = "scheduler"
):
    """
    Background task to sync bookings data to newbook_bookings_data table.

    Modes:
    - incremental: Uses modified_since from last successful sync (or -7 days fallback)
    - staying_range: Uses bookings_list with list_type="staying" for date range
    - full: Fetches all bookings
    """
    import json
    import sys
    import asyncio
    from services.newbook_client import NewbookClient

    print(f"[SYNC-BOOKINGS] Starting sync (mode={sync_mode})", flush=True)
    sys.stdout.flush()

    db = SyncSessionLocal()

    try:
        # Load credentials
        def get_config(key):
            result = db.execute(
                text("SELECT config_value, is_encrypted FROM system_config WHERE config_key = :key"),
                {"key": key}
            )
            row = result.fetchone()
            if row and row.config_value:
                if row.is_encrypted:
                    import base64
                    try:
                        return base64.b64decode(row.config_value.encode()).decode()
                    except:
                        return row.config_value
                return row.config_value
            return None

        creds = {
            'api_key': get_config('newbook_api_key'),
            'username': get_config('newbook_username'),
            'password': get_config('newbook_password'),
            'region': get_config('newbook_region')
        }

        # Determine modified_since for incremental sync
        modified_since = None
        if sync_mode == "incremental":
            # Get last successful sync
            result = db.execute(
                text("""
                    SELECT completed_at FROM sync_log
                    WHERE source = 'newbook' AND sync_type = 'bookings_data' AND status = 'success'
                    ORDER BY completed_at DESC LIMIT 1
                """)
            )
            row = result.fetchone()
            if row and row.completed_at:
                modified_since = row.completed_at.isoformat()
                print(f"[SYNC-BOOKINGS] Incremental: fetching since {modified_since}", flush=True)
            else:
                # Fallback: last 7 days
                fallback_date = date.today() - timedelta(days=7)
                modified_since = fallback_date.isoformat() + "T00:00:00"
                print(f"[SYNC-BOOKINGS] No history, fallback to {modified_since}", flush=True)

        # Log sync start
        db.execute(
            text("""
                INSERT INTO sync_log (sync_type, source, started_at, status, date_from, date_to, triggered_by)
                VALUES ('bookings_data', 'newbook', NOW(), 'running', :from_date, :to_date, :triggered_by)
            """),
            {"from_date": from_date, "to_date": to_date, "triggered_by": triggered_by}
        )
        db.commit()

        print("[SYNC-BOOKINGS] Creating NewbookClient...", flush=True)

        async def do_sync():
            async with NewbookClient(
                api_key=creds['api_key'],
                username=creds['username'],
                password=creds['password'],
                region=creds['region']
            ) as client:
                # Test connection
                if not await client.test_connection():
                    raise Exception("Newbook connection failed")

                # Fetch bookings based on mode
                if sync_mode == "staying_range" and from_date and to_date:
                    bookings = await client.get_bookings_by_stay_dates(
                        from_date=from_date,
                        to_date=to_date,
                        list_type="staying"
                    )
                    print(f"[SYNC-BOOKINGS] Fetched {len(bookings)} bookings (staying {from_date} to {to_date})", flush=True)
                elif sync_mode == "full":
                    bookings = await client.get_bookings(modified_since=None)
                    print(f"[SYNC-BOOKINGS] Fetched {len(bookings)} bookings (full sync)", flush=True)
                else:
                    # Incremental
                    bookings = await client.get_bookings(modified_since=modified_since)
                    print(f"[SYNC-BOOKINGS] Fetched {len(bookings)} bookings (incremental)", flush=True)

                return bookings

        # Run async sync - create new event loop for background task
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            bookings = loop.run_until_complete(do_sync())
        finally:
            loop.close()

        records_created = 0
        records_updated = 0

        print(f"[SYNC-BOOKINGS] Processing {len(bookings)} bookings...", flush=True)

        for i, booking in enumerate(bookings):
            newbook_id = booking.get("booking_id")

            if i > 0 and i % 100 == 0:
                print(f"[SYNC-BOOKINGS] Processed {i}/{len(bookings)}", flush=True)

            if not newbook_id:
                continue

            newbook_id = str(newbook_id)

            try:
                # Create sanitized raw JSON (remove guest PII)
                raw_booking = {k: v for k, v in booking.items() if k != "guests"}
                raw_json_str = json.dumps(raw_booking)

                # Parse dates
                arrival_raw = booking.get("booking_arrival")
                departure_raw = booking.get("booking_departure")
                arrival = arrival_raw.split(" ")[0] if arrival_raw else None
                departure = departure_raw.split(" ")[0] if departure_raw else None

                # Extract all fields for the extended schema
                status = booking.get("booking_status")
                category_id = str(booking.get("category_id")) if booking.get("category_id") else None
                category_name = booking.get("category_name")

                # Check if record exists
                existing = db.execute(
                    text("SELECT id FROM newbook_bookings_data WHERE newbook_id = :nid"),
                    {"nid": newbook_id}
                ).fetchone()

                # Upsert booking with extended fields
                db.execute(
                    text("""
                        INSERT INTO newbook_bookings_data (
                            newbook_id, booking_reference, bookings_group_id,
                            booking_placed, arrival_date, departure_date, nights,
                            adults, children, infants, total_guests,
                            category_id, room_type, site_id, room_number,
                            status, total_amount, tariff_name, tariff_total,
                            travel_agent_id, travel_agent_name, travel_agent_commission,
                            booking_source_id, booking_source_name,
                            booking_parent_source_id, booking_parent_source_name,
                            booking_method_id, booking_method_name,
                            raw_json, fetched_at
                        ) VALUES (
                            :newbook_id, :reference, :group_id,
                            :booking_placed, :arrival, :departure, :nights,
                            :adults, :children, :infants, :total_guests,
                            :category_id, :room_type, :site_id, :room_number,
                            :status, :total_amount, :tariff_name, :tariff_total,
                            :travel_agent_id, :travel_agent_name, :travel_agent_commission,
                            :source_id, :source_name,
                            :parent_source_id, :parent_source_name,
                            :method_id, :method_name,
                            :raw_json, NOW()
                        )
                        ON CONFLICT (newbook_id) DO UPDATE SET
                            booking_reference = EXCLUDED.booking_reference,
                            booking_placed = COALESCE(EXCLUDED.booking_placed, newbook_bookings_data.booking_placed),
                            status = EXCLUDED.status,
                            total_amount = EXCLUDED.total_amount,
                            tariff_total = EXCLUDED.tariff_total,
                            travel_agent_commission = EXCLUDED.travel_agent_commission,
                            raw_json = EXCLUDED.raw_json,
                            fetched_at = NOW()
                    """),
                    {
                        "newbook_id": newbook_id,
                        "reference": booking.get("booking_reference_id"),
                        "group_id": str(booking.get("bookings_group_id")) if booking.get("bookings_group_id") else None,
                        "booking_placed": booking.get("booking_placed"),
                        "arrival": arrival,
                        "departure": departure,
                        "nights": booking.get("booking_length"),
                        "adults": int(booking.get("booking_adults") or 0),
                        "children": int(booking.get("booking_children") or 0),
                        "infants": int(booking.get("booking_infants") or 0),
                        "total_guests": int(booking.get("booking_adults") or 0) + int(booking.get("booking_children") or 0),
                        "category_id": category_id,
                        "room_type": category_name,
                        "site_id": str(booking.get("site_id")) if booking.get("site_id") else None,
                        "room_number": booking.get("site_name"),
                        "status": status,
                        "total_amount": booking.get("booking_total"),
                        "tariff_name": booking.get("tariff_name"),
                        "tariff_total": booking.get("tariff_total"),
                        "travel_agent_id": str(booking.get("travel_agent_id")) if booking.get("travel_agent_id") else None,
                        "travel_agent_name": booking.get("travel_agent_name"),
                        "travel_agent_commission": booking.get("travel_agent_commission"),
                        "source_id": str(booking.get("booking_source_id")) if booking.get("booking_source_id") else None,
                        "source_name": booking.get("booking_source_name"),
                        "parent_source_id": str(booking.get("booking_parent_source_id")) if booking.get("booking_parent_source_id") else None,
                        "parent_source_name": booking.get("booking_parent_source_name"),
                        "method_id": str(booking.get("booking_method_id")) if booking.get("booking_method_id") else None,
                        "method_name": booking.get("booking_method_name"),
                        "raw_json": raw_json_str
                    }
                )

                if existing:
                    records_updated += 1
                else:
                    records_created += 1

                db.commit()

            except Exception as booking_error:
                print(f"[SYNC-BOOKINGS] Error processing {newbook_id}: {booking_error}", flush=True)
                logger.error(f"Error processing booking {newbook_id}: {booking_error}")
                db.rollback()
                continue

        # Update sync log - success
        db.execute(
            text("""
                UPDATE sync_log
                SET completed_at = NOW(), status = 'success',
                    records_fetched = :fetched, records_created = :created, records_updated = :updated
                WHERE id = (
                    SELECT id FROM sync_log
                    WHERE source = 'newbook' AND sync_type = 'bookings_data' AND status = 'running'
                    ORDER BY started_at DESC LIMIT 1
                )
            """),
            {"fetched": len(bookings), "created": records_created, "updated": records_updated}
        )
        db.commit()

        print(f"[SYNC-BOOKINGS] Completed: {records_created} created, {records_updated} updated", flush=True)
        logger.info(f"Bookings data sync completed: {records_created} created, {records_updated} updated")

        # Trigger bookings aggregation after successful sync
        print(f"[SYNC-BOOKINGS] Triggering bookings aggregation...", flush=True)
        try:
            from jobs.bookings_aggregation import run_bookings_aggregation
            agg_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(agg_loop)
            try:
                agg_loop.run_until_complete(run_bookings_aggregation(triggered_by=triggered_by))
                print(f"[SYNC-BOOKINGS] Bookings aggregation completed", flush=True)
            finally:
                agg_loop.close()
        except Exception as agg_error:
            print(f"[SYNC-BOOKINGS] Aggregation warning: {agg_error}", flush=True)
            logger.warning(f"Bookings aggregation failed (non-fatal): {agg_error}")

    except Exception as e:
        print(f"[SYNC-BOOKINGS] FAILED: {e}", flush=True)
        import traceback
        traceback.print_exc()
        logger.error(f"Bookings data sync failed: {e}")
        try:
            db.rollback()
            db.execute(
                text("""
                    UPDATE sync_log
                    SET completed_at = NOW(), status = 'failed', error_message = :error
                    WHERE id = (
                        SELECT id FROM sync_log
                        WHERE source = 'newbook' AND sync_type = 'bookings_data' AND status = 'running'
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


# ============================================
# OCCUPANCY DATA SYNC ENDPOINTS
# ============================================

@router.get("/occupancy-data/status")
async def get_occupancy_sync_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get sync status for newbook occupancy report data including last sync info.
    """
    # Get last successful sync
    result = await db.execute(
        text("""
            SELECT id, sync_type, started_at, completed_at, status,
                   records_fetched, records_created, records_updated,
                   date_from, date_to, error_message, triggered_by
            FROM sync_log
            WHERE source = 'newbook' AND sync_type = 'occupancy_report'
            AND status = 'success'
            ORDER BY completed_at DESC
            LIMIT 1
        """)
    )
    last_success = result.fetchone()

    # Get last sync (any status)
    result = await db.execute(
        text("""
            SELECT id, sync_type, started_at, completed_at, status,
                   records_fetched, records_created, records_updated,
                   date_from, date_to, error_message, triggered_by
            FROM sync_log
            WHERE source = 'newbook' AND sync_type = 'occupancy_report'
            ORDER BY started_at DESC
            LIMIT 1
        """)
    )
    last_sync = result.fetchone()

    # Get auto sync config
    result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'sync_newbook_occupancy_enabled'")
    )
    row = result.fetchone()
    auto_enabled = row.config_value.lower() == 'true' if row and row.config_value else False

    result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'sync_newbook_occupancy_time'")
    )
    row = result.fetchone()
    sync_time = row.config_value if row and row.config_value else '05:00'

    # Get total records in table
    result = await db.execute(text("SELECT COUNT(*) as count FROM newbook_occupancy_report_data"))
    total_records = result.fetchone().count

    # Get date range of data
    result = await db.execute(
        text("SELECT MIN(date) as min_date, MAX(date) as max_date FROM newbook_occupancy_report_data")
    )
    date_range = result.fetchone()

    return {
        "last_successful_sync": {
            "completed_at": last_success.completed_at if last_success else None,
            "records_fetched": last_success.records_fetched if last_success else None,
            "records_created": last_success.records_created if last_success else None,
            "date_from": last_success.date_from if last_success else None,
            "date_to": last_success.date_to if last_success else None,
            "triggered_by": last_success.triggered_by if last_success else None,
        } if last_success else None,
        "last_sync": {
            "started_at": last_sync.started_at if last_sync else None,
            "completed_at": last_sync.completed_at if last_sync else None,
            "status": last_sync.status if last_sync else None,
            "records_fetched": last_sync.records_fetched if last_sync else None,
            "date_from": last_sync.date_from if last_sync else None,
            "date_to": last_sync.date_to if last_sync else None,
            "error_message": last_sync.error_message if last_sync else None,
            "triggered_by": last_sync.triggered_by if last_sync else None,
        } if last_sync else None,
        "auto_sync": {
            "enabled": auto_enabled,
            "time": sync_time
        },
        "total_records": total_records,
        "data_range": {
            "from": date_range.min_date if date_range else None,
            "to": date_range.max_date if date_range else None
        }
    }


@router.get("/occupancy-data/logs")
async def get_occupancy_sync_logs(
    limit: int = Query(5, description="Number of logs to return"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get recent sync logs for occupancy report data.
    """
    result = await db.execute(
        text("""
            SELECT id, sync_type, started_at, completed_at, status,
                   records_fetched, records_created, records_updated,
                   date_from, date_to, error_message, triggered_by
            FROM sync_log
            WHERE source = 'newbook' AND sync_type = 'occupancy_report'
            ORDER BY started_at DESC
            LIMIT :limit
        """),
        {"limit": limit}
    )
    rows = result.fetchall()

    return [
        {
            "id": row.id,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "status": row.status,
            "records_fetched": row.records_fetched,
            "records_created": row.records_created,
            "date_from": row.date_from,
            "date_to": row.date_to,
            "error_message": row.error_message,
            "triggered_by": row.triggered_by
        }
        for row in rows
    ]


@router.post("/occupancy-data/sync")
async def trigger_occupancy_sync(
    background_tasks: BackgroundTasks,
    from_date: Optional[date] = Query(None, description="Start date for sync (default: today - 7 days)"),
    to_date: Optional[date] = Query(None, description="End date for sync (default: today + 365 days)"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger an occupancy report data sync.

    If dates not provided, defaults to -7 to +365 days from today.
    """
    # Default date range
    if not from_date:
        from_date = date.today() - timedelta(days=7)
    if not to_date:
        to_date = date.today() + timedelta(days=365)

    # Queue background task
    background_tasks.add_task(
        run_occupancy_data_sync,
        from_date=from_date,
        to_date=to_date,
        triggered_by=f"user:{current_user['username']}"
    )

    return {
        "status": "started",
        "from_date": from_date,
        "to_date": to_date,
        "message": f"Occupancy data sync started for {from_date} to {to_date}"
    }


@router.post("/occupancy-data/config")
async def update_occupancy_sync_config(
    config: OccupancySyncConfig,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update auto sync configuration for occupancy report data.
    """
    # Upsert enabled setting
    await db.execute(
        text("""
            INSERT INTO system_config (config_key, config_value, description, updated_at, updated_by)
            VALUES ('sync_newbook_occupancy_enabled', :value, 'Enable automatic Newbook occupancy sync', NOW(), :user)
            ON CONFLICT (config_key) DO UPDATE SET
                config_value = :value,
                updated_at = NOW(),
                updated_by = :user
        """),
        {"value": str(config.enabled).lower(), "user": current_user['username']}
    )

    # Upsert sync time setting
    await db.execute(
        text("""
            INSERT INTO system_config (config_key, config_value, description, updated_at, updated_by)
            VALUES ('sync_newbook_occupancy_time', :value, 'Newbook occupancy sync time (HH:MM)', NOW(), :user)
            ON CONFLICT (config_key) DO UPDATE SET
                config_value = :value,
                updated_at = NOW(),
                updated_by = :user
        """),
        {"value": config.sync_time, "user": current_user['username']}
    )

    await db.commit()

    return {
        "status": "success",
        "enabled": config.enabled,
        "sync_time": config.sync_time
    }


def run_occupancy_data_sync(
    from_date: date,
    to_date: date,
    triggered_by: str = "scheduler"
):
    """
    Background task to sync occupancy report data to newbook_occupancy_report_data table.
    """
    import sys
    import asyncio
    from jobs.data_sync import sync_newbook_occupancy_report

    print(f"[SYNC-OCCUPANCY] Starting sync ({from_date} to {to_date})", flush=True)
    sys.stdout.flush()

    # Run async sync - create new event loop for background task
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            sync_newbook_occupancy_report(from_date, to_date, triggered_by)
        )
        print(f"[SYNC-OCCUPANCY] Sync completed", flush=True)
    except Exception as e:
        print(f"[SYNC-OCCUPANCY] FAILED: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise
    finally:
        loop.close()


# ============================================
# EARNED REVENUE DATA SYNC ENDPOINTS
# ============================================

@router.get("/earned-revenue-data/status")
async def get_earned_revenue_sync_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get sync status for newbook earned revenue data including last sync info.
    """
    # Get last successful sync
    result = await db.execute(
        text("""
            SELECT id, sync_type, started_at, completed_at, status,
                   records_fetched, records_created, records_updated,
                   date_from, date_to, error_message, triggered_by
            FROM sync_log
            WHERE source = 'newbook' AND sync_type = 'earned_revenue'
            AND status = 'success'
            ORDER BY completed_at DESC
            LIMIT 1
        """)
    )
    last_success = result.fetchone()

    # Get last sync (any status)
    result = await db.execute(
        text("""
            SELECT id, sync_type, started_at, completed_at, status,
                   records_fetched, records_created, records_updated,
                   date_from, date_to, error_message, triggered_by
            FROM sync_log
            WHERE source = 'newbook' AND sync_type = 'earned_revenue'
            ORDER BY started_at DESC
            LIMIT 1
        """)
    )
    last_sync = result.fetchone()

    # Get auto sync config
    result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'sync_newbook_earned_revenue_enabled'")
    )
    row = result.fetchone()
    auto_enabled = row.config_value.lower() == 'true' if row and row.config_value else False

    result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'sync_newbook_earned_revenue_time'")
    )
    row = result.fetchone()
    sync_time = row.config_value if row and row.config_value else '05:10'

    # Get total records in table
    result = await db.execute(text("SELECT COUNT(*) as count FROM newbook_earned_revenue_data"))
    total_records = result.fetchone().count

    # Get date range of data
    result = await db.execute(
        text("SELECT MIN(date) as min_date, MAX(date) as max_date FROM newbook_earned_revenue_data")
    )
    date_range = result.fetchone()

    return {
        "last_successful_sync": {
            "completed_at": last_success.completed_at if last_success else None,
            "records_fetched": last_success.records_fetched if last_success else None,
            "records_created": last_success.records_created if last_success else None,
            "date_from": last_success.date_from if last_success else None,
            "date_to": last_success.date_to if last_success else None,
            "triggered_by": last_success.triggered_by if last_success else None,
        } if last_success else None,
        "last_sync": {
            "started_at": last_sync.started_at if last_sync else None,
            "completed_at": last_sync.completed_at if last_sync else None,
            "status": last_sync.status if last_sync else None,
            "records_fetched": last_sync.records_fetched if last_sync else None,
            "date_from": last_sync.date_from if last_sync else None,
            "date_to": last_sync.date_to if last_sync else None,
            "error_message": last_sync.error_message if last_sync else None,
            "triggered_by": last_sync.triggered_by if last_sync else None,
        } if last_sync else None,
        "auto_sync": {
            "enabled": auto_enabled,
            "time": sync_time
        },
        "total_records": total_records,
        "data_range": {
            "from": date_range.min_date if date_range else None,
            "to": date_range.max_date if date_range else None
        }
    }


@router.get("/earned-revenue-data/logs")
async def get_earned_revenue_sync_logs(
    limit: int = Query(5, description="Number of logs to return"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get recent sync logs for earned revenue data.
    """
    result = await db.execute(
        text("""
            SELECT id, sync_type, started_at, completed_at, status,
                   records_fetched, records_created, records_updated,
                   date_from, date_to, error_message, triggered_by
            FROM sync_log
            WHERE source = 'newbook' AND sync_type = 'earned_revenue'
            ORDER BY started_at DESC
            LIMIT :limit
        """),
        {"limit": limit}
    )
    rows = result.fetchall()

    return [
        {
            "id": row.id,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "status": row.status,
            "records_fetched": row.records_fetched,
            "records_created": row.records_created,
            "date_from": row.date_from,
            "date_to": row.date_to,
            "error_message": row.error_message,
            "triggered_by": row.triggered_by
        }
        for row in rows
    ]


@router.post("/earned-revenue-data/sync")
async def trigger_earned_revenue_sync(
    background_tasks: BackgroundTasks,
    from_date: Optional[date] = Query(None, description="Start date for sync (default: today - 7 days)"),
    to_date: Optional[date] = Query(None, description="End date for sync (default: today)"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger an earned revenue data sync.

    If dates not provided, defaults to last 7 days (catches backdated adjustments).
    """
    # Default date range - last 7 days (revenue is historical)
    if not from_date:
        from_date = date.today() - timedelta(days=7)
    if not to_date:
        to_date = date.today()

    # Queue background task
    background_tasks.add_task(
        run_earned_revenue_data_sync,
        from_date=from_date,
        to_date=to_date,
        triggered_by=f"user:{current_user['username']}"
    )

    return {
        "status": "started",
        "from_date": from_date,
        "to_date": to_date,
        "message": f"Earned revenue sync started for {from_date} to {to_date}"
    }


@router.post("/earned-revenue-data/config")
async def update_earned_revenue_sync_config(
    config: EarnedRevenueSyncConfig,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update auto sync configuration for earned revenue data.
    """
    # Upsert enabled setting
    await db.execute(
        text("""
            INSERT INTO system_config (config_key, config_value, description, updated_at, updated_by)
            VALUES ('sync_newbook_earned_revenue_enabled', :value, 'Enable automatic Newbook earned revenue sync', NOW(), :user)
            ON CONFLICT (config_key) DO UPDATE SET
                config_value = :value,
                updated_at = NOW(),
                updated_by = :user
        """),
        {"value": str(config.enabled).lower(), "user": current_user['username']}
    )

    # Upsert sync time setting
    await db.execute(
        text("""
            INSERT INTO system_config (config_key, config_value, description, updated_at, updated_by)
            VALUES ('sync_newbook_earned_revenue_time', :value, 'Newbook earned revenue sync time (HH:MM)', NOW(), :user)
            ON CONFLICT (config_key) DO UPDATE SET
                config_value = :value,
                updated_at = NOW(),
                updated_by = :user
        """),
        {"value": config.sync_time, "user": current_user['username']}
    )

    await db.commit()

    return {
        "status": "success",
        "enabled": config.enabled,
        "sync_time": config.sync_time
    }


def run_earned_revenue_data_sync(
    from_date: date,
    to_date: date,
    triggered_by: str = "scheduler"
):
    """
    Background task to sync earned revenue data to newbook_earned_revenue_data table.
    """
    import sys
    import asyncio
    from jobs.data_sync import sync_newbook_earned_revenue

    print(f"[SYNC-EARNED-REV] Starting sync ({from_date} to {to_date})", flush=True)
    sys.stdout.flush()

    # Run async sync - create new event loop for background task
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            sync_newbook_earned_revenue(from_date, to_date, triggered_by)
        )
        print(f"[SYNC-EARNED-REV] Sync completed", flush=True)
    except Exception as e:
        print(f"[SYNC-EARNED-REV] FAILED: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise
    finally:
        loop.close()
