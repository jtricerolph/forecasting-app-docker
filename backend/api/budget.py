"""
Budget API endpoints
"""
import io
import re
import logging
from datetime import date, datetime
from typing import Optional, List

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from database import get_db
from auth import get_current_user

logger = logging.getLogger(__name__)

# Mapping from spreadsheet row labels to budget_type values
BUDGET_TYPE_MAPPING = {
    'accom': 'net_accom',
    'accommodation': 'net_accom',
    'acc': 'net_accom',
    'dry': 'net_dry',
    'food': 'net_dry',
    'wet': 'net_wet',
    'beverage': 'net_wet',
    'beverages': 'net_wet',
}

router = APIRouter()


class MonthlyBudgetCreate(BaseModel):
    year: int
    month: int
    budget_type: str
    budget_value: float
    notes: Optional[str] = None


class MonthlyBudgetResponse(BaseModel):
    id: int
    year: int
    month: int
    budget_type: str
    budget_value: float
    notes: Optional[str]


@router.get("/monthly")
async def get_monthly_budgets(
    year: int = Query(..., description="Year to get budgets for"),
    budget_type: Optional[str] = Query(None, description="Filter by budget type"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get monthly budgets for a year.
    """
    query = """
        SELECT id, year, month, budget_type, budget_value, notes, created_at, updated_at
        FROM monthly_budgets
        WHERE year = :year
    """
    params = {"year": year}

    if budget_type:
        query += " AND budget_type = :budget_type"
        params["budget_type"] = budget_type

    query += " ORDER BY month, budget_type"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "id": row.id,
            "year": row.year,
            "month": row.month,
            "budget_type": row.budget_type,
            "budget_value": float(row.budget_value),
            "notes": row.notes,
            "created_at": row.created_at,
            "updated_at": row.updated_at
        }
        for row in rows
    ]


@router.post("/monthly")
async def create_or_update_monthly_budget(
    budget: MonthlyBudgetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create or update a monthly budget.
    """
    query = """
        INSERT INTO monthly_budgets (year, month, budget_type, budget_value, notes, updated_at)
        VALUES (:year, :month, :budget_type, :budget_value, :notes, NOW())
        ON CONFLICT (year, month, budget_type)
        DO UPDATE SET budget_value = :budget_value, notes = :notes, updated_at = NOW()
        RETURNING id
    """

    result = await db.execute(text(query), {
        "year": budget.year,
        "month": budget.month,
        "budget_type": budget.budget_type,
        "budget_value": budget.budget_value,
        "notes": budget.notes
    })
    await db.commit()

    row = result.fetchone()
    return {"id": row.id, "status": "saved", **budget.model_dump()}


@router.get("/daily")
async def get_daily_budgets(
    from_date: date = Query(...),
    to_date: date = Query(...),
    budget_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get daily distributed budgets for a date range.
    """
    query = """
        SELECT
            date,
            budget_type,
            budget_value,
            distribution_method,
            prior_year_pct
        FROM daily_budgets
        WHERE date BETWEEN :from_date AND :to_date
    """
    params = {"from_date": from_date, "to_date": to_date}

    if budget_type:
        query += " AND budget_type = :budget_type"
        params["budget_type"] = budget_type

    query += " ORDER BY date, budget_type"

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "date": row.date,
            "budget_type": row.budget_type,
            "budget_value": float(row.budget_value),
            "distribution_method": row.distribution_method,
            "prior_year_pct": float(row.prior_year_pct) if row.prior_year_pct else None
        }
        for row in rows
    ]


@router.post("/distribute")
async def distribute_monthly_budget(
    year: int = Query(...),
    month: int = Query(...),
    budget_type: Optional[str] = Query(None, description="Budget type to distribute, or all if not specified"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Distribute monthly budget to daily values using prior year patterns.
    """
    from services.forecasting.budget_service import distribute_budget

    result = await distribute_budget(db, year, month, budget_type)

    return {
        "status": "distributed",
        "year": year,
        "month": month,
        "budget_type": budget_type or "all",
        "days_distributed": result.get("days_distributed", 0)
    }


@router.get("/variance")
async def get_budget_variance(
    from_date: date = Query(...),
    to_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get forecast vs budget vs actual variance for date range.
    """
    query = """
        SELECT
            db.date,
            db.budget_type,
            db.budget_value,
            f.predicted_value as forecast_value,
            dm.actual_value,
            (f.predicted_value - db.budget_value) as forecast_vs_budget,
            CASE WHEN db.budget_value != 0 THEN
                ROUND(((f.predicted_value - db.budget_value) / db.budget_value * 100)::numeric, 2)
            END as forecast_vs_budget_pct,
            CASE WHEN dm.actual_value IS NOT NULL THEN
                (dm.actual_value - db.budget_value)
            END as actual_vs_budget,
            CASE WHEN dm.actual_value IS NOT NULL AND db.budget_value != 0 THEN
                ROUND(((dm.actual_value - db.budget_value) / db.budget_value * 100)::numeric, 2)
            END as actual_vs_budget_pct
        FROM daily_budgets db
        LEFT JOIN forecasts f ON db.date = f.forecast_date
            AND db.budget_type = f.forecast_type
            AND f.model_type = 'prophet'
        LEFT JOIN daily_metrics dm ON db.date = dm.date
            AND db.budget_type = dm.metric_code
        WHERE db.date BETWEEN :from_date AND :to_date
        ORDER BY db.date, db.budget_type
    """

    result = await db.execute(text(query), {"from_date": from_date, "to_date": to_date})
    rows = result.fetchall()

    return [
        {
            "date": row.date,
            "budget_type": row.budget_type,
            "budget": float(row.budget_value) if row.budget_value else None,
            "forecast": float(row.forecast_value) if row.forecast_value else None,
            "actual": float(row.actual_value) if row.actual_value else None,
            "forecast_vs_budget": float(row.forecast_vs_budget) if row.forecast_vs_budget else None,
            "forecast_vs_budget_pct": float(row.forecast_vs_budget_pct) if row.forecast_vs_budget_pct else None,
            "actual_vs_budget": float(row.actual_vs_budget) if row.actual_vs_budget else None,
            "actual_vs_budget_pct": float(row.actual_vs_budget_pct) if row.actual_vs_budget_pct else None
        }
        for row in rows
    ]


def parse_month_header(header) -> Optional[tuple]:
    """
    Parse month header in various formats to (year, month).

    Supported formats:
    - datetime/Timestamp objects (from Excel date cells)
    - mm/yy (01/25, 12/26)
    - mm-yy (01-25, 12-26)
    - mmm/yy (Jan/25, Dec-26)
    - mmm yy (Jan 25, Dec 26)
    - yyyy-mm (2025-01)
    - dd/mm/yyyy or mm/dd/yyyy (will use first of month)
    - Full month names (January 2025)

    Returns None if cannot parse.
    """
    if header is None:
        return None

    # Handle pandas NaT or NaN
    if pd.isna(header):
        return None

    # Handle datetime objects (from Excel date columns)
    if isinstance(header, (datetime, date)):
        return (header.year, header.month)

    # Handle pandas Timestamp
    if hasattr(header, 'year') and hasattr(header, 'month'):
        try:
            return (int(header.year), int(header.month))
        except (ValueError, TypeError):
            pass

    # Convert to string for text parsing
    if not isinstance(header, str):
        header = str(header)

    header = header.strip()
    if not header:
        return None

    # Try mm/yy or mm-yy format
    match = re.match(r'^(\d{1,2})[/\-](\d{2,4})$', header)
    if match:
        month = int(match.group(1))
        year = int(match.group(2))
        if year < 100:
            year = 2000 + year if year < 50 else 1900 + year
        if 1 <= month <= 12:
            return (year, month)

    # Try yyyy-mm format
    match = re.match(r'^(\d{4})[/\-](\d{1,2})$', header)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        if 1 <= month <= 12:
            return (year, month)

    # Try dd/mm/yyyy or yyyy-mm-dd format (use year/month, ignore day)
    match = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$', header)
    if match:
        # Assume dd/mm/yyyy
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        if 1 <= month <= 12:
            return (year, month)

    match = re.match(r'^(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})$', header)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        if 1 <= month <= 12:
            return (year, month)

    # Try month name formats (Jan/25, Jan-25, Jan 25, Jan25)
    month_names = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    match = re.match(r'^([a-zA-Z]+)[/\-\s]?(\d{2,4})$', header, re.IGNORECASE)
    if match:
        month_str = match.group(1).lower()
        year = int(match.group(2))
        if year < 100:
            year = 2000 + year if year < 50 else 1900 + year
        if month_str in month_names:
            return (year, month_names[month_str])

    # Try "2025 January" or "2025-January" format
    match = re.match(r'^(\d{4})[/\-\s]?([a-zA-Z]+)$', header, re.IGNORECASE)
    if match:
        year = int(match.group(1))
        month_str = match.group(2).lower()
        if month_str in month_names:
            return (year, month_names[month_str])

    return None


def clean_numeric_value(value) -> Optional[float]:
    """
    Clean a value that might contain currency symbols, commas, etc.
    Returns None if the value cannot be converted to a number.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        # Remove currency symbols, commas, spaces
        cleaned = re.sub(r'[£$€,\s]', '', value.strip())
        if cleaned == '' or cleaned == '-':
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    return None


@router.post("/upload")
async def upload_budget_spreadsheet(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload budget spreadsheet (CSV/Excel) in format:

    month | 01/25  | 02/25  | 03/25  | ...
    accom | 150000 | 145000 | 160000 | ...
    dry   | 45000  | 42000  | 48000  | ...
    wet   | 35000  | 32000  | 38000  | ...

    Returns summary of records created/updated.
    """
    # Validate file type
    filename = file.filename.lower()
    if not (filename.endswith('.csv') or filename.endswith('.xlsx') or filename.endswith('.xls')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a CSV or Excel file (.csv, .xlsx, .xls)"
        )

    # Read file content
    content = await file.read()

    try:
        # Parse file based on type
        if filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(content), header=None)
        else:
            df = pd.read_excel(io.BytesIO(content), header=None)
    except Exception as e:
        logger.error(f"Failed to parse budget file: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

    if df.empty:
        raise HTTPException(status_code=400, detail="File is empty")

    # Parse the spreadsheet structure
    # First row should contain month headers (skip first column which is the label column)
    # Subsequent rows contain budget type label and values

    records_created = 0
    records_updated = 0
    errors = []

    # Get month headers from first row (skip first column)
    month_headers = df.iloc[0, 1:].tolist()
    parsed_months = []

    logger.info(f"Found {len(month_headers)} column headers")
    for idx, header in enumerate(month_headers):
        logger.debug(f"Header {idx}: {header} (type: {type(header).__name__})")
        parsed = parse_month_header(header)  # Pass raw value, parser handles types
        if parsed:
            parsed_months.append((idx + 1, parsed))  # Store column index and (year, month)
            logger.debug(f"  -> Parsed as {parsed[0]}-{parsed[1]:02d}")
        else:
            if header is not None and not pd.isna(header) and str(header).strip():
                errors.append(f"Could not parse month header: '{header}' (type: {type(header).__name__})")

    if not parsed_months:
        # Log what we received for debugging
        sample_headers = month_headers[:5] if len(month_headers) > 5 else month_headers
        logger.error(f"No valid month headers found. Sample headers: {sample_headers}")
        raise HTTPException(
            status_code=400,
            detail=f"No valid month headers found. Got: {sample_headers}. Expected formats: mm/yy, Jan-25, 2025-01, or Excel dates"
        )

    # Process budget rows (skip first header row)
    for row_idx in range(1, len(df)):
        row = df.iloc[row_idx]
        row_label = str(row.iloc[0]).lower().strip() if row.iloc[0] else ''

        # Map row label to budget_type
        budget_type = BUDGET_TYPE_MAPPING.get(row_label)
        if not budget_type:
            if row_label and row_label not in ['month', 'total', '']:
                errors.append(f"Unknown budget type: '{row_label}'")
            continue

        # Process each month column
        for col_idx, (year, month) in parsed_months:
            value = clean_numeric_value(row.iloc[col_idx])
            if value is None:
                continue

            # Upsert the budget value
            try:
                result = await db.execute(
                    text("""
                        INSERT INTO monthly_budgets (year, month, budget_type, budget_value, updated_at)
                        VALUES (:year, :month, :budget_type, :budget_value, NOW())
                        ON CONFLICT (year, month, budget_type)
                        DO UPDATE SET budget_value = :budget_value, updated_at = NOW()
                        RETURNING (xmax = 0) as inserted
                    """),
                    {
                        "year": year,
                        "month": month,
                        "budget_type": budget_type,
                        "budget_value": value
                    }
                )
                row_result = result.fetchone()
                if row_result and row_result.inserted:
                    records_created += 1
                else:
                    records_updated += 1
            except Exception as e:
                errors.append(f"Failed to save {budget_type} for {month:02d}/{year}: {str(e)}")

    await db.commit()

    logger.info(f"Budget upload complete: {records_created} created, {records_updated} updated")

    return {
        "status": "success",
        "filename": file.filename,
        "records_created": records_created,
        "records_updated": records_updated,
        "total_records": records_created + records_updated,
        "errors": errors if errors else None
    }


@router.get("/template")
async def download_budget_template(
    current_user: dict = Depends(get_current_user)
):
    """
    Download empty budget template Excel file.
    Pre-fills month headers for current and next year.
    """
    # Generate month headers for current year and next year
    current_year = datetime.now().year
    months = []

    for year in [current_year, current_year + 1]:
        for month in range(1, 13):
            months.append(f"{month:02d}/{year % 100:02d}")

    # Create DataFrame with template structure
    data = {
        'Type': ['accom', 'dry', 'wet']
    }

    # Add empty columns for each month
    for month_header in months:
        data[month_header] = ['', '', '']

    df = pd.DataFrame(data)

    # Write to Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Budget', index=False)

        # Auto-adjust column widths
        worksheet = writer.sheets['Budget']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            worksheet.column_dimensions[column_letter].width = max(max_length + 2, 10)

    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=budget_template_{current_year}.xlsx"
        }
    )
