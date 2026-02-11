"""
Reconciliation API Endpoints

Provides cash-up management, Newbook payment integration, multi-day reporting,
float management, attachment handling, and reconciliation settings.
"""
import os
import shutil
import logging
from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from database import get_db
from auth import get_current_user, get_admin_user
from services.reconciliation_service import (
    categorize_payments,
    calculate_payment_totals,
    parse_till_transactions,
    build_reconciliation_rows,
    build_multi_day_report,
)

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = "/app/uploads/reconciliation"


# ============================================
# PYDANTIC MODELS
# ============================================

class DenominationEntry(BaseModel):
    count_type: str  # 'float' | 'takings'
    denomination_type: str  # 'note' | 'coin'
    denomination_value: float
    quantity: Optional[int] = None
    value_entered: Optional[float] = None
    total_amount: float


class CardMachineEntry(BaseModel):
    machine_name: str
    total_amount: float
    amex_amount: float
    visa_mc_amount: float


class ReconciliationEntry(BaseModel):
    category: str
    banked_amount: float
    reported_amount: float
    variance: float


class CashUpCreate(BaseModel):
    session_date: str  # YYYY-MM-DD


class CashUpUpdate(BaseModel):
    denominations: List[DenominationEntry] = []
    card_machines: List[CardMachineEntry] = []
    reconciliation: List[ReconciliationEntry] = []
    notes: Optional[str] = None
    total_float_counted: float = 0.0
    total_cash_counted: float = 0.0


class FloatDenominationEntry(BaseModel):
    denomination_value: float
    quantity: int
    total_amount: float


class FloatReceiptEntry(BaseModel):
    receipt_value: float
    receipt_description: Optional[str] = None


class FloatCountCreate(BaseModel):
    count_type: str  # 'petty_cash' | 'change_tin' | 'safe_cash'
    count_date: Optional[str] = None
    denominations: List[FloatDenominationEntry] = []
    receipts: List[FloatReceiptEntry] = []
    total_counted: float = 0.0
    total_receipts: float = 0.0
    target_amount: float = 0.0
    variance: float = 0.0
    notes: Optional[str] = None


class ReconSettingsUpdate(BaseModel):
    expected_till_float: Optional[float] = None
    variance_threshold: Optional[float] = None
    default_report_days: Optional[int] = None
    petty_cash_target: Optional[float] = None
    change_tin_breakdown: Optional[dict] = None
    safe_cash_target: Optional[float] = None
    sales_breakdown_columns: Optional[list] = None
    denominations: Optional[dict] = None


class BulkFinalizeRequest(BaseModel):
    ids: List[int]


# ============================================
# CASH UP CRUD
# ============================================

@router.get("/cash-ups")
async def list_cash_ups(
    status: Optional[str] = Query(None, description="Filter by status (draft/final)"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List cash-ups with filters and pagination."""
    conditions = []
    params = {}

    if status:
        conditions.append("c.status = :status")
        params["status"] = status
    if date_from:
        conditions.append("c.session_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        conditions.append("c.session_date <= :date_to")
        params["date_to"] = date_to

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * per_page
    params["limit"] = per_page
    params["offset"] = offset

    # Get count
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM recon_cash_ups c {where}"), params
    )
    total = count_result.scalar()

    # Get rows
    result = await db.execute(
        text(f"""
            SELECT c.*, u.display_name as created_by_name,
                   su.display_name as submitted_by_name
            FROM recon_cash_ups c
            LEFT JOIN users u ON c.created_by = u.id
            LEFT JOIN users su ON c.submitted_by = su.id
            {where}
            ORDER BY c.session_date DESC
            LIMIT :limit OFFSET :offset
        """), params
    )
    rows = result.fetchall()

    cash_ups = []
    for row in rows:
        cash_ups.append({
            "id": row.id,
            "session_date": row.session_date.isoformat() if row.session_date else None,
            "status": row.status,
            "total_float_counted": float(row.total_float_counted or 0),
            "total_cash_counted": float(row.total_cash_counted or 0),
            "notes": row.notes,
            "created_by": row.created_by,
            "created_by_name": row.created_by_name,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
            "submitted_by_name": row.submitted_by_name,
        })

    return {
        "cash_ups": cash_ups,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    }


@router.get("/cash-ups/by-date/{session_date}")
async def get_cash_up_by_date(
    session_date: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Check if cash-up exists for a given date and return full data."""
    result = await db.execute(
        text("SELECT * FROM recon_cash_ups WHERE session_date = :d"),
        {"d": session_date}
    )
    cash_up = result.fetchone()
    if not cash_up:
        raise HTTPException(status_code=404, detail="No cash-up found for this date")

    return await _build_full_cash_up(db, cash_up)


@router.get("/cash-ups/{cash_up_id}")
async def get_cash_up(
    cash_up_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get full cash-up with all related data."""
    result = await db.execute(
        text("SELECT * FROM recon_cash_ups WHERE id = :id"),
        {"id": cash_up_id}
    )
    cash_up = result.fetchone()
    if not cash_up:
        raise HTTPException(status_code=404, detail="Cash-up not found")

    return await _build_full_cash_up(db, cash_up)


async def _build_full_cash_up(db: AsyncSession, cash_up) -> dict:
    """Build full cash-up response with denominations, cards, reconciliation, attachments."""
    cash_up_id = cash_up.id

    # Denominations
    denom_result = await db.execute(
        text("SELECT * FROM recon_denominations WHERE cash_up_id = :id ORDER BY count_type, denomination_value DESC"),
        {"id": cash_up_id}
    )
    denominations = [
        {
            "id": d.id,
            "count_type": d.count_type,
            "denomination_type": d.denomination_type,
            "denomination_value": float(d.denomination_value),
            "quantity": d.quantity,
            "value_entered": float(d.value_entered) if d.value_entered else None,
            "total_amount": float(d.total_amount),
        }
        for d in denom_result.fetchall()
    ]

    # Card machines
    card_result = await db.execute(
        text("SELECT * FROM recon_card_machines WHERE cash_up_id = :id"),
        {"id": cash_up_id}
    )
    card_machines = [
        {
            "id": c.id,
            "machine_name": c.machine_name,
            "total_amount": float(c.total_amount),
            "amex_amount": float(c.amex_amount),
            "visa_mc_amount": float(c.visa_mc_amount),
        }
        for c in card_result.fetchall()
    ]

    # Reconciliation rows
    recon_result = await db.execute(
        text("SELECT * FROM recon_reconciliation WHERE cash_up_id = :id"),
        {"id": cash_up_id}
    )
    reconciliation = [
        {
            "id": r.id,
            "category": r.category,
            "banked_amount": float(r.banked_amount),
            "reported_amount": float(r.reported_amount),
            "variance": float(r.variance),
        }
        for r in recon_result.fetchall()
    ]

    # Attachments
    attach_result = await db.execute(
        text("SELECT * FROM recon_attachments WHERE cash_up_id = :id ORDER BY uploaded_at DESC"),
        {"id": cash_up_id}
    )
    attachments = [
        {
            "id": a.id,
            "file_name": a.file_name,
            "file_type": a.file_type,
            "file_size": a.file_size,
            "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None,
        }
        for a in attach_result.fetchall()
    ]

    # Creator name
    user_result = await db.execute(
        text("SELECT display_name FROM users WHERE id = :id"),
        {"id": cash_up.created_by}
    )
    creator = user_result.fetchone()

    return {
        "cash_up": {
            "id": cash_up.id,
            "session_date": cash_up.session_date.isoformat() if cash_up.session_date else None,
            "status": cash_up.status,
            "total_float_counted": float(cash_up.total_float_counted or 0),
            "total_cash_counted": float(cash_up.total_cash_counted or 0),
            "notes": cash_up.notes,
            "created_by": cash_up.created_by,
            "created_by_name": creator.display_name if creator else None,
            "created_at": cash_up.created_at.isoformat() if cash_up.created_at else None,
            "updated_at": cash_up.updated_at.isoformat() if cash_up.updated_at else None,
            "submitted_at": cash_up.submitted_at.isoformat() if cash_up.submitted_at else None,
        },
        "denominations": denominations,
        "card_machines": card_machines,
        "reconciliation": reconciliation,
        "attachments": attachments,
    }


@router.post("/cash-ups")
async def create_cash_up(
    data: CashUpCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new cash-up session."""
    # Check if date already exists
    existing = await db.execute(
        text("SELECT id FROM recon_cash_ups WHERE session_date = :d"),
        {"d": data.session_date}
    )
    if existing.fetchone():
        raise HTTPException(status_code=409, detail="Cash-up already exists for this date")

    result = await db.execute(
        text("""
            INSERT INTO recon_cash_ups (session_date, created_by, status, created_at, updated_at)
            VALUES (:session_date, :created_by, 'draft', NOW(), NOW())
            RETURNING id, session_date, status, created_at
        """),
        {"session_date": data.session_date, "created_by": current_user["id"]}
    )
    await db.commit()
    row = result.fetchone()
    return {
        "id": row.id,
        "session_date": row.session_date.isoformat(),
        "status": row.status,
        "created_at": row.created_at.isoformat(),
    }


@router.put("/cash-ups/{cash_up_id}")
async def update_cash_up(
    cash_up_id: int,
    data: CashUpUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update a cash-up (denominations, cards, reconciliation, notes)."""
    # Verify exists and is draft
    existing = await db.execute(
        text("SELECT id, status FROM recon_cash_ups WHERE id = :id"),
        {"id": cash_up_id}
    )
    cash_up = existing.fetchone()
    if not cash_up:
        raise HTTPException(status_code=404, detail="Cash-up not found")
    if cash_up.status == 'final':
        raise HTTPException(status_code=400, detail="Cannot edit a finalized cash-up")

    # Update main record
    await db.execute(
        text("""
            UPDATE recon_cash_ups
            SET total_float_counted = :float_total,
                total_cash_counted = :cash_total,
                notes = :notes,
                updated_at = NOW()
            WHERE id = :id
        """),
        {
            "id": cash_up_id,
            "float_total": data.total_float_counted,
            "cash_total": data.total_cash_counted,
            "notes": data.notes,
        }
    )

    # Replace denominations
    await db.execute(
        text("DELETE FROM recon_denominations WHERE cash_up_id = :id"),
        {"id": cash_up_id}
    )
    for d in data.denominations:
        await db.execute(
            text("""
                INSERT INTO recon_denominations
                (cash_up_id, count_type, denomination_type, denomination_value, quantity, value_entered, total_amount)
                VALUES (:cid, :ct, :dt, :dv, :q, :ve, :ta)
            """),
            {
                "cid": cash_up_id,
                "ct": d.count_type,
                "dt": d.denomination_type,
                "dv": d.denomination_value,
                "q": d.quantity,
                "ve": d.value_entered,
                "ta": d.total_amount,
            }
        )

    # Replace card machines
    await db.execute(
        text("DELETE FROM recon_card_machines WHERE cash_up_id = :id"),
        {"id": cash_up_id}
    )
    for c in data.card_machines:
        await db.execute(
            text("""
                INSERT INTO recon_card_machines
                (cash_up_id, machine_name, total_amount, amex_amount, visa_mc_amount)
                VALUES (:cid, :mn, :ta, :aa, :vma)
            """),
            {
                "cid": cash_up_id,
                "mn": c.machine_name,
                "ta": c.total_amount,
                "aa": c.amex_amount,
                "vma": c.visa_mc_amount,
            }
        )

    # Replace reconciliation rows
    await db.execute(
        text("DELETE FROM recon_reconciliation WHERE cash_up_id = :id"),
        {"id": cash_up_id}
    )
    for r in data.reconciliation:
        await db.execute(
            text("""
                INSERT INTO recon_reconciliation
                (cash_up_id, category, banked_amount, reported_amount, variance)
                VALUES (:cid, :cat, :ba, :ra, :var)
            """),
            {
                "cid": cash_up_id,
                "cat": r.category,
                "ba": r.banked_amount,
                "ra": r.reported_amount,
                "var": r.variance,
            }
        )

    await db.commit()
    return {"message": "Cash-up updated successfully", "id": cash_up_id}


@router.post("/cash-ups/{cash_up_id}/finalize")
async def finalize_cash_up(
    cash_up_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Finalize a draft cash-up."""
    existing = await db.execute(
        text("SELECT id, status FROM recon_cash_ups WHERE id = :id"),
        {"id": cash_up_id}
    )
    cash_up = existing.fetchone()
    if not cash_up:
        raise HTTPException(status_code=404, detail="Cash-up not found")
    if cash_up.status == 'final':
        raise HTTPException(status_code=400, detail="Cash-up is already finalized")

    await db.execute(
        text("""
            UPDATE recon_cash_ups
            SET status = 'final', submitted_at = NOW(), submitted_by = :user_id, updated_at = NOW()
            WHERE id = :id
        """),
        {"id": cash_up_id, "user_id": current_user["id"]}
    )
    await db.commit()
    return {"message": "Cash-up finalized", "id": cash_up_id}


@router.delete("/cash-ups/{cash_up_id}")
async def delete_cash_up(
    cash_up_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete a draft cash-up. Admins can delete any; staff only drafts they created."""
    existing = await db.execute(
        text("SELECT id, status, created_by FROM recon_cash_ups WHERE id = :id"),
        {"id": cash_up_id}
    )
    cash_up = existing.fetchone()
    if not cash_up:
        raise HTTPException(status_code=404, detail="Cash-up not found")
    if cash_up.status == 'final' and current_user.get("role") != "admin":
        raise HTTPException(status_code=400, detail="Cannot delete a finalized cash-up")

    # Delete attachments from filesystem
    attach_result = await db.execute(
        text("SELECT file_path FROM recon_attachments WHERE cash_up_id = :id"),
        {"id": cash_up_id}
    )
    for a in attach_result.fetchall():
        if os.path.exists(a.file_path):
            os.remove(a.file_path)

    # CASCADE handles child records
    await db.execute(
        text("DELETE FROM recon_cash_ups WHERE id = :id"),
        {"id": cash_up_id}
    )
    await db.commit()
    return {"message": "Cash-up deleted"}


@router.post("/cash-ups/bulk-finalize")
async def bulk_finalize_cash_ups(
    data: BulkFinalizeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_admin_user)
):
    """Finalize multiple cash-ups (admin only)."""
    finalized = 0
    errors = []
    for cash_up_id in data.ids:
        result = await db.execute(
            text("SELECT id, status FROM recon_cash_ups WHERE id = :id"),
            {"id": cash_up_id}
        )
        row = result.fetchone()
        if not row:
            errors.append(f"ID {cash_up_id}: not found")
        elif row.status == 'final':
            errors.append(f"ID {cash_up_id}: already finalized")
        else:
            await db.execute(
                text("""
                    UPDATE recon_cash_ups
                    SET status = 'final', submitted_at = NOW(), submitted_by = :user_id, updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": cash_up_id, "user_id": current_user["id"]}
            )
            finalized += 1

    await db.commit()
    return {"finalized": finalized, "errors": errors}


# ============================================
# NEWBOOK PAYMENT INTEGRATION
# ============================================

@router.get("/newbook/payments/{payment_date}")
async def fetch_newbook_payments(
    payment_date: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Fetch and categorize payments from Newbook for a given date."""
    from services.newbook_client import NewbookClient

    try:
        target_date = date.fromisoformat(payment_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    try:
        async with await NewbookClient.from_db(db) as client:
            raw_transactions = await client.get_transaction_flow(target_date, target_date)
    except Exception as e:
        logger.error(f"Newbook API error: {e}")
        raise HTTPException(status_code=502, detail=f"Newbook API error: {str(e)}")

    # Process transactions
    payments = categorize_payments(raw_transactions)
    totals = calculate_payment_totals(payments)
    till_breakdown = parse_till_transactions(raw_transactions)

    # Store payment records (replace existing for this date)
    await db.execute(
        text("DELETE FROM recon_payment_records WHERE payment_date::date = :d"),
        {"d": payment_date}
    )
    for p in payments:
        await db.execute(
            text("""
                INSERT INTO recon_payment_records
                (newbook_payment_id, booking_id, guest_name, payment_date,
                 payment_type, payment_method, transaction_method, card_type,
                 amount, tendered, processed_by, item_type, synced_at)
                VALUES (:pid, :bid, :gn, :pd, :pt, :pm, :tm, :ct, :amt, :ten, :pb, :it, NOW())
            """),
            {
                "pid": p['payment_id'],
                "bid": p['booking_id'],
                "gn": p['guest_name'],
                "pd": p['payment_date'],
                "pt": p['payment_type'],
                "pm": p['payment_method'],
                "tm": p['transaction_method'],
                "ct": p['card_type'],
                "amt": p['amount'],
                "ten": p['tendered'],
                "pb": p['processed_by'],
                "it": p['item_type'],
            }
        )
    await db.commit()

    return {
        "date": payment_date,
        "payment_count": len(payments),
        "totals": totals,
        "till_breakdown": till_breakdown,
        "payments": payments,
    }


@router.get("/newbook/daily-stats/{stats_date}")
async def fetch_newbook_daily_stats(
    stats_date: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Fetch daily stats (occupancy, sales, debtors/creditors) from existing app data."""
    try:
        target_date = date.fromisoformat(stats_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    # Fetch from existing bookings stats
    stats_result = await db.execute(
        text("""
            SELECT booking_count as rooms_sold, guests_count as total_people,
                   guest_rate_total as gross_sales
            FROM newbook_bookings_stats
            WHERE date = :d
        """),
        {"d": stats_date}
    )
    stats_row = stats_result.fetchone()

    stats = {
        "business_date": stats_date,
        "rooms_sold": stats_row.rooms_sold if stats_row else 0,
        "total_people": stats_row.total_people if stats_row else 0,
        "gross_sales": float(stats_row.gross_sales) if stats_row else 0,
        "debtors_creditors_balance": 0,
    }

    # Upsert into recon_daily_stats
    await db.execute(
        text("""
            INSERT INTO recon_daily_stats (business_date, gross_sales, rooms_sold, total_people, source, updated_at)
            VALUES (:d, :gs, :rs, :tp, 'newbook_auto', NOW())
            ON CONFLICT (business_date)
            DO UPDATE SET gross_sales = :gs, rooms_sold = :rs, total_people = :tp,
                          source = 'newbook_auto', updated_at = NOW()
        """),
        {"d": stats_date, "gs": stats["gross_sales"], "rs": stats["rooms_sold"], "tp": stats["total_people"]}
    )
    await db.commit()

    return stats


# ============================================
# MULTI-DAY REPORT
# ============================================

@router.get("/reports/multi-day")
async def generate_multi_day_report(
    start_date: str = Query(...),
    num_days: int = Query(7, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Generate multi-day reconciliation report with 3 tables."""
    from datetime import timedelta

    try:
        start = date.fromisoformat(start_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    end = start + timedelta(days=num_days - 1)

    # Fetch cash-ups for range
    cu_result = await db.execute(
        text("""
            SELECT c.* FROM recon_cash_ups c
            WHERE c.session_date BETWEEN :start AND :end
            ORDER BY c.session_date ASC
        """),
        {"start": start.isoformat(), "end": end.isoformat()}
    )
    cash_up_rows = cu_result.fetchall()

    # Build cash-up dicts with card machines
    cash_ups = []
    for cu in cash_up_rows:
        cards_result = await db.execute(
            text("SELECT * FROM recon_card_machines WHERE cash_up_id = :id"),
            {"id": cu.id}
        )
        card_machines = [
            {"machine_name": c.machine_name, "total_amount": float(c.total_amount),
             "amex_amount": float(c.amex_amount), "visa_mc_amount": float(c.visa_mc_amount)}
            for c in cards_result.fetchall()
        ]
        cash_ups.append({
            "session_date": cu.session_date.isoformat(),
            "status": cu.status,
            "total_float_counted": float(cu.total_float_counted or 0),
            "total_cash_counted": float(cu.total_cash_counted or 0),
            "card_machines": card_machines,
        })

    # Fetch stored payment totals by date from recon_payment_records
    payment_totals_by_date = {}
    pr_result = await db.execute(
        text("""
            SELECT payment_date::date as pdate, card_type, transaction_method,
                   SUM(amount) as total
            FROM recon_payment_records
            WHERE payment_date::date BETWEEN :start AND :end
            GROUP BY payment_date::date, card_type, transaction_method
        """),
        {"start": start.isoformat(), "end": end.isoformat()}
    )
    for row in pr_result.fetchall():
        d = row.pdate.isoformat()
        if d not in payment_totals_by_date:
            payment_totals_by_date[d] = {
                'cash': 0, 'manual_visa_mc': 0, 'manual_amex': 0,
                'gateway_visa_mc': 0, 'gateway_amex': 0, 'bacs': 0
            }
        card_type = row.card_type or ''
        tm = (row.transaction_method or '').lower()
        amount = float(row.total or 0)

        if card_type == 'cash':
            payment_totals_by_date[d]['cash'] += amount
        elif card_type == 'bacs':
            payment_totals_by_date[d]['bacs'] += amount
        elif tm == 'manual':
            if card_type == 'amex':
                payment_totals_by_date[d]['manual_amex'] += amount
            elif card_type == 'visa_mc':
                payment_totals_by_date[d]['manual_visa_mc'] += amount
        elif tm in ('automated', 'gateway', 'cc_gateway'):
            if card_type == 'amex':
                payment_totals_by_date[d]['gateway_amex'] += amount
            elif card_type == 'visa_mc':
                payment_totals_by_date[d]['gateway_visa_mc'] += amount

    # Fetch daily stats
    ds_result = await db.execute(
        text("""
            SELECT * FROM recon_daily_stats
            WHERE business_date BETWEEN :start AND :end
            ORDER BY business_date ASC
        """),
        {"start": start.isoformat(), "end": end.isoformat()}
    )
    daily_stats = [
        {
            "business_date": s.business_date.isoformat(),
            "gross_sales": float(s.gross_sales or 0),
            "rooms_sold": s.rooms_sold or 0,
            "total_people": s.total_people or 0,
            "debtors_creditors_balance": float(s.debtors_creditors_balance or 0),
        }
        for s in ds_result.fetchall()
    ]

    # Fetch sales breakdown
    sb_result = await db.execute(
        text("""
            SELECT * FROM recon_sales_breakdown
            WHERE business_date BETWEEN :start AND :end
            ORDER BY business_date ASC, category ASC
        """),
        {"start": start.isoformat(), "end": end.isoformat()}
    )
    sales_breakdown = [
        {
            "business_date": s.business_date.isoformat(),
            "category": s.category,
            "net_amount": float(s.net_amount or 0),
        }
        for s in sb_result.fetchall()
    ]

    report = build_multi_day_report(cash_ups, payment_totals_by_date, daily_stats, sales_breakdown)
    return report


# ============================================
# FLOAT COUNTS (Petty Cash, Change Tin, Safe Cash)
# ============================================

@router.get("/float-counts")
async def list_float_counts(
    count_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List float counts with filters."""
    conditions = []
    params = {}

    if count_type:
        conditions.append("f.count_type = :count_type")
        params["count_type"] = count_type
    if date_from:
        conditions.append("f.count_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        conditions.append("f.count_date <= :date_to")
        params["date_to"] = date_to + " 23:59:59"

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * per_page
    params["limit"] = per_page
    params["offset"] = offset

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM recon_float_counts f {where}"), params
    )
    total = count_result.scalar()

    result = await db.execute(
        text(f"""
            SELECT f.*, u.display_name as created_by_name
            FROM recon_float_counts f
            LEFT JOIN users u ON f.created_by = u.id
            {where}
            ORDER BY f.count_date DESC
            LIMIT :limit OFFSET :offset
        """), params
    )
    rows = result.fetchall()

    float_counts = []
    for row in rows:
        float_counts.append({
            "id": row.id,
            "count_type": row.count_type,
            "count_date": row.count_date.isoformat() if row.count_date else None,
            "total_counted": float(row.total_counted or 0),
            "total_receipts": float(row.total_receipts or 0),
            "target_amount": float(row.target_amount or 0),
            "variance": float(row.variance or 0),
            "notes": row.notes,
            "created_by_name": row.created_by_name,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })

    return {"float_counts": float_counts, "total": total, "page": page, "per_page": per_page}


@router.get("/float-counts/{count_id}")
async def get_float_count(
    count_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get float count with denominations and receipts."""
    result = await db.execute(
        text("SELECT f.*, u.display_name as created_by_name FROM recon_float_counts f LEFT JOIN users u ON f.created_by = u.id WHERE f.id = :id"),
        {"id": count_id}
    )
    fc = result.fetchone()
    if not fc:
        raise HTTPException(status_code=404, detail="Float count not found")

    denom_result = await db.execute(
        text("SELECT * FROM recon_float_denominations WHERE float_count_id = :id ORDER BY denomination_value DESC"),
        {"id": count_id}
    )
    denominations = [
        {"denomination_value": float(d.denomination_value), "quantity": d.quantity, "total_amount": float(d.total_amount)}
        for d in denom_result.fetchall()
    ]

    receipt_result = await db.execute(
        text("SELECT * FROM recon_float_receipts WHERE float_count_id = :id"),
        {"id": count_id}
    )
    receipts = [
        {"id": r.id, "receipt_value": float(r.receipt_value), "receipt_description": r.receipt_description}
        for r in receipt_result.fetchall()
    ]

    return {
        "float_count": {
            "id": fc.id,
            "count_type": fc.count_type,
            "count_date": fc.count_date.isoformat() if fc.count_date else None,
            "total_counted": float(fc.total_counted or 0),
            "total_receipts": float(fc.total_receipts or 0),
            "target_amount": float(fc.target_amount or 0),
            "variance": float(fc.variance or 0),
            "notes": fc.notes,
            "created_by_name": fc.created_by_name,
        },
        "denominations": denominations,
        "receipts": receipts,
    }


@router.post("/float-counts")
async def create_float_count(
    data: FloatCountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new float count."""
    count_date = data.count_date or datetime.now().isoformat()

    result = await db.execute(
        text("""
            INSERT INTO recon_float_counts
            (count_type, count_date, created_by, total_counted, total_receipts, target_amount, variance, notes)
            VALUES (:ct, :cd, :cb, :tc, :tr, :ta, :var, :notes)
            RETURNING id
        """),
        {
            "ct": data.count_type,
            "cd": count_date,
            "cb": current_user["id"],
            "tc": data.total_counted,
            "tr": data.total_receipts,
            "ta": data.target_amount,
            "var": data.variance,
            "notes": data.notes,
        }
    )
    fc_id = result.fetchone().id

    # Insert denominations
    for d in data.denominations:
        await db.execute(
            text("""
                INSERT INTO recon_float_denominations (float_count_id, denomination_value, quantity, total_amount)
                VALUES (:fid, :dv, :q, :ta)
            """),
            {"fid": fc_id, "dv": d.denomination_value, "q": d.quantity, "ta": d.total_amount}
        )

    # Insert receipts
    for r in data.receipts:
        await db.execute(
            text("""
                INSERT INTO recon_float_receipts (float_count_id, receipt_value, receipt_description)
                VALUES (:fid, :rv, :rd)
            """),
            {"fid": fc_id, "rv": r.receipt_value, "rd": r.receipt_description}
        )

    await db.commit()
    return {"id": fc_id, "message": "Float count saved"}


@router.put("/float-counts/{count_id}")
async def update_float_count(
    count_id: int,
    data: FloatCountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update a float count."""
    existing = await db.execute(
        text("SELECT id FROM recon_float_counts WHERE id = :id"),
        {"id": count_id}
    )
    if not existing.fetchone():
        raise HTTPException(status_code=404, detail="Float count not found")

    await db.execute(
        text("""
            UPDATE recon_float_counts
            SET total_counted = :tc, total_receipts = :tr, target_amount = :ta,
                variance = :var, notes = :notes
            WHERE id = :id
        """),
        {
            "id": count_id,
            "tc": data.total_counted,
            "tr": data.total_receipts,
            "ta": data.target_amount,
            "var": data.variance,
            "notes": data.notes,
        }
    )

    # Replace denominations
    await db.execute(text("DELETE FROM recon_float_denominations WHERE float_count_id = :id"), {"id": count_id})
    for d in data.denominations:
        await db.execute(
            text("INSERT INTO recon_float_denominations (float_count_id, denomination_value, quantity, total_amount) VALUES (:fid, :dv, :q, :ta)"),
            {"fid": count_id, "dv": d.denomination_value, "q": d.quantity, "ta": d.total_amount}
        )

    # Replace receipts
    await db.execute(text("DELETE FROM recon_float_receipts WHERE float_count_id = :id"), {"id": count_id})
    for r in data.receipts:
        await db.execute(
            text("INSERT INTO recon_float_receipts (float_count_id, receipt_value, receipt_description) VALUES (:fid, :rv, :rd)"),
            {"fid": count_id, "rv": r.receipt_value, "rd": r.receipt_description}
        )

    await db.commit()
    return {"message": "Float count updated", "id": count_id}


@router.delete("/float-counts/{count_id}")
async def delete_float_count(
    count_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete a float count."""
    existing = await db.execute(
        text("SELECT id FROM recon_float_counts WHERE id = :id"),
        {"id": count_id}
    )
    if not existing.fetchone():
        raise HTTPException(status_code=404, detail="Float count not found")

    await db.execute(text("DELETE FROM recon_float_counts WHERE id = :id"), {"id": count_id})
    await db.commit()
    return {"message": "Float count deleted"}


# ============================================
# ATTACHMENTS
# ============================================

@router.post("/cash-ups/{cash_up_id}/attachments")
async def upload_attachment(
    cash_up_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Upload an attachment to a cash-up."""
    # Verify cash-up exists
    existing = await db.execute(
        text("SELECT id FROM recon_cash_ups WHERE id = :id"),
        {"id": cash_up_id}
    )
    if not existing.fetchone():
        raise HTTPException(status_code=404, detail="Cash-up not found")

    # Validate file type
    allowed_types = ['image/jpeg', 'image/png', 'application/pdf']
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"File type not allowed. Use JPEG, PNG, or PDF.")

    # Read file and check size (5MB max)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum 5MB.")

    # Save file
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{cash_up_id}_{timestamp}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)

    with open(file_path, "wb") as f:
        f.write(contents)

    # Insert record
    result = await db.execute(
        text("""
            INSERT INTO recon_attachments (cash_up_id, file_name, file_path, file_type, file_size, uploaded_by)
            VALUES (:cid, :fn, :fp, :ft, :fs, :ub)
            RETURNING id, file_name, uploaded_at
        """),
        {
            "cid": cash_up_id,
            "fn": file.filename,
            "fp": file_path,
            "ft": file.content_type,
            "fs": len(contents),
            "ub": current_user["id"],
        }
    )
    await db.commit()
    row = result.fetchone()

    return {
        "id": row.id,
        "file_name": row.file_name,
        "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
    }


@router.delete("/attachments/{attachment_id}")
async def delete_attachment(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete an attachment."""
    result = await db.execute(
        text("SELECT id, file_path FROM recon_attachments WHERE id = :id"),
        {"id": attachment_id}
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Delete file
    if os.path.exists(row.file_path):
        os.remove(row.file_path)

    await db.execute(text("DELETE FROM recon_attachments WHERE id = :id"), {"id": attachment_id})
    await db.commit()
    return {"message": "Attachment deleted"}


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Download an attachment file."""
    result = await db.execute(
        text("SELECT file_name, file_path, file_type FROM recon_attachments WHERE id = :id"),
        {"id": attachment_id}
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if not os.path.exists(row.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=row.file_path,
        filename=row.file_name,
        media_type=row.file_type
    )


# ============================================
# RECONCILIATION SETTINGS
# ============================================

@router.get("/settings")
async def get_recon_settings(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all reconciliation settings from system_config."""
    result = await db.execute(
        text("SELECT config_key, config_value FROM system_config WHERE config_key LIKE 'recon_%'")
    )
    rows = result.fetchall()

    settings = {}
    for row in rows:
        key = row.config_key.replace('recon_', '', 1)
        value = row.config_value
        # Try to parse JSON values
        if value and value.startswith('{') or value and value.startswith('['):
            import json
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass
        settings[key] = value

    return settings


@router.post("/settings")
async def update_recon_settings(
    data: ReconSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_admin_user)
):
    """Update reconciliation settings (admin only)."""
    import json

    updates = {}
    if data.expected_till_float is not None:
        updates['recon_expected_till_float'] = str(data.expected_till_float)
    if data.variance_threshold is not None:
        updates['recon_variance_threshold'] = str(data.variance_threshold)
    if data.default_report_days is not None:
        updates['recon_default_report_days'] = str(data.default_report_days)
    if data.petty_cash_target is not None:
        updates['recon_petty_cash_target'] = str(data.petty_cash_target)
    if data.change_tin_breakdown is not None:
        updates['recon_change_tin_breakdown'] = json.dumps(data.change_tin_breakdown)
    if data.safe_cash_target is not None:
        updates['recon_safe_cash_target'] = str(data.safe_cash_target)
    if data.sales_breakdown_columns is not None:
        updates['recon_sales_breakdown_columns'] = json.dumps(data.sales_breakdown_columns)
    if data.denominations is not None:
        updates['recon_denominations'] = json.dumps(data.denominations)

    for key, value in updates.items():
        await db.execute(
            text("""
                UPDATE system_config SET config_value = :val, updated_at = NOW(), updated_by = :user
                WHERE config_key = :key
            """),
            {"key": key, "val": value, "user": current_user["username"]}
        )

    await db.commit()
    return {"message": "Settings updated", "updated_keys": list(updates.keys())}


@router.post("/settings/refresh-gl-accounts")
async def refresh_gl_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_admin_user)
):
    """Fetch GL accounts from Newbook and return for column configuration."""
    from services.newbook_client import NewbookClient

    try:
        async with await NewbookClient.from_db(db) as client:
            gl_accounts = await client.get_gl_account_list()
    except Exception as e:
        logger.error(f"Failed to fetch GL accounts: {e}")
        raise HTTPException(status_code=502, detail=f"Newbook API error: {str(e)}")

    return {"gl_accounts": gl_accounts}
