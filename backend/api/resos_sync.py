"""
Resos Bookings Sync API Endpoints
Pattern: Similar to sync_bookings.py but for Resos
"""
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from database import get_db
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class ResosSyncConfig(BaseModel):
    """Auto sync configuration for Resos bookings"""
    auto_sync_enabled: bool
    sync_time: str = "05:05"  # HH:MM format


@router.get("/resos-bookings/status")
async def get_resos_sync_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get sync status for Resos bookings data including last sync info."""
    # Get last successful sync
    result = await db.execute(
        text("""
            SELECT id, sync_type, started_at, completed_at, status,
                   records_fetched, records_created, records_updated,
                   date_from, date_to, error_message, triggered_by
            FROM sync_log
            WHERE source = 'resos' AND sync_type = 'bookings_data'
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
            WHERE source = 'resos' AND sync_type = 'bookings_data'
            ORDER BY started_at DESC
            LIMIT 1
        """)
    )
    last_sync = result.fetchone()

    # Get auto sync config
    result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'sync_resos_bookings_enabled'")
    )
    row = result.fetchone()
    auto_enabled = row.config_value.lower() == 'true' if row and row.config_value else False

    result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'sync_resos_bookings_time'")
    )
    row = result.fetchone()
    sync_time = row.config_value if row and row.config_value else '05:05'

    # Get total records
    result = await db.execute(text("SELECT COUNT(*) as count FROM resos_bookings_data"))
    total_records = result.fetchone().count

    # Get date range
    result = await db.execute(
        text("SELECT MIN(booking_date) as min_date, MAX(booking_date) as max_date FROM resos_bookings_data")
    )
    date_range = result.fetchone()

    return {
        "last_successful_sync": {
            "completed_at": last_success.completed_at.isoformat() if last_success and last_success.completed_at else None,
            "records_fetched": last_success.records_fetched if last_success else None,
            "records_created": last_success.records_created if last_success else None,
            "records_updated": last_success.records_updated if last_success else None,
            "date_from": last_success.date_from.isoformat() if last_success and last_success.date_from else None,
            "date_to": last_success.date_to.isoformat() if last_success and last_success.date_to else None,
            "triggered_by": last_success.triggered_by if last_success else None,
        } if last_success else None,
        "last_sync": {
            "started_at": last_sync.started_at.isoformat() if last_sync and last_sync.started_at else None,
            "completed_at": last_sync.completed_at.isoformat() if last_sync and last_sync.completed_at else None,
            "status": last_sync.status if last_sync else None,
            "records_fetched": last_sync.records_fetched if last_sync else None,
            "date_from": last_sync.date_from.isoformat() if last_sync and last_sync.date_from else None,
            "date_to": last_sync.date_to.isoformat() if last_sync and last_sync.date_to else None,
            "error_message": last_sync.error_message if last_sync else None,
            "triggered_by": last_sync.triggered_by if last_sync else None,
        } if last_sync else None,
        "auto_sync": {
            "enabled": auto_enabled,
            "time": sync_time
        },
        "total_records": total_records,
        "data_range": {
            "from": date_range.min_date.isoformat() if date_range and date_range.min_date else None,
            "to": date_range.max_date.isoformat() if date_range and date_range.max_date else None
        }
    }


@router.post("/resos-bookings/sync")
async def trigger_resos_sync(
    background_tasks: BackgroundTasks,
    from_date: Optional[date] = Query(None, description="Start date (default: today - 365)"),
    to_date: Optional[date] = Query(None, description="End date (default: today + 365)"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger a Resos bookings sync.
    Default: -365 to +365 days (historical + forecast window)
    """
    if not from_date:
        from_date = date.today() - timedelta(days=365)
    if not to_date:
        to_date = date.today() + timedelta(days=365)

    # Queue background task
    background_tasks.add_task(
        run_resos_sync_task,
        from_date=from_date,
        to_date=to_date,
        triggered_by=f"user:{current_user['username']}"
    )

    return {
        "status": "started",
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "message": f"Resos bookings sync started for {from_date} to {to_date}"
    }


@router.get("/resos-bookings/config")
async def get_resos_sync_config(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get auto sync configuration for Resos bookings."""
    # Get enabled setting
    result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'sync_resos_bookings_enabled'")
    )
    row = result.fetchone()
    enabled = row.config_value.lower() == 'true' if row and row.config_value else False

    # Get sync time setting
    result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'sync_resos_bookings_time'")
    )
    row = result.fetchone()
    sync_time = row.config_value if row and row.config_value else '05:05'

    return {
        "auto_sync_enabled": enabled,
        "sync_time": sync_time
    }


@router.post("/resos-bookings/config")
async def update_resos_sync_config(
    config: ResosSyncConfig,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update auto sync configuration for Resos bookings."""
    # Upsert enabled setting
    await db.execute(
        text("""
            INSERT INTO system_config (config_key, config_value, description, updated_at, updated_by)
            VALUES ('sync_resos_bookings_enabled', :value, 'Enable automatic Resos bookings sync', NOW(), :user)
            ON CONFLICT (config_key) DO UPDATE SET
                config_value = :value,
                updated_at = NOW(),
                updated_by = :user
        """),
        {"value": str(config.auto_sync_enabled).lower(), "user": current_user['username']}
    )

    # Upsert sync time setting
    await db.execute(
        text("""
            INSERT INTO system_config (config_key, config_value, description, updated_at, updated_by)
            VALUES ('sync_resos_bookings_time', :value, 'Resos bookings sync time (HH:MM)', NOW(), :user)
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
        "auto_sync_enabled": config.auto_sync_enabled,
        "sync_time": config.sync_time
    }


def run_resos_sync_task(
    from_date: date,
    to_date: date,
    triggered_by: str = "scheduler"
):
    """Background task to run Resos sync."""
    import sys
    import asyncio
    from jobs.resos_bookings_sync import sync_resos_bookings_data

    print(f"[SYNC-RESOS] Starting sync ({from_date} to {to_date})", flush=True)
    sys.stdout.flush()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            sync_resos_bookings_data(from_date, to_date, triggered_by)
        )
        print(f"[SYNC-RESOS] Sync completed", flush=True)
    except Exception as e:
        print(f"[SYNC-RESOS] FAILED: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise
    finally:
        loop.close()
