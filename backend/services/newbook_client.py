"""
Newbook API Client

CRITICAL: This client is READ-ONLY.
Newbook API uses POST for all requests - the "action" parameter determines the operation.
This client ONLY uses read actions (bookings_list, site_list, report_*).
NO write actions (booking_create, booking_update, booking_cancel, etc.) are used.
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

    BASE_URL = "https://api.newbook.cloud/rest"

    def __init__(self, api_key: str = None, username: str = None, password: str = None, region: str = None):
        # Use provided credentials or fall back to environment variables
        self.api_key = api_key or os.getenv("NEWBOOK_API_KEY")
        self.username = username or os.getenv("NEWBOOK_USERNAME")
        self.password = password or os.getenv("NEWBOOK_PASSWORD")
        self.region = region or os.getenv("NEWBOOK_REGION")

        if not all([self.api_key, self.username, self.password, self.region]):
            logger.warning("Newbook credentials not fully configured")

    def _get_url(self, endpoint: str) -> str:
        """Get full URL for an endpoint"""
        return f"{self.BASE_URL}/{endpoint}"

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
        """Get base authentication payload (api_key and region only - username/password go in Basic Auth)"""
        return {
            "api_key": self.api_key,
            "region": self.region
        }

    async def test_connection(self) -> bool:
        """Test API connection"""
        try:
            payload = self._get_auth_payload()

            response = await self.client.post(
                self._get_url("site_list"),
                json=payload,
                auth=(self.username, self.password)
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Newbook connection test failed: {e}")
            return False

    async def get_bookings(
        self,
        modified_since: Optional[str] = None,
        modified_until: Optional[str] = None,
        batch_size: int = 1000
    ) -> List[dict]:
        """
        Fetch all bookings with pagination and rate limiting.

        Uses list_type="all" which returns all bookings (including cancelled).
        period_from/period_to filter by created/modified timestamp, not stay dates.

        Args:
            modified_since: ISO timestamp - only bookings created/modified after this
            modified_until: ISO timestamp - only bookings created/modified before this
            batch_size: Records per request (max 1000)

        Returns:
            List of booking objects (all statuses including cancelled)
        """
        all_bookings = []
        offset = 0

        while True:
            logger.info(f"Fetching Newbook bookings (all): modified_since={modified_since} (offset: {offset})")

            payload = self._get_auth_payload()
            payload.update({
                "list_type": "all",
                "data_offset": offset,
                "data_limit": batch_size
            })

            # Add optional timestamp filters
            if modified_since:
                payload["period_from"] = modified_since
            if modified_until:
                payload["period_to"] = modified_until

            response = await self.client.post(
                self._get_url("bookings_list"),
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

    async def get_bookings_by_stay_dates(
        self,
        from_date: date,
        to_date: date,
        list_type: str = "staying",
        batch_size: int = 1000
    ) -> List[dict]:
        """
        Fetch bookings by stay dates (arrival/departure/staying period).

        Args:
            from_date: Start date for stay period
            to_date: End date for stay period
            list_type: Type of booking list:
                       "staying" - bookings staying during dates (excludes cancelled)
                       "arrived" - arrived during dates (add mode="projected" for expected)
                       "arriving" - expected to arrive before period_to
                       "departed" - departed during dates
                       "departing" - expected to depart during dates
                       "cancelled" - cancelled during dates
                       "placed" - created during dates
                       "no_show" - no shows for dates
            batch_size: Records per request (max 1000)

        Returns:
            List of booking objects
        """
        all_bookings = []
        offset = 0

        while True:
            logger.info(f"Fetching Newbook bookings ({list_type}): {from_date} to {to_date} (offset: {offset})")

            payload = self._get_auth_payload()
            payload.update({
                "list_type": list_type,
                "period_from": from_date.isoformat(),
                "period_to": to_date.isoformat(),
                "data_offset": offset,
                "data_limit": batch_size
            })

            response = await self.client.post(
                self._get_url("bookings_list"),
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
    ) -> List[dict]:
        """
        Fetch occupancy report for date range.

        Uses reports_occupancy endpoint which returns data by room category.
        Returns all categories with nested occupancy data for each date in range.
        No pagination needed - API returns full dataset in single response.

        Response format:
        [
            {
                "category_id": "1",
                "category_name": "Single Room",
                "occupancy": {
                    "2024-08-01": {
                        "date": "2024-08-01",
                        "available": 5,
                        "occupied": 3,
                        "maintenance": 1,
                        "allotted": 0,
                        "revenue_gross": 450.00,
                        "revenue_net": 375.00
                    },
                    ...
                }
            },
            ...
        ]

        Returns list of category objects with nested occupancy by date
        """
        logger.info(f"Fetching occupancy report: {from_date} to {to_date}")

        payload = self._get_auth_payload()
        payload.update({
            "period_from": f"{from_date.isoformat()} 00:00:00",
            "period_to": f"{to_date.isoformat()} 23:59:59"
        })

        response = await self.client.post(
            self._get_url("reports_occupancy"),
            json=payload,
            auth=(self.username, self.password)
        )

        if response.status_code != 200:
            raise NewbookAPIError(f"Failed to fetch occupancy: {response.status_code}")

        data = response.json()

        if not data.get("success"):
            raise NewbookAPIError(f"Newbook API returned failure: {data.get('message')}")

        records = data.get("data", [])
        logger.info(f"Fetched occupancy report: {len(records)} categories")
        return records

    async def get_site_list(self) -> List[dict]:
        """Fetch list of rooms/sites with categories"""
        payload = self._get_auth_payload()

        response = await self.client.post(
            self._get_url("site_list"),
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
                "period_from": current_date.isoformat(),
                "period_to": current_date.isoformat()
            })

            response = await self.client.post(
                self._get_url("reports_earned_revenue"),
                json=payload,
                auth=(self.username, self.password)
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    day_data = data.get("data", {})
                    # Debug: log first day's response structure
                    if current_date == from_date:
                        import json
                        logger.info(f"Sample earned revenue response: {json.dumps(day_data)[:500]}")
                    all_revenue[current_date.isoformat()] = day_data

            current_date += timedelta(days=1)

            # Rate limiting
            await asyncio.sleep(0.75)

        return all_revenue

    async def get_transaction_flow(
        self,
        from_date: date,
        to_date: date,
        batch_size: int = 5000
    ) -> List[dict]:
        """
        Fetch transaction flow report for date range.
        Used by reconciliation module for payment categorization.

        Returns raw transaction records (payments, refunds, voided items).
        Excludes balance_transfer items.
        Handles pagination via data_offset/data_limit.
        """
        logger.info(f"Fetching transaction flow: {from_date} to {to_date}")

        all_transactions = []
        offset = 0

        while True:
            payload = self._get_auth_payload()
            payload.update({
                "period_from": f"{from_date.isoformat()} 00:00:00",
                "period_to": f"{to_date.isoformat()} 23:59:59",
                "data_offset": offset,
                "data_limit": batch_size
            })

            response = await self.client.post(
                self._get_url("reports_transaction_flow"),
                json=payload,
                auth=(self.username, self.password)
            )

            if response.status_code != 200:
                raise NewbookAPIError(f"Failed to fetch transaction flow: {response.status_code}")

            data = response.json()
            if not data.get("success"):
                raise NewbookAPIError(f"Newbook API returned failure: {data.get('message')}")

            records = data.get("data", [])
            all_transactions.extend(records)

            # If we got fewer records than the limit, we're done
            if len(records) < batch_size:
                break

            offset += batch_size
            await asyncio.sleep(0.75)

        logger.info(f"Fetched transaction flow: {len(all_transactions)} transactions")
        return all_transactions

    async def get_gl_account_list(self) -> List[dict]:
        """
        Fetch GL account list from Newbook.
        Used for reconciliation sales breakdown column configuration.
        """
        logger.info("Fetching GL account list from Newbook")

        payload = self._get_auth_payload()

        response = await self.client.post(
            self._get_url("gl_account_list"),
            json=payload,
            auth=(self.username, self.password)
        )

        if response.status_code != 200:
            raise NewbookAPIError(f"Failed to fetch GL accounts: {response.status_code}")

        data = response.json()
        if not data.get("success"):
            raise NewbookAPIError(f"Newbook API returned failure: {data.get('message')}")

        records = data.get("data", [])
        logger.info(f"Fetched {len(records)} GL accounts")
        return records
