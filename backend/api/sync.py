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
    Get last sync times and status for all data sources.
    """
    query = """
        SELECT
            source,
            MAX(completed_at) as last_sync,
            (SELECT status FROM sync_log sl2
             WHERE sl2.source = sl.source
             ORDER BY completed_at DESC LIMIT 1) as last_status,
            (SELECT records_fetched FROM sync_log sl2
             WHERE sl2.source = sl.source
             ORDER BY completed_at DESC LIMIT 1) as last_records
        FROM sync_log sl
        GROUP BY source
    """

    result = await db.execute(text(query))
    rows = result.fetchall()

    return {
        row.source: {
            "last_sync": row.last_sync,
            "status": row.last_status,
            "records_fetched": row.last_records
        }
        for row in rows
    }


@router.post("/newbook")
async def trigger_newbook_sync(
    background_tasks: BackgroundTasks,
    from_date: Optional[date] = Query(None, description="Start date for sync"),
    to_date: Optional[date] = Query(None, description="End date for sync"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger manual Newbook data sync.
    Runs in background to avoid timeout.
    """
    from jobs.data_sync import sync_newbook_data

    if from_date is None:
        from_date = date.today() - timedelta(days=7)
    if to_date is None:
        to_date = date.today() + timedelta(days=365)

    # Queue background task
    background_tasks.add_task(
        sync_newbook_data,
        from_date=from_date,
        to_date=to_date,
        triggered_by=f"user:{current_user['username']}"
    )

    return {
        "status": "started",
        "source": "newbook",
        "from_date": from_date,
        "to_date": to_date,
        "message": "Newbook sync started in background"
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


@router.post("/full")
async def trigger_full_sync(
    background_tasks: BackgroundTasks,
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger full sync from all sources (Newbook + Resos).
    """
    from jobs.data_sync import run_data_sync

    if from_date is None:
        from_date = date.today() - timedelta(days=7)
    if to_date is None:
        to_date = date.today() + timedelta(days=365)

    background_tasks.add_task(
        run_data_sync,
        from_date=from_date,
        to_date=to_date,
        triggered_by=f"user:{current_user['username']}"
    )

    return {
        "status": "started",
        "sources": ["newbook", "resos"],
        "from_date": from_date,
        "to_date": to_date,
        "message": "Full sync started in background"
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
    """
    from jobs.data_sync import sync_newbook_data, sync_resos_data

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
                    await sync_newbook_data(current_start, current_end, f"backfill:{job_id}")

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
