-- Forecasting Application Database Schema
-- PostgreSQL 15+
-- Database: forecast_data (created via POSTGRES_DB env var)

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- USERS & AUTHENTICATION
-- ============================================

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Default admin user (password: admin123 - change in production!)
INSERT INTO users (username, password_hash, display_name) VALUES
('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VTtYH0lHXG0Kku', 'Administrator')
ON CONFLICT (username) DO NOTHING;

-- ============================================
-- API KEYS (for external integrations)
-- ============================================

CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    key_hash VARCHAR(64) NOT NULL UNIQUE,     -- SHA256 hash of key (never store plaintext)
    key_prefix VARCHAR(20) NOT NULL,          -- First chars for display (e.g., "fk_abc123...")
    name VARCHAR(100) NOT NULL,               -- Descriptive name (e.g., "Kitchen Flash App")
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP,
    created_by VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active);

-- ============================================
-- SYSTEM CONFIGURATION
-- ============================================

CREATE TABLE IF NOT EXISTS system_config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT,
    is_encrypted BOOLEAN DEFAULT FALSE,
    description TEXT,
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by VARCHAR(100)
);

-- Default config entries
INSERT INTO system_config (config_key, description) VALUES
('newbook_api_key', 'Newbook API Key'),
('newbook_username', 'Newbook Username'),
('newbook_password', 'Newbook Password'),
('newbook_region', 'Newbook Region Code'),
('resos_api_key', 'Resos API Key'),
('total_rooms', 'Total number of hotel rooms'),
('hotel_name', 'Hotel/Property Name'),
('timezone', 'Local timezone (e.g., Europe/London)'),
('accommodation_vat_rate', 'VAT rate for accommodation (e.g., 0.20 for 20%)'),
('sync_newbook_enabled', 'Enable automatic Newbook sync (true/false)'),
('sync_resos_enabled', 'Enable automatic Resos sync (true/false)'),
('sync_schedule_time', 'Time for daily sync (HH:MM format)'),
('sync_newbook_bookings_enabled', 'Enable automatic Newbook bookings data sync (true/false)'),
('sync_newbook_bookings_type', 'Newbook bookings sync type (incremental/full)'),
('sync_newbook_bookings_time', 'Newbook bookings sync time (HH:MM)'),
('sync_newbook_occupancy_enabled', 'Enable automatic Newbook occupancy report sync (true/false)'),
('sync_newbook_occupancy_time', 'Newbook occupancy report sync time (HH:MM)'),
('last_bookings_aggregation_at', 'Timestamp of last bookings stats aggregation'),
('sync_newbook_earned_revenue_enabled', 'Enable automatic Newbook earned revenue sync (true/false)'),
('sync_newbook_earned_revenue_time', 'Newbook earned revenue sync time (HH:MM)'),
('last_revenue_aggregation_at', 'Timestamp of last revenue aggregation'),
('sync_newbook_current_rates_enabled', 'Enable automatic Newbook current rates sync for pickup-v2 (true/false)'),
('sync_newbook_current_rates_time', 'Newbook current rates sync time (HH:MM)')
ON CONFLICT (config_key) DO NOTHING;

-- Set defaults
UPDATE system_config SET config_value = '80' WHERE config_key = 'total_rooms' AND config_value IS NULL;
UPDATE system_config SET config_value = 'Europe/London' WHERE config_key = 'timezone' AND config_value IS NULL;
UPDATE system_config SET config_value = '0.20' WHERE config_key = 'accommodation_vat_rate' AND config_value IS NULL;
UPDATE system_config SET config_value = 'false' WHERE config_key = 'sync_newbook_enabled' AND config_value IS NULL;
UPDATE system_config SET config_value = 'false' WHERE config_key = 'sync_resos_enabled' AND config_value IS NULL;
UPDATE system_config SET config_value = '05:00' WHERE config_key = 'sync_schedule_time' AND config_value IS NULL;
UPDATE system_config SET config_value = 'false' WHERE config_key = 'sync_newbook_bookings_enabled' AND config_value IS NULL;
UPDATE system_config SET config_value = 'incremental' WHERE config_key = 'sync_newbook_bookings_type' AND config_value IS NULL;
UPDATE system_config SET config_value = '05:00' WHERE config_key = 'sync_newbook_bookings_time' AND config_value IS NULL;
UPDATE system_config SET config_value = 'false' WHERE config_key = 'sync_newbook_occupancy_enabled' AND config_value IS NULL;
UPDATE system_config SET config_value = '05:00' WHERE config_key = 'sync_newbook_occupancy_time' AND config_value IS NULL;
UPDATE system_config SET config_value = 'false' WHERE config_key = 'sync_newbook_earned_revenue_enabled' AND config_value IS NULL;
UPDATE system_config SET config_value = '05:10' WHERE config_key = 'sync_newbook_earned_revenue_time' AND config_value IS NULL;
UPDATE system_config SET config_value = 'false' WHERE config_key = 'sync_newbook_current_rates_enabled' AND config_value IS NULL;
UPDATE system_config SET config_value = '05:20' WHERE config_key = 'sync_newbook_current_rates_time' AND config_value IS NULL;

-- ============================================
-- TAX RATES (date-based tax configuration)
-- ============================================

CREATE TABLE IF NOT EXISTS tax_rates (
    id SERIAL PRIMARY KEY,
    tax_type VARCHAR(50) NOT NULL,          -- 'accommodation_vat', 'food_vat', etc.
    rate DECIMAL(5,4) NOT NULL,             -- e.g., 0.20 for 20%
    effective_from DATE NOT NULL,           -- Date this rate becomes effective
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(tax_type, effective_from)
);

CREATE INDEX IF NOT EXISTS idx_tax_rates_type ON tax_rates(tax_type);
CREATE INDEX IF NOT EXISTS idx_tax_rates_effective ON tax_rates(tax_type, effective_from);

-- Default accommodation VAT rate (20% from 2022-01-01)
INSERT INTO tax_rates (tax_type, rate, effective_from) VALUES
('accommodation_vat', 0.20, '2022-01-01')
ON CONFLICT (tax_type, effective_from) DO NOTHING;

-- ============================================
-- NEWBOOK ROOM CATEGORIES (for occupancy settings)
-- ============================================

CREATE TABLE IF NOT EXISTS newbook_room_categories (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(50) NOT NULL UNIQUE,
    site_name VARCHAR(255) NOT NULL,
    site_type VARCHAR(100),
    room_count INTEGER DEFAULT 0,
    is_included BOOLEAN DEFAULT TRUE,
    display_order INTEGER DEFAULT 0,
    fetched_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- NEWBOOK GL ACCOUNTS (for revenue mapping)
-- ============================================

CREATE TABLE IF NOT EXISTS newbook_gl_accounts (
    id SERIAL PRIMARY KEY,
    gl_account_id VARCHAR(50) NOT NULL UNIQUE,
    gl_code VARCHAR(50),
    gl_name VARCHAR(255),
    gl_group_id VARCHAR(50),
    gl_group_name VARCHAR(255),
    department VARCHAR(20),  -- 'accommodation', 'dry', 'wet', or null
    last_seen_date DATE,
    total_amount DECIMAL(14,2) DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    fetched_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gl_accounts_department ON newbook_gl_accounts(department);
CREATE INDEX IF NOT EXISTS idx_gl_accounts_group ON newbook_gl_accounts(gl_group_name);

-- ============================================
-- NEWBOOK BOOKINGS DATA (historical booking data)
-- ============================================

CREATE TABLE IF NOT EXISTS newbook_bookings_data (
    id SERIAL PRIMARY KEY,
    newbook_id VARCHAR(50) NOT NULL UNIQUE,
    booking_reference VARCHAR(100),
    bookings_group_id VARCHAR(50),
    booking_placed TIMESTAMP,  -- When booking was created (for lead time calculations)
    arrival_date DATE NOT NULL,
    departure_date DATE NOT NULL,
    nights INTEGER,
    adults INTEGER DEFAULT 0,
    children INTEGER DEFAULT 0,
    infants INTEGER DEFAULT 0,
    total_guests INTEGER,
    category_id VARCHAR(50),
    room_type VARCHAR(100),
    site_id VARCHAR(50),
    room_number VARCHAR(50),
    status VARCHAR(50),
    total_amount DECIMAL(12,2),
    tariff_name VARCHAR(255),
    tariff_total DECIMAL(12,2),
    travel_agent_id VARCHAR(50),
    travel_agent_name VARCHAR(255),
    travel_agent_commission DECIMAL(12,2),
    booking_source_id VARCHAR(50),
    booking_source_name VARCHAR(255),
    booking_parent_source_id VARCHAR(50),
    booking_parent_source_name VARCHAR(255),
    booking_method_id VARCHAR(50),
    booking_method_name VARCHAR(100),
    raw_json JSONB,
    fetched_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bookings_arrival ON newbook_bookings_data(arrival_date);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON newbook_bookings_data(status);
CREATE INDEX IF NOT EXISTS idx_bookings_placed ON newbook_bookings_data(booking_placed);

-- ============================================
-- NEWBOOK EARNED REVENUE DATA (historical revenue data)
-- ============================================

CREATE TABLE IF NOT EXISTS newbook_earned_revenue_data (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    gl_account_id VARCHAR(50),
    gl_code VARCHAR(50),
    gl_name VARCHAR(255),
    amount_gross DECIMAL(12,2) DEFAULT 0,
    amount_net DECIMAL(12,2) DEFAULT 0,
    revenue_type VARCHAR(30),
    fetched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, gl_account_id)
);

CREATE INDEX IF NOT EXISTS idx_earned_revenue_data_date ON newbook_earned_revenue_data(date);
CREATE INDEX IF NOT EXISTS idx_earned_revenue_data_type ON newbook_earned_revenue_data(date, revenue_type);

-- ============================================
-- NEWBOOK NET REVENUE DATA (aggregated by department)
-- ============================================

CREATE TABLE IF NOT EXISTS newbook_net_revenue_data (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    accommodation DECIMAL(12,2) DEFAULT 0,  -- Net accommodation revenue
    dry DECIMAL(12,2) DEFAULT 0,            -- Net dry (food) revenue
    wet DECIMAL(12,2) DEFAULT 0,            -- Net wet (beverage) revenue
    aggregated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_net_revenue_data_date ON newbook_net_revenue_data(date);

-- ============================================
-- NEWBOOK OCCUPANCY REPORT DATA (official capacity & occupancy)
-- ============================================

CREATE TABLE IF NOT EXISTS newbook_occupancy_report_data (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    category_id VARCHAR(50) NOT NULL,
    category_name VARCHAR(255),
    available INTEGER DEFAULT 0,       -- Total configured rooms for category
    occupied INTEGER DEFAULT 0,        -- Official occupied per Newbook
    maintenance INTEGER DEFAULT 0,     -- Rooms offline (deduct from available for bookable rooms)
    allotted INTEGER DEFAULT 0,        -- Block allocations
    revenue_gross DECIMAL(12,2) DEFAULT 0,
    revenue_net DECIMAL(12,2) DEFAULT 0,
    occupancy_pct DECIMAL(5,2),
    fetched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, category_id)
);

CREATE INDEX IF NOT EXISTS idx_occupancy_report_data_date ON newbook_occupancy_report_data(date);

-- ============================================
-- SYNC LOGGING
-- ============================================

CREATE TABLE IF NOT EXISTS sync_log (
    id SERIAL PRIMARY KEY,
    sync_type VARCHAR(30) NOT NULL,
    source VARCHAR(20) NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status VARCHAR(20) NOT NULL,
    records_fetched INTEGER,
    records_created INTEGER,
    records_updated INTEGER,
    date_from DATE,
    date_to DATE,
    error_message TEXT,
    triggered_by VARCHAR(100)
);

-- ============================================
-- NEWBOOK BOOKINGS STATS (aggregated daily stats)
-- ============================================

CREATE TABLE IF NOT EXISTS newbook_bookings_stats (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,

    -- Room availability (from newbook_occupancy_report_data)
    rooms_count INTEGER DEFAULT 0,           -- Total available rooms (included categories)
    maintenance_count INTEGER DEFAULT 0,     -- Rooms offline/maintenance
    bookable_count INTEGER DEFAULT 0,        -- rooms_count - maintenance_count

    -- Occupancy totals (from bookings)
    booking_count INTEGER DEFAULT 0,         -- Occupied rooms (bookings staying this night)
    guests_count INTEGER DEFAULT 0,
    adults_count INTEGER DEFAULT 0,
    children_count INTEGER DEFAULT 0,
    infants_count INTEGER DEFAULT 0,

    -- Occupancy percentages
    total_occupancy_pct DECIMAL(5,2),        -- booking_count / rooms_count * 100
    bookable_occupancy_pct DECIMAL(5,2),     -- booking_count / bookable_count * 100

    -- Revenue totals
    guest_rate_total DECIMAL(12,2) DEFAULT 0,      -- SUM of calculated_amount (gross)
    net_booking_rev_total DECIMAL(12,2) DEFAULT 0, -- SUM of net accommodation

    -- Per-category breakdowns (JSONB)
    occupancy_by_category JSONB DEFAULT '{}',
    revenue_by_category JSONB DEFAULT '{}',
    availability_by_category JSONB DEFAULT '{}',

    -- Pickup-V2: Rate statistics per category for bounds calculation
    -- Structure: { "category_id": { "min_net": 120, "max_net": 200, "adr_net": 155, "rooms": 12 } }
    rate_stats_by_category JSONB DEFAULT '{}',

    aggregated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bookings_stats_date ON newbook_bookings_stats(date);

-- ============================================
-- NEWBOOK BOOKING PACE (lead-time snapshots for forecasting)
-- ============================================

CREATE TABLE IF NOT EXISTS newbook_booking_pace (
    id SERIAL PRIMARY KEY,
    arrival_date DATE NOT NULL UNIQUE,

    -- Monthly intervals: months 7-12 (6 columns)
    d365 INTEGER,    -- 12 months out
    d330 INTEGER,    -- 11 months out
    d300 INTEGER,    -- 10 months out
    d270 INTEGER,    -- 9 months out
    d240 INTEGER,    -- 8 months out
    d210 INTEGER,    -- 7 months out

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

    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_booking_pace_arrival ON newbook_booking_pace(arrival_date);

-- ============================================
-- PICKUP-V2: CATEGORY BOOKING PACE (per-category room counts at lead times)
-- ============================================

CREATE TABLE IF NOT EXISTS category_booking_pace (
    id SERIAL PRIMARY KEY,
    arrival_date DATE NOT NULL,
    category_id VARCHAR(50) NOT NULL,

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
    UNIQUE(arrival_date, category_id)
);

CREATE INDEX IF NOT EXISTS idx_category_booking_pace_arrival ON category_booking_pace(arrival_date);
CREATE INDEX IF NOT EXISTS idx_category_booking_pace_category ON category_booking_pace(category_id);

-- ============================================
-- PICKUP-V2: REVENUE PACE (booked accommodation revenue at lead times)
-- ============================================

CREATE TABLE IF NOT EXISTS revenue_pace (
    id SERIAL PRIMARY KEY,
    stay_date DATE NOT NULL UNIQUE,

    -- Monthly intervals: months 7-12 (6 columns) - DECIMAL for revenue
    d365 DECIMAL(12,2), d330 DECIMAL(12,2), d300 DECIMAL(12,2),
    d270 DECIMAL(12,2), d240 DECIMAL(12,2), d210 DECIMAL(12,2),

    -- Weekly intervals: weeks 5-25 (21 columns)
    d177 DECIMAL(12,2), d170 DECIMAL(12,2), d163 DECIMAL(12,2), d156 DECIMAL(12,2), d149 DECIMAL(12,2),
    d142 DECIMAL(12,2), d135 DECIMAL(12,2), d128 DECIMAL(12,2), d121 DECIMAL(12,2), d114 DECIMAL(12,2),
    d107 DECIMAL(12,2), d100 DECIMAL(12,2), d93 DECIMAL(12,2), d86 DECIMAL(12,2), d79 DECIMAL(12,2),
    d72 DECIMAL(12,2), d65 DECIMAL(12,2), d58 DECIMAL(12,2), d51 DECIMAL(12,2), d44 DECIMAL(12,2), d37 DECIMAL(12,2),

    -- Daily intervals: days 0-30 (31 columns)
    d30 DECIMAL(12,2), d29 DECIMAL(12,2), d28 DECIMAL(12,2), d27 DECIMAL(12,2), d26 DECIMAL(12,2),
    d25 DECIMAL(12,2), d24 DECIMAL(12,2), d23 DECIMAL(12,2), d22 DECIMAL(12,2), d21 DECIMAL(12,2),
    d20 DECIMAL(12,2), d19 DECIMAL(12,2), d18 DECIMAL(12,2), d17 DECIMAL(12,2), d16 DECIMAL(12,2),
    d15 DECIMAL(12,2), d14 DECIMAL(12,2), d13 DECIMAL(12,2), d12 DECIMAL(12,2), d11 DECIMAL(12,2),
    d10 DECIMAL(12,2), d9 DECIMAL(12,2), d8 DECIMAL(12,2), d7 DECIMAL(12,2), d6 DECIMAL(12,2),
    d5 DECIMAL(12,2), d4 DECIMAL(12,2), d3 DECIMAL(12,2), d2 DECIMAL(12,2), d1 DECIMAL(12,2), d0 DECIMAL(12,2),

    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_revenue_pace_stay ON revenue_pace(stay_date);

-- ============================================
-- PICKUP-V2: CURRENT RATES FROM NEWBOOK (for ceiling calculations)
-- Now with rate history tracking - stores snapshots when rates change
-- ============================================

CREATE TABLE IF NOT EXISTS newbook_current_rates (
    id SERIAL PRIMARY KEY,
    category_id VARCHAR(50) NOT NULL,
    rate_date DATE NOT NULL,
    rate_name VARCHAR(255),
    rate_gross DECIMAL(12,2),
    rate_net DECIMAL(12,2),
    tariffs_data JSONB DEFAULT '{}',  -- All available tariff options with availability status
    valid_from TIMESTAMP DEFAULT NOW(),  -- When this rate version started
    last_verified_at TIMESTAMP DEFAULT NOW()  -- Last time we confirmed rate is still current
    -- No UNIQUE constraint - allows multiple versions per (category_id, rate_date)
);

CREATE INDEX IF NOT EXISTS idx_current_rates_date ON newbook_current_rates(rate_date);
CREATE INDEX IF NOT EXISTS idx_current_rates_category ON newbook_current_rates(category_id);
CREATE INDEX IF NOT EXISTS idx_current_rates_tariffs ON newbook_current_rates USING gin(tariffs_data);
CREATE INDEX IF NOT EXISTS idx_current_rates_latest ON newbook_current_rates(category_id, rate_date, valid_from DESC);

-- Migration: Add tariffs_data column if missing (for existing databases)
ALTER TABLE newbook_current_rates ADD COLUMN IF NOT EXISTS tariffs_data JSONB DEFAULT '{}';

-- Migration: Convert from old schema to new snapshot schema
-- Rename fetched_at to valid_from if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'newbook_current_rates' AND column_name = 'fetched_at') THEN
        ALTER TABLE newbook_current_rates RENAME COLUMN fetched_at TO valid_from;
    END IF;
END $$;

-- Add last_verified_at column if missing
ALTER TABLE newbook_current_rates ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMP DEFAULT NOW();

-- Drop unique constraint if it exists (allows rate history)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint
               WHERE conname = 'newbook_current_rates_category_id_rate_date_key') THEN
        ALTER TABLE newbook_current_rates
        DROP CONSTRAINT newbook_current_rates_category_id_rate_date_key;
    END IF;
END $$;

-- ============================================
-- FORECASTING TABLES (for Prophet, XGBoost, CatBoost models)
-- ============================================

-- Forecast metrics configuration
CREATE TABLE IF NOT EXISTS forecast_metrics (
    id SERIAL PRIMARY KEY,
    metric_code VARCHAR(50) NOT NULL UNIQUE,
    metric_name VARCHAR(100) NOT NULL,
    description TEXT,
    unit VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    use_prophet BOOLEAN DEFAULT TRUE,
    use_xgboost BOOLEAN DEFAULT TRUE,
    use_pickup BOOLEAN DEFAULT FALSE,
    use_catboost BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Default metrics for forecasting
INSERT INTO forecast_metrics (metric_code, metric_name, description, unit, use_prophet, use_xgboost, use_pickup, use_catboost) VALUES
('hotel_occupancy_pct', 'Hotel Occupancy %', 'Percentage of available rooms occupied', '%', TRUE, TRUE, TRUE, TRUE),
('hotel_room_nights', 'Room Nights', 'Number of rooms sold', 'rooms', TRUE, TRUE, TRUE, TRUE),
('hotel_guests', 'Guest Count', 'Total guests staying', 'guests', TRUE, TRUE, FALSE, TRUE),
('hotel_arrivals', 'Arrivals', 'Number of check-ins', 'arrivals', TRUE, TRUE, FALSE, TRUE)
ON CONFLICT (metric_code) DO NOTHING;

-- Daily metrics (actuals storage - populated from newbook_bookings_stats)
CREATE TABLE IF NOT EXISTS daily_metrics (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    metric_code VARCHAR(50) NOT NULL,
    actual_value DECIMAL(12,2),
    source VARCHAR(50) DEFAULT 'newbook',
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, metric_code)
);

CREATE INDEX IF NOT EXISTS idx_daily_metrics_date ON daily_metrics(date);
CREATE INDEX IF NOT EXISTS idx_daily_metrics_code ON daily_metrics(metric_code, date);

-- Forecasts storage
CREATE TABLE IF NOT EXISTS forecasts (
    id SERIAL PRIMARY KEY,
    run_id UUID,
    forecast_date DATE NOT NULL,
    forecast_type VARCHAR(50) NOT NULL,
    model_type VARCHAR(20) NOT NULL,  -- 'prophet', 'xgboost', 'pickup', 'catboost'
    predicted_value DECIMAL(12,2) NOT NULL,
    lower_bound DECIMAL(12,2),
    upper_bound DECIMAL(12,2),
    generated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(forecast_date, forecast_type, model_type, generated_at)
);

CREATE INDEX IF NOT EXISTS idx_forecasts_date ON forecasts(forecast_date);
CREATE INDEX IF NOT EXISTS idx_forecasts_type ON forecasts(forecast_type, model_type);
CREATE INDEX IF NOT EXISTS idx_forecasts_generated ON forecasts(generated_at DESC);

-- Actual vs forecast comparison
CREATE TABLE IF NOT EXISTS actual_vs_forecast (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    metric_type VARCHAR(50) NOT NULL,
    actual_value DECIMAL(12,2),
    budget_value DECIMAL(12,2),
    -- Prophet
    prophet_forecast DECIMAL(12,2),
    prophet_lower DECIMAL(12,2),
    prophet_upper DECIMAL(12,2),
    prophet_error DECIMAL(12,4),
    prophet_pct_error DECIMAL(8,4),
    -- XGBoost
    xgboost_forecast DECIMAL(12,2),
    xgboost_error DECIMAL(12,4),
    xgboost_pct_error DECIMAL(8,4),
    -- Pickup
    pickup_forecast DECIMAL(12,2),
    pickup_error DECIMAL(12,4),
    pickup_pct_error DECIMAL(8,4),
    -- CatBoost
    catboost_forecast DECIMAL(12,2),
    catboost_error DECIMAL(12,4),
    catboost_pct_error DECIMAL(8,4),
    -- Analysis
    best_model VARCHAR(20),
    calculated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, metric_type)
);

CREATE INDEX IF NOT EXISTS idx_actual_vs_forecast_date ON actual_vs_forecast(date);
CREATE INDEX IF NOT EXISTS idx_actual_vs_forecast_type ON actual_vs_forecast(metric_type);

-- Prophet decomposition storage
CREATE TABLE IF NOT EXISTS prophet_decomposition (
    id SERIAL PRIMARY KEY,
    run_id UUID,
    forecast_date DATE NOT NULL,
    forecast_type VARCHAR(50) NOT NULL,
    trend DECIMAL(12,2),
    yearly_seasonality DECIMAL(12,2),
    weekly_seasonality DECIMAL(12,2),
    daily_seasonality DECIMAL(12,2),
    holiday_effects JSONB,
    regressor_effects JSONB,
    generated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prophet_decomposition_date ON prophet_decomposition(forecast_date, forecast_type);

-- XGBoost SHAP explanations
CREATE TABLE IF NOT EXISTS xgboost_explanations (
    id SERIAL PRIMARY KEY,
    run_id UUID,
    forecast_date DATE NOT NULL,
    forecast_type VARCHAR(50) NOT NULL,
    base_value DECIMAL(12,2),
    feature_values JSONB,
    shap_values JSONB,
    top_positive JSONB,
    top_negative JSONB,
    generated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_xgboost_explanations_date ON xgboost_explanations(forecast_date, forecast_type);

-- Pickup model explanations
CREATE TABLE IF NOT EXISTS pickup_explanations (
    id SERIAL PRIMARY KEY,
    run_id UUID,
    forecast_date DATE NOT NULL,
    forecast_type VARCHAR(50) NOT NULL,
    current_otb DECIMAL(12,2),
    days_out INTEGER,
    comparison_date DATE,
    comparison_otb DECIMAL(12,2),
    comparison_final DECIMAL(12,2),
    pickup_curve_pct DECIMAL(8,4),
    pickup_curve_stddev DECIMAL(8,4),
    pace_vs_prior_pct DECIMAL(8,4),
    projection_method VARCHAR(50),
    projected_value DECIMAL(12,2),
    confidence_note TEXT,
    generated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pickup_explanations_date ON pickup_explanations(forecast_date, forecast_type);

-- Monthly budgets from FD
CREATE TABLE IF NOT EXISTS monthly_budgets (
    id SERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
    budget_type VARCHAR(50) NOT NULL,
    budget_value DECIMAL(12,2) NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(year, month, budget_type)
);

CREATE INDEX IF NOT EXISTS idx_monthly_budgets_year ON monthly_budgets(year, budget_type);

-- Daily budgets (distributed from monthly)
CREATE TABLE IF NOT EXISTS daily_budgets (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    budget_type VARCHAR(50) NOT NULL,
    budget_value DECIMAL(12,2),
    distribution_method VARCHAR(50),
    prior_year_pct DECIMAL(10,6),
    monthly_budget_id INTEGER REFERENCES monthly_budgets(id),
    calculated_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    UNIQUE(date, budget_type)
);

CREATE INDEX IF NOT EXISTS idx_daily_budgets_date ON daily_budgets(date, budget_type);

-- Forecast snapshots (for tracking how forecasts evolve over time)
CREATE TABLE IF NOT EXISTS forecast_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    target_date DATE NOT NULL,
    metric_code VARCHAR(50) NOT NULL,
    days_out INTEGER NOT NULL,
    prophet_value DECIMAL(12,2),
    xgboost_value DECIMAL(12,2),
    pickup_value DECIMAL(12,2),
    catboost_value DECIMAL(12,2),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(snapshot_date, target_date, metric_code)
);

CREATE INDEX IF NOT EXISTS idx_forecast_snapshots_target ON forecast_snapshots(target_date, metric_code);

-- ============================================
-- USER ROLES (migration for existing users table)
-- ============================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'admin';

-- ============================================
-- RECONCILIATION: CASH UP SESSIONS
-- ============================================

CREATE TABLE IF NOT EXISTS recon_cash_ups (
    id SERIAL PRIMARY KEY,
    session_date DATE NOT NULL UNIQUE,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'final')),
    total_float_counted DECIMAL(10,2) DEFAULT 0.00,
    total_cash_counted DECIMAL(10,2) DEFAULT 0.00,
    notes TEXT,
    submitted_at TIMESTAMP,
    submitted_by INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_recon_cash_ups_date ON recon_cash_ups(session_date);
CREATE INDEX IF NOT EXISTS idx_recon_cash_ups_status ON recon_cash_ups(status);

-- ============================================
-- RECONCILIATION: DENOMINATION COUNTS
-- ============================================

CREATE TABLE IF NOT EXISTS recon_denominations (
    id SERIAL PRIMARY KEY,
    cash_up_id INTEGER NOT NULL REFERENCES recon_cash_ups(id) ON DELETE CASCADE,
    count_type VARCHAR(20) NOT NULL DEFAULT 'takings' CHECK (count_type IN ('float', 'takings')),
    denomination_type VARCHAR(20) NOT NULL CHECK (denomination_type IN ('note', 'coin')),
    denomination_value DECIMAL(10,2) NOT NULL,
    quantity INTEGER DEFAULT NULL,
    value_entered DECIMAL(10,2) DEFAULT NULL,
    total_amount DECIMAL(10,2) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_recon_denoms_cashup ON recon_denominations(cash_up_id);

-- ============================================
-- RECONCILIATION: CARD MACHINE DATA
-- ============================================

CREATE TABLE IF NOT EXISTS recon_card_machines (
    id SERIAL PRIMARY KEY,
    cash_up_id INTEGER NOT NULL REFERENCES recon_cash_ups(id) ON DELETE CASCADE,
    machine_name VARCHAR(100) NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    amex_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    visa_mc_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00
);

CREATE INDEX IF NOT EXISTS idx_recon_cards_cashup ON recon_card_machines(cash_up_id);

-- ============================================
-- RECONCILIATION: NEWBOOK PAYMENT RECORDS
-- ============================================

CREATE TABLE IF NOT EXISTS recon_payment_records (
    id SERIAL PRIMARY KEY,
    cash_up_id INTEGER REFERENCES recon_cash_ups(id) ON DELETE SET NULL,
    newbook_payment_id VARCHAR(100),
    booking_id VARCHAR(100),
    guest_name VARCHAR(255),
    payment_date TIMESTAMP NOT NULL,
    payment_type VARCHAR(100),
    payment_method VARCHAR(50),
    transaction_method VARCHAR(50),
    card_type VARCHAR(50),
    amount DECIMAL(10,2) NOT NULL,
    tendered DECIMAL(10,2),
    processed_by VARCHAR(255),
    item_type VARCHAR(50),
    synced_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recon_payments_cashup ON recon_payment_records(cash_up_id);
CREATE INDEX IF NOT EXISTS idx_recon_payments_date ON recon_payment_records(payment_date);

-- ============================================
-- RECONCILIATION: RECONCILIATION RESULTS
-- ============================================

CREATE TABLE IF NOT EXISTS recon_reconciliation (
    id SERIAL PRIMARY KEY,
    cash_up_id INTEGER NOT NULL REFERENCES recon_cash_ups(id) ON DELETE CASCADE,
    category VARCHAR(50) NOT NULL,
    banked_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    reported_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    variance DECIMAL(10,2) NOT NULL DEFAULT 0.00
);

CREATE INDEX IF NOT EXISTS idx_recon_recon_cashup ON recon_reconciliation(cash_up_id);

-- ============================================
-- RECONCILIATION: DAILY STATISTICS
-- ============================================

CREATE TABLE IF NOT EXISTS recon_daily_stats (
    id SERIAL PRIMARY KEY,
    business_date DATE NOT NULL UNIQUE,
    gross_sales DECIMAL(10,2) DEFAULT 0.00,
    debtors_creditors_balance DECIMAL(10,2) DEFAULT 0.00,
    rooms_sold INTEGER DEFAULT 0,
    total_people INTEGER DEFAULT 0,
    source VARCHAR(50) DEFAULT 'manual',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recon_daily_date ON recon_daily_stats(business_date);

-- ============================================
-- RECONCILIATION: SALES BREAKDOWN
-- ============================================

CREATE TABLE IF NOT EXISTS recon_sales_breakdown (
    id SERIAL PRIMARY KEY,
    business_date DATE NOT NULL,
    category VARCHAR(100) NOT NULL,
    net_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00
);

CREATE INDEX IF NOT EXISTS idx_recon_sales_date ON recon_sales_breakdown(business_date);

-- ============================================
-- RECONCILIATION: FLOAT COUNTS (Petty Cash, Change Tin, Safe Cash)
-- ============================================

CREATE TABLE IF NOT EXISTS recon_float_counts (
    id SERIAL PRIMARY KEY,
    count_type VARCHAR(20) NOT NULL CHECK (count_type IN ('petty_cash', 'change_tin', 'safe_cash')),
    count_date TIMESTAMP NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    total_counted DECIMAL(10,2) DEFAULT 0.00,
    total_receipts DECIMAL(10,2) DEFAULT 0.00,
    target_amount DECIMAL(10,2) DEFAULT 0.00,
    variance DECIMAL(10,2) DEFAULT 0.00,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_recon_floats_type ON recon_float_counts(count_type);
CREATE INDEX IF NOT EXISTS idx_recon_floats_date ON recon_float_counts(count_date);

-- ============================================
-- RECONCILIATION: FLOAT DENOMINATION COUNTS
-- ============================================

CREATE TABLE IF NOT EXISTS recon_float_denominations (
    id SERIAL PRIMARY KEY,
    float_count_id INTEGER NOT NULL REFERENCES recon_float_counts(id) ON DELETE CASCADE,
    denomination_value DECIMAL(10,2) NOT NULL,
    quantity INTEGER DEFAULT 0,
    total_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00
);

CREATE INDEX IF NOT EXISTS idx_recon_float_denoms_fc ON recon_float_denominations(float_count_id);

-- ============================================
-- RECONCILIATION: FLOAT RECEIPTS
-- ============================================

CREATE TABLE IF NOT EXISTS recon_float_receipts (
    id SERIAL PRIMARY KEY,
    float_count_id INTEGER NOT NULL REFERENCES recon_float_counts(id) ON DELETE CASCADE,
    receipt_value DECIMAL(10,2) NOT NULL,
    receipt_description VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_recon_float_receipts_fc ON recon_float_receipts(float_count_id);

-- ============================================
-- RECONCILIATION: CASH COUNT ATTACHMENTS
-- ============================================

CREATE TABLE IF NOT EXISTS recon_attachments (
    id SERIAL PRIMARY KEY,
    cash_up_id INTEGER NOT NULL REFERENCES recon_cash_ups(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_size BIGINT NOT NULL,
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    uploaded_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recon_attachments_cashup ON recon_attachments(cash_up_id);

-- ============================================
-- RECONCILIATION: SYSTEM CONFIG ENTRIES
-- ============================================

INSERT INTO system_config (config_key, config_value, description) VALUES
('recon_expected_till_float', '300.00', 'Expected till float amount (GBP)'),
('recon_variance_threshold', '10.00', 'Variance threshold for highlighting (GBP)'),
('recon_default_report_days', '7', 'Default number of days for multi-day reports'),
('recon_petty_cash_target', '200.00', 'Target amount for petty cash float'),
('recon_change_tin_breakdown', '{"50.00":0,"20.00":0,"10.00":0,"5.00":0,"2.00":20.00,"1.00":20.00,"0.50":10.00,"0.20":10.00,"0.10":5.00,"0.05":5.00}', 'Change tin denomination breakdown targets (JSON)'),
('recon_denominations', '{"notes":[50.00,20.00,10.00,5.00],"coins":[2.00,1.00,0.50,0.20,0.10,0.05,0.02,0.01]}', 'GBP denominations configuration (JSON)'),
('recon_sales_breakdown_columns', '[]', 'Sales breakdown column configuration (JSON)'),
('recon_safe_cash_target', '0.00', 'Target amount for safe cash float')
ON CONFLICT (config_key) DO NOTHING;
