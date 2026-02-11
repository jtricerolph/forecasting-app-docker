-- ============================================
-- RESOS BOOKINGS INTEGRATION
-- Adds tables for restaurant booking data sync from Resos API
-- Follows same pattern as Newbook hotel bookings integration
-- ============================================

-- Custom field mappings (user-configured)
CREATE TABLE IF NOT EXISTS resos_custom_field_mapping (
    id SERIAL PRIMARY KEY,
    field_id VARCHAR(100) NOT NULL UNIQUE,
    field_name VARCHAR(255) NOT NULL,
    field_type VARCHAR(50) NOT NULL,        -- 'radio', 'checkbox', 'text', 'textarea'
    maps_to VARCHAR(50) NOT NULL,           -- 'hotel_guest', 'dbb', 'package', 'booking_number', 'group_exclude', 'allergies', 'ignore'
    value_for_true VARCHAR(100),            -- For radio/checkbox: which value means "yes"
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resos_cf_maps_to ON resos_custom_field_mapping(maps_to);

-- Opening hours/service period mappings (user-configured)
CREATE TABLE IF NOT EXISTS resos_opening_hours_mapping (
    id SERIAL PRIMARY KEY,
    opening_hour_id VARCHAR(100) NOT NULL UNIQUE,
    opening_hour_name VARCHAR(255) NOT NULL,
    period_type VARCHAR(50) NOT NULL,       -- 'breakfast', 'lunch', 'afternoon', 'dinner', 'other', 'ignore'
    display_name VARCHAR(100),              -- User-friendly display name override
    actual_end_time TIME,                   -- Actual service end time (may differ from Resos)
    is_regular BOOLEAN DEFAULT TRUE,        -- Regular vs special/one-off periods
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resos_oh_period ON resos_opening_hours_mapping(period_type);

-- Raw bookings data (PII removed)
CREATE TABLE IF NOT EXISTS resos_bookings_data (
    id SERIAL PRIMARY KEY,
    resos_id VARCHAR(100) NOT NULL UNIQUE,
    booking_date DATE NOT NULL,
    booking_time TIME,
    opening_hour_id VARCHAR(100),
    period_type VARCHAR(50),                -- Denormalized from mapping for fast queries
    covers INTEGER DEFAULT 0,
    status VARCHAR(50),
    source VARCHAR(100),
    table_name VARCHAR(100),
    table_area VARCHAR(100),

    -- Business attributes (extracted from custom fields)
    is_hotel_guest BOOLEAN,
    is_dbb BOOLEAN,
    is_package BOOLEAN,
    hotel_booking_number VARCHAR(100),      -- Primary/lead hotel booking (e.g., "NB12345")
    group_exclude_field TEXT,               -- Additional bookings + excludes: "#12346,#12347,NOT-#56748"

    -- Aggregated fields
    total_guests INTEGER DEFAULT 0,

    -- Metadata
    booking_placed TIMESTAMP,               -- CRITICAL: For pace/pickup forecasting
    notes TEXT,                             -- Sanitized notes (PII removed)
    raw_json JSONB,                         -- Full Resos API response minus guest object
    fetched_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resos_bookings_date ON resos_bookings_data(booking_date);
CREATE INDEX IF NOT EXISTS idx_resos_bookings_status ON resos_bookings_data(status);
CREATE INDEX IF NOT EXISTS idx_resos_bookings_period ON resos_bookings_data(period_type);
CREATE INDEX IF NOT EXISTS idx_resos_bookings_opening_hour ON resos_bookings_data(opening_hour_id);
CREATE INDEX IF NOT EXISTS idx_resos_bookings_placed ON resos_bookings_data(booking_placed);
CREATE INDEX IF NOT EXISTS idx_resos_bookings_hotel_guest ON resos_bookings_data(is_hotel_guest);
CREATE INDEX IF NOT EXISTS idx_resos_bookings_hotel_number ON resos_bookings_data(hotel_booking_number);

-- Daily aggregated stats
CREATE TABLE IF NOT EXISTS resos_bookings_stats (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,

    -- Total covers by period type
    breakfast_covers INTEGER DEFAULT 0,
    lunch_covers INTEGER DEFAULT 0,
    afternoon_covers INTEGER DEFAULT 0,
    dinner_covers INTEGER DEFAULT 0,
    other_covers INTEGER DEFAULT 0,
    total_covers INTEGER DEFAULT 0,

    -- Booking counts by period type
    breakfast_bookings INTEGER DEFAULT 0,
    lunch_bookings INTEGER DEFAULT 0,
    afternoon_bookings INTEGER DEFAULT 0,
    dinner_bookings INTEGER DEFAULT 0,
    other_bookings INTEGER DEFAULT 0,
    total_bookings INTEGER DEFAULT 0,

    -- Business segment breakdowns
    covers_by_source JSONB DEFAULT '{}',            -- {"Website": 120, "Phone": 45}
    covers_by_period JSONB DEFAULT '{}',            -- {"oh_dinner_fri": {"period_type": "dinner", "covers": 86, "bookings": 28}}
    hotel_guest_covers INTEGER DEFAULT 0,
    non_hotel_guest_covers INTEGER DEFAULT 0,
    dbb_covers INTEGER DEFAULT 0,
    package_covers INTEGER DEFAULT 0,

    -- Hotel booking correlation (for Newbook matching)
    hotel_booking_numbers JSONB DEFAULT '{}',       -- {"NB12345": "resos_booking_id", "NB12346": "resos_booking_id"}
    distinct_hotel_bookings INTEGER DEFAULT 0,      -- Count of unique hotel booking numbers
    bookings_with_hotel_link INTEGER DEFAULT 0,     -- Count of Resos bookings that have hotel links

    -- Average party sizes
    avg_party_size DECIMAL(5,2),
    avg_party_size_by_period JSONB DEFAULT '{}',    -- {"breakfast": 2.5, "lunch": 3.0, "dinner": 3.5}

    aggregated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resos_stats_date ON resos_bookings_stats(date);

-- Booking pace (lead-time snapshots with type)
CREATE TABLE IF NOT EXISTS resos_booking_pace (
    id SERIAL PRIMARY KEY,
    booking_date DATE NOT NULL,
    pace_type VARCHAR(20) NOT NULL,         -- 'total', 'resident', 'non_resident'

    -- Monthly intervals: months 7-12 (6 columns)
    d365 INTEGER, d330 INTEGER, d300 INTEGER, d270 INTEGER, d240 INTEGER, d210 INTEGER,

    -- Weekly intervals: weeks 5-25 (21 columns)
    d177 INTEGER, d170 INTEGER, d163 INTEGER, d156 INTEGER, d149 INTEGER,
    d142 INTEGER, d135 INTEGER, d128 INTEGER, d121 INTEGER, d114 INTEGER,
    d107 INTEGER, d100 INTEGER, d93 INTEGER, d86 INTEGER, d79 INTEGER,
    d72 INTEGER, d65 INTEGER, d58 INTEGER, d51 INTEGER, d44 INTEGER, d37 INTEGER,

    -- Daily intervals: days 0-30 (31 columns)
    d30 INTEGER, d29 INTEGER, d28 INTEGER, d27 INTEGER, d26 INTEGER,
    d25 INTEGER, d24 INTEGER, d23 INTEGER, d22 INTEGER, d21 INTEGER,
    d20 INTEGER, d19 INTEGER, d18 INTEGER, d17 INTEGER, d16 INTEGER,
    d15 INTEGER, d14 INTEGER, d13 INTEGER, d12 INTEGER, d11 INTEGER,
    d10 INTEGER, d9 INTEGER, d8 INTEGER, d7 INTEGER, d6 INTEGER,
    d5 INTEGER, d4 INTEGER, d3 INTEGER, d2 INTEGER, d1 INTEGER, d0 INTEGER,

    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(booking_date, pace_type)
);

CREATE INDEX IF NOT EXISTS idx_resos_pace_date_type ON resos_booking_pace(booking_date, pace_type);
CREATE INDEX IF NOT EXISTS idx_resos_pace_type ON resos_booking_pace(pace_type);

-- Manual breakfast periods
CREATE TABLE IF NOT EXISTS resos_manual_breakfast_periods (
    id SERIAL PRIMARY KEY,
    day_of_week INTEGER NOT NULL,          -- 1=Monday, 7=Sunday
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(day_of_week)
);

CREATE INDEX IF NOT EXISTS idx_resos_manual_breakfast_day ON resos_manual_breakfast_periods(day_of_week, is_active);

-- Add Resos sync config to system_config
INSERT INTO system_config (config_key, description) VALUES
('sync_resos_bookings_enabled', 'Enable automatic Resos bookings sync (true/false)'),
('sync_resos_bookings_time', 'Resos bookings sync time (HH:MM)'),
('last_resos_aggregation_at', 'Timestamp of last Resos bookings aggregation'),
('resos_enable_manual_breakfast', 'Enable manual breakfast configuration (true/false)')
ON CONFLICT (config_key) DO NOTHING;

-- Set defaults
UPDATE system_config SET config_value = 'false' WHERE config_key = 'sync_resos_bookings_enabled' AND config_value IS NULL;
UPDATE system_config SET config_value = '05:05' WHERE config_key = 'sync_resos_bookings_time' AND config_value IS NULL;
UPDATE system_config SET config_value = 'false' WHERE config_key = 'resos_enable_manual_breakfast' AND config_value IS NULL;
