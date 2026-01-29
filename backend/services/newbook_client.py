"""
Newbook API Client

CRITICAL: This client is READ-ONLY. All methods use GET/POST for reading only.
NO data is written, modified, or deleted in Newbook.
Data flows ONE WAY: Newbook → Local Database
"""
import os
import httpx
import asyncio
import logging
from datetime import date, timedelta
from typing import Optional, List

logger = logging.getLogger(__name__)


class NewbookAPIError(Exception):
    """Custom exception for Newbook API errors"""
    pass


class NewbookClient:
    """
    Async client for Newbook REST API

    Rate limiting: ~100 requests/min, using 0.75s delay between requests
    Pagination: Uses data_offset/data_limit, max 1000 per request
    """

    BASE_URL = "https://api.newbook.cloud/rest/"

    def __init__(self, api_key: str = None, username: str = None, password: str = None, region: str = None):
        # Use provided credentials or fall back to environment variables
        self.api_key = api_key or os.getenv("NEWBOOK_API_KEY")
        self.username = username or os.getenv("NEWBOOK_USERNAME")
        self.password = password or os.getenv("NEWBOOK_PASSWORD")
        self.region = region or os.getenv("NEWBOOK_REGION")

        if not all([self.api_key, self.username, self.password, self.region]):
            logger.warning("Newbook credentials not fully configured")

    @classmethod
    async def from_db(cls, db):
        """Create client with credentials from database"""
        from api.config import _get_config_value

        api_key = await _get_config_value(db, "newbook_api_key")
        username = await _get_config_value(db, "newbook_username")
        password = await _get_config_value(db, "newbook_password")
        region = await _get_config_value(db, "newbook_region")

        return cls(api_key=api_key, username=username, password=password, region=region)

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=60.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    def _get_auth_payload(self) -> dict:
        """Get base authentication payload"""
        return {
            "api_key": self.api_key,
            "username": self.username,
            "password": self.password,
            "region": self.region
        }

    async def test_connection(self) -> bool:
        """Test API connection"""
        try:
            payload = self._get_auth_payload()
            payload["action"] = "site_list"

            response = await self.client.post(
                self.BASE_URL,
                json=payload,
                auth=(self.username, self.password)
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Newbook connection test failed: {e}")
            return False

    async def get_bookings(
        self,
        from_date: date,
        to_date: date,
        batch_size: int = 1000
    ) -> List[dict]:
        """
        Fetch bookings for date range with pagination and rate limiting

        Args:
            from_date: Start date
            to_date: End date
            batch_size: Records per request (max 1000)

        Returns:
            List of booking objects
        """
        all_bookings = []
        offset = 0

        while True:
            logger.info(f"Fetching Newbook bookings: {from_date} to {to_date} (offset: {offset})")

            payload = self._get_auth_payload()
            payload.update({
                "action": "booking_search",
                "period_from": from_date.isoformat(),
                "period_to": to_date.isoformat(),
                "include_inventory_items": True,
                "include_tariffs": True,
                "data_offset": offset,
                "data_limit": batch_size
            })

            response = await self.client.post(
                self.BASE_URL,
                json=payload,
                auth=(self.username, self.password)
            )

            if response.status_code != 200:
                logger.error(f"Newbook API error {response.status_code}: {response.text}")
                raise NewbookAPIError(f"Failed to fetch bookings: {response.status_code}")

            data = response.json()

            if not data.get("success"):
                raise NewbookAPIError(f"Newbook API returned failure: {data.get('message')}")

            bookings = data.get("data", [])

            if not bookings:
                break

            all_bookings.extend(bookings)
            logger.info(f"Fetched {len(bookings)} bookings (offset {offset})")

            # Check if we've got all records
            total = data.get("data_total", 0)
            if offset + len(bookings) >= total:
                break

            offset += batch_size

            # Rate limiting: 0.75s delay
            await asyncio.sleep(0.75)

        logger.info(f"Total bookings fetched: {len(all_bookings)}")
        return all_bookings

    async def get_occupancy_report(
        self,
        from_date: date,
        to_date: date
    ) -> dict:
        """
        Fetch occupancy report for date range

        Returns dict keyed by date with occupancy data
        """
        logger.info(f"Fetching occupancy report: {from_date} to {to_date}")

        payload = self._get_auth_payload()
        payload.update({
            "action": "report_booking_occupancy",
            "period_from": from_date.isoformat(),
            "period_to": to_date.isoformat()
        })

        response = await self.client.post(
            self.BASE_URL,
            json=payload,
            auth=(self.username, self.password)
        )

        if response.status_code != 200:
            raise NewbookAPIError(f"Failed to fetch occupancy: {response.status_code}")

        data = response.json()

        if not data.get("success"):
            raise NewbookAPIError(f"Newbook API returned failure: {data.get('message')}")

        return data.get("data", {})

    async def get_site_list(self) -> List[dict]:
        """Fetch list of rooms/sites with categories"""
        payload = self._get_auth_payload()
        payload["action"] = "site_list"

        response = await self.client.post(
            self.BASE_URL,
            json=payload,
            auth=(self.username, self.password)
        )

        if response.status_code != 200:
            raise NewbookAPIError(f"Failed to fetch site list: {response.status_code}")

        data = response.json()
        return data.get("data", [])

    async def get_earned_revenue(
        self,
        from_date: date,
        to_date: date
    ) -> dict:
        """
        Fetch earned revenue report day by day

        Returns dict keyed by date with revenue breakdown by GL code
        """
        all_revenue = {}
        current_date = from_date

        while current_date <= to_date:
            logger.info(f"Fetching earned revenue for {current_date}")

            payload = self._get_auth_payload()
            payload.update({
                "action": "report_earned_revenue",
                "period_from": current_date.isoformat(),
                "period_to": current_date.isoformat()
            })

            response = await self.client.post(
                self.BASE_URL,
                json=payload,
                auth=(self.username, self.password)
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    all_revenue[current_date.isoformat()] = data.get("data", {})

            current_date += timedelta(days=1)

            # Rate limiting
            await asyncio.sleep(0.75)

        return all_revenue
