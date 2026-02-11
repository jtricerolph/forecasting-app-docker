"""
Scraper backends for booking.com rate scraping.

Provides pluggable backends to allow switching between:
- playwright_local: Direct Playwright (default)
- playwright_proxy: Playwright with rotating proxies (future)
- apify_backend: Apify scraping service (future)
"""

from .base import ScraperBackend, ScraperResult, HotelData, RateData, AvailabilityStatus
from .playwright_local import PlaywrightLocalBackend

__all__ = [
    'ScraperBackend',
    'ScraperResult',
    'HotelData',
    'RateData',
    'AvailabilityStatus',
    'PlaywrightLocalBackend',
]
