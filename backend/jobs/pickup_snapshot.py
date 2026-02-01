"""
Pickup snapshot job - captures daily on-the-books values
Used by the pickup model for pace comparison

Prior year comparison uses 364 days (52 weeks) for day-of-week alignment:
- Monday compares to Monday
- Saturday compares to Saturday
"""
import logging
from datetime import date, timedelta

from sqlalchemy import text
from database import SyncSessionLocal
from utils.time_alignment import get_prior_year_daily, SQL_PRIOR_YEAR_OFFSET

logger = logging.getLogger(__name__)


async def run_pickup_snapshot():
    """
    Capture daily on-the-books snapshot for future dates.
    Stores OTB values at various lead times for pickup model.
    """
    logger.info("Starting pickup snapshot capture")

    db = next(iter([SyncSessionLocal()]))
    snapshot_date = date.today()

    # Overflow room category (category_id=5) is used for chargeable no-shows/cancellations
    # and should be excluded from room night counts
    overflow_category_id = '5'

    try:
        # Capture OTB for next 365 days (extended from 60 for longer-term forecasting)
        for days_out in range(1, 366):
            stay_date = snapshot_date + timedelta(days=days_out)

            # Get total available rooms for this date from occupancy report
            rooms_result = db.execute(
                text("""
                SELECT COALESCE(SUM(available), 25) as total_rooms
                FROM newbook_occupancy_report
                WHERE date = :stay_date
                """),
                {"stay_date": stay_date}
            ).fetchone()
            total_rooms = rooms_result.total_rooms if rooms_result and rooms_result.total_rooms else 25

            # Get hotel occupancy OTB (count rooms on the books for this stay date)
            # EXCLUDES overflow category (chargeable no-shows)
            hotel_result = db.execute(
                text("""
                SELECT COUNT(DISTINCT newbook_id) as bookings,
                       SUM(CASE WHEN LOWER(status) IN ('confirmed', 'provisional', 'unconfirmed', 'arrived') THEN 1 ELSE 0 END) as active_bookings
                FROM newbook_bookings
                WHERE arrival_date <= :stay_date AND departure_date > :stay_date
                    AND LOWER(status) NOT IN ('cancelled', 'no show', 'no_show', 'quote', 'waitlist')
                    AND (category_id IS NULL OR category_id != :overflow_cat)
                """),
                {"stay_date": stay_date, "overflow_cat": overflow_category_id}
            )
            hotel_row = hotel_result.fetchone()
            hotel_otb = hotel_row.active_bookings or 0

            # Get dinner covers OTB
            dinner_result = db.execute(
                text("""
                SELECT COUNT(*) as bookings, COALESCE(SUM(covers), 0) as total_covers
                FROM resos_bookings
                WHERE booking_date = :stay_date
                    AND LOWER(status) NOT IN ('cancelled', 'no show', 'no_show')
                    AND booking_time >= '15:00'
                """),
                {"stay_date": stay_date}
            )
            dinner_row = dinner_result.fetchone()
            dinner_otb = dinner_row.total_covers or 0

            # Get lunch covers OTB
            lunch_result = db.execute(
                text("""
                SELECT COUNT(*) as bookings, COALESCE(SUM(covers), 0) as total_covers
                FROM resos_bookings
                WHERE booking_date = :stay_date
                    AND LOWER(status) NOT IN ('cancelled', 'no show', 'no_show')
                    AND booking_time < '15:00'
                """),
                {"stay_date": stay_date}
            )
            lunch_row = lunch_result.fetchone()
            lunch_otb = lunch_row.total_covers or 0

            # Get prior year comparison data (same day of week, exactly 52 weeks ago)
            # Uses SQL_PRIOR_YEAR_OFFSET (364 days = 52 weeks) for Mon→Mon, Sat→Sat alignment
            prior_year_stay_date = get_prior_year_daily(stay_date)
            prior_year_snapshot_date = get_prior_year_daily(snapshot_date)  # Same lead time last year

            # Calculate prior year hotel OTB at same lead time using booking_placed
            # EXCLUDES overflow category
            prior_hotel_otb_result = db.execute(
                text("""
                SELECT COUNT(DISTINCT newbook_id) as otb_count
                FROM newbook_bookings
                WHERE arrival_date <= :prior_stay_date
                    AND departure_date > :prior_stay_date
                    AND LOWER(status) NOT IN ('cancelled', 'no show', 'no_show', 'quote', 'waitlist')
                    AND (raw_json->>'booking_placed')::timestamp <= :prior_snapshot_date
                    AND (category_id IS NULL OR category_id != :overflow_cat)
                """),
                {"prior_stay_date": prior_year_stay_date, "prior_snapshot_date": prior_year_snapshot_date, "overflow_cat": overflow_category_id}
            ).fetchone()
            prior_hotel_otb = prior_hotel_otb_result.otb_count if prior_hotel_otb_result else None

            # Store snapshots for each metric
            # For hotel_occupancy_pct: store room count, convert to % for otb_value
            # For hotel_room_nights: store raw room count (no conversion)
            # For restaurant: store cover counts directly
            for metric_type, otb_raw, otb_bookings_count in [
                ('hotel_occupancy_pct', hotel_otb, hotel_row.bookings),
                ('hotel_room_nights', hotel_otb, hotel_row.bookings),  # Same count, stored as-is
                ('resos_dinner_covers', dinner_otb, dinner_row.bookings),
                ('resos_lunch_covers', lunch_otb, lunch_row.bookings)
            ]:
                # Convert to percentage for occupancy metric, keep raw counts for others
                if metric_type == 'hotel_occupancy_pct':
                    otb_value = (otb_raw / total_rooms) * 100 if total_rooms > 0 else 0
                    # Use 'is not None' check - 0 is valid data (no bookings at that lead time)
                    prior_otb_value = (prior_hotel_otb / total_rooms) * 100 if prior_hotel_otb is not None and total_rooms > 0 else None
                elif metric_type == 'hotel_room_nights':
                    otb_value = otb_raw  # Raw room count
                    prior_otb_value = prior_hotel_otb  # Raw room count from prior year
                else:
                    otb_value = otb_raw
                    prior_otb_value = None  # Will try historical snapshots below

                # Get prior year ACTUAL from daily_metrics (the final outcome)
                prior_final_result = db.execute(
                    text("""
                    SELECT actual_value
                    FROM daily_metrics
                    WHERE date = :prior_date AND metric_code = :metric
                    """),
                    {"prior_date": prior_year_stay_date, "metric": metric_type}
                ).fetchone()
                prior_final = float(prior_final_result.actual_value) if prior_final_result and prior_final_result.actual_value else None

                # Use reconstructed prior year OTB for hotel metrics, or try historical snapshots
                if metric_type in ('hotel_occupancy_pct', 'hotel_room_nights') and prior_otb_value is not None:
                    prior_otb = prior_otb_value
                else:
                    # For restaurant metrics, fall back to historical snapshots
                    prior_otb_result = db.execute(
                        text("""
                        SELECT otb_value
                        FROM pickup_snapshots
                        WHERE stay_date = :prior_stay_date
                            AND metric_type = :metric
                            AND days_out = :days_out
                        ORDER BY snapshot_date DESC LIMIT 1
                        """),
                        {"prior_stay_date": prior_year_stay_date, "metric": metric_type, "days_out": days_out}
                    ).fetchone()
                    # Use 'is not None' - 0 is valid OTB data
                    prior_otb = float(prior_otb_result.otb_value) if prior_otb_result and prior_otb_result.otb_value is not None else None

                # Calculate pace vs prior year if we have comparison data
                pace_pct = None
                if prior_otb and prior_otb > 0:
                    pace_pct = ((otb_value - prior_otb) / prior_otb) * 100

                db.execute(
                    text("""
                    INSERT INTO pickup_snapshots (
                        snapshot_date, stay_date, days_out, metric_type,
                        otb_value, otb_bookings, prior_year_otb, prior_year_final,
                        pace_vs_prior_pct, created_at
                    ) VALUES (
                        :snapshot_date, :stay_date, :days_out, :metric_type,
                        :otb_value, :otb_bookings, :prior_year_otb, :prior_year_final,
                        :pace_pct, NOW()
                    )
                    ON CONFLICT (snapshot_date, stay_date, metric_type) DO UPDATE SET
                        otb_value = :otb_value,
                        prior_year_otb = :prior_year_otb,
                        pace_vs_prior_pct = :pace_pct
                    """),
                    {
                        "snapshot_date": snapshot_date,
                        "stay_date": stay_date,
                        "days_out": days_out,
                        "metric_type": metric_type,
                        "otb_value": round(otb_value, 2),  # % for hotel, covers for restaurant
                        "otb_bookings": otb_raw,  # Raw count (rooms or covers)
                        "prior_year_otb": round(prior_otb, 2) if prior_otb is not None else None,
                        "prior_year_final": prior_final,
                        "pace_pct": round(pace_pct, 2) if pace_pct else None
                    }
                )

        db.commit()
        logger.info(f"Pickup snapshot completed for {snapshot_date}")

    except Exception as e:
        logger.error(f"Pickup snapshot failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()
