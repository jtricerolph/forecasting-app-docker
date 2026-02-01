-- Forecasting Application Database Schema (Clean)
-- PostgreSQL 15+
-- New database: forecast_data

-- Create the forecast_data database if it doesn't exist
-- Note: This runs as superuser during docker-entrypoint
SELECT 'CREATE DATABASE forecast_data OWNER forecast'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'forecast_data')\gexec

-- Connect to forecast_data database
\c forecast_data

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
('last_revenue_aggregation_at', 'Timestamp of last revenue aggregation')
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
-- FORECASTING TABLES (for Prophet, XGBoost, TFT models)
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
    use_tft BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Default metrics for forecasting
INSERT INTO forecast_metrics (metric_code, metric_name, description, unit, use_prophet, use_xgboost, use_pickup, use_tft) VALUES
('hotel_occupancy_pct', 'Hotel Occupancy %', 'Percentage of available rooms occupied', '%', TRUE, TRUE, TRUE, TRUE),
('hotel_room_nights', 'Room Nights', 'Number of rooms sold', 'rooms', TRUE, TRUE, TRUE, TRUE),
('hotel_guests', 'Guest Count', 'Total guests staying', 'guests', TRUE, TRUE, FALSE, FALSE),
('hotel_arrivals', 'Arrivals', 'Number of check-ins', 'arrivals', TRUE, TRUE, FALSE, FALSE)
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
    model_type VARCHAR(20) NOT NULL,  -- 'prophet', 'xgboost', 'pickup', 'tft'
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
    -- TFT
    tft_forecast DECIMAL(12,2),
    tft_lower DECIMAL(12,2),
    tft_upper DECIMAL(12,2),
    tft_error DECIMAL(12,4),
    tft_pct_error DECIMAL(8,4),
    -- Analysis
    best_model VARCHAR(20),
    calculated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, metric_type)
);

CREATE INDEX IF NOT EXISTS idx_actual_vs_forecast_date ON actual_vs_forecast(date);
CREATE INDEX IF NOT EXISTS idx_actual_vs_forecast_type ON actual_vs_forecast(metric_type);

-- TFT explanations table
CREATE TABLE IF NOT EXISTS tft_explanations (
    id SERIAL PRIMARY KEY,
    run_id UUID,
    forecast_date DATE NOT NULL,
    forecast_type VARCHAR(50) NOT NULL,
    encoder_attention JSONB,
    decoder_attention JSONB,
    variable_importance JSONB,
    quantile_10 DECIMAL(12,2),
    quantile_50 DECIMAL(12,2),
    quantile_90 DECIMAL(12,2),
    top_historical_drivers JSONB,
    top_future_drivers JSONB,
    generated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tft_explanations_date ON tft_explanations(forecast_date, forecast_type);

-- TFT training log
CREATE TABLE IF NOT EXISTS tft_training_log (
    id SERIAL PRIMARY KEY,
    forecast_type VARCHAR(50) NOT NULL,
    trained_at TIMESTAMP DEFAULT NOW(),
    training_from DATE NOT NULL,
    training_to DATE NOT NULL,
    training_rows INTEGER,
    validation_loss DECIMAL(12,6),
    hyperparameters JSONB,
    feature_list JSONB,
    encoder_length INTEGER,
    prediction_length INTEGER,
    model_path VARCHAR(500),
    training_time_seconds INTEGER,
    gpu_used BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_tft_training_log_type ON tft_training_log(forecast_type, trained_at DESC);

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

-- Daily budgets
CREATE TABLE IF NOT EXISTS daily_budgets (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    budget_type VARCHAR(50) NOT NULL,
    budget_value DECIMAL(12,2),
    created_at TIMESTAMP DEFAULT NOW(),
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
    tft_value DECIMAL(12,2),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(snapshot_date, target_date, metric_code)
);

CREATE INDEX IF NOT EXISTS idx_forecast_snapshots_target ON forecast_snapshots(target_date, metric_code);
