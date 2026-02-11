"""
Abstract base class for booking.com scraper backends.

Defines the interface that all scraper backends must implement,
allowing easy switching between local Playwright, proxied Playwright,
or external services like Apify.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional, Dict, Any
from enum import Enum


class AvailabilityStatus(str, Enum):
    """Availability status for a hotel rate."""
    AVAILABLE = 'available'      # Rate found, bookable
    SOLD_OUT = 'sold_out'        # Hotel shows no availability
    NO_DATA = 'no_data'          # Couldn't determine (scraper issue)


@dataclass
class RateData:
    """Rate data for a single hotel on a single date."""
    hotel_id: Optional[str] = None       # Our internal hotel_id (filled after DB lookup)
    booking_com_id: str = ''             # Hotel ID from booking.com
    rate_date: date = None
    availability_status: AvailabilityStatus = AvailabilityStatus.NO_DATA
    rate_gross: Optional[Decimal] = None
    currency: str = 'GBP'
    room_type: Optional[str] = None
    breakfast_included: Optional[bool] = None
    free_cancellation: Optional[bool] = None
    no_prepayment: Optional[bool] = None
    rooms_left: Optional[int] = None     # "Only X rooms left"
    available_qty: Optional[int] = None  # Future: from hotel page dropdown


@dataclass
class HotelData:
    """Hotel data discovered from search results."""
    booking_com_id: str
    name: str
    booking_com_url: Optional[str] = None
    star_rating: Optional[Decimal] = None
    review_score: Optional[Decimal] = None
    review_count: Optional[int] = None


@dataclass
class ScraperResult:
    """Result from a scraping operation."""
    success: bool
    blocked: bool = False                # True if anti-scrape blocking detected
    block_reason: Optional[str] = None   # CAPTCHA, rate limit, etc.
    hotels: List[HotelData] = field(default_factory=list)
    rates: List[RateData] = field(default_factory=list)
    error_message: Optional[str] = None
    page_content_sample: Optional[str] = None  # For debugging


class ScraperBackend(ABC):
    """
    Abstract base class for scraper backends.

    All backends must implement these methods to provide a consistent
    interface for the main booking_scraper.py service.
    """

    # Common block detection signals
    BLOCK_SIGNALS = [
        'captcha',
        'unusual traffic',
        'access denied',
        'please verify',
        'too many requests',
        'are you a robot',
        'verify you are human',
        'security check',
    ]

    @abstractmethod
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
            location: Location name (e.g., "Bowness-on-Windermere")
            check_in: Check-in date
            check_out: Check-out date (typically check_in + 1 for single night)
            adults: Number of adults for search
            pages: Number of search result pages to scrape

        Returns:
            ScraperResult with hotels and rates found
        """
        pass

    @abstractmethod
    async def scrape_hotel_page(
        self,
        hotel_url: str,
        check_in: date,
        check_out: date,
        adults: int = 2
    ) -> ScraperResult:
        """
        Scrape an individual hotel page for detailed rates.

        Future expansion - not used in initial implementation.
        Will provide available_qty from room dropdowns.

        Args:
            hotel_url: Full booking.com URL for the hotel
            check_in: Check-in date
            check_out: Check-out date
            adults: Number of adults

        Returns:
            ScraperResult with detailed rate information
        """
        pass

    @abstractmethod
    async def close(self):
        """Clean up any resources (browser instances, etc.)."""
        pass

    def detect_blocking(self, page_content: str) -> tuple[bool, Optional[str]]:
        """
        Check if page content shows anti-scrape response.

        Args:
            page_content: HTML content of the page

        Returns:
            Tuple of (is_blocked, reason)
        """
        content_lower = page_content.lower()
        for signal in self.BLOCK_SIGNALS:
            if signal in content_lower:
                return True, signal
        return False, None
