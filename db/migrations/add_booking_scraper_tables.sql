-- ============================================
-- BOOKING.COM RATE SCRAPING INTEGRATION
-- Phase 2: Competitor rate comparison and own hotel rate verification
-- Scrapes booking.com via Playwright headless browser
-- ============================================

-- ============================================
-- SCRAPE LOCATION CONFIGURATION
-- Stores location search parameters (e.g., "Bowness-on-Windermere")
-- ============================================

CREATE TABLE IF NOT EXISTS booking_scrape_config (
    id SERIAL PRIMARY KEY,
    location_name VARCHAR(255) NOT NULL,         -- "Bowness-on-Windermere"
    location_search_url TEXT,                     -- Pre-built search URL (optional)
    pages_to_scrape INTEGER DEFAULT 2,            -- Number of search result pages
    adults INTEGER DEFAULT 2,                     -- Search parameter: adults
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_booking_scrape_config_active ON booking_scrape_config(is_active);

-- ============================================
-- HOTELS DISCOVERED FROM LOCATION SEARCHES
-- All hotels found in search results, tagged by tier
-- ============================================

CREATE TABLE IF NOT EXISTS booking_com_hotels (
    id SERIAL PRIMARY KEY,
    booking_com_id VARCHAR(100) UNIQUE,          -- Hotel ID extracted from booking.com URL
    name VARCHAR(255) NOT NULL,
    booking_com_url TEXT,
    star_rating DECIMAL(2,1),                    -- e.g., 4.0, 4.5
    review_score DECIMAL(3,1),                   -- e.g., 8.5, 9.2
    review_count INTEGER,                        -- Number of reviews
    tier VARCHAR(20) DEFAULT 'market',           -- 'own', 'competitor', 'market'
    display_order INTEGER DEFAULT 999,           -- Competitors sorted first
    is_active BOOLEAN DEFAULT TRUE,              -- Show in UI
    notes TEXT,                                  -- User notes about this hotel
    first_seen_at TIMESTAMP DEFAULT NOW(),
    last_seen_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_booking_hotels_tier ON booking_com_hotels(tier, display_order);
CREATE INDEX IF NOT EXISTS idx_booking_hotels_active ON booking_com_hotels(is_active);
CREATE INDEX IF NOT EXISTS idx_booking_hotels_booking_id ON booking_com_hotels(booking_com_id);

-- ============================================
-- SCRAPED RATES FROM SEARCH RESULTS
-- Best available rate per hotel per date
-- ============================================

CREATE TABLE IF NOT EXISTS booking_com_rates (
    id SERIAL PRIMARY KEY,
    hotel_id INTEGER REFERENCES booking_com_hotels(id) ON DELETE CASCADE,
    rate_date DATE NOT NULL,

    -- Availability status (distinguish sold out vs scraper issues)
    availability_status VARCHAR(20) NOT NULL,     -- 'available', 'sold_out', 'no_data'

    -- Rate data (null if sold_out or no_data)
    rate_gross DECIMAL(10,2),                     -- Displayed price including taxes
    currency VARCHAR(10) DEFAULT 'GBP',
    room_type VARCHAR(255),                       -- e.g., "Double Room", "Superior Suite"

    -- Rate options shown on search results
    breakfast_included BOOLEAN,
    free_cancellation BOOLEAN,
    no_prepayment BOOLEAN,

    -- Scarcity indicator ("Only X rooms left at this price")
    rooms_left INTEGER,                           -- null if not shown

    -- Future: from individual hotel page scrapes
    available_qty INTEGER,                        -- Max qty from dropdown (future expansion)

    -- Metadata
    scraped_at TIMESTAMP DEFAULT NOW(),
    scrape_batch_id UUID,                         -- Groups results from same scrape run

    CONSTRAINT unique_hotel_date_batch
        UNIQUE(hotel_id, rate_date, scrape_batch_id)
);

CREATE INDEX IF NOT EXISTS idx_booking_rates_hotel_date ON booking_com_rates(hotel_id, rate_date);
CREATE INDEX IF NOT EXISTS idx_booking_rates_date ON booking_com_rates(rate_date);
CREATE INDEX IF NOT EXISTS idx_booking_rates_batch ON booking_com_rates(scrape_batch_id);
CREATE INDEX IF NOT EXISTS idx_booking_rates_status ON booking_com_rates(availability_status);

-- ============================================
-- SCRAPE QUEUE FOR RETRY/RESUME
-- Queue-based processing with pause/resume on blocking
-- ============================================

CREATE TABLE IF NOT EXISTS booking_scrape_queue (
    id SERIAL PRIMARY KEY,
    rate_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',         -- 'pending', 'in_progress', 'completed', 'failed', 'blocked'
    priority INTEGER DEFAULT 0,                   -- Higher = sooner (used for near-term dates)
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    last_attempt_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    UNIQUE(rate_date, status)
);

CREATE INDEX IF NOT EXISTS idx_booking_queue_status ON booking_scrape_queue(status, priority DESC, created_at);
CREATE INDEX IF NOT EXISTS idx_booking_queue_date ON booking_scrape_queue(rate_date);

-- ============================================
-- RATE PARITY ALERTS (OWN HOTEL ONLY)
-- Flags when booking.com rates differ from Newbook
-- ============================================

CREATE TABLE IF NOT EXISTS rate_parity_alerts (
    id SERIAL PRIMARY KEY,
    rate_date DATE NOT NULL,
    room_category VARCHAR(100),                   -- Newbook category name
    newbook_rate DECIMAL(10,2),                   -- Rate from Newbook
    booking_com_rate DECIMAL(10,2),               -- Rate scraped from booking.com
    difference_pct DECIMAL(5,2),                  -- (booking - newbook) / newbook * 100
    alert_type VARCHAR(20),                       -- 'higher', 'lower', 'unavailable'
    alert_status VARCHAR(20) DEFAULT 'new',       -- 'new', 'acknowledged', 'resolved'
    created_at TIMESTAMP DEFAULT NOW(),
    acknowledged_at TIMESTAMP,
    acknowledged_by VARCHAR(100),
    resolved_at TIMESTAMP,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_parity_alerts_date ON rate_parity_alerts(rate_date);
CREATE INDEX IF NOT EXISTS idx_parity_alerts_status ON rate_parity_alerts(alert_status);

-- ============================================
-- SCRAPE BATCH LOG
-- Track each scrape run for monitoring/debugging
-- ============================================

CREATE TABLE IF NOT EXISTS booking_scrape_log (
    id SERIAL PRIMARY KEY,
    batch_id UUID NOT NULL UNIQUE,
    scrape_type VARCHAR(30) NOT NULL,             -- 'daily_30', 'weekly_extended', 'full_refresh', 'manual'
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status VARCHAR(20) NOT NULL,                  -- 'running', 'completed', 'failed', 'blocked'
    dates_queued INTEGER DEFAULT 0,
    dates_completed INTEGER DEFAULT 0,
    dates_failed INTEGER DEFAULT 0,
    hotels_found INTEGER DEFAULT 0,
    rates_scraped INTEGER DEFAULT 0,
    error_message TEXT,
    blocked_at TIMESTAMP,                         -- When anti-scrape blocking detected
    resume_after TIMESTAMP                        -- When to resume after blocking
);

CREATE INDEX IF NOT EXISTS idx_scrape_log_batch ON booking_scrape_log(batch_id);
CREATE INDEX IF NOT EXISTS idx_scrape_log_status ON booking_scrape_log(status);

-- ============================================
-- SYSTEM CONFIG ADDITIONS
-- Scraper settings stored in system_config table
-- ============================================

INSERT INTO system_config (config_key, description) VALUES
('booking_scraper_enabled', 'Enable booking.com rate scraping (true/false)'),
('booking_scraper_backend', 'Scraper backend type: playwright_local, playwright_proxy, apify'),
('booking_scraper_paused', 'Scraper pause flag set when blocking detected'),
('booking_scraper_pause_until', 'ISO timestamp when scraper can resume'),
('booking_scraper_daily_time', 'Daily scrape time (HH:MM) for 30-day window'),
('booking_scraper_own_hotel_id', 'booking_com_hotels.id for own hotel (for parity checking)'),
('booking_scraper_proxy_url', 'Proxy server URL (if using proxy backend)'),
('booking_scraper_proxy_username', 'Proxy username'),
('booking_scraper_proxy_password', 'Proxy password (encrypted)'),
('booking_scraper_apify_key', 'Apify API key (if using Apify backend)')
ON CONFLICT (config_key) DO NOTHING;

-- Set defaults
UPDATE system_config SET config_value = 'false' WHERE config_key = 'booking_scraper_enabled' AND config_value IS NULL;
UPDATE system_config SET config_value = 'playwright_local' WHERE config_key = 'booking_scraper_backend' AND config_value IS NULL;
UPDATE system_config SET config_value = 'false' WHERE config_key = 'booking_scraper_paused' AND config_value IS NULL;
UPDATE system_config SET config_value = '05:30' WHERE config_key = 'booking_scraper_daily_time' AND config_value IS NULL;

-- ============================================
-- VIEWS FOR COMMON QUERIES
-- ============================================

-- Latest rate per hotel per date (most recent scrape)
CREATE OR REPLACE VIEW booking_latest_rates AS
SELECT DISTINCT ON (hotel_id, rate_date)
    r.id,
    r.hotel_id,
    h.name AS hotel_name,
    h.tier,
    h.star_rating,
    h.review_score,
    r.rate_date,
    r.availability_status,
    r.rate_gross,
    r.room_type,
    r.breakfast_included,
    r.free_cancellation,
    r.no_prepayment,
    r.rooms_left,
    r.scraped_at
FROM booking_com_rates r
JOIN booking_com_hotels h ON r.hotel_id = h.id
WHERE h.is_active = TRUE
ORDER BY hotel_id, rate_date, scraped_at DESC;

-- Competitor comparison matrix (own hotel vs competitors)
CREATE OR REPLACE VIEW booking_competitor_matrix AS
SELECT
    r.rate_date,
    h.id AS hotel_id,
    h.name AS hotel_name,
    h.tier,
    h.display_order,
    r.availability_status,
    r.rate_gross,
    r.room_type,
    r.breakfast_included,
    r.free_cancellation
FROM booking_latest_rates r
JOIN booking_com_hotels h ON r.hotel_id = h.id
WHERE h.tier IN ('own', 'competitor')
  AND h.is_active = TRUE
ORDER BY r.rate_date, h.display_order, h.name;
