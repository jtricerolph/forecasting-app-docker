# Phase 2: Booking.com Rate Scraping

## Overview

Add competitor rate comparison and own hotel rate verification by scraping booking.com. Uses Playwright headless browser with tiered scheduling to avoid anti-scraping detection.

## Goals

1. **Own Rate Verification** - Verify hotel's booking.com rates match Newbook
2. **Competitor Comparison** - See what nearby competitors charge for same dates
3. **Rate Parity Alerts** - Flag when booking.com rates differ from direct rates

## Scraping Strategy: Location Search (Query Efficient)

Instead of scraping individual hotel pages (1 query per hotel), use **location search**:

### How It Works
1. Search booking.com for location (e.g., "Bowness-on-Windermere")
2. Scrape first 2 pages of results (~40-50 hotels)
3. Extract best available rate per hotel per date from search results
4. Store ALL hotels found (wide market picture)
5. Mark "main competitors" for detailed tracking

### Benefits
- **1 search = 40+ hotels** vs 40 individual page scrapes
- Reduces queries by ~95%
- Get market-wide pricing picture
- Less suspicious to anti-scrape systems (normal user behavior)

### Hotel Tiers

| Tier | Description | Data Captured |
|------|-------------|---------------|
| **Primary** | Own hotel | Full rate matrix, parity alerts |
| **Main Competitors** | 3-5 selected competitors | Full rate matrix, comparison charts |
| **Market** | All other hotels in search | Best available rate only (from search results) |

### UI: Competitor Selection
- Initially scrape location → discover hotels
- User selects which are "main competitors" in Settings
- Main competitors sorted to top of comparison views
- Market hotels shown below for context

## Architecture

### New Components

```
backend/
├── services/
│   ├── booking_scraper.py           # Main scraper + factory
│   └── scraper_backends/            # Pluggable backends
│       ├── base.py                  # Abstract interface
│       ├── playwright_local.py      # Direct Playwright (Phase 2)
│       ├── playwright_proxy.py      # + Rotating proxies (future)
│       └── apify_backend.py         # Apify service (future)
├── jobs/
│   └── scrape_booking_rates.py      # Tiered scheduling job
├── api/
│   └── competitor_rates.py          # API endpoints
frontend/
└── src/pages/
    └── CompetitorRates.tsx          # Comparison matrix UI
```

### Database Tables

```sql
-- Scrape location configuration
CREATE TABLE booking_scrape_config (
    id SERIAL PRIMARY KEY,
    location_name VARCHAR(255) NOT NULL,     -- "Bowness-on-Windermere"
    location_search_url TEXT,                 -- Pre-built search URL
    pages_to_scrape INTEGER DEFAULT 2,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Hotels discovered from location searches
CREATE TABLE booking_com_hotels (
    id SERIAL PRIMARY KEY,
    booking_com_id VARCHAR(100) UNIQUE,      -- Hotel ID from booking.com
    name VARCHAR(255) NOT NULL,
    booking_com_url TEXT,
    star_rating DECIMAL(2,1),
    review_score DECIMAL(3,1),
    tier VARCHAR(20) DEFAULT 'market',       -- 'own', 'competitor', 'market'
    display_order INTEGER DEFAULT 999,        -- Competitors sorted first
    is_active BOOLEAN DEFAULT TRUE,
    first_seen_at TIMESTAMP DEFAULT NOW(),
    last_seen_at TIMESTAMP DEFAULT NOW()
);

-- Scraped rates (from location search results)
CREATE TABLE booking_com_rates (
    id SERIAL PRIMARY KEY,
    hotel_id INTEGER REFERENCES booking_com_hotels(id),
    rate_date DATE NOT NULL,

    -- Availability status (distinguish sold out vs no data)
    availability_status VARCHAR(20) NOT NULL,  -- 'available', 'sold_out', 'no_data'

    -- Rate data (null if sold_out or no_data)
    rate_gross DECIMAL(10,2),
    room_type VARCHAR(255),

    -- Rate options
    breakfast_included BOOLEAN,
    free_cancellation BOOLEAN,
    no_prepayment BOOLEAN,

    -- Scarcity indicator ("Only X rooms left")
    rooms_left INTEGER,                        -- null if not shown

    -- Future: from individual hotel page scrapes
    available_qty INTEGER,                     -- Max from dropdown (future)

    -- Metadata
    scraped_at TIMESTAMP DEFAULT NOW(),
    scrape_batch_id UUID,

    CONSTRAINT unique_hotel_date_batch
        UNIQUE(hotel_id, rate_date, scrape_batch_id)
);

-- Scrape queue for retry/resume
CREATE TABLE booking_scrape_queue (
    id SERIAL PRIMARY KEY,
    rate_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',     -- 'pending', 'in_progress', 'completed', 'failed', 'blocked'
    priority INTEGER DEFAULT 0,                -- Higher = sooner
    attempts INTEGER DEFAULT 0,
    last_attempt_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    UNIQUE(rate_date, status)
);

-- Rate parity alerts (own hotel only)
CREATE TABLE rate_parity_alerts (
    id SERIAL PRIMARY KEY,
    rate_date DATE NOT NULL,
    room_category VARCHAR(100),
    newbook_rate DECIMAL(10,2),
    booking_com_rate DECIMAL(10,2),
    difference_pct DECIMAL(5,2),
    alert_status VARCHAR(20) DEFAULT 'new',
    created_at TIMESTAMP DEFAULT NOW(),
    acknowledged_at TIMESTAMP,
    acknowledged_by VARCHAR(100)
);

-- Index for fast lookups
CREATE INDEX idx_booking_rates_hotel_date ON booking_com_rates(hotel_id, rate_date);
CREATE INDEX idx_booking_hotels_tier ON booking_com_hotels(tier, display_order);
```

## Tiered Scraping Schedule

Using location search = far fewer queries needed.

### Query Math
- **Old approach**: 40 hotels × 30 days = 1,200 queries/month for 30-day window
- **Location search**: 30 days × 2 pages = 60 queries/month (captures 40+ hotels!)

### Tier 1: Daily Morning Scrape (5:30 AM)
- Location search for next **30 days**
- 30 searches × 2 pages = **60 page loads total**
- Captures all hotels in area with best available rates
- Random 3-7 second delays between pages

### Tier 2: Extended Range (Staggered through week)
- Background scrapes for days 31-90
- Spread across week to avoid patterns:
  - Mon 10am: Days 31-45
  - Tue 2pm: Days 46-60
  - Wed 11am: Days 61-75
  - Thu 3pm: Days 76-90
- ~15 searches × 2 pages = 30 page loads per session

### Tier 3: Deep Refresh (Weekly)
- Saturday 3am: Full refresh days 1-90
- Catches any missed data from the week

### Randomization
- Add 0-15 minute random delay to job starts
- Random 3-7 second delays between page loads
- Rotate user agents per session
- Mimic human scroll behavior on pages

## Anti-Scrape Detection & Queue System

### Detection Signals

The scraper monitors for blocking indicators:

```python
BLOCK_SIGNALS = [
    'captcha',                           # CAPTCHA challenge
    'unusual traffic',                   # Rate limit message
    'access denied',                     # IP blocked
    'please verify',                     # Human verification
    'too many requests',                 # 429-like response
]

async def detect_blocking(page) -> bool:
    """Check if page shows anti-scrape response."""
    content = await page.content()
    content_lower = content.lower()
    return any(signal in content_lower for signal in BLOCK_SIGNALS)
```

### Queue-Based Scraping

Instead of scraping dates directly, push to queue and process:

```python
# 1. Scheduler populates queue with dates to check
async def schedule_scrape_batch(from_date, to_date, priority=0):
    for d in date_range(from_date, to_date):
        await db.execute("""
            INSERT INTO booking_scrape_queue (rate_date, priority, status)
            VALUES (:date, :priority, 'pending')
            ON CONFLICT (rate_date, status) DO NOTHING
        """)

# 2. Worker processes queue items
async def process_scrape_queue():
    while True:
        # Get next pending item (highest priority, oldest first)
        item = await get_next_queue_item()
        if not item:
            break

        # Mark in progress
        await update_queue_status(item.id, 'in_progress')

        try:
            results = await scrape_date(item.rate_date)

            if results.get('blocked'):
                # Blocked! Pause and requeue
                await handle_blocking(item)
                break  # Stop processing, let scheduler resume later

            # Success
            await save_results(results)
            await update_queue_status(item.id, 'completed')

        except Exception as e:
            await update_queue_status(item.id, 'failed', str(e))
            item.attempts += 1
```

### Blocking Response

When blocking detected:

```python
async def handle_blocking(queue_item):
    """Handle anti-scrape blocking."""
    # 1. Mark current item for retry
    await db.execute("""
        UPDATE booking_scrape_queue
        SET status = 'pending',
            attempts = attempts + 1,
            last_attempt_at = NOW(),
            error_message = 'Blocked - will retry later'
        WHERE id = :id
    """, {'id': queue_item.id})

    # 2. Set global pause flag
    await set_config('scraper_paused', 'true')
    await set_config('scraper_pause_until', (datetime.now() + timedelta(hours=2)).isoformat())

    # 3. Log alert for admin
    logger.warning(f"Scraper blocked at {datetime.now()}, pausing for 2 hours")
```

### Resume Logic

Scheduler checks pause status before running:

```python
async def should_scrape():
    """Check if scraping is allowed."""
    paused = await get_config('scraper_paused')
    if paused == 'true':
        pause_until = await get_config('scraper_pause_until')
        if datetime.now() < datetime.fromisoformat(pause_until):
            return False
        # Pause expired, reset
        await set_config('scraper_paused', 'false')
    return True
```

### Distinguishing "Sold Out" vs "No Data"

```python
async def parse_hotel_availability(card) -> dict:
    """Parse availability status from hotel card."""

    # Check for explicit "no availability" message
    no_avail_el = await card.query_selector('[data-testid="availability-message"]')
    if no_avail_el:
        text = await no_avail_el.inner_text()
        if 'no availability' in text.lower():
            return {
                'availability_status': 'sold_out',
                'rate_gross': None,
                # ... other fields null
            }

    # Check for price - if present, it's available
    price_el = await card.query_selector('[data-testid="price-and-discounted-price"]')
    if price_el:
        return {
            'availability_status': 'available',
            'rate_gross': parse_price(await price_el.inner_text()),
            # ... extract other fields
        }

    # No clear signal - mark as no_data (needs investigation)
    return {
        'availability_status': 'no_data',
        'rate_gross': None,
    }
```

### Status Values

| Status | Meaning | Action |
|--------|---------|--------|
| `available` | Rate found, bookable | Store rate + options |
| `sold_out` | Property explicitly shows no availability | Store as sold_out (valid data!) |
| `no_data` | Couldn't determine (scraper issue) | Flag for review, retry |

## Data Extraction Strategy

### Why data-testid (not XPath)

| Method | Stability | Reason |
|--------|-----------|--------|
| **XPath** | Fragile | Breaks when DOM structure changes (common) |
| **CSS class names** | Medium | Classes can change with redesigns |
| **data-testid** | Stable | Booking.com uses these for testing - rarely change |
| **Text selectors** | Medium | Language-dependent, but useful for labels |

Booking.com uses `data-testid` attributes on key elements. These are test hooks they maintain for their own QA, so they're more stable than layout-based selectors.

### Data Captured Per Hotel

From search results page:
- Hotel name, URL, booking.com ID
- Star rating, review score
- **Best available rate** (displayed price)
- **Room type** (e.g., "Double Room", "Superior Suite")
- **Breakfast included** (boolean - often shown as badge)
- **Free cancellation** (boolean)
- **No prepayment** (boolean)
- **Limited availability** ("Only X rooms left at this price" → integer)
- **Sold out flag** (explicitly track when property shows no availability)

From individual hotel page (future expansion):
- **Available quantity per room type** (from dropdown max values)
- Full rate breakdown by room type
- All rate options not just "best"

### Fallback Strategy

If data-testid selectors break:
1. Log warning + continue with partial data
2. Alert in admin that scraper needs update
3. Fallback selectors (CSS classes) as backup

## Implementation Phases

### Phase 2a: Foundation (1-2 days)
1. Database migrations for new tables
2. Playwright setup + Docker config
3. Basic location search scraper
4. Manual trigger endpoint for testing

### Phase 2b: Hotel Discovery (1 day)
1. Location config in Settings
2. Run initial scrape → populate booking_com_hotels
3. Hotel management UI (tier assignment, ordering)

### Phase 2c: Rate Matrix (1 day)
1. Store scraped rates in database
2. Build CompetitorRates page
3. Matrix view with tiers (competitors at top)

### Phase 2d: Own Hotel Parity (1 day)
1. Match own hotel to Newbook categories
2. Compare rates, generate parity alerts
3. Add parity section to Bookability page

### Phase 2e: Queue & Anti-Scrape (1 day)
1. Implement scrape queue table
2. Queue-based processing with pause/resume
3. Anti-scrape detection logic
4. Sold out vs no data distinction

### Phase 2f: Scheduling (1 day)
1. Implement tiered schedule populating queue
2. Add randomization/delays
3. Batch tracking and logging

### Phase 2g: Polish (1 day)
1. Rate parity alert management
2. Dashboard summary widget
3. Scraper status/health monitoring

## Key Files to Modify/Create

### New Files:
- `backend/services/booking_scraper.py` - Playwright scraper
- `backend/services/scraper_backends/base.py` - Abstract interface
- `backend/services/scraper_backends/playwright_local.py` - Local Playwright
- `backend/jobs/scrape_booking_rates.py` - Scheduled job
- `backend/api/competitor_rates.py` - API endpoints
- `frontend/src/pages/CompetitorRates.tsx` - UI

### Modify:
- `backend/main.py` - Register new router
- `backend/scheduler.py` - Add new jobs
- `docker-compose.yml` - Add Playwright dependencies
- `backend/requirements.txt` - Add `playwright`
- `backend/Dockerfile` - Install Playwright browsers

## Dependencies

```txt
# requirements.txt additions
playwright>=1.40.0
```

```dockerfile
# Dockerfile additions
RUN pip install playwright && playwright install chromium --with-deps
```

## Future Extensibility: Proxy & Scraping Services

Architecture supports pluggable backends:
- `playwright_local` - Direct Playwright (current)
- `playwright_proxy` - Playwright + rotating proxies
- `apify_backend` - Apify scraping service

Configuration stored in system_config table for easy switching.

## Questions Resolved

- Goal: Both competitor comparison AND own rate verification
- Method: Playwright headless browser
- Schedule: Tiered (30 days daily + rolling background scrapes)
- UI: Parity check on Bookability + separate CompetitorRates page
- Initial scope: Own hotel + 2-3 nearby competitors
- Scraping approach: Location search (1 query = 40+ hotels, 95% fewer requests)
- Hotel tiers: Own / Competitor (3-5 selected) / Market (all others for context)
- Data captured: Rate, room type, breakfast, cancellation, prepayment, rooms left
- Selector strategy: data-testid attributes (stable, used by booking.com for QA)
- **Extensibility**: Abstraction layer for future proxy/Apify integration
- **Availability tracking**: Distinguish 'available' / 'sold_out' / 'no_data'
- **Anti-scrape handling**: Queue system with pause/resume on blocking detection
- **Future expansion**: available_qty from hotel page dropdowns when needed
