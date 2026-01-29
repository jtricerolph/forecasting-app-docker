"""
Pickup snapshot job - captures daily on-the-books values
Used by the pickup model for pace comparison
"""
import logging
from datetime import date, timedelta

from database import SyncSessionLocal

logger = logging.getLogger(__name__)


async def run_pickup_snapshot():
    """
    Capture daily on-the-books snapshot for future dates.
    Stores OTB values at various lead times for pickup model.
    """
    logger.info("Starting pickup snapshot capture")

    db = next(iter([SyncSessionLocal()]))
    snapshot_date = date.today()

    try:
        # Capture OTB for next 60 days
        for days_out in range(1, 61):
            stay_date = snapshot_date + timedelta(days=days_out)

            # Get hotel occupancy OTB
            hotel_result = db.execute(
                """
                SELECT COUNT(DISTINCT newbook_id) as bookings,
                       SUM(CASE WHEN status IN ('confirmed', 'provisional') THEN 1 ELSE 0 END) as active_bookings
                FROM newbook_bookings
                WHERE arrival_date <= :stay_date AND departure_date > :stay_date
                    AND status IN ('confirmed', 'provisional')
                """,
                {"stay_date": stay_date}
            )
            hotel_row = hotel_result.fetchone()
            hotel_otb = hotel_row.active_bookings or 0

            # Get dinner covers OTB
            dinner_result = db.execute(
                """
                SELECT COUNT(*) as bookings, COALESCE(SUM(covers), 0) as total_covers
                FROM resos_bookings
                WHERE booking_date = :stay_date
                    AND status IN ('approved', 'confirmed')
                    AND booking_time >= '17:00'
                """,
                {"stay_date": stay_date}
            )
            dinner_row = dinner_result.fetchone()
            dinner_otb = dinner_row.total_covers or 0

            # Get lunch covers OTB
            lunch_result = db.execute(
                """
                SELECT COUNT(*) as bookings, COALESCE(SUM(covers), 0) as total_covers
                FROM resos_bookings
                WHERE booking_date = :stay_date
                    AND status IN ('approved', 'confirmed')
                    AND booking_time < '17:00'
                """,
                {"stay_date": stay_date}
            )
            lunch_row = lunch_result.fetchone()
            lunch_otb = lunch_row.total_covers or 0

            # Get prior year comparison data
            prior_year_stay_date = stay_date - timedelta(days=364)  # Same day of week

            prior_hotel = db.execute(
                """
                SELECT otb_value, projected_final
                FROM pickup_snapshots
                WHERE stay_date = :prior_stay_date
                    AND metric_type = 'hotel_occupancy_pct'
                    AND days_out = :days_out
                ORDER BY snapshot_date DESC LIMIT 1
                """,
                {"prior_stay_date": prior_year_stay_date, "days_out": days_out}
            ).fetchone()

            # Store snapshots
            for metric_type, otb_value in [
                ('hotel_occupancy_pct', hotel_otb),
                ('resos_dinner_covers', dinner_otb),
                ('resos_lunch_covers', lunch_otb)
            ]:
                db.execute(
                    """
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
                    """,
                    {
                        "snapshot_date": snapshot_date,
                        "stay_date": stay_date,
                        "days_out": days_out,
                        "metric_type": metric_type,
                        "otb_value": otb_value,
                        "otb_bookings": hotel_row.bookings if metric_type == 'hotel_occupancy_pct' else None,
                        "prior_year_otb": prior_hotel.otb_value if prior_hotel else None,
                        "prior_year_final": prior_hotel.projected_final if prior_hotel else None,
                        "pace_pct": ((otb_value - prior_hotel.otb_value) / prior_hotel.otb_value * 100)
                                   if prior_hotel and prior_hotel.otb_value else None
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
