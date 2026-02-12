"""
Newbook Rates Client

Fetches current rack rates from Newbook API for revenue forecasting.
Uses the bookings_availability_pricing endpoint to simulate booking requests.

This client is READ-ONLY - it only queries available rates, never creates bookings.
"""
import os
import httpx
import asyncio
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class NewbookRatesError(Exception):
    """Custom exception for Newbook rates API errors"""
    pass


class NewbookRatesClient:
    """
    Async client for fetching current rates from Newbook API.

    Uses bookings_availability_pricing endpoint which simulates a booking request.
    Handles minimum stay restrictions by extending the stay period when needed.

    Rate limiting: ~100 requests/min, using 0.75s delay between requests
    """

    BASE_URL = "https://api.newbook.cloud/rest"

    def __init__(self, api_key: str = None, username: str = None, password: str = None,
                 region: str = None, vat_rate: Decimal = Decimal('0.20')):
        self.api_key = api_key or os.getenv("NEWBOOK_API_KEY")
        self.username = username or os.getenv("NEWBOOK_USERNAME")
        self.password = password or os.getenv("NEWBOOK_PASSWORD")
        self.region = region or os.getenv("NEWBOOK_REGION")
        self.vat_rate = vat_rate

        if not all([self.api_key, self.username, self.password, self.region]):
            logger.warning("Newbook credentials not fully configured")

    def _get_url(self, endpoint: str) -> str:
        """Get full URL for an endpoint"""
        return f"{self.BASE_URL}/{endpoint}"

    @classmethod
    async def from_db(cls, db):
        """Create client with credentials and VAT rate from database"""
        from sqlalchemy import text

        # Get credentials from config
        result = await db.execute(
            text("SELECT config_key, config_value FROM system_config WHERE config_key IN ('newbook_api_key', 'newbook_username', 'newbook_password', 'newbook_region', 'accommodation_vat_rate')")
        )
        rows = result.fetchall()
        config = {row.config_key: row.config_value for row in rows}

        vat_rate = Decimal(config.get('accommodation_vat_rate', '0.20'))

        return cls(
            api_key=config.get('newbook_api_key'),
            username=config.get('newbook_username'),
            password=config.get('newbook_password'),
            region=config.get('newbook_region'),
            vat_rate=vat_rate
        )

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=60.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    def _get_auth_payload(self) -> dict:
        """Get base authentication payload"""
        return {
            "api_key": self.api_key,
            "region": self.region
        }

    async def get_category_rates(
        self,
        category_id: str,
        from_date: date,
        to_date: date,
        guests_adults: int = 2,
        guests_children: int = 0
    ) -> List[Dict]:
        """
        Fetch current rates for a category over a date range.

        Uses daily=true to get per-night rates. Handles minimum stay
        restrictions by extending the period when needed.

        Args:
            category_id: Newbook category ID
            from_date: Start date for rates
            to_date: End date for rates (inclusive)
            guests_adults: Number of adult guests (default 2)
            guests_children: Number of child guests (default 0)

        Returns:
            List of dicts with {date, gross_rate, net_rate}
        """
        rates = []
        current_date = from_date

        while current_date <= to_date:
            try:
                # Fetch rates for up to 7 days at a time to optimize API calls
                batch_end = min(current_date + timedelta(days=6), to_date)
                batch_rates = await self._fetch_rates_batch(
                    category_id, current_date, batch_end, guests_adults, guests_children
                )
                rates.extend(batch_rates)

                # Move to next batch
                current_date = batch_end + timedelta(days=1)

            except Exception as e:
                logger.error(f"Failed to fetch rates for category {category_id} starting {current_date}: {e}")
                # Skip this batch and continue
                current_date = current_date + timedelta(days=7)

            # Rate limiting - ALWAYS wait 1.5s between requests, even after errors
            await asyncio.sleep(1.5)

        return rates

    async def get_single_night_rates(
        self,
        category_id: str,
        from_date: date,
        to_date: date,
        guests_adults: int = 2,
        guests_children: int = 0
    ) -> List[Dict]:
        """
        Fetch rates with single-night queries for accurate per-day tariff availability.

        Unlike get_category_rates which batches, this queries each date individually
        as a 1-night stay. This gives accurate tariff_success per night, catching
        issues like Valentine's Day blocking only that night, not a whole week.

        Much slower but necessary for accurate bookability data.

        Args:
            category_id: Newbook category ID
            from_date: Start date for rates
            to_date: End date for rates (inclusive)
            guests_adults: Number of adult guests (default 2)
            guests_children: Number of child guests (default 0)

        Returns:
            List of dicts with {date, gross_rate, net_rate, tariffs_data}
        """
        rates = []
        current_date = from_date

        while current_date <= to_date:
            try:
                # Single-night query for accurate tariff availability
                batch_rates = await self._fetch_rates_batch(
                    category_id, current_date, current_date, guests_adults, guests_children
                )
                rates.extend(batch_rates)

            except Exception as e:
                logger.warning(f"Failed to fetch single-night rate for {category_id} on {current_date}: {e}")
                # Continue with next date

            current_date += timedelta(days=1)

            # Rate limiting - wait between each single-night query
            await asyncio.sleep(1.0)

        return rates

    async def fetch_single_date_all_categories(
        self,
        for_date: date,
        guests_adults: int = 2,
        guests_children: int = 0
    ) -> Dict[str, List[Dict]]:
        """
        Fetch single-night rates for ALL categories for one date.

        Returns:
            Dict of {category_id: [{date, gross_rate, net_rate, tariffs_data}]}
        """
        return await self._fetch_all_categories_batch(
            for_date, guests_adults, guests_children
        )

    async def fetch_multi_night_for_date(
        self,
        for_date: date,
        nights: int,
        guests_adults: int = 2,
        guests_children: int = 0
    ) -> Dict[str, Dict[str, bool]]:
        """
        Fetch multi-night availability for ALL categories for one date.

        Returns:
            Dict of {category_id: {tariff_name: available}}
        """
        return await self._fetch_all_categories_multi_night(
            for_date, nights, guests_adults, guests_children
        )

    async def get_all_categories_single_night_rates(
        self,
        from_date: date,
        to_date: date,
        guests_adults: int = 2,
        guests_children: int = 0
    ) -> Dict[str, List[Dict]]:
        """
        Fetch rates for ALL categories with single-night queries.

        More efficient than get_single_night_rates - omits category_id to get
        all categories in a single API call per date. This reduces API calls
        from (categories × days) to just (days).

        Args:
            from_date: Start date for rates
            to_date: End date for rates (inclusive)
            guests_adults: Number of adult guests (default 2)
            guests_children: Number of child guests (default 0)

        Returns:
            Dict of {category_id: [{date, gross_rate, net_rate, tariffs_data}, ...]}
        """
        all_rates: Dict[str, List[Dict]] = {}
        current_date = from_date
        total_days = (to_date - from_date).days + 1
        day_count = 0

        while current_date <= to_date:
            day_count += 1
            try:
                # Single-night query WITHOUT category_id - returns ALL categories
                category_rates = await self._fetch_all_categories_batch(
                    current_date, guests_adults, guests_children
                )

                # Merge into all_rates dict
                for cat_id, rates in category_rates.items():
                    if cat_id not in all_rates:
                        all_rates[cat_id] = []
                    all_rates[cat_id].extend(rates)

                logger.info(f"Fetched {current_date} ({day_count}/{total_days}) - {len(category_rates)} categories")

            except Exception as e:
                logger.warning(f"Failed to fetch rates for {current_date}: {e}")
                # Continue with next date

            current_date += timedelta(days=1)

            # Rate limiting - wait between each query
            await asyncio.sleep(1.0)

        return all_rates

    async def _fetch_all_categories_batch(
        self,
        for_date: date,
        guests_adults: int,
        guests_children: int,
        retry_count: int = 0
    ) -> Dict[str, List[Dict]]:
        """
        Fetch rates for ALL categories for a single date.

        Omits category_id from request - Newbook returns all available categories.

        Returns:
            Dict of {category_id: [{date, gross_rate, net_rate, tariffs_data}]}
        """
        # Single-night query
        period_from = f"{for_date.isoformat()} 14:00:00"
        period_to = f"{(for_date + timedelta(days=1)).isoformat()} 10:00:00"

        payload = self._get_auth_payload()
        payload.update({
            "period_from": period_from,
            "period_to": period_to,
            "adults": guests_adults,
            "children": guests_children,
            "infants": 0,
            "daily_mode": "true"
            # NO category_id - returns all categories
        })

        response = await self.client.post(
            self._get_url("bookings_availability_pricing"),
            json=payload,
            auth=(self.username, self.password)
        )

        # Handle rate limiting with exponential backoff
        if response.status_code == 429:
            if retry_count < 3:
                wait_time = 60 * (retry_count + 1)
                logger.warning(f"Rate limited by Newbook API, waiting {wait_time}s before retry {retry_count + 1}/3")
                await asyncio.sleep(wait_time)
                return await self._fetch_all_categories_batch(
                    for_date, guests_adults, guests_children, retry_count + 1
                )
            else:
                raise NewbookRatesError(f"Rate limited after 3 retries")

        if response.status_code != 200:
            raise NewbookRatesError(f"API error {response.status_code}: {response.text}")

        data = response.json()

        if not data.get("success"):
            raise NewbookRatesError(f"API returned failure: {data.get('message')}")

        # Parse all categories from response
        return self._parse_all_categories_tariffs(data, for_date)

    async def _fetch_all_categories_multi_night(
        self,
        for_date: date,
        nights: int,
        guests_adults: int = 2,
        guests_children: int = 0,
        retry_count: int = 0
    ) -> Dict[str, Dict[str, bool]]:
        """
        Fetch multi-night availability for ALL categories for a specific date.

        Used to verify that rates with min_stay requirements are actually bookable.

        Args:
            for_date: Check-in date
            nights: Number of nights to query (e.g., 2 for min_stay=2)
            guests_adults: Number of adult guests
            guests_children: Number of child guests

        Returns:
            Dict of {category_id: {tariff_name: available}}
        """
        # Multi-night query
        period_from = f"{for_date.isoformat()} 14:00:00"
        period_to = f"{(for_date + timedelta(days=nights)).isoformat()} 10:00:00"

        payload = self._get_auth_payload()
        payload.update({
            "period_from": period_from,
            "period_to": period_to,
            "adults": guests_adults,
            "children": guests_children,
            "infants": 0,
            "daily_mode": "true"
        })

        response = await self.client.post(
            self._get_url("bookings_availability_pricing"),
            json=payload,
            auth=(self.username, self.password)
        )

        # Handle rate limiting
        if response.status_code == 429:
            if retry_count < 3:
                wait_time = 60 * (retry_count + 1)
                logger.warning(f"Rate limited (multi-night), waiting {wait_time}s")
                await asyncio.sleep(wait_time)
                return await self._fetch_all_categories_multi_night(
                    for_date, nights, guests_adults, guests_children, retry_count + 1
                )
            else:
                raise NewbookRatesError(f"Rate limited after 3 retries")

        if response.status_code != 200:
            raise NewbookRatesError(f"API error {response.status_code}: {response.text}")

        data = response.json()

        if not data.get("success"):
            raise NewbookRatesError(f"API returned failure: {data.get('message')}")

        # Parse availability by tariff name for each category
        results: Dict[str, Dict[str, bool]] = {}

        if not isinstance(data.get("data"), dict):
            return results

        for key, cat_data in data["data"].items():
            if not (key.isdigit() or str(key).isnumeric()):
                continue
            if not isinstance(cat_data, dict):
                continue

            category_id = str(key)
            tariffs_available = cat_data.get("tariffs_available", [])

            results[category_id] = {}
            for tariff in tariffs_available:
                tariff_name = tariff.get("tariff_name", "")
                tariff_label = tariff.get("tariff_label", "")
                # Check tariff_success (API returns string "true"/"false")
                tariff_success = str(tariff.get("tariff_success", False)).lower() in ("true", "1")
                # Available if API says success, OR if rates are quoted and no restriction message
                is_available = tariff_success or (
                    bool(tariff.get("tariffs_quoted")) and not tariff.get("tariff_message")
                )
                # Store under both tariff_name and tariff_label for flexible matching
                results[category_id][tariff_name] = is_available
                if tariff_label and tariff_label != tariff_name:
                    results[category_id][tariff_label] = is_available

        return results

    async def get_multi_night_availability(
        self,
        dates_by_nights: Dict[int, List[date]],
        guests_adults: int = 2,
        guests_children: int = 0
    ) -> Dict[date, Dict[str, Dict[str, bool]]]:
        """
        Fetch multi-night availability for specific dates grouped by stay length.

        Checks if a tariff is available when booking N nights starting from each date.

        Args:
            dates_by_nights: Dict of {nights: [dates]} e.g., {2: [date1, date2], 3: [date3]}
            guests_adults: Number of adult guests
            guests_children: Number of child guests

        Returns:
            Dict of {date: {category_id: {tariff_name: available}}}
        """
        results: Dict[date, Dict[str, Dict[str, bool]]] = {}

        total_queries = sum(len(dates) for dates in dates_by_nights.values())
        query_count = 0

        for nights, dates in dates_by_nights.items():
            for query_date in dates:
                query_count += 1

                try:
                    result = await self._fetch_all_categories_multi_night(
                        query_date, nights, guests_adults, guests_children
                    )
                    results[query_date] = result
                    logger.info(f"Multi-night check {query_count}/{total_queries}: {query_date} ({nights} nights)")
                except Exception as e:
                    logger.warning(f"Failed multi-night check for {query_date}: {e}")

                # Rate limiting
                await asyncio.sleep(1.0)

        return results

    async def _fetch_rates_batch(
        self,
        category_id: str,
        from_date: date,
        to_date: date,
        guests_adults: int,
        guests_children: int,
        retry_count: int = 0
    ) -> List[Dict]:
        """
        Fetch rates for a batch of dates (up to 7 days).

        Handles minimum stay restrictions by extending the period and
        extracting only the dates we need.

        Returns:
            List of dicts with {date, gross_rate, net_rate}
        """
        # Format dates with times (check-in 14:00, check-out 10:00)
        period_from = f"{from_date.isoformat()} 14:00:00"
        period_to = f"{(to_date + timedelta(days=1)).isoformat()} 10:00:00"

        payload = self._get_auth_payload()
        payload.update({
            "period_from": period_from,
            "period_to": period_to,
            "adults": guests_adults,
            "children": guests_children,
            "infants": 0,
            "category_id": category_id,
            "daily_mode": "true"  # Get per-night breakdown
        })

        response = await self.client.post(
            self._get_url("bookings_availability_pricing"),
            json=payload,
            auth=(self.username, self.password)
        )

        # Handle rate limiting with exponential backoff
        if response.status_code == 429:
            if retry_count < 3:
                wait_time = 60 * (retry_count + 1)  # 60s, 120s, 180s
                logger.warning(f"Rate limited by Newbook API, waiting {wait_time}s before retry {retry_count + 1}/3")
                await asyncio.sleep(wait_time)
                return await self._fetch_rates_batch(
                    category_id, from_date, to_date, guests_adults, guests_children, retry_count + 1
                )
            else:
                raise NewbookRatesError(f"Rate limited after 3 retries")

        if response.status_code != 200:
            raise NewbookRatesError(f"API error {response.status_code}: {response.text}")

        data = response.json()

        if not data.get("success"):
            # Check if minimum stay restriction
            categories = data.get("data", {}).get("categories", [])
            if categories:
                cat = categories[0] if isinstance(categories, list) else categories.get(category_id, {})
                min_periods = cat.get("minimum_periods", 1)

                if min_periods > 1:
                    # Extend the stay to meet minimum and retry
                    extended_to = from_date + timedelta(days=min_periods)
                    logger.info(f"Minimum stay {min_periods} nights for category {category_id}, extending to {extended_to}")
                    return await self._fetch_rates_with_min_stay(
                        category_id, from_date, to_date, extended_to,
                        guests_adults, guests_children
                    )

            raise NewbookRatesError(f"API returned failure: {data.get('message')}")

        # Parse tariffs_quoted from response
        return self._parse_tariffs(data, from_date, to_date)

    async def _fetch_rates_with_min_stay(
        self,
        category_id: str,
        from_date: date,
        to_date: date,
        extended_to: date,
        guests_adults: int,
        guests_children: int,
        retry_count: int = 0
    ) -> List[Dict]:
        """
        Fetch rates with extended period for minimum stay requirement.

        Args:
            category_id: Newbook category ID
            from_date: Original start date
            to_date: Original end date (dates we want)
            extended_to: Extended end date to meet minimum stay
            guests_adults: Number of adults
            guests_children: Number of children

        Returns:
            List of rates for the original date range only
        """
        period_from = f"{from_date.isoformat()} 14:00:00"
        period_to = f"{(extended_to + timedelta(days=1)).isoformat()} 10:00:00"

        payload = self._get_auth_payload()
        payload.update({
            "period_from": period_from,
            "period_to": period_to,
            "adults": guests_adults,
            "children": guests_children,
            "infants": 0,
            "category_id": category_id,
            "daily_mode": "true"
        })

        response = await self.client.post(
            self._get_url("bookings_availability_pricing"),
            json=payload,
            auth=(self.username, self.password)
        )

        # Handle rate limiting with exponential backoff
        if response.status_code == 429:
            if retry_count < 3:
                wait_time = 60 * (retry_count + 1)
                logger.warning(f"Rate limited by Newbook API, waiting {wait_time}s before retry")
                await asyncio.sleep(wait_time)
                return await self._fetch_rates_with_min_stay(
                    category_id, from_date, to_date, extended_to, guests_adults, guests_children, retry_count + 1
                )
            else:
                raise NewbookRatesError(f"Rate limited after 3 retries")

        if response.status_code != 200:
            raise NewbookRatesError(f"API error {response.status_code}: {response.text}")

        data = response.json()

        if not data.get("success"):
            raise NewbookRatesError(f"API returned failure even with extended stay: {data.get('message')}")

        # Parse tariffs but only return dates in our original range
        return self._parse_tariffs(data, from_date, to_date)

    def _parse_tariffs(self, data: dict, from_date: date, to_date: date) -> List[Dict]:
        """
        Parse tariffs from API response.

        With daily_mode=true, the API returns tariffs_quoted as a dict keyed by date.
        Falls back to tariffs_available average if tariffs_quoted not available.

        Args:
            data: Full API response
            from_date: Start date to include
            to_date: End date to include

        Returns:
            List of dicts with {date, gross_rate, net_rate, tariffs_data}
            tariffs_data contains all available tariff options for rate report
        """
        rates = []
        tariffs_quoted = {}
        fallback_rate = None
        inventory_items = []
        all_tariffs_available = []  # Store all tariff options for reporting

        # Find tariffs data in the response
        if isinstance(data.get("data"), dict):
            for key in data["data"].keys():
                # Category IDs are numeric strings
                if key.isdigit() or key.isnumeric():
                    cat_data = data["data"][key]
                    if isinstance(cat_data, dict):
                        tariffs_available = cat_data.get("tariffs_available", [])
                        all_tariffs_available = tariffs_available  # Capture all options
                        if tariffs_available:
                            first_tariff = tariffs_available[0]
                            # tariffs_quoted is a dict keyed by date string
                            tariffs_quoted = first_tariff.get("tariffs_quoted", {})
                            # inventory_items are at tariff level (total for whole stay)
                            inventory_items = first_tariff.get("inventory_items", [])
                            # Fallback average rate
                            fallback_rate = Decimal(str(first_tariff.get('average_nightly_tariff', 0) or 0))
                        break

        # If we have per-night tariffs_quoted dict, parse it
        if isinstance(tariffs_quoted, dict) and tariffs_quoted:
            num_nights = len(tariffs_quoted)

            # Calculate per-night inventory item amount for items already included in tariff
            included_inventory_per_night = Decimal('0')
            for item in inventory_items:
                already_included = item.get('amount_already_included_in_tariff_total', '')
                if str(already_included).lower() == 'true':
                    total_amount = Decimal(str(item.get('amount', 0) or 0))
                    included_inventory_per_night += total_amount / num_nights

            for date_str, tariff in tariffs_quoted.items():
                try:
                    stay_date = date.fromisoformat(date_str)
                except ValueError:
                    continue

                # Only include dates in our range
                if stay_date < from_date or stay_date > to_date:
                    continue

                gross_rate = Decimal(str(tariff.get('amount', 0) or 0))
                # Net = (gross - included_inventory_per_night) / (1 + VAT)
                gross_after_inventory = gross_rate - included_inventory_per_night
                net_rate = (gross_after_inventory / (1 + self.vat_rate)).quantize(Decimal('0.01'))

                # Build tariffs_data with day-specific rates
                tariffs_data = self._build_tariffs_summary(all_tariffs_available, stay_date)

                rates.append({
                    'date': stay_date,
                    'gross_rate': float(gross_rate),
                    'net_rate': float(net_rate),
                    'tariffs_data': tariffs_data
                })

            return rates

        # Fallback: use average_nightly_tariff and apply to all dates
        if fallback_rate and fallback_rate > 0:
            net_rate = (fallback_rate / (1 + self.vat_rate)).quantize(Decimal('0.01'))
            current_date = from_date
            while current_date <= to_date:
                # Build tariffs_data (no day-specific rates in fallback)
                tariffs_data = self._build_tariffs_summary(all_tariffs_available, current_date)
                rates.append({
                    'date': current_date,
                    'gross_rate': float(fallback_rate),
                    'net_rate': float(net_rate),
                    'tariffs_data': tariffs_data
                })
                current_date += timedelta(days=1)
            return rates

        logger.warning(f"No rate found in response for {from_date} to {to_date}")
        return rates

    def _build_tariffs_summary(self, tariffs_available: list, for_date: date = None) -> dict:
        """
        Build a summary of all available tariff options for rate reporting.

        Args:
            tariffs_available: List of tariff dicts from API response
            for_date: Optional specific date to extract day-specific rates

        Returns:
            Dict with tariff summaries - tariff_count and list of tariff details
        """
        if not tariffs_available:
            return {}

        summary = {
            'tariff_count': len(tariffs_available),
            'tariffs': []
        }

        date_key = for_date.isoformat() if for_date else None

        for idx, tariff in enumerate(tariffs_available):
            # Get day-specific rate from tariffs_quoted if available
            day_rate = None
            if date_key:
                tariffs_quoted = tariff.get('tariffs_quoted', {})
                if isinstance(tariffs_quoted, dict) and date_key in tariffs_quoted:
                    day_quote = tariffs_quoted[date_key]
                    if isinstance(day_quote, dict):
                        day_rate = float(day_quote.get('amount', 0) or 0)
                    else:
                        day_rate = float(day_quote or 0)

            # API uses tariff_label for the name
            message = tariff.get('tariff_message', '')

            # Extract minimum stay from message or dedicated field
            min_stay = tariff.get('minimum_nights', None)
            if min_stay is None and message:
                # Try to parse from message like "Minimum 2 nights" or "2 Night Minimum"
                import re
                match = re.search(r'(\d+)\s*[Nn]ight\s*[Mm]inimum', message)
                if not match:
                    match = re.search(r'[Mm]inimum\s+(\d+)\s*(?:night|period)', message)
                if match:
                    min_stay = int(match.group(1))

            # Extract advance booking requirement from message
            min_advance_days = None
            if message:
                import re
                advance_match = re.search(r'(\d+)\s*days?\s*in\s*advance', message, re.IGNORECASE)
                if advance_match:
                    min_advance_days = int(advance_match.group(1))

            tariff_info = {
                'name': tariff.get('tariff_label', 'Unknown'),
                'description': tariff.get('tariff_short_description', ''),
                'rate': day_rate,  # Day-specific rate (None if not available)
                'average_nightly': float(tariff.get('average_nightly_tariff', 0) or 0),
                'success': str(tariff.get('tariff_success', False)).lower() in ('true', '1'),
                'message': message,
                'sort_order': idx,  # Preserve Newbook ordering
                'min_stay': min_stay,  # Minimum nights required (if any)
                'min_advance_days': min_advance_days,  # Advance booking requirement (if any)
            }

            summary['tariffs'].append(tariff_info)

        return summary

    def _parse_all_categories_tariffs(self, data: dict, for_date: date) -> Dict[str, List[Dict]]:
        """
        Parse tariffs from API response for ALL categories.

        When category_id is omitted, data.data contains category IDs as keys,
        each with their own tariffs_available.

        Args:
            data: Full API response
            for_date: The date we queried

        Returns:
            Dict of {category_id: [{date, gross_rate, net_rate, tariffs_data}]}
        """
        results: Dict[str, List[Dict]] = {}

        if not isinstance(data.get("data"), dict):
            return results

        for key, cat_data in data["data"].items():
            # Category IDs are numeric strings like "1", "8", etc.
            if not (key.isdigit() or str(key).isnumeric()):
                continue

            if not isinstance(cat_data, dict):
                continue

            category_id = str(key)
            tariffs_available = cat_data.get("tariffs_available", [])

            if not tariffs_available:
                continue

            # Get the first (best) tariff for gross/net calculation
            first_tariff = tariffs_available[0]
            tariffs_quoted = first_tariff.get("tariffs_quoted", {})
            inventory_items = first_tariff.get("inventory_items", [])

            # Get rate for this date
            date_key = for_date.isoformat()
            gross_rate = Decimal('0')
            net_rate = Decimal('0')

            if isinstance(tariffs_quoted, dict) and date_key in tariffs_quoted:
                day_tariff = tariffs_quoted[date_key]
                gross_rate = Decimal(str(day_tariff.get('amount', 0) or 0))

                # Calculate included inventory per night
                included_inventory = Decimal('0')
                for item in inventory_items:
                    already_included = item.get('amount_already_included_in_tariff_total', '')
                    if str(already_included).lower() == 'true':
                        included_inventory += Decimal(str(item.get('amount', 0) or 0))

                gross_after_inventory = gross_rate - included_inventory
                net_rate = (gross_after_inventory / (1 + self.vat_rate)).quantize(Decimal('0.01'))
            else:
                # Fallback to average
                gross_rate = Decimal(str(first_tariff.get('average_nightly_tariff', 0) or 0))
                net_rate = (gross_rate / (1 + self.vat_rate)).quantize(Decimal('0.01'))

            # Build tariffs summary for all options
            tariffs_data = self._build_tariffs_summary(tariffs_available, for_date)

            results[category_id] = [{
                'date': for_date,
                'gross_rate': float(gross_rate),
                'net_rate': float(net_rate),
                'tariffs_data': tariffs_data
            }]

        return results

