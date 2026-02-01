"""
Data Sync API endpoints
"""
import uuid
import logging
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from database import get_db, SyncSessionLocal
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class BackfillRequest(BaseModel):
    """Request model for backfill job"""
    source: str  # 'newbook', 'resos', or 'all'
    from_date: date
    to_date: date
    chunk_months: int = 1  # Process in monthly chunks to avoid timeouts


@router.get("/status")
async def get_sync_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get last sync times and status for all data sources and sync types.

    Returns dict keyed by "{source}_{sync_type}" (e.g., "newbook_bookings", "newbook_earned_revenue")
    """
    query = """
        SELECT DISTINCT ON (source, sync_type)
            source,
            sync_type,
            completed_at as last_sync,
            status as last_status,
            records_fetched as last_records,
            records_created as last_created,
            date_from,
            date_to
        FROM sync_log
        ORDER BY source, sync_type, completed_at DESC
    """

    result = await db.execute(text(query))
    rows = result.fetchall()

    response = {}
    for row in rows:
        # Create key like "newbook_bookings" or "newbook_earned_revenue"
        key = f"{row.source}_{row.sync_type}" if row.sync_type else row.source
        response[key] = {
            "source": row.source,
            "sync_type": row.sync_type,
            "last_sync": row.last_sync,
            "status": row.last_status,
            "records_fetched": row.last_records,
            "records_created": row.last_created,
            "date_from": row.date_from,
            "date_to": row.date_to
        }

    return response


@router.post("/newbook")
async def trigger_newbook_sync(
    background_tasks: BackgroundTasks,
    full_sync: bool = Query(False, description="If True, fetches all bookings. If False, only fetches since last sync."),
    from_date: Optional[date] = Query(None, description="Start date for stay period (filters by arrival/stay dates)"),
    to_date: Optional[date] = Query(None, description="End date for stay period (filters by arrival/stay dates)"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger manual Newbook data sync.
    Runs in background to avoid timeout.

    - full_sync=False (default): Incremental sync - only bookings modified since last successful sync
    - full_sync=True: Full sync - fetches entire booking database
    - from_date/to_date: If provided, fetches bookings staying during this period (overrides full_sync)
    """
    from jobs.data_sync import sync_newbook_data

    # Queue background task
    background_tasks.add_task(
        sync_newbook_data,
        full_sync=full_sync,
        from_date=from_date,
        to_date=to_date,
        triggered_by=f"user:{current_user['username']}"
    )

    msg = "Newbook sync started in background"
    if from_date and to_date:
        msg = f"Newbook sync for {from_date} to {to_date} started in background"
    elif full_sync:
        msg = "Newbook full sync started in background"
    else:
        msg = "Newbook incremental sync started in background"

    return {
        "status": "started",
        "source": "newbook",
        "full_sync": full_sync,
        "from_date": from_date,
        "to_date": to_date,
        "message": msg
    }


@router.post("/resos")
async def trigger_resos_sync(
    background_tasks: BackgroundTasks,
    from_date: Optional[date] = Query(None, description="Start date for sync"),
    to_date: Optional[date] = Query(None, description="End date for sync"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger manual Resos data sync.
    Runs in background to avoid timeout.
    """
    from jobs.data_sync import sync_resos_data

    if from_date is None:
        from_date = date.today() - timedelta(days=7)
    if to_date is None:
        to_date = date.today() + timedelta(days=365)

    # Queue background task
    background_tasks.add_task(
        sync_resos_data,
        from_date=from_date,
        to_date=to_date,
        triggered_by=f"user:{current_user['username']}"
    )

    return {
        "status": "started",
        "source": "resos",
        "from_date": from_date,
        "to_date": to_date,
        "message": "Resos sync started in background"
    }


@router.post("/newbook/occupancy-report")
async def trigger_occupancy_report_sync(
    background_tasks: BackgroundTasks,
    from_date: Optional[date] = Query(None, description="Start date for report"),
    to_date: Optional[date] = Query(None, description="End date for report"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger Newbook occupancy report sync.

    This fetches Newbook's official occupancy report which provides:
    - Available rooms (accounting for maintenance/offline)
    - Official occupied room counts
    - Maintenance/offline room counts
    - Official revenue figures (gross and net)

    Use this to ensure accurate occupancy % calculations when rooms
    have been taken offline for maintenance.
    """
    from jobs.data_sync import sync_newbook_occupancy_report

    if from_date is None:
        from_date = date.today() - timedelta(days=90)
    if to_date is None:
        to_date = date.today() + timedelta(days=30)

    background_tasks.add_task(
        sync_newbook_occupancy_report,
        from_date=from_date,
        to_date=to_date,
        triggered_by=f"user:{current_user['username']}"
    )

    return {
        "status": "started",
        "source": "newbook_occupancy_report",
        "from_date": from_date,
        "to_date": to_date,
        "message": f"Newbook occupancy report sync started for {from_date} to {to_date}"
    }


@router.post("/newbook/earned-revenue")
async def trigger_earned_revenue_sync(
    background_tasks: BackgroundTasks,
    from_date: Optional[date] = Query(None, description="Start date for revenue"),
    to_date: Optional[date] = Query(None, description="End date for revenue"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger Newbook earned revenue sync.

    This fetches official financial figures by GL account from Newbook's
    report_earned_revenue endpoint. Uses accommodation_gl_codes config
    to identify which GL accounts are room revenue.

    Defaults to last 7 days if no dates specified (catches adjustments).
    For historical backfill, specify a wider date range.
    """
    from jobs.data_sync import sync_newbook_earned_revenue

    if from_date is None:
        from_date = date.today() - timedelta(days=7)
    if to_date is None:
        to_date = date.today()

    background_tasks.add_task(
        sync_newbook_earned_revenue,
        from_date=from_date,
        to_date=to_date,
        triggered_by=f"user:{current_user['username']}"
    )

    return {
        "status": "started",
        "source": "newbook_earned_revenue",
        "from_date": from_date,
        "to_date": to_date,
        "message": f"Newbook earned revenue sync started for {from_date} to {to_date}"
    }


@router.post("/full")
async def trigger_full_sync(
    background_tasks: BackgroundTasks,
    full_sync: bool = Query(False, description="If True, fetches all bookings from both sources"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger full sync from all sources (Newbook bookings, Newbook occupancy report, Resos).
    """
    from jobs.data_sync import run_data_sync

    background_tasks.add_task(
        run_data_sync,
        full_sync=full_sync,
        triggered_by=f"user:{current_user['username']}"
    )

    return {
        "status": "started",
        "sources": ["newbook", "newbook_occupancy_report", "resos"],
        "full_sync": full_sync,
        "message": f"Full {'complete' if full_sync else 'incremental'} sync started in background"
    }


@router.post("/aggregate")
async def trigger_aggregation(
    background_tasks: BackgroundTasks,
    source: Optional[str] = Query(None, description="Filter by source: newbook, resos. Leave empty for all."),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger manual aggregation of pending dates.
    Processes the aggregation queue and updates daily_occupancy/daily_covers tables.
    """
    from jobs.aggregation import run_aggregation

    if source and source not in ['newbook', 'resos']:
        raise HTTPException(status_code=400, detail="Source must be 'newbook', 'resos', or omitted for all")

    background_tasks.add_task(
        run_aggregation,
        source=source
    )

    return {
        "status": "started",
        "source": source or "all",
        "message": f"Aggregation started for {source or 'all sources'}"
    }


@router.post("/aggregate/requeue")
async def requeue_for_aggregation(
    background_tasks: BackgroundTasks,
    source: str = Query(..., description="Source to requeue: newbook or resos"),
    from_date: Optional[date] = Query(None, description="Start date (optional, defaults to all)"),
    to_date: Optional[date] = Query(None, description="End date (optional, defaults to all)"),
    run_aggregation_after: bool = Query(True, description="Automatically run aggregation after queuing"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Re-queue dates from raw data for aggregation.

    Useful when you want to re-aggregate existing data (e.g., after changing
    mappings or fixing bugs in aggregation logic).
    """
    if source not in ['newbook', 'resos']:
        raise HTTPException(status_code=400, detail="Source must be 'newbook' or 'resos'")

    # Get distinct dates from raw data
    if source == 'resos':
        date_query = "SELECT DISTINCT booking_date as date FROM resos_bookings WHERE 1=1"
    else:  # newbook
        date_query = """
            SELECT DISTINCT stay_date as date
            FROM newbook_booking_nights bn
            JOIN newbook_bookings b ON bn.booking_id = b.id
            WHERE 1=1
        """

    params = {}
    if from_date:
        if source == 'resos':
            date_query += " AND booking_date >= :from_date"
        else:
            date_query += " AND stay_date >= :from_date"
        params["from_date"] = from_date

    if to_date:
        if source == 'resos':
            date_query += " AND booking_date <= :to_date"
        else:
            date_query += " AND stay_date <= :to_date"
        params["to_date"] = to_date

    date_query += " ORDER BY date"

    result = await db.execute(text(date_query), params)
    dates = [row.date for row in result.fetchall()]

    if not dates:
        return {
            "status": "no_data",
            "message": f"No dates found in {source} raw data for the specified range"
        }

    # Insert dates into queue (delete existing pending entries first, then insert)
    # Clear any existing pending entries for these dates
    await db.execute(
        text("""
            DELETE FROM aggregation_queue
            WHERE source = :source
              AND aggregated_at IS NULL
        """),
        {"source": source}
    )

    # Insert all dates
    for d in dates:
        await db.execute(
            text("""
                INSERT INTO aggregation_queue (date, source, reason, queued_at)
                VALUES (:date, :source, 'manual_requeue', NOW())
            """),
            {"date": d, "source": source}
        )

    await db.commit()

    # Optionally trigger aggregation
    if run_aggregation_after:
        from jobs.aggregation import run_aggregation as do_aggregation
        background_tasks.add_task(do_aggregation, source=source)

    return {
        "status": "queued",
        "source": source,
        "dates_queued": len(dates),
        "date_range": f"{min(dates)} to {max(dates)}",
        "aggregation_started": run_aggregation_after,
        "message": f"Queued {len(dates)} dates for {source} aggregation"
    }


@router.get("/aggregate/status")
async def get_aggregation_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get aggregation status summary including pending counts and totals.
    """
    # Get pending counts by source
    pending_query = """
        SELECT
            source,
            COUNT(*) as pending_count,
            MIN(date) as earliest_date,
            MAX(date) as latest_date
        FROM aggregation_queue
        WHERE aggregated_at IS NULL
        GROUP BY source
    """
    result = await db.execute(text(pending_query))
    pending_rows = result.fetchall()

    pending_by_source = {
        row.source: {
            "count": row.pending_count,
            "earliest": row.earliest_date,
            "latest": row.latest_date
        }
        for row in pending_rows
    }

    # Get total pending count
    total_pending_result = await db.execute(
        text("SELECT COUNT(*) as total FROM aggregation_queue WHERE aggregated_at IS NULL")
    )
    total_pending = total_pending_result.fetchone().total

    # Get aggregated totals
    occupancy_result = await db.execute(
        text("SELECT COUNT(*) as count, MIN(date) as earliest, MAX(date) as latest FROM daily_occupancy")
    )
    occupancy_row = occupancy_result.fetchone()

    covers_result = await db.execute(
        text("SELECT COUNT(*) as count, MIN(date) as earliest, MAX(date) as latest FROM daily_covers")
    )
    covers_row = covers_result.fetchone()

    # Get last aggregation timestamp (from most recent processed queue entry)
    last_agg_result = await db.execute(
        text("SELECT MAX(aggregated_at) as last_run FROM aggregation_queue WHERE aggregated_at IS NOT NULL")
    )
    last_agg_row = last_agg_result.fetchone()

    return {
        "pending": {
            "total": total_pending,
            "by_source": pending_by_source
        },
        "aggregated": {
            "daily_occupancy": {
                "count": occupancy_row.count if occupancy_row else 0,
                "earliest": occupancy_row.earliest if occupancy_row else None,
                "latest": occupancy_row.latest if occupancy_row else None
            },
            "daily_covers": {
                "count": covers_row.count if covers_row else 0,
                "earliest": covers_row.earliest if covers_row else None,
                "latest": covers_row.latest if covers_row else None
            }
        },
        "last_aggregation": last_agg_row.last_run if last_agg_row else None
    }


@router.get("/aggregate/queue")
async def get_aggregation_queue(
    source: Optional[str] = Query(None, description="Filter by source"),
    pending_only: bool = Query(True, description="Only show pending (un-aggregated) entries"),
    limit: int = Query(100, description="Max entries to return"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    View the aggregation queue status.
    """
    query = """
        SELECT date, source, reason, booking_id, queued_at, aggregated_at
        FROM aggregation_queue
        WHERE 1=1
    """
    params = {"limit": limit}

    if source:
        query += " AND source = :source"
        params["source"] = source

    if pending_only:
        query += " AND aggregated_at IS NULL"

    query += " ORDER BY date, source LIMIT :limit"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return {
        "count": len(rows),
        "entries": [
            {
                "date": row.date,
                "source": row.source,
                "reason": row.reason,
                "booking_id": row.booking_id,
                "queued_at": row.queued_at,
                "aggregated_at": row.aggregated_at
            }
            for row in rows
        ]
    }


@router.get("/logs")
async def get_sync_logs(
    source: Optional[str] = Query(None, description="Filter by source: newbook, resos"),
    limit: int = Query(20, description="Number of logs to return"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get recent sync logs for monitoring.
    """
    query = """
        SELECT
            id,
            sync_type,
            source,
            started_at,
            completed_at,
            status,
            records_fetched,
            records_created,
            records_updated,
            date_from,
            date_to,
            error_message,
            triggered_by
        FROM sync_log
    """
    params = {"limit": limit}

    if source:
        query += " WHERE source = :source"
        params["source"] = source

    query += " ORDER BY started_at DESC LIMIT :limit"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "id": row.id,
            "sync_type": row.sync_type,
            "source": row.source,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "status": row.status,
            "records_fetched": row.records_fetched,
            "records_created": row.records_created,
            "records_updated": row.records_updated,
            "date_range": f"{row.date_from} to {row.date_to}" if row.date_from else None,
            "error_message": row.error_message,
            "triggered_by": row.triggered_by
        }
        for row in rows
    ]


# ============================================
# HISTORICAL BACKFILL ENDPOINTS
# ============================================

@router.post("/backfill")
async def start_backfill(
    request: BackfillRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Start a historical data backfill job.

    Processes data in monthly chunks to avoid API timeouts and rate limits.
    Progress can be monitored via GET /sync/backfill/status/{job_id}
    """
    if request.source not in ['newbook', 'resos', 'all']:
        raise HTTPException(status_code=400, detail="Source must be 'newbook', 'resos', or 'all'")

    if request.from_date >= request.to_date:
        raise HTTPException(status_code=400, detail="from_date must be before to_date")

    # Calculate number of chunks
    total_months = (request.to_date.year - request.from_date.year) * 12 + \
                   (request.to_date.month - request.from_date.month) + 1
    chunks_total = (total_months + request.chunk_months - 1) // request.chunk_months

    # Create backfill job record
    job_id = str(uuid.uuid4())
    await db.execute(
        text("""
            INSERT INTO backfill_jobs (
                job_id, source, from_date, to_date, chunk_months,
                status, chunks_total, triggered_by, created_at
            ) VALUES (
                :job_id, :source, :from_date, :to_date, :chunk_months,
                'pending', :chunks_total, :triggered_by, NOW()
            )
        """),
        {
            "job_id": job_id,
            "source": request.source,
            "from_date": request.from_date,
            "to_date": request.to_date,
            "chunk_months": request.chunk_months,
            "chunks_total": chunks_total,
            "triggered_by": f"user:{current_user['username']}"
        }
    )
    await db.commit()

    # Queue background task
    background_tasks.add_task(
        run_backfill_job,
        job_id=job_id,
        source=request.source,
        from_date=request.from_date,
        to_date=request.to_date,
        chunk_months=request.chunk_months
    )

    return {
        "status": "started",
        "job_id": job_id,
        "source": request.source,
        "from_date": request.from_date,
        "to_date": request.to_date,
        "chunk_months": request.chunk_months,
        "chunks_total": chunks_total,
        "message": f"Backfill job started. Monitor progress at /sync/backfill/status/{job_id}"
    }


@router.get("/backfill/status/{job_id}")
async def get_backfill_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get status of a backfill job.
    """
    result = await db.execute(
        text("""
            SELECT
                job_id, source, from_date, to_date, chunk_months,
                status, current_chunk_start, current_chunk_end,
                chunks_total, chunks_completed, records_total,
                error_message, started_at, completed_at, triggered_by
            FROM backfill_jobs
            WHERE job_id = :job_id
        """),
        {"job_id": job_id}
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Backfill job not found")

    progress_pct = 0
    if row.chunks_total and row.chunks_total > 0:
        progress_pct = round((row.chunks_completed / row.chunks_total) * 100, 1)

    return {
        "job_id": row.job_id,
        "source": row.source,
        "date_range": f"{row.from_date} to {row.to_date}",
        "chunk_months": row.chunk_months,
        "status": row.status,
        "progress": {
            "current_chunk": f"{row.current_chunk_start} to {row.current_chunk_end}" if row.current_chunk_start else None,
            "chunks_completed": row.chunks_completed,
            "chunks_total": row.chunks_total,
            "percent_complete": progress_pct,
            "records_synced": row.records_total
        },
        "error_message": row.error_message,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
        "triggered_by": row.triggered_by
    }


@router.get("/backfill/jobs")
async def list_backfill_jobs(
    status: Optional[str] = Query(None, description="Filter by status: pending, running, completed, failed"),
    limit: int = Query(20, description="Number of jobs to return"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List recent backfill jobs.
    """
    query = """
        SELECT
            job_id, source, from_date, to_date, status,
            chunks_completed, chunks_total, records_total,
            started_at, completed_at
        FROM backfill_jobs
    """
    params = {"limit": limit}

    if status:
        query += " WHERE status = :status"
        params["status"] = status

    query += " ORDER BY created_at DESC LIMIT :limit"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "job_id": row.job_id,
            "source": row.source,
            "date_range": f"{row.from_date} to {row.to_date}",
            "status": row.status,
            "progress": f"{row.chunks_completed}/{row.chunks_total} chunks",
            "records_synced": row.records_total,
            "started_at": row.started_at,
            "completed_at": row.completed_at
        }
        for row in rows
    ]


async def run_backfill_job(
    job_id: str,
    source: str,
    from_date: date,
    to_date: date,
    chunk_months: int
):
    """
    Background task to run backfill in chunks.

    For Newbook: Uses modified_since/modified_until to backfill booking data by modification date.
    For Resos: Uses from_date/to_date to backfill by booking date.
    """
    from jobs.data_sync import sync_resos_data
    from services.newbook_client import NewbookClient
    import json

    db = SyncSessionLocal()

    try:
        # Mark job as running
        db.execute(
            text("""
                UPDATE backfill_jobs
                SET status = 'running', started_at = NOW()
                WHERE job_id = :job_id
            """),
            {"job_id": job_id}
        )
        db.commit()

        # Process in chunks
        current_start = from_date
        chunks_completed = 0
        total_records = 0

        while current_start <= to_date:
            # Calculate chunk end date
            current_end = current_start + relativedelta(months=chunk_months) - timedelta(days=1)
            if current_end > to_date:
                current_end = to_date

            logger.info(f"Backfill {job_id}: Processing {current_start} to {current_end}")

            # Update current chunk in job
            db.execute(
                text("""
                    UPDATE backfill_jobs
                    SET current_chunk_start = :start, current_chunk_end = :end
                    WHERE job_id = :job_id
                """),
                {"job_id": job_id, "start": current_start, "end": current_end}
            )
            db.commit()

            # Sync data for this chunk
            try:
                if source in ['newbook', 'all']:
                    # For backfill, do a full sync (no modified_since filter)
                    # This pulls all bookings - the sync job handles deduplication via upserts
                    from jobs.data_sync import sync_newbook_data, sync_newbook_occupancy_report
                    await sync_newbook_data(
                        full_sync=True,
                        triggered_by=f"backfill:{job_id}"
                    )
                    # Also backfill occupancy report for this chunk
                    # This provides available rooms, maintenance, official occupancy figures
                    await sync_newbook_occupancy_report(
                        from_date=current_start,
                        to_date=current_end,
                        triggered_by=f"backfill:{job_id}"
                    )

                    # Backfill earned revenue for this chunk (historical dates only)
                    # This provides official financial figures by GL account
                    from jobs.data_sync import sync_newbook_earned_revenue
                    # Only sync earned revenue for historical dates (not future)
                    earned_rev_end = min(current_end, date.today())
                    if current_start <= earned_rev_end:
                        await sync_newbook_earned_revenue(
                            from_date=current_start,
                            to_date=earned_rev_end,
                            triggered_by=f"backfill:{job_id}"
                        )

                if source in ['resos', 'all']:
                    await sync_resos_data(current_start, current_end, f"backfill:{job_id}")

            except Exception as chunk_error:
                logger.error(f"Backfill chunk error: {chunk_error}")
                # Continue with next chunk instead of failing entire job

            chunks_completed += 1

            # Get records synced for this chunk from sync_log
            result = db.execute(
                text("""
                    SELECT COALESCE(SUM(records_fetched), 0) as total
                    FROM sync_log
                    WHERE triggered_by = :triggered_by
                """),
                {"triggered_by": f"backfill:{job_id}"}
            )
            row = result.fetchone()
            total_records = row.total if row else 0

            # Update progress
            db.execute(
                text("""
                    UPDATE backfill_jobs
                    SET chunks_completed = :completed, records_total = :records
                    WHERE job_id = :job_id
                """),
                {"job_id": job_id, "completed": chunks_completed, "records": total_records}
            )
            db.commit()

            # Move to next chunk
            current_start = current_end + timedelta(days=1)

            # For Newbook full sync, we only need to run once (not chunked)
            if source == 'newbook':
                break

        # Run aggregation after backfill
        from jobs.aggregation import run_aggregation
        await run_aggregation()

        # Mark job as completed
        db.execute(
            text("""
                UPDATE backfill_jobs
                SET status = 'completed', completed_at = NOW()
                WHERE job_id = :job_id
            """),
            {"job_id": job_id}
        )
        db.commit()

        logger.info(f"Backfill {job_id} completed: {total_records} records synced")

    except Exception as e:
        logger.error(f"Backfill {job_id} failed: {e}")
        db.execute(
            text("""
                UPDATE backfill_jobs
                SET status = 'failed', error_message = :error, completed_at = NOW()
                WHERE job_id = :job_id
            """),
            {"job_id": job_id, "error": str(e)}
        )
        db.commit()
        raise
    finally:
        db.close()
