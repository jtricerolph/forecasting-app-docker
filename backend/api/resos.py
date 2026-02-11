"""
Resos Mapping API Endpoints

Handles Resos custom field and opening hours configuration.
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from database import get_db
from auth import get_current_user
from services.resos_client import ResosClient, ResosAPIError

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ Pydantic Schemas ============

class CustomFieldMappingItem(BaseModel):
    field_id: str
    field_name: str
    field_type: str
    maps_to: str  # 'hotel_guest', 'dbb', 'booking_number', 'allergies', 'ignore'
    value_for_true: Optional[str] = None  # For radio/checkbox: which value means "yes"


class OpeningHoursMappingItem(BaseModel):
    opening_hour_id: str
    opening_hour_name: str
    period_type: str  # 'lunch', 'afternoon', 'dinner', 'ignore'
    is_regular: bool = True


class MappingUpdate(BaseModel):
    custom_fields: Optional[List[CustomFieldMappingItem]] = None
    opening_hours: Optional[List[OpeningHoursMappingItem]] = None


# ============ Custom Fields Endpoints ============

@router.get("/custom-fields")
async def fetch_custom_fields(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch custom field definitions from Resos API.
    Returns fields that can be mapped to hotel_guest, dbb, etc.
    """
    try:
        async with await ResosClient.from_db(db) as client:
            fields = await client.get_custom_field_definitions()
    except ResosAPIError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to fetch Resos custom fields: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch custom fields from Resos")

    # Return all custom fields (no filtering by type - let user decide what to map)
    formatted_fields = [
        {
            "id": f.get("_id") or f.get("id"),
            "name": f.get("name", ""),
            "type": f.get("type", ""),
            "values": f.get("choices", [])  # For radio/dropdown fields
        }
        for f in fields
    ]

    return formatted_fields


@router.get("/opening-hours")
async def fetch_opening_hours(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch opening hours/service periods from Resos API.
    Filters to regular (non-special) periods only.
    """
    try:
        async with await ResosClient.from_db(db) as client:
            hours = await client.get_opening_hours()
    except ResosAPIError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to fetch Resos opening hours: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch opening hours from Resos")

    logger.info(f"Raw opening hours from Resos API: {len(hours)} periods")

    # Filter out special/one-off periods - only return regular service periods
    # special=True means one-off events, special=False means recurring
    regular_hours = [h for h in hours if h.get('special') == False]

    # Day of week mapping (Resos uses 1=Monday, 7=Sunday)
    day_names = ['', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    # Transform and add helpful fields
    formatted_hours = []
    for hour in regular_hours:
        hour_id = hour.get('_id') or hour.get('id', '')
        hour_name = hour.get('name', '')
        day_num = hour.get('day', 0)

        # Convert open/close times from HHMM integers to HH:MM strings
        start_time = None
        end_time = None

        if 'open' in hour:
            open_val = hour['open']
            hours_part = open_val // 100
            mins_part = open_val % 100
            start_time = f"{hours_part:02d}:{mins_part:02d}"

        if 'close' in hour:
            close_val = hour['close']
            hours_part = close_val // 100
            mins_part = close_val % 100
            end_time = f"{hours_part:02d}:{mins_part:02d}"

        formatted_hours.append({
            "id": hour_id,
            "name": hour_name,
            "day": day_num,
            "day_name": day_names[day_num] if 1 <= day_num <= 7 else "Unknown",
            "start_time": start_time,
            "end_time": end_time
        })

    # Sort by day of week first, then by open time
    formatted_hours.sort(key=lambda h: (h.get('day', 0), h.get('start_time', '')))

    logger.info(f"After filtering: {len(formatted_hours)} regular periods (filtered out {len(hours) - len(formatted_hours)} special periods)")

    return formatted_hours


# ============ Mapping Storage Endpoints ============

@router.get("/custom-field-mapping")
async def get_custom_field_mappings(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get saved custom field mappings."""
    cf_result = await db.execute(text("""
        SELECT field_id, field_name, field_type, maps_to, value_for_true
        FROM resos_custom_field_mapping
        ORDER BY field_name
    """))
    custom_field_rows = cf_result.fetchall()

    return [
        {
            "custom_field_id": row.field_id,
            "mapping_type": row.maps_to,
            "value_for_true": row.value_for_true
        }
        for row in custom_field_rows
    ]


@router.get("/opening-hours-mapping")
async def get_opening_hours_mappings(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get saved opening hours mappings."""
    oh_result = await db.execute(text("""
        SELECT opening_hour_id, opening_hour_name, period_type, display_name, is_regular
        FROM resos_opening_hours_mapping
        ORDER BY opening_hour_name
    """))
    opening_hour_rows = oh_result.fetchall()

    return [
        {
            "opening_hour_id": row.opening_hour_id,
            "opening_hour_name": row.opening_hour_name,
            "period_type": row.period_type,
            "display_name": row.display_name,
            "is_regular": row.is_regular
        }
        for row in opening_hour_rows
    ]


@router.get("/manual-breakfast-periods")
async def get_manual_breakfast_periods(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get manual breakfast period configuration."""
    # Get enabled flag
    result = await db.execute(text("""
        SELECT config_value FROM system_config WHERE config_key = 'resos_enable_manual_breakfast'
    """))
    row = result.fetchone()
    enabled = row.config_value.lower() == 'true' if row and row.config_value else False

    # Get periods
    result = await db.execute(text("""
        SELECT day_of_week, start_time, end_time, is_active
        FROM resos_manual_breakfast_periods
        ORDER BY day_of_week
    """))
    rows = result.fetchall()

    periods = [
        {
            "day_of_week": row.day_of_week,
            "start_time": str(row.start_time) if row.start_time else None,
            "end_time": str(row.end_time) if row.end_time else None,
            "is_active": row.is_active
        }
        for row in rows
    ]

    return {
        "enabled": enabled,
        "periods": periods
    }


@router.post("/custom-field-mapping")
async def save_custom_field_mappings(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Save custom field mappings."""
    mappings = data.get("mappings", [])
    saved = 0

    for mapping in mappings:
        field_id = mapping.get("custom_field_id")
        mapping_type = mapping.get("mapping_type")
        value_for_true = mapping.get("value_for_true")

        if not field_id or not mapping_type:
            continue

        await db.execute(text("""
            INSERT INTO resos_custom_field_mapping
                (field_id, field_name, field_type, maps_to, value_for_true, updated_at)
            VALUES
                (:field_id, '', '', :maps_to, :value_for_true, NOW())
            ON CONFLICT (field_id) DO UPDATE SET
                maps_to = EXCLUDED.maps_to,
                value_for_true = EXCLUDED.value_for_true,
                updated_at = NOW()
        """), {
            "field_id": field_id,
            "maps_to": mapping_type,
            "value_for_true": value_for_true
        })
        saved += 1

    await db.commit()
    logger.info(f"Saved {saved} custom field mappings")

    return {
        "message": "Custom field mappings saved successfully",
        "saved": saved
    }


@router.post("/opening-hours-mapping")
async def save_opening_hours_mappings(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Save opening hours mappings."""
    mappings = data.get("mappings", [])
    saved = 0

    for mapping in mappings:
        opening_hour_id = mapping.get("opening_hour_id")
        period_type = mapping.get("period_type")
        display_name = mapping.get("display_name")

        if not opening_hour_id or not period_type:
            continue

        await db.execute(text("""
            INSERT INTO resos_opening_hours_mapping
                (opening_hour_id, opening_hour_name, period_type, display_name, is_regular, updated_at)
            VALUES
                (:opening_hour_id, '', :period_type, :display_name, TRUE, NOW())
            ON CONFLICT (opening_hour_id) DO UPDATE SET
                period_type = EXCLUDED.period_type,
                display_name = EXCLUDED.display_name,
                updated_at = NOW()
        """), {
            "opening_hour_id": opening_hour_id,
            "period_type": period_type,
            "display_name": display_name
        })
        saved += 1

    await db.commit()
    logger.info(f"Saved {saved} opening hours mappings")

    return {
        "message": "Opening hours mappings saved successfully",
        "saved": saved
    }


@router.post("/manual-breakfast-periods")
async def save_manual_breakfast_periods(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Save manual breakfast period configuration."""
    from datetime import time as dt_time

    enabled = data.get("enabled", False)
    periods = data.get("periods", [])

    # Save enabled flag to system_config
    await db.execute(text("""
        INSERT INTO system_config (config_key, config_value, description, updated_at)
        VALUES ('resos_enable_manual_breakfast', :value, 'Enable manual breakfast configuration', NOW())
        ON CONFLICT (config_key) DO UPDATE SET
            config_value = EXCLUDED.config_value,
            updated_at = NOW()
    """), {"value": str(enabled).lower()})

    # Save periods
    for period in periods:
        # Convert time strings to Python time objects for asyncpg
        start_time_str = period.get("start_time")
        end_time_str = period.get("end_time")

        start_time_obj = None
        end_time_obj = None

        if start_time_str:
            hour, minute = map(int, start_time_str.split(':'))
            start_time_obj = dt_time(hour, minute)

        if end_time_str:
            hour, minute = map(int, end_time_str.split(':'))
            end_time_obj = dt_time(hour, minute)

        await db.execute(text("""
            INSERT INTO resos_manual_breakfast_periods
                (day_of_week, start_time, end_time, is_active, updated_at)
            VALUES
                (:day_of_week, :start_time, :end_time, :is_active, NOW())
            ON CONFLICT (day_of_week) DO UPDATE SET
                start_time = EXCLUDED.start_time,
                end_time = EXCLUDED.end_time,
                is_active = EXCLUDED.is_active,
                updated_at = NOW()
        """), {
            "day_of_week": period["day_of_week"],
            "start_time": start_time_obj,
            "end_time": end_time_obj,
            "is_active": period.get("is_active", True)
        })

    await db.commit()
    return {"message": "Manual breakfast periods saved successfully"}


@router.get("/mapping")
async def get_mappings(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get saved custom field and opening hours mappings.
    """
    # Get custom field mappings
    cf_result = await db.execute(text("""
        SELECT field_id, field_name, field_type, maps_to, value_for_true
        FROM resos_custom_field_mapping
        ORDER BY field_name
    """))
    custom_field_rows = cf_result.fetchall()

    # Get opening hours mappings
    oh_result = await db.execute(text("""
        SELECT opening_hour_id, opening_hour_name, period_type, is_regular
        FROM resos_opening_hours_mapping
        ORDER BY opening_hour_name
    """))
    opening_hour_rows = oh_result.fetchall()

    return {
        "custom_fields": [
            {
                "field_id": row.field_id,
                "field_name": row.field_name,
                "field_type": row.field_type,
                "maps_to": row.maps_to,
                "value_for_true": row.value_for_true
            }
            for row in custom_field_rows
        ],
        "opening_hours": [
            {
                "opening_hour_id": row.opening_hour_id,
                "opening_hour_name": row.opening_hour_name,
                "period_type": row.period_type,
                "is_regular": row.is_regular
            }
            for row in opening_hour_rows
        ]
    }


@router.post("/mapping")
async def save_mappings(
    update: MappingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Save custom field and opening hours mappings.
    Uses upsert to update existing or insert new mappings.
    """
    saved_cf = 0
    saved_oh = 0

    # Save custom field mappings
    if update.custom_fields:
        for cf in update.custom_fields:
            await db.execute(text("""
                INSERT INTO resos_custom_field_mapping
                    (field_id, field_name, field_type, maps_to, value_for_true, updated_at)
                VALUES
                    (:field_id, :field_name, :field_type, :maps_to, :value_for_true, NOW())
                ON CONFLICT (field_id) DO UPDATE SET
                    field_name = EXCLUDED.field_name,
                    field_type = EXCLUDED.field_type,
                    maps_to = EXCLUDED.maps_to,
                    value_for_true = EXCLUDED.value_for_true,
                    updated_at = NOW()
            """), {
                "field_id": cf.field_id,
                "field_name": cf.field_name,
                "field_type": cf.field_type,
                "maps_to": cf.maps_to,
                "value_for_true": cf.value_for_true
            })
            saved_cf += 1

    # Save opening hours mappings
    if update.opening_hours:
        for oh in update.opening_hours:
            await db.execute(text("""
                INSERT INTO resos_opening_hours_mapping
                    (opening_hour_id, opening_hour_name, period_type, is_regular, updated_at)
                VALUES
                    (:opening_hour_id, :opening_hour_name, :period_type, :is_regular, NOW())
                ON CONFLICT (opening_hour_id) DO UPDATE SET
                    opening_hour_name = EXCLUDED.opening_hour_name,
                    period_type = EXCLUDED.period_type,
                    is_regular = EXCLUDED.is_regular,
                    updated_at = NOW()
            """), {
                "opening_hour_id": oh.opening_hour_id,
                "opening_hour_name": oh.opening_hour_name,
                "period_type": oh.period_type,
                "is_regular": oh.is_regular
            })
            saved_oh += 1

    await db.commit()

    logger.info(f"Saved {saved_cf} custom field mappings, {saved_oh} opening hours mappings")

    return {
        "message": "Mappings saved successfully",
        "custom_fields_saved": saved_cf,
        "opening_hours_saved": saved_oh
    }


@router.delete("/mapping/custom-field/{field_id}")
async def delete_custom_field_mapping(
    field_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete a custom field mapping."""
    await db.execute(text("""
        DELETE FROM resos_custom_field_mapping WHERE field_id = :field_id
    """), {"field_id": field_id})
    await db.commit()
    return {"message": "Mapping deleted"}


@router.delete("/mapping/opening-hour/{opening_hour_id}")
async def delete_opening_hour_mapping(
    opening_hour_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete an opening hours mapping."""
    await db.execute(text("""
        DELETE FROM resos_opening_hours_mapping WHERE opening_hour_id = :opening_hour_id
    """), {"opening_hour_id": opening_hour_id})
    await db.commit()
    return {"message": "Mapping deleted"}


# ============ Average Spend Settings Endpoints ============

@router.get("/average-spend")
async def get_average_spend(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get average spend settings for breakfast, lunch and dinner."""
    # Get values from system_config
    result = await db.execute(text("""
        SELECT config_key, config_value FROM system_config
        WHERE config_key IN (
            'resos_breakfast_food_spend',
            'resos_breakfast_drinks_spend',
            'resos_lunch_food_spend',
            'resos_lunch_drinks_spend',
            'resos_dinner_food_spend',
            'resos_dinner_drinks_spend'
        )
    """))
    rows = result.fetchall()

    settings = {}
    for row in rows:
        key = row.config_key.replace('resos_', '')
        try:
            settings[key] = float(row.config_value) if row.config_value else 0
        except (ValueError, TypeError):
            settings[key] = 0

    return {
        "breakfast_food_spend": settings.get('breakfast_food_spend', 0),
        "breakfast_drinks_spend": settings.get('breakfast_drinks_spend', 0),
        "lunch_food_spend": settings.get('lunch_food_spend', 0),
        "lunch_drinks_spend": settings.get('lunch_drinks_spend', 0),
        "dinner_food_spend": settings.get('dinner_food_spend', 0),
        "dinner_drinks_spend": settings.get('dinner_drinks_spend', 0)
    }


@router.post("/average-spend")
async def save_average_spend(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Save average spend settings for breakfast, lunch and dinner."""
    settings = [
        ('resos_breakfast_food_spend', data.get('breakfast_food_spend', 0), 'Average food spend per cover for breakfast'),
        ('resos_breakfast_drinks_spend', data.get('breakfast_drinks_spend', 0), 'Average drinks spend per cover for breakfast'),
        ('resos_lunch_food_spend', data.get('lunch_food_spend', 0), 'Average food spend per cover for lunch'),
        ('resos_lunch_drinks_spend', data.get('lunch_drinks_spend', 0), 'Average drinks spend per cover for lunch'),
        ('resos_dinner_food_spend', data.get('dinner_food_spend', 0), 'Average food spend per cover for dinner'),
        ('resos_dinner_drinks_spend', data.get('dinner_drinks_spend', 0), 'Average drinks spend per cover for dinner'),
    ]

    for config_key, config_value, description in settings:
        await db.execute(text("""
            INSERT INTO system_config (config_key, config_value, description, updated_at)
            VALUES (:config_key, :config_value, :description, NOW())
            ON CONFLICT (config_key) DO UPDATE SET
                config_value = EXCLUDED.config_value,
                updated_at = NOW()
        """), {
            "config_key": config_key,
            "config_value": str(config_value),
            "description": description
        })

    await db.commit()
    logger.info("Saved average spend settings")

    return {"message": "Average spend settings saved successfully"}


# ============ Pace Data Backfill Endpoint ============

@router.post("/backfill-pace")
async def backfill_pace_data(
    start_date: str,
    end_date: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Backfill resos_booking_pace table for historical dates.

    This calculates pace snapshots using booking_placed timestamps
    to reconstruct what was on the books at each lead time.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
    """
    from datetime import datetime, timedelta

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD"}

    if (end - start).days > 400:
        return {"error": "Date range too large. Max 400 days at a time."}

    # Valid statuses and pace intervals
    VALID_STATUSES = ('approved', 'arrived', 'seated', 'left')
    PACE_INTERVALS = [
        365, 330, 300, 270, 240, 210,
        177, 170, 163, 156, 149, 142, 135, 128, 121, 114,
        107, 100, 93, 86, 79, 72, 65, 58, 51, 44, 37,
        30, 29, 28, 27, 26, 25, 24, 23, 22, 21,
        20, 19, 18, 17, 16, 15, 14, 13, 12, 11,
        10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0
    ]

    dates_processed = 0
    current = start

    while current <= end:
        for pace_type in ['total', 'resident', 'non_resident']:
            pace_values = {}

            for days_out in PACE_INTERVALS:
                snapshot_date = current - timedelta(days=days_out)

                # Build query based on pace_type
                if pace_type == 'total':
                    result = await db.execute(
                        text("""
                            SELECT COALESCE(SUM(covers), 0) as total_covers
                            FROM resos_bookings_data
                            WHERE booking_date = :target_date
                            AND status IN ('approved', 'arrived', 'seated', 'left')
                            AND booking_placed <= :snapshot_date
                        """),
                        {"target_date": current, "snapshot_date": snapshot_date}
                    )
                elif pace_type == 'resident':
                    result = await db.execute(
                        text("""
                            SELECT COALESCE(SUM(covers), 0) as total_covers
                            FROM resos_bookings_data
                            WHERE booking_date = :target_date
                            AND status IN ('approved', 'arrived', 'seated', 'left')
                            AND booking_placed <= :snapshot_date
                            AND is_hotel_guest = true
                        """),
                        {"target_date": current, "snapshot_date": snapshot_date}
                    )
                else:  # non_resident
                    result = await db.execute(
                        text("""
                            SELECT COALESCE(SUM(covers), 0) as total_covers
                            FROM resos_bookings_data
                            WHERE booking_date = :target_date
                            AND status IN ('approved', 'arrived', 'seated', 'left')
                            AND booking_placed <= :snapshot_date
                            AND (is_hotel_guest = false OR is_hotel_guest IS NULL)
                        """),
                        {"target_date": current, "snapshot_date": snapshot_date}
                    )

                row = result.fetchone()
                pace_values[f"d{days_out}"] = row.total_covers if row else 0

            # Upsert pace record
            columns = ", ".join(pace_values.keys())
            placeholders = ", ".join([f":{k}" for k in pace_values.keys()])
            updates = ", ".join([f"{k} = :{k}" for k in pace_values.keys()])

            await db.execute(
                text(f"""
                    INSERT INTO resos_booking_pace (booking_date, pace_type, {columns}, updated_at)
                    VALUES (:booking_date, :pace_type, {placeholders}, NOW())
                    ON CONFLICT (booking_date, pace_type) DO UPDATE SET
                        {updates},
                        updated_at = NOW()
                """),
                {"booking_date": current, "pace_type": pace_type, **pace_values}
            )

        dates_processed += 1
        current += timedelta(days=1)

        # Commit every 30 days to avoid large transactions
        if dates_processed % 30 == 0:
            await db.commit()
            logger.info(f"Backfill progress: {dates_processed} dates processed")

    await db.commit()
    logger.info(f"Pace backfill completed: {dates_processed} dates from {start_date} to {end_date}")

    return {
        "message": f"Pace data backfilled successfully",
        "dates_processed": dates_processed,
        "start_date": start_date,
        "end_date": end_date
    }
