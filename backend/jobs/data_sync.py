"""
Data sync job - pulls data from Newbook and Resos APIs
"""
import logging
from datetime import date, timedelta
from typing import Optional

from database import SyncSessionLocal
from services.newbook_client import NewbookClient
from services.resos_client import ResosClient

logger = logging.getLogger(__name__)


async def run_data_sync(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    triggered_by: str = "scheduler"
):
    """
    Main data sync job - runs both Newbook and Resos sync.
    """
    if from_date is None:
        from_date = date.today() - timedelta(days=7)
    if to_date is None:
        to_date = date.today() + timedelta(days=365)

    logger.info(f"Starting data sync from {from_date} to {to_date}")

    try:
        # Sync Newbook data
        await sync_newbook_data(from_date, to_date, triggered_by)

        # Sync Resos data
        await sync_resos_data(from_date, to_date, triggered_by)

        logger.info("Data sync completed successfully")
    except Exception as e:
        logger.error(f"Data sync failed: {e}")
        raise


async def sync_newbook_data(
    from_date: date,
    to_date: date,
    triggered_by: str = "scheduler"
):
    """
    Sync hotel bookings and occupancy data from Newbook.
    """
    logger.info(f"Starting Newbook sync from {from_date} to {to_date}")

    db = next(iter([SyncSessionLocal()]))

    try:
        # Log sync start
        db.execute(
            """
            INSERT INTO sync_log (sync_type, source, started_at, status, date_from, date_to, triggered_by)
            VALUES ('bookings', 'newbook', NOW(), 'running', :from_date, :to_date, :triggered_by)
            RETURNING id
            """,
            {"from_date": from_date, "to_date": to_date, "triggered_by": triggered_by}
        )
        db.commit()

        async with NewbookClient() as client:
            # Test connection
            if not await client.test_connection():
                raise Exception("Newbook connection failed")

            # Fetch bookings
            bookings = await client.get_bookings(from_date, to_date)
            logger.info(f"Fetched {len(bookings)} bookings from Newbook")

            records_created = 0
            records_updated = 0

            for booking in bookings:
                # Upsert booking
                result = db.execute(
                    """
                    INSERT INTO newbook_bookings (
                        newbook_id, booking_reference, arrival_date, departure_date,
                        nights, adults, children, infants, total_guests,
                        room_type, status, total_amount, tariff_name,
                        booking_source_name, fetched_at
                    ) VALUES (
                        :newbook_id, :reference, :arrival, :departure,
                        :nights, :adults, :children, :infants, :total_guests,
                        :room_type, :status, :total, :tariff_name,
                        :source, NOW()
                    )
                    ON CONFLICT (newbook_id) DO UPDATE SET
                        status = :status,
                        total_amount = :total,
                        fetched_at = NOW()
                    """,
                    {
                        "newbook_id": booking.get("id"),
                        "reference": booking.get("reference"),
                        "arrival": booking.get("booking_arrival"),
                        "departure": booking.get("booking_departure"),
                        "nights": booking.get("booking_length"),
                        "adults": booking.get("booking_adults", 0),
                        "children": booking.get("booking_children", 0),
                        "infants": booking.get("booking_infants", 0),
                        "total_guests": booking.get("booking_adults", 0) + booking.get("booking_children", 0),
                        "room_type": booking.get("category_name"),
                        "status": booking.get("status"),
                        "total": booking.get("total"),
                        "tariff_name": booking.get("tariff_name"),
                        "source": booking.get("booking_source_name")
                    }
                )

                if result.rowcount > 0:
                    records_created += 1

            db.commit()

            # Update sync log
            db.execute(
                """
                UPDATE sync_log
                SET completed_at = NOW(), status = 'success',
                    records_fetched = :fetched, records_created = :created
                WHERE source = 'newbook' AND status = 'running'
                ORDER BY started_at DESC LIMIT 1
                """,
                {"fetched": len(bookings), "created": records_created}
            )
            db.commit()

        logger.info(f"Newbook sync completed: {records_created} records processed")

    except Exception as e:
        logger.error(f"Newbook sync failed: {e}")
        db.execute(
            """
            UPDATE sync_log
            SET completed_at = NOW(), status = 'failed', error_message = :error
            WHERE source = 'newbook' AND status = 'running'
            ORDER BY started_at DESC LIMIT 1
            """,
            {"error": str(e)}
        )
        db.commit()
        raise
    finally:
        db.close()


async def sync_resos_data(
    from_date: date,
    to_date: date,
    triggered_by: str = "scheduler"
):
    """
    Sync restaurant bookings from Resos.
    """
    logger.info(f"Starting Resos sync from {from_date} to {to_date}")

    db = next(iter([SyncSessionLocal()]))

    try:
        # Log sync start
        db.execute(
            """
            INSERT INTO sync_log (sync_type, source, started_at, status, date_from, date_to, triggered_by)
            VALUES ('bookings', 'resos', NOW(), 'running', :from_date, :to_date, :triggered_by)
            """,
            {"from_date": from_date, "to_date": to_date, "triggered_by": triggered_by}
        )
        db.commit()

        async with ResosClient() as client:
            # Test connection
            if not await client.test_connection():
                raise Exception("Resos connection failed")

            # Fetch bookings
            bookings = await client.get_bookings(from_date, to_date)
            logger.info(f"Fetched {len(bookings)} bookings from Resos")

            records_created = 0

            for booking in bookings:
                # Parse guest info
                guest = booking.get("guest", {})

                # Upsert booking
                db.execute(
                    """
                    INSERT INTO resos_bookings (
                        resos_id, booking_date, booking_time, covers,
                        status, source, guest_name, guest_email,
                        opening_hour_id, notes, fetched_at
                    ) VALUES (
                        :resos_id, :booking_date, :booking_time, :covers,
                        :status, :source, :guest_name, :guest_email,
                        :opening_hour_id, :notes, NOW()
                    )
                    ON CONFLICT (resos_id) DO UPDATE SET
                        status = :status,
                        covers = :covers,
                        fetched_at = NOW()
                    """,
                    {
                        "resos_id": booking.get("_id"),
                        "booking_date": booking.get("date"),
                        "booking_time": booking.get("time"),
                        "covers": booking.get("people"),
                        "status": booking.get("status"),
                        "source": booking.get("source"),
                        "guest_name": guest.get("name"),
                        "guest_email": guest.get("email"),
                        "opening_hour_id": booking.get("openingHourId"),
                        "notes": str(booking.get("restaurantNotes", []))
                    }
                )
                records_created += 1

            db.commit()

            # Update sync log
            db.execute(
                """
                UPDATE sync_log
                SET completed_at = NOW(), status = 'success',
                    records_fetched = :fetched, records_created = :created
                WHERE source = 'resos' AND status = 'running'
                ORDER BY started_at DESC LIMIT 1
                """,
                {"fetched": len(bookings), "created": records_created}
            )
            db.commit()

        logger.info(f"Resos sync completed: {records_created} records processed")

    except Exception as e:
        logger.error(f"Resos sync failed: {e}")
        db.execute(
            """
            UPDATE sync_log
            SET completed_at = NOW(), status = 'failed', error_message = :error
            WHERE source = 'resos' AND status = 'running'
            ORDER BY started_at DESC LIMIT 1
            """,
            {"error": str(e)}
        )
        db.commit()
        raise
    finally:
        db.close()
