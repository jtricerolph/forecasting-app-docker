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

    # Filter to relevant field types (radio, checkbox, text)
    relevant_types = ['radio', 'checkbox', 'text', 'textarea']
    filtered_fields = [
        {
            "id": f.get("_id") or f.get("id"),
            "name": f.get("name", ""),
            "type": f.get("type", ""),
            "choices": f.get("choices", [])  # For radio/dropdown fields
        }
        for f in fields
        if f.get("type") in relevant_types
    ]

    return {"custom_fields": filtered_fields}


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

    return {"opening_hours": formatted_hours}


# ============ Mapping Storage Endpoints ============

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
