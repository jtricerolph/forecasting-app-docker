"""
Bookability API endpoints
Rate availability matrix and competitor rate comparison
"""
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
import logging
import json

from database import get_db, SyncSessionLocal
from auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================
# RESPONSE MODELS
# ============================================

class CategoryInfo(BaseModel):
    category_id: str
    category_name: str
    room_count: int


class TariffInfo(BaseModel):
    name: str
    description: Optional[str] = None
    rate: Optional[float] = None
    average_nightly: Optional[float] = None
    available: bool
    message: str
    sort_order: int = 999
    min_stay: Optional[int] = None
    available_for_min_stay: Optional[bool] = None  # True if available when queried with min_stay nights


class OccupancyInfo(BaseModel):
    occupied: int = 0
    available: int = 0
    maintenance: int = 0


class DateRateInfo(BaseModel):
    rate_gross: Optional[float] = None
    rate_net: Optional[float] = None
    tariffs: List[TariffInfo]
    tariff_count: int
    occupancy: Optional[OccupancyInfo] = None


class RateMatrixResponse(BaseModel):
    categories: List[CategoryInfo]
    dates: List[str]
    matrix: Dict[str, Dict[str, DateRateInfo]]


# ============================================
# RATE MATRIX ENDPOINT
# ============================================

@router.get("/rate-matrix", response_model=RateMatrixResponse)
async def get_rate_matrix(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    category_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get rate availability matrix for all tariffs across dates and categories.

    Returns a matrix showing all available tariff options for each room category
    and date combination, including availability status and rates.

    Args:
        from_date: Start date (YYYY-MM-DD), defaults to today
        to_date: End date (YYYY-MM-DD), defaults to today + 30 days
        category_id: Optional filter to specific category

    Returns:
        RateMatrixResponse with categories, dates, and the matrix data
    """
    # Default date range
    today = date.today()
    start = date.fromisoformat(from_date) if from_date else today
    end = date.fromisoformat(to_date) if to_date else today + timedelta(days=30)

    # Validate date range
    if end < start:
        raise HTTPException(status_code=400, detail="to_date must be after from_date")
    if (end - start).days > 366:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 366 days")

    # Fetch categories
    cat_query = """
        SELECT site_id, site_name, room_count
        FROM newbook_room_categories
        WHERE is_included = true
    """
    params: Dict[str, Any] = {}

    if category_id:
        cat_query += " AND site_id = :category_id"
        params["category_id"] = category_id

    cat_query += " ORDER BY display_order, site_name"

    cat_result = await db.execute(text(cat_query), params)
    categories = [
        CategoryInfo(
            category_id=row.site_id,
            category_name=row.site_name,
            room_count=row.room_count or 0
        )
        for row in cat_result.fetchall()
    ]

    if not categories:
        return RateMatrixResponse(categories=[], dates=[], matrix={})

    # Build date list
    dates = []
    current = start
    while current <= end:
        dates.append(current.isoformat())
        current += timedelta(days=1)

    # Fetch rates with tariffs_data (get latest version per category/date)
    rates_query = """
        SELECT DISTINCT ON (category_id, rate_date)
            category_id, rate_date, rate_gross, rate_net, tariffs_data, valid_from
        FROM newbook_current_rates
        WHERE rate_date >= :from_date AND rate_date <= :to_date
    """
    rates_params: Dict[str, Any] = {"from_date": start, "to_date": end}

    if category_id:
        rates_query += " AND category_id = :category_id"
        rates_params["category_id"] = category_id

    rates_query += " ORDER BY category_id, rate_date, valid_from DESC"

    rates_result = await db.execute(text(rates_query), rates_params)
    rates_rows = rates_result.fetchall()

    # Fetch occupancy data from newbook_occupancy_report_data
    occupancy_query = """
        SELECT category_id, date, occupied, available, maintenance
        FROM newbook_occupancy_report_data
        WHERE date >= :from_date AND date <= :to_date
    """
    occupancy_params: Dict[str, Any] = {"from_date": start, "to_date": end}

    if category_id:
        occupancy_query += " AND category_id = :category_id"
        occupancy_params["category_id"] = category_id

    occupancy_result = await db.execute(text(occupancy_query), occupancy_params)
    occupancy_rows = occupancy_result.fetchall()

    # Build occupancy lookup: category_id -> date -> OccupancyInfo
    occupancy_map: Dict[str, Dict[str, OccupancyInfo]] = {}
    for row in occupancy_rows:
        cat_id = row.category_id
        occ_date = row.date.isoformat()
        if cat_id not in occupancy_map:
            occupancy_map[cat_id] = {}
        occupancy_map[cat_id][occ_date] = OccupancyInfo(
            occupied=row.occupied or 0,
            available=row.available or 0,
            maintenance=row.maintenance or 0
        )

    # Build matrix
    matrix: Dict[str, Dict[str, DateRateInfo]] = {}

    # Initialize matrix with empty data for all categories and dates
    for cat in categories:
        matrix[cat.category_id] = {}
        for date_str in dates:
            # Get occupancy for this category/date if available
            occ = occupancy_map.get(cat.category_id, {}).get(date_str)
            matrix[cat.category_id][date_str] = DateRateInfo(
                rate_gross=None,
                rate_net=None,
                tariffs=[],
                tariff_count=0,
                occupancy=occ
            )

    # Populate matrix with actual data
    for row in rates_rows:
        cat_id = row.category_id
        rate_date = row.rate_date.isoformat()

        if cat_id not in matrix or rate_date not in matrix[cat_id]:
            continue

        # Parse tariffs_data
        tariffs_data = row.tariffs_data or {}
        if isinstance(tariffs_data, str):
            try:
                tariffs_data = json.loads(tariffs_data)
            except json.JSONDecodeError:
                tariffs_data = {}

        # Build tariff list
        tariffs_list = []
        raw_tariffs = tariffs_data.get('tariffs', [])

        for idx, tariff in enumerate(raw_tariffs):
            tariffs_list.append(TariffInfo(
                name=tariff.get('name', 'Unknown'),
                description=tariff.get('description'),
                rate=tariff.get('rate'),
                average_nightly=tariff.get('average_nightly'),
                available=tariff.get('success', False),
                message=tariff.get('message', ''),
                sort_order=tariff.get('sort_order', idx),
                min_stay=tariff.get('min_stay'),
                available_for_min_stay=tariff.get('available_for_min_stay')
            ))

        # Preserve existing occupancy data
        existing_occ = matrix[cat_id][rate_date].occupancy

        matrix[cat_id][rate_date] = DateRateInfo(
            rate_gross=float(row.rate_gross) if row.rate_gross else None,
            rate_net=float(row.rate_net) if row.rate_net else None,
            tariffs=tariffs_list,
            tariff_count=tariffs_data.get('tariff_count', len(tariffs_list)),
            occupancy=existing_occ
        )

    return RateMatrixResponse(
        categories=categories,
        dates=dates,
        matrix=matrix
    )


# ============================================
# RATE MATRIX SUMMARY (lightweight endpoint)
# ============================================

@router.get("/rate-matrix/summary")
async def get_rate_matrix_summary(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a summary of rate availability issues.

    Returns counts of unavailable tariffs by category and date for quick
    identification of potential bookability problems.
    """
    today = date.today()
    start = date.fromisoformat(from_date) if from_date else today
    end = date.fromisoformat(to_date) if to_date else today + timedelta(days=30)

    # Query rates with issues (get latest version per category/date)
    result = await db.execute(
        text("""
            SELECT DISTINCT ON (category_id, rate_date)
                category_id,
                rate_date,
                tariffs_data
            FROM newbook_current_rates
            WHERE rate_date >= :from_date AND rate_date <= :to_date
            AND tariffs_data IS NOT NULL
            ORDER BY category_id, rate_date, valid_from DESC
        """),
        {"from_date": start, "to_date": end}
    )

    issues = []
    for row in result.fetchall():
        tariffs_data = row.tariffs_data or {}
        if isinstance(tariffs_data, str):
            try:
                tariffs_data = json.loads(tariffs_data)
            except json.JSONDecodeError:
                continue

        tariffs = tariffs_data.get('tariffs', [])
        unavailable = [t for t in tariffs if not t.get('success', False)]

        if unavailable:
            issues.append({
                "category_id": row.category_id,
                "date": row.rate_date.isoformat(),
                "unavailable_count": len(unavailable),
                "unavailable_tariffs": [t.get('name') for t in unavailable],
                "messages": [t.get('message') for t in unavailable if t.get('message')]
            })

    return {
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "total_issues": len(issues),
        "issues": issues
    }


# ============================================
# RATE HISTORY ENDPOINT
# ============================================

@router.get("/rate-history/{category_id}/{rate_date}")
async def get_rate_history(
    category_id: str,
    rate_date: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get rate change history for a specific category and date.

    Returns all rate snapshots showing how rates evolved over time.
    Useful for understanding when rates changed and by how much.
    """
    try:
        target_date = date.fromisoformat(rate_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    result = await db.execute(
        text("""
            SELECT
                id,
                rate_gross,
                rate_net,
                tariffs_data,
                valid_from,
                last_verified_at
            FROM newbook_current_rates
            WHERE category_id = :category_id AND rate_date = :rate_date
            ORDER BY valid_from DESC
        """),
        {"category_id": category_id, "rate_date": target_date}
    )

    history = []
    for row in result.fetchall():
        tariffs_data = row.tariffs_data or {}
        if isinstance(tariffs_data, str):
            try:
                tariffs_data = json.loads(tariffs_data)
            except json.JSONDecodeError:
                tariffs_data = {}

        tariffs = tariffs_data.get('tariffs', [])

        history.append({
            "id": row.id,
            "rate_gross": float(row.rate_gross) if row.rate_gross else None,
            "rate_net": float(row.rate_net) if row.rate_net else None,
            "valid_from": row.valid_from.isoformat() if row.valid_from else None,
            "last_verified_at": row.last_verified_at.isoformat() if row.last_verified_at else None,
            "tariff_count": len(tariffs),
            "tariffs_available": sum(1 for t in tariffs if t.get('success', False)),
            "tariffs_unavailable": sum(1 for t in tariffs if not t.get('success', False)),
            "tariffs": [
                {
                    "name": t.get('name'),
                    "rate": t.get('rate'),
                    "available": t.get('success', False),
                    "message": t.get('message', ''),
                    "min_stay": t.get('min_stay')
                }
                for t in tariffs
            ]
        })

    return {
        "category_id": category_id,
        "rate_date": rate_date,
        "version_count": len(history),
        "history": history
    }


# ============================================
# RATE CHANGES SUMMARY
# ============================================

@router.get("/rate-changes")
async def get_rate_changes(
    days: int = 7,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get summary of rate changes in the last N days.

    Shows which rates changed and when, useful for tracking pricing strategy changes.
    """
    cutoff = datetime.now() - timedelta(days=days)

    # Find dates with multiple versions (indicating changes)
    result = await db.execute(
        text("""
            SELECT
                category_id,
                rate_date,
                COUNT(*) as version_count,
                MIN(valid_from) as first_version,
                MAX(valid_from) as latest_version
            FROM newbook_current_rates
            WHERE valid_from >= :cutoff
            GROUP BY category_id, rate_date
            HAVING COUNT(*) > 1
            ORDER BY MAX(valid_from) DESC
            LIMIT 100
        """),
        {"cutoff": cutoff}
    )

    changes = []
    for row in result.fetchall():
        changes.append({
            "category_id": row.category_id,
            "rate_date": row.rate_date.isoformat(),
            "version_count": row.version_count,
            "first_version": row.first_version.isoformat() if row.first_version else None,
            "latest_version": row.latest_version.isoformat() if row.latest_version else None
        })

    return {
        "days": days,
        "total_changes": len(changes),
        "changes": changes
    }


# ============================================
# FETCH RATES TRIGGER (manual refresh)
# ============================================

@router.post("/refresh-rates")
async def refresh_rates(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    category_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger a manual refresh of current rates from Newbook.

    This runs the rate fetch job for the specified date range.
    Note: This can be slow as it respects Newbook API rate limits.
    """
    from jobs.fetch_current_rates import run_fetch_current_rates

    # For now, just run the standard fetch
    # TODO: Add support for custom date range and category filter
    try:
        await run_fetch_current_rates()
        return {"status": "success", "message": "Rates refresh completed"}
    except Exception as e:
        logger.error(f"Rates refresh failed: {e}")
        raise HTTPException(status_code=500, detail=f"Rates refresh failed: {str(e)}")


# ============================================
# SINGLE-DATE RATE REFRESH
# ============================================

def _refresh_date_sync(rate_date: date):
    """
    Fetch rates for a single date from Newbook and save to DB.
    Runs synchronously in a background task.
    """
    import asyncio
    from decimal import Decimal
    from services.newbook_rates_client import NewbookRatesClient
    from jobs.fetch_current_rates import save_rate_snapshot

    db = SyncSessionLocal()
    try:
        # Get config
        config_result = db.execute(
            text("""
                SELECT config_key, config_value FROM system_config
                WHERE config_key IN ('newbook_api_key', 'newbook_username', 'newbook_password', 'newbook_region', 'accommodation_vat_rate')
            """)
        )
        config = {row.config_key: row.config_value for row in config_result.fetchall()}

        if not all(k in config for k in ['newbook_api_key', 'newbook_username', 'newbook_password', 'newbook_region']):
            logger.error("Newbook credentials not configured for single-date refresh")
            return

        vat_rate = Decimal(config.get('accommodation_vat_rate', '0.20'))

        # Get included categories
        cat_result = db.execute(
            text("SELECT site_id FROM newbook_room_categories WHERE is_included = true")
        )
        included_categories = set(row.site_id for row in cat_result.fetchall())

        client = NewbookRatesClient(
            api_key=config['newbook_api_key'],
            username=config['newbook_username'],
            password=config['newbook_password'],
            region=config['newbook_region'],
            vat_rate=vat_rate
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def _fetch():
                async with client:
                    # Single-night query for this date (all categories)
                    category_rates = await client._fetch_all_categories_batch(
                        rate_date, guests_adults=2, guests_children=0
                    )

                    # Check for min_stay tariffs needing multi-night verification
                    dates_by_nights: Dict[int, list] = {}
                    for cat_id, rates in category_rates.items():
                        if cat_id not in included_categories:
                            continue
                        for rate in rates:
                            for tariff in rate.get('tariffs_data', {}).get('tariffs', []):
                                min_stay = tariff.get('min_stay')
                                if min_stay and min_stay > 1 and not tariff.get('success', False):
                                    if min_stay not in dates_by_nights:
                                        dates_by_nights[min_stay] = []
                                    if rate_date not in dates_by_nights[min_stay]:
                                        dates_by_nights[min_stay].append(rate_date)

                    # Run multi-night verification if needed
                    if dates_by_nights:
                        multi_results = await client.get_multi_night_availability(dates_by_nights)
                        for cat_id, rates in category_rates.items():
                            if cat_id not in included_categories:
                                continue
                            for rate in rates:
                                if rate_date in multi_results:
                                    cat_avail = multi_results[rate_date].get(cat_id, {})
                                    for tariff in rate.get('tariffs_data', {}).get('tariffs', []):
                                        if tariff.get('min_stay') and tariff['min_stay'] > 1:
                                            tariff['available_for_min_stay'] = cat_avail.get(tariff.get('name', ''), False)

                    # Save snapshots
                    inserted = 0
                    for cat_id, rates in category_rates.items():
                        if cat_id not in included_categories:
                            continue
                        for rate in rates:
                            result = save_rate_snapshot(db, cat_id, rate['date'], rate)
                            if result == 'inserted':
                                inserted += 1

                    return inserted

            inserted = loop.run_until_complete(_fetch())
            db.commit()
            logger.info(f"Single-date refresh for {rate_date}: {inserted} new snapshots")

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Single-date refresh failed for {rate_date}: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


@router.post("/refresh-date/{rate_date}")
async def refresh_single_date(
    rate_date: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger a refresh of rates for a single date from Newbook.
    Runs in background - returns immediately.
    """
    try:
        target_date = date.fromisoformat(rate_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    background_tasks.add_task(_refresh_date_sync, target_date)
    return {"status": "queued", "date": rate_date, "message": f"Refreshing rates for {rate_date}"}
