"""
Local Playwright backend for booking.com scraping.

Uses Playwright with Chromium to scrape search results.
No proxy - direct connection. Suitable for low-volume scraping.
"""

import asyncio
import logging
import random
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import List, Optional
from urllib.parse import urlencode

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .base import (
    ScraperBackend,
    ScraperResult,
    HotelData,
    RateData,
    AvailabilityStatus
)

logger = logging.getLogger(__name__)


class PlaywrightLocalBackend(ScraperBackend):
    """
    Local Playwright backend using Chromium.

    Features:
    - Rotates user agents
    - Random delays between requests
    - Mimics human scroll behavior
    - Uses data-testid selectors for stability
    """

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    ]

    def __init__(self, proxy_config: dict = None):
        """
        Initialize the backend.

        Args:
            proxy_config: Optional proxy configuration (for future use)
        """
        self.proxy_config = proxy_config
        self._playwright = None
        self._browser: Optional[Browser] = None

    async def _ensure_browser(self) -> Browser:
        """Ensure browser is running, start if needed."""
        if self._browser is None or not self._browser.is_connected():
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )
        return self._browser

    async def _create_context(self) -> BrowserContext:
        """Create a new browser context with random user agent."""
        browser = await self._ensure_browser()
        context = await browser.new_context(
            user_agent=random.choice(self.USER_AGENTS),
            viewport={'width': 1920, 'height': 1080},
            locale='en-GB',
            timezone_id='Europe/London',
        )
        return context

    def _build_search_url(
        self,
        location: str,
        check_in: date,
        check_out: date,
        adults: int,
        offset: int = 0
    ) -> str:
        """Build booking.com search URL with parameters."""
        params = {
            'ss': location,
            'checkin': check_in.isoformat(),
            'checkout': check_out.isoformat(),
            'group_adults': adults,
            'no_rooms': 1,
            'group_children': 0,
        }
        if offset > 0:
            params['offset'] = offset

        return f"https://www.booking.com/searchresults.en-gb.html?{urlencode(params)}"

    def _parse_price(self, price_text: str) -> Optional[Decimal]:
        """Parse price from text like '£150' or 'GBP 150'."""
        if not price_text:
            return None
        # Remove currency symbols and extract number
        cleaned = re.sub(r'[£$€,\s]', '', price_text)
        # Find first number (including decimals)
        match = re.search(r'[\d,]+(?:\.\d{2})?', cleaned)
        if match:
            try:
                return Decimal(match.group().replace(',', ''))
            except InvalidOperation:
                return None
        return None

    def _extract_hotel_id(self, url: str) -> Optional[str]:
        """Extract hotel ID from booking.com URL."""
        if not url:
            return None
        # URL format: /hotel/gb/hotel-name.en-gb.html or ?dest_id=123
        # Try to extract from URL path
        match = re.search(r'/hotel/[a-z]{2}/([^/]+)\.', url)
        if match:
            return match.group(1)
        # Try dest_id parameter
        match = re.search(r'dest_id=(-?\d+)', url)
        if match:
            return match.group(1)
        return None

    async def _human_like_scroll(self, page: Page):
        """Simulate human-like scrolling behavior."""
        # Scroll down in increments
        for _ in range(3):
            await page.mouse.wheel(0, random.randint(300, 600))
            await asyncio.sleep(random.uniform(0.3, 0.8))

    async def _extract_search_results(self, page: Page, rate_date: date) -> tuple[List[HotelData], List[RateData]]:
        """Extract hotel and rate data from search results page."""
        hotels = []
        rates = []

        # Wait for property cards - booking.com uses data-testid
        try:
            await page.wait_for_selector('[data-testid="property-card"]', timeout=15000)
        except Exception as e:
            logger.warning(f"No property cards found: {e}")
            return hotels, rates

        # Get all property cards
        cards = await page.query_selector_all('[data-testid="property-card"]')
        logger.info(f"Found {len(cards)} property cards")

        for card in cards:
            try:
                hotel = HotelData(booking_com_id='', name='')
                rate = RateData(rate_date=rate_date)

                # Hotel name
                name_el = await card.query_selector('[data-testid="title"]')
                if name_el:
                    hotel.name = (await name_el.inner_text()).strip()

                if not hotel.name:
                    continue  # Skip if no name found

                # Hotel URL and ID
                link_el = await card.query_selector('[data-testid="title-link"]')
                if link_el:
                    hotel.booking_com_url = await link_el.get_attribute('href')
                    hotel.booking_com_id = self._extract_hotel_id(hotel.booking_com_url) or ''

                rate.booking_com_id = hotel.booking_com_id

                # Star rating - look for star icons or rating text
                stars_el = await card.query_selector('[data-testid="rating-stars"]')
                if stars_el:
                    stars_text = await stars_el.get_attribute('aria-label') or ''
                    match = re.search(r'(\d+)', stars_text)
                    if match:
                        hotel.star_rating = Decimal(match.group(1))

                # Review score
                score_el = await card.query_selector('[data-testid="review-score"]')
                if score_el:
                    score_text = await score_el.inner_text()
                    match = re.search(r'([\d.]+)', score_text)
                    if match:
                        try:
                            hotel.review_score = Decimal(match.group(1))
                        except InvalidOperation:
                            pass

                # Check for no availability message FIRST
                no_avail_el = await card.query_selector('[data-testid="availability-message"]')
                if no_avail_el:
                    avail_text = (await no_avail_el.inner_text()).lower()
                    if 'no availability' in avail_text or 'sold out' in avail_text:
                        rate.availability_status = AvailabilityStatus.SOLD_OUT
                        hotels.append(hotel)
                        rates.append(rate)
                        continue

                # Price
                price_el = await card.query_selector('[data-testid="price-and-discounted-price"]')
                if not price_el:
                    # Try alternative selector
                    price_el = await card.query_selector('[data-testid="price"]')

                if price_el:
                    price_text = await price_el.inner_text()
                    rate.rate_gross = self._parse_price(price_text)
                    if rate.rate_gross:
                        rate.availability_status = AvailabilityStatus.AVAILABLE

                # Room type
                room_el = await card.query_selector('[data-testid="recommended-units"]')
                if room_el:
                    rate.room_type = (await room_el.inner_text()).strip()

                # Rate option badges - try multiple selectors
                # Breakfast included
                breakfast_el = await card.query_selector('[data-testid="breakfast-included"]')
                if not breakfast_el:
                    # Check text content for breakfast mentions
                    card_text = (await card.inner_text()).lower()
                    rate.breakfast_included = 'breakfast included' in card_text
                else:
                    rate.breakfast_included = True

                # Free cancellation
                cancel_el = await card.query_selector('[data-testid="cancellation-policy"]')
                if cancel_el:
                    cancel_text = (await cancel_el.inner_text()).lower()
                    rate.free_cancellation = 'free cancellation' in cancel_text
                else:
                    card_text = (await card.inner_text()).lower()
                    rate.free_cancellation = 'free cancellation' in card_text

                # No prepayment
                prepay_el = await card.query_selector('[data-testid="no-prepayment"]')
                if prepay_el:
                    rate.no_prepayment = True
                else:
                    card_text = (await card.inner_text()).lower()
                    rate.no_prepayment = 'no prepayment' in card_text

                # Rooms left / scarcity indicator
                scarcity_el = await card.query_selector('[data-testid="availability-rate"]')
                if scarcity_el:
                    scarcity_text = await scarcity_el.inner_text()
                    match = re.search(r'(\d+)\s*room', scarcity_text.lower())
                    if match:
                        rate.rooms_left = int(match.group(1))

                hotels.append(hotel)
                rates.append(rate)

            except Exception as e:
                logger.warning(f"Error extracting hotel data: {e}")
                continue

        return hotels, rates

    async def scrape_location_search(
        self,
        location: str,
        check_in: date,
        check_out: date,
        adults: int = 2,
        pages: int = 2
    ) -> ScraperResult:
        """
        Scrape booking.com location search results.

        Args:
            location: Location name
            check_in: Check-in date
            check_out: Check-out date (check_in + 1 for single night rate)
            adults: Number of adults
            pages: Number of result pages to scrape

        Returns:
            ScraperResult with hotels and rates found
        """
        all_hotels = []
        all_rates = []
        seen_hotel_ids = set()

        context = None
        page = None

        try:
            context = await self._create_context()
            page = await context.new_page()

            for page_num in range(pages):
                # Random delay between pages (3-7 seconds)
                if page_num > 0:
                    delay = random.uniform(3, 7)
                    logger.info(f"Waiting {delay:.1f}s before page {page_num + 1}")
                    await asyncio.sleep(delay)

                # Build URL with offset for pagination (25 results per page)
                url = self._build_search_url(
                    location, check_in, check_out, adults,
                    offset=page_num * 25
                )

                logger.info(f"Scraping page {page_num + 1}: {url}")

                try:
                    await page.goto(url, wait_until='networkidle', timeout=30000)
                except Exception as e:
                    logger.warning(f"Page load timeout, continuing: {e}")

                # Check for blocking
                content = await page.content()
                is_blocked, reason = self.detect_blocking(content)
                if is_blocked:
                    logger.warning(f"Blocking detected: {reason}")
                    return ScraperResult(
                        success=False,
                        blocked=True,
                        block_reason=reason,
                        hotels=all_hotels,
                        rates=all_rates,
                        page_content_sample=content[:1000]
                    )

                # Human-like scrolling
                await self._human_like_scroll(page)

                # Extract data
                hotels, rates = await self._extract_search_results(page, check_in)

                # Deduplicate by booking_com_id
                for hotel, rate in zip(hotels, rates):
                    if hotel.booking_com_id and hotel.booking_com_id not in seen_hotel_ids:
                        seen_hotel_ids.add(hotel.booking_com_id)
                        all_hotels.append(hotel)
                        all_rates.append(rate)

                logger.info(f"Page {page_num + 1}: found {len(hotels)} hotels, {len(all_hotels)} total unique")

            return ScraperResult(
                success=True,
                blocked=False,
                hotels=all_hotels,
                rates=all_rates
            )

        except Exception as e:
            logger.error(f"Scrape error: {e}")
            return ScraperResult(
                success=False,
                blocked=False,
                error_message=str(e),
                hotels=all_hotels,
                rates=all_rates
            )
        finally:
            if page:
                await page.close()
            if context:
                await context.close()

    async def scrape_hotel_page(
        self,
        hotel_url: str,
        check_in: date,
        check_out: date,
        adults: int = 2
    ) -> ScraperResult:
        """
        Scrape individual hotel page for detailed rates.

        Future expansion - placeholder for now.
        Will extract available_qty from room dropdowns.
        """
        # Not implemented in Phase 2a
        logger.warning("scrape_hotel_page not yet implemented")
        return ScraperResult(
            success=False,
            error_message="Hotel page scraping not yet implemented"
        )

    async def close(self):
        """Clean up browser resources."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
