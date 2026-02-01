"""
Resos API Client

CRITICAL: This client is READ-ONLY. All methods use GET requests only.
NO data is written, modified, or deleted in Resos.
Data flows ONE WAY: Resos → Local Database
"""
import os
import httpx
import base64
import asyncio
import logging
from datetime import date, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)


class ResosAPIError(Exception):
    """Custom exception for Resos API errors"""
    pass


class ResosClient:
    """
    Async client for Resos API

    Rate limiting: ~60 requests/min, using 1s delay between requests
    Pagination: Uses skip/limit, max 100 per request
    Date filtering: Uses fromDateTime/toDateTime
    """

    BASE_URL = "https://api.resos.com/v1"

    def __init__(self, api_key: str = None):
        # Use provided credentials or fall back to environment variables
        self.api_key = api_key or os.getenv("RESOS_API_KEY")
        if self.api_key:
            # HTTP Basic Auth: base64_encode(api_key + ':')
            self.auth_header = f"Basic {base64.b64encode(f'{self.api_key}:'.encode()).decode()}"
        else:
            self.auth_header = None
            logger.warning("Resos API key not configured")

    @classmethod
    async def from_db(cls, db):
        """Create client with credentials from database"""
        from api.config import _get_config_value

        api_key = await _get_config_value(db, "resos_api_key")
        return cls(api_key=api_key)

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def test_connection(self) -> bool:
        """Test API connection by fetching opening hours"""
        try:
            response = await self.client.get(
                f"{self.BASE_URL}/openingHours",
                headers={"Authorization": self.auth_header}
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Resos connection test failed: {e}")
            return False

    async def get_bookings(
        self,
        from_date: date,
        to_date: date
    ) -> List[dict]:
        """
        Fetch bookings for date range with pagination and rate limiting.

        Returns list of booking objects with structure:
        {
            '_id': 'booking_id',
            'date': '2026-01-20',
            'time': '19:00',
            'people': 2,
            'status': 'confirmed',
            'source': 'website',
            'guest': {...},
            'customFields': [...],
            'restaurantNotes': [...]
        }
        """
        all_bookings = []
        offset = 0

        from_datetime = f"{from_date}T00:00:00"
        to_datetime = f"{to_date}T23:59:59"

        while True:
            logger.info(f"Fetching Resos bookings: {from_date} to {to_date} (offset: {offset})")

            response = await self.client.get(
                f"{self.BASE_URL}/bookings",
                headers={"Authorization": self.auth_header},
                params={
                    "fromDateTime": from_datetime,
                    "toDateTime": to_datetime,
                    "limit": 100,
                    "skip": offset
                }
            )

            if response.status_code != 200:
                error_body = response.text
                logger.error(f"Resos API error {response.status_code}: {error_body}")
                raise ResosAPIError(f"Failed to fetch bookings: {response.status_code} - {error_body}")

            data = response.json()
            page_bookings = data if isinstance(data, list) else []

            if not page_bookings:
                break

            all_bookings.extend(page_bookings)
            logger.info(f"Fetched {len(page_bookings)} bookings (offset {offset})")

            # If we got fewer than the limit, we've reached the end
            if len(page_bookings) < 100:
                break

            offset += 100

            # Rate limiting: 1 request per second
            await asyncio.sleep(1)

        logger.info(f"Total bookings fetched: {len(all_bookings)}")
        return all_bookings

    async def get_opening_hours(self) -> List[dict]:
        """
        Fetch opening hours/service periods

        Returns list of opening hour objects:
        {
            '_id': 'opening_hour_id',
            'name': 'Dinner',
            'startTime': '18:00',
            'endTime': '22:00',
            'days': ['monday', 'tuesday', 'wednesday', ...]
        }
        """
        response = await self.client.get(
            f"{self.BASE_URL}/openingHours",
            headers={"Authorization": self.auth_header},
            params={"showDeleted": "false", "onlySpecial": "false"}
        )

        if response.status_code != 200:
            raise ResosAPIError(f"Failed to fetch opening hours: {response.status_code}")

        return response.json()

    async def get_custom_field_definitions(self) -> List[dict]:
        """
        Fetch custom field definitions

        Returns field definitions with choice options for dropdowns/radios
        """
        response = await self.client.get(
            f"{self.BASE_URL}/customFields",
            headers={"Authorization": self.auth_header}
        )

        if response.status_code != 200:
            raise ResosAPIError(f"Failed to fetch custom fields: {response.status_code}")

        return response.json()
