"""
Public API endpoints - accessible with API key authentication
For external integrations like Kitchen Flash app
"""
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging

from database import get_db
from auth import get_api_key_auth

router = APIRouter()
logger = logging.getLogger(__name__)


def get_prior_year_date(target_date: date) -> date:
    """
    Get prior year date with 364-day offset for day-of-week alignment.
    52 weeks = 364 days, so Monday aligns with Monday.
    """
    return target_date - timedelta(days=364)


@router.get("/forecast/rooms")
async def get_rooms_forecast(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    days: int = Query(7, ge=1, le=365, description="Number of days to forecast"),
    db: AsyncSession = Depends(get_db),
    api_key: dict = Depends(get_api_key_auth)
):
    """
    Get forecasted room bookings for external applications.

    Returns: OTB rooms, forecast rooms, occupancy %, prior year data
    """
    from services.forecasting.pickup_v2_model import forecast_rooms_for_date

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    end = start + timedelta(days=days - 1)
    today = date.today()

    # Get total rooms for occupancy calculation
    result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'total_rooms'")
    )
    row = result.fetchone()
    total_rooms = int(row.config_value) if row and row.config_value else 30

    data = []
    current = start
    while current <= end:
        lead_days = (current - today).days if current >= today else 0
        prior_date = get_prior_year_date(current)

        try:
            if current >= today:
                # Future date - get forecast
                forecast = await forecast_rooms_for_date(
                    db, current, lead_days, prior_date, 'hotel_room_nights'
                )
                otb_rooms = forecast.get('current_otb', 0) or 0
                pickup_rooms = forecast.get('expected_pickup', 0) or 0
                forecast_rooms = otb_rooms + pickup_rooms
                prior_otb = forecast.get('prior_year_otb', 0) or 0
                prior_final = forecast.get('prior_year_final', 0) or 0

                # Get guest counts from stats
                stats_result = await db.execute(
                    text("""
                        SELECT booking_count, guests_count FROM newbook_bookings_stats
                        WHERE date = :target_date
                    """),
                    {"target_date": current}
                )
                stats_row = stats_result.fetchone()
                otb_guests = stats_row.guests_count if stats_row and stats_row.guests_count else 0

                # Prior year guests for ratio
                prior_stats = await db.execute(
                    text("""
                        SELECT booking_count, guests_count FROM newbook_bookings_stats
                        WHERE date = :prior_date
                    """),
                    {"prior_date": prior_date}
                )
                prior_stats_row = prior_stats.fetchone()
                prior_guests = prior_stats_row.guests_count if prior_stats_row and prior_stats_row.guests_count else 0
                prior_rooms_actual = prior_stats_row.booking_count if prior_stats_row and prior_stats_row.booking_count else 0

                # Calculate guests per room ratio (prior year -> current OTB -> default)
                if prior_rooms_actual > 0:
                    guests_per_room = prior_guests / prior_rooms_actual
                elif otb_rooms > 0:
                    guests_per_room = otb_guests / otb_rooms
                else:
                    guests_per_room = 1.8

                pickup_guests = round(pickup_rooms * guests_per_room)
                forecast_guests = otb_guests + pickup_guests
            else:
                # Past date - get actuals from stats
                stats_result = await db.execute(
                    text("""
                        SELECT booking_count, guests_count FROM newbook_bookings_stats
                        WHERE date = :target_date
                    """),
                    {"target_date": current}
                )
                stats_row = stats_result.fetchone()
                otb_rooms = stats_row.booking_count if stats_row else 0
                otb_guests = stats_row.guests_count if stats_row and stats_row.guests_count else 0
                forecast_rooms = otb_rooms
                forecast_guests = otb_guests
                pickup_rooms = 0
                pickup_guests = 0

                # Prior year stats
                prior_result = await db.execute(
                    text("""
                        SELECT booking_count FROM newbook_bookings_stats
                        WHERE date = :prior_date
                    """),
                    {"prior_date": prior_date}
                )
                prior_row = prior_result.fetchone()
                prior_final = prior_row.booking_count if prior_row else 0
                prior_otb = prior_final

            occupancy_pct = round((forecast_rooms / total_rooms) * 100, 1) if total_rooms > 0 else 0

            data.append({
                "date": current.isoformat(),
                "day": current.strftime("%A"),
                "lead_days": lead_days,
                "otb_rooms": otb_rooms,
                "pickup_rooms": pickup_rooms,
                "forecast_rooms": forecast_rooms,
                "otb_guests": otb_guests,
                "pickup_guests": pickup_guests,
                "forecast_guests": forecast_guests,
                "occupancy_pct": occupancy_pct,
                "prior_year_otb": prior_otb,
                "prior_year_final": prior_final,
            })
        except Exception as e:
            logger.warning(f"Error forecasting rooms for {current}: {e}")
            data.append({
                "date": current.isoformat(),
                "day": current.strftime("%A"),
                "lead_days": lead_days,
                "otb_rooms": 0,
                "pickup_rooms": 0,
                "forecast_rooms": 0,
                "otb_guests": 0,
                "pickup_guests": 0,
                "forecast_guests": 0,
                "occupancy_pct": 0,
                "prior_year_otb": 0,
                "prior_year_final": 0,
                "error": str(e)
            })

        current += timedelta(days=1)

    return {"data": data, "total_rooms": total_rooms}


@router.get("/forecast/covers")
async def get_covers_forecast(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    days: int = Query(7, ge=1, le=365, description="Number of days to forecast"),
    db: AsyncSession = Depends(get_db),
    api_key: dict = Depends(get_api_key_auth)
):
    """
    Get forecasted restaurant covers by period for external applications.

    Returns: OTB covers, forecast covers, prior year data for breakfast, lunch, dinner
    """
    from services.forecasting.covers_model import forecast_covers_range

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    end = start + timedelta(days=days - 1)
    today = date.today()

    try:
        # Get covers forecast
        covers_data = await forecast_covers_range(db, start, end, include_details=False)
    except Exception as e:
        logger.error(f"Covers forecast failed: {e}")
        raise HTTPException(status_code=500, detail=f"Forecast error: {str(e)}")

    # Get prior year covers from stats
    prior_start = get_prior_year_date(start)
    prior_end = get_prior_year_date(end)

    prior_result = await db.execute(
        text("""
            SELECT date, breakfast_covers, lunch_covers, dinner_covers
            FROM resos_bookings_stats
            WHERE date >= :start_date AND date <= :end_date
        """),
        {"start_date": prior_start, "end_date": prior_end}
    )
    prior_rows = prior_result.fetchall()
    prior_by_date = {row.date: row for row in prior_rows}

    data = []
    for day_data in covers_data.get("data", []):
        target_date = datetime.strptime(day_data["date"], "%Y-%m-%d").date()
        prior_date = get_prior_year_date(target_date)
        lead_days = (target_date - today).days if target_date >= today else 0

        prior_row = prior_by_date.get(prior_date)
        prior_breakfast = prior_row.breakfast_covers if prior_row else 0
        prior_lunch = prior_row.lunch_covers if prior_row else 0
        prior_dinner = prior_row.dinner_covers if prior_row else 0

        # For prior OTB, we don't have pace data, so use same as final for simplicity
        data.append({
            "date": day_data["date"],
            "day": day_data["day_of_week"],
            "lead_days": lead_days,
            "breakfast": {
                "otb": day_data["breakfast"]["otb"],
                "forecast": day_data["breakfast"]["forecast"],
                "prior_otb": prior_breakfast,  # Same as final for prior year
                "prior_final": prior_breakfast
            },
            "lunch": {
                "otb": day_data["lunch"]["otb"],
                "forecast": day_data["lunch"]["forecast"],
                "prior_otb": prior_lunch,
                "prior_final": prior_lunch
            },
            "dinner": {
                "otb": day_data["dinner"]["otb"],
                "forecast": day_data["dinner"]["forecast"],
                "prior_otb": prior_dinner,
                "prior_final": prior_dinner
            },
            "total": {
                "otb": day_data["totals"]["otb"],
                "forecast": day_data["totals"]["forecast"],
                "prior_final": prior_breakfast + prior_lunch + prior_dinner
            }
        })

    return {"data": data}


@router.get("/forecast/revenue")
async def get_revenue_forecast(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    days: int = Query(7, ge=1, le=365, description="Number of days to forecast"),
    type: str = Query("all", description="Revenue type: all, accom, dry, wet"),
    db: AsyncSession = Depends(get_db),
    api_key: dict = Depends(get_api_key_auth)
):
    """
    Get forecasted revenue by type for external applications.

    Returns: OTB revenue, forecast revenue, prior year actuals, budget
    """
    from services.forecasting.covers_model import forecast_covers_range
    from services.forecasting.pickup_v2_model import forecast_revenue_for_date

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    end = start + timedelta(days=days - 1)
    today = date.today()
    VAT_RATE = 1.20

    # Get spend settings for restaurant revenue
    spend_result = await db.execute(
        text("""
            SELECT config_key, config_value
            FROM system_config
            WHERE config_key LIKE 'resos_%_spend'
        """)
    )
    spend_rows = spend_result.fetchall()
    spend_settings = {row.config_key: float(row.config_value or 0) for row in spend_rows}

    def get_spend_by_period(period: str, revenue_type: str) -> float:
        if revenue_type == 'dry':
            return spend_settings.get(f'resos_{period}_food_spend', 0) / VAT_RATE
        elif revenue_type == 'wet':
            return spend_settings.get(f'resos_{period}_drinks_spend', 0) / VAT_RATE
        else:
            food = spend_settings.get(f'resos_{period}_food_spend', 0)
            drinks = spend_settings.get(f'resos_{period}_drinks_spend', 0)
            return (food + drinks) / VAT_RATE

    # Get actual revenue
    actual_result = await db.execute(
        text("""
            SELECT date, accommodation, dry, wet
            FROM newbook_net_revenue_data
            WHERE date >= :start_date AND date <= :end_date
        """),
        {"start_date": start, "end_date": end}
    )
    actual_by_date = {row.date: row for row in actual_result.fetchall()}

    # Get prior year revenue
    prior_start = get_prior_year_date(start)
    prior_end = get_prior_year_date(end)
    prior_result = await db.execute(
        text("""
            SELECT date, accommodation, dry, wet
            FROM newbook_net_revenue_data
            WHERE date >= :start_date AND date <= :end_date
        """),
        {"start_date": prior_start, "end_date": prior_end}
    )
    prior_by_date = {row.date: row for row in prior_result.fetchall()}

    # Get budgets
    budget_types = []
    if type in ['all', 'accom']:
        budget_types.append('net_accom')
    if type in ['all', 'dry']:
        budget_types.append('net_dry')
    if type in ['all', 'wet']:
        budget_types.append('net_wet')
    if type == 'all':
        budget_types.append('total_rev')

    budget_result = await db.execute(
        text("""
            SELECT date, budget_type, budget_value
            FROM daily_budgets
            WHERE date >= :start_date AND date <= :end_date
            AND budget_type = ANY(:types)
        """),
        {"start_date": start, "end_date": end, "types": budget_types if budget_types else ['']}
    )
    budget_data = {}
    for row in budget_result.fetchall():
        if row.date not in budget_data:
            budget_data[row.date] = {}
        budget_data[row.date][row.budget_type] = float(row.budget_value or 0)

    # Get covers forecast for restaurant revenue
    try:
        covers_data = await forecast_covers_range(db, start, end, include_details=False)
        covers_by_date = {c["date"]: c for c in covers_data.get("data", [])}
    except Exception as e:
        logger.warning(f"Covers forecast failed: {e}")
        covers_by_date = {}

    data = []
    current = start
    while current <= end:
        is_past = current < today
        lead_days = (current - today).days if current >= today else 0
        prior_date = get_prior_year_date(current)

        # Prior year actual
        prior_row = prior_by_date.get(prior_date)
        prior_accom = float(prior_row.accommodation) if prior_row and prior_row.accommodation else 0
        prior_dry = float(prior_row.dry) if prior_row and prior_row.dry else 0
        prior_wet = float(prior_row.wet) if prior_row and prior_row.wet else 0

        # Budget
        day_budget = budget_data.get(current, {})
        budget_accom = day_budget.get('net_accom', 0)
        budget_dry = day_budget.get('net_dry', 0)
        budget_wet = day_budget.get('net_wet', 0)
        budget_total = day_budget.get('total_rev', budget_accom + budget_dry + budget_wet)

        if is_past:
            # Past: use actual revenue
            actual_row = actual_by_date.get(current)
            accom_otb = float(actual_row.accommodation) if actual_row and actual_row.accommodation else 0
            dry_otb = float(actual_row.dry) if actual_row and actual_row.dry else 0
            wet_otb = float(actual_row.wet) if actual_row and actual_row.wet else 0
            accom_forecast = accom_otb
            dry_forecast = dry_otb
            wet_forecast = wet_otb
            accom_prior_otb = prior_accom
        else:
            # Future: forecast
            # Accommodation - use revenue forecast model
            try:
                accom_forecast_data = await forecast_revenue_for_date(
                    db, current, lead_days, prior_date
                )
                accom_otb = accom_forecast_data.get('current_otb_rev', 0) or 0
                accom_pickup = accom_forecast_data.get('forecast_pickup_rev', 0) or 0
                accom_forecast = accom_otb + accom_pickup
                accom_prior_otb = accom_forecast_data.get('prior_year_otb_rev', 0) or 0
            except Exception:
                accom_otb = accom_forecast = accom_prior_otb = 0

            # Restaurant
            day_covers = covers_by_date.get(current.isoformat())
            if day_covers:
                breakfast_otb = day_covers["breakfast"]["otb"]
                lunch_otb = day_covers["lunch"]["otb"]
                dinner_otb = day_covers["dinner"]["otb"]
                breakfast_forecast = day_covers["breakfast"]["forecast"]
                lunch_forecast = day_covers["lunch"]["forecast"]
                dinner_forecast = day_covers["dinner"]["forecast"]

                dry_otb = (
                    breakfast_otb * get_spend_by_period('breakfast', 'dry') +
                    lunch_otb * get_spend_by_period('lunch', 'dry') +
                    dinner_otb * get_spend_by_period('dinner', 'dry')
                )
                dry_forecast = (
                    breakfast_forecast * get_spend_by_period('breakfast', 'dry') +
                    lunch_forecast * get_spend_by_period('lunch', 'dry') +
                    dinner_forecast * get_spend_by_period('dinner', 'dry')
                )
                wet_otb = (
                    breakfast_otb * get_spend_by_period('breakfast', 'wet') +
                    lunch_otb * get_spend_by_period('lunch', 'wet') +
                    dinner_otb * get_spend_by_period('dinner', 'wet')
                )
                wet_forecast = (
                    breakfast_forecast * get_spend_by_period('breakfast', 'wet') +
                    lunch_forecast * get_spend_by_period('lunch', 'wet') +
                    dinner_forecast * get_spend_by_period('dinner', 'wet')
                )
            else:
                dry_otb = dry_forecast = wet_otb = wet_forecast = 0

        day_data = {
            "date": current.isoformat(),
            "day": current.strftime("%A"),
            "is_past": is_past,
            "lead_days": lead_days,
        }

        if type in ['all', 'accom']:
            day_data["accom"] = {
                "otb": round(accom_otb, 2),
                "forecast": round(accom_forecast, 2),
                "prior_otb": round(accom_prior_otb, 2) if not is_past else round(prior_accom, 2),
                "prior_final": round(prior_accom, 2),
                "budget": round(budget_accom, 2)
            }

        if type in ['all', 'dry']:
            day_data["dry"] = {
                "otb": round(dry_otb, 2),
                "forecast": round(dry_forecast, 2),
                "prior_final": round(prior_dry, 2),
                "budget": round(budget_dry, 2)
            }

        if type in ['all', 'wet']:
            day_data["wet"] = {
                "otb": round(wet_otb, 2),
                "forecast": round(wet_forecast, 2),
                "prior_final": round(prior_wet, 2),
                "budget": round(budget_wet, 2)
            }

        if type == 'all':
            total_otb = accom_otb + dry_otb + wet_otb
            total_forecast = accom_forecast + dry_forecast + wet_forecast
            total_prior = prior_accom + prior_dry + prior_wet
            day_data["total"] = {
                "otb": round(total_otb, 2),
                "forecast": round(total_forecast, 2),
                "prior_final": round(total_prior, 2),
                "budget": round(budget_total, 2)
            }

        data.append(day_data)
        current += timedelta(days=1)

    return {"data": data}


@router.get("/forecast/spend-rates")
async def get_spend_rates(
    db: AsyncSession = Depends(get_db),
    api_key: dict = Depends(get_api_key_auth)
):
    """
    Return spend-per-cover rates for each meal period.
    Values are gross (inc VAT) from system_config, plus the VAT rate.
    Kitchen app can divide by VAT rate to get net values.
    """
    VAT_RATE = 1.20

    spend_result = await db.execute(
        text("""
            SELECT config_key, config_value
            FROM system_config
            WHERE config_key LIKE 'resos_%_spend'
        """)
    )
    spend_rows = spend_result.fetchall()
    spend_settings = {row.config_key: float(row.config_value or 0) for row in spend_rows}

    return {
        "vat_rate": VAT_RATE,
        "periods": {
            "breakfast": {
                "food_spend_gross": spend_settings.get("resos_breakfast_food_spend", 0),
                "drinks_spend_gross": spend_settings.get("resos_breakfast_drinks_spend", 0),
                "food_spend_net": round(spend_settings.get("resos_breakfast_food_spend", 0) / VAT_RATE, 2),
                "drinks_spend_net": round(spend_settings.get("resos_breakfast_drinks_spend", 0) / VAT_RATE, 2),
            },
            "lunch": {
                "food_spend_gross": spend_settings.get("resos_lunch_food_spend", 0),
                "drinks_spend_gross": spend_settings.get("resos_lunch_drinks_spend", 0),
                "food_spend_net": round(spend_settings.get("resos_lunch_food_spend", 0) / VAT_RATE, 2),
                "drinks_spend_net": round(spend_settings.get("resos_lunch_drinks_spend", 0) / VAT_RATE, 2),
            },
            "dinner": {
                "food_spend_gross": spend_settings.get("resos_dinner_food_spend", 0),
                "drinks_spend_gross": spend_settings.get("resos_dinner_drinks_spend", 0),
                "food_spend_net": round(spend_settings.get("resos_dinner_food_spend", 0) / VAT_RATE, 2),
                "drinks_spend_net": round(spend_settings.get("resos_dinner_drinks_spend", 0) / VAT_RATE, 2),
            },
        }
    }
