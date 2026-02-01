-- Forecasting Application Database Schema
-- PostgreSQL 15+

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- USERS & AUTHENTICATION
-- ============================================

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Default admin user (password: admin123 - change in production!)
INSERT INTO users (username, password_hash, display_name) VALUES
('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VTtYH0lHXG0Kku', 'Administrator');

-- ============================================
-- GRANULAR BOOKING DATA (from APIs)
-- ============================================

-- Room category lookup (populated from booking data)
CREATE TABLE room_categories (
    id SERIAL PRIMARY KEY,
    category_id VARCHAR(50) NOT NULL UNIQUE,   -- Newbook category_id
    category_name VARCHAR(255),                 -- Newbook category_name
    first_seen_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Room types/categories from Newbook API site_list (for selecting which to include in occupancy)
CREATE TABLE newbook_room_categories (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(50) NOT NULL UNIQUE,       -- Room type identifier from Newbook
    site_name VARCHAR(255) NOT NULL,           -- Room type name (e.g., "Standard Room")
    site_type VARCHAR(100),                    -- Type classification
    room_count INTEGER DEFAULT 0,              -- Number of rooms of this type
    is_included BOOLEAN DEFAULT TRUE,          -- Include in occupancy/guest calculations
    display_order INTEGER DEFAULT 0,
    fetched_at TIMESTAMP DEFAULT NOW()
);

-- Individual hotel bookings from Newbook
CREATE TABLE newbook_bookings (
    id SERIAL PRIMARY KEY,
    newbook_id VARCHAR(50) NOT NULL,           -- Internal Newbook booking ID
    booking_reference VARCHAR(100),             -- 3rd party/OTA reference ID
    bookings_group_id VARCHAR(50),
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
    -- Raw JSON from API (minus "guests" array to exclude PII)
    -- Future-proofs data extraction without re-syncing history
    raw_json JSONB,
    fetched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(newbook_id)
);

-- Per-night tariff/rate breakdown (including consolidated inventory items)
CREATE TABLE newbook_booking_nights (
    id SERIAL PRIMARY KEY,
    booking_id INTEGER REFERENCES newbook_bookings(id) ON DELETE CASCADE,
    stay_date DATE NOT NULL,
    -- Tariff data
    tariff_quoted_id VARCHAR(50),
    tariff_label VARCHAR(255),
    tariff_type_id VARCHAR(50),
    tariff_applied_id VARCHAR(50),
    original_amount DECIMAL(12,2),
    calculated_amount DECIMAL(12,2),
    charge_amount DECIMAL(12,2),
    taxes JSONB,
    occupant_charges JSONB,
    -- Inventory items (consolidated from API inventory_items array)
    -- Breakfast: matched by GL code against configured breakfast GL codes
    breakfast_gross DECIMAL(12,2) DEFAULT 0,  -- Gross amount (inc VAT)
    breakfast_net DECIMAL(12,2) DEFAULT 0,    -- Net amount (exc VAT)
    -- Dinner: matched by GL code against configured dinner GL codes
    dinner_gross DECIMAL(12,2) DEFAULT 0,     -- Gross amount (inc VAT)
    dinner_net DECIMAL(12,2) DEFAULT 0,       -- Net amount (exc VAT)
    -- Other inventory items (non-breakfast/dinner)
    other_items JSONB,
    fetched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(booking_id, stay_date)
);

-- Individual restaurant bookings from Resos
CREATE TABLE resos_bookings (
    id SERIAL PRIMARY KEY,
    resos_id VARCHAR(100) NOT NULL,
    booked_at TIMESTAMP,
    booking_date DATE NOT NULL,
    booking_time TIME NOT NULL,
    duration_minutes INTEGER,
    end_time TIME,
    covers INTEGER NOT NULL,
    opening_hour_id VARCHAR(100),
    status VARCHAR(50),
    table_name VARCHAR(50),
    table_area VARCHAR(100),
    source VARCHAR(100),
    referrer VARCHAR(500),
    is_hotel_guest BOOLEAN,
    is_dbb BOOLEAN,
    is_package BOOLEAN,
    hotel_booking_number VARCHAR(100),
    allergies TEXT,
    notes TEXT,
    is_flagged BOOLEAN DEFAULT FALSE,
    flag_reasons VARCHAR(255),
    fetched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(resos_id)
);

-- ============================================
-- NEWBOOK OCCUPANCY REPORT (official capacity & revenue)
-- ============================================

-- Store Newbook's reports_occupancy data which provides:
-- - Available rooms per category (accounts for maintenance/offline)
-- - Official occupied rooms per Newbook
-- - Maintenance/offline rooms
-- - Official revenue figures (gross and net)
CREATE TABLE newbook_occupancy_report (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    category_id VARCHAR(50) NOT NULL,        -- Room category ID
    category_name VARCHAR(255),              -- Room category name
    available INTEGER DEFAULT 0,             -- Rooms available (total capacity - maintenance)
    occupied INTEGER DEFAULT 0,              -- Rooms occupied per Newbook
    maintenance INTEGER DEFAULT 0,           -- Rooms offline/maintenance
    allotted INTEGER DEFAULT 0,              -- Block allocations
    revenue_gross DECIMAL(12,2) DEFAULT 0,   -- Gross revenue (inc VAT)
    revenue_net DECIMAL(12,2) DEFAULT 0,     -- Net revenue (exc VAT)
    occupancy_pct DECIMAL(5,2),              -- Calculated: occupied/available * 100
    fetched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, category_id)
);

CREATE INDEX idx_occupancy_report_date ON newbook_occupancy_report(date);

-- View to aggregate across all categories for a given date
-- Use this to get total available rooms (accounts for maintenance)
CREATE VIEW daily_occupancy_totals AS
SELECT
    date,
    SUM(available) as total_available,
    SUM(occupied) as total_occupied,
    SUM(maintenance) as total_maintenance,
    SUM(allotted) as total_allotted,
    SUM(revenue_gross) as total_revenue_gross,
    SUM(revenue_net) as total_revenue_net,
    CASE
        WHEN SUM(available) > 0 THEN ROUND((SUM(occupied)::DECIMAL / SUM(available)) * 100, 2)
        ELSE 0
    END as occupancy_pct
FROM newbook_occupancy_report
GROUP BY date;

-- ============================================
-- NEWBOOK EARNED REVENUE (official financial figures)
-- ============================================

-- Store Newbook's report_earned_revenue data which provides:
-- - Official financial figures by GL account
-- - This is the declared accounting revenue
-- Used to populate newbook_revenue_gross/net in daily_occupancy
CREATE TABLE newbook_earned_revenue (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    gl_account_id VARCHAR(50),                   -- Newbook's internal GL account ID
    gl_code VARCHAR(50),                         -- GL account code (e.g., "4100")
    gl_name VARCHAR(255),                        -- Human-readable name (e.g., "Accommodation Revenue")
    amount_gross DECIMAL(12,2) DEFAULT 0,        -- Gross amount (inc VAT)
    amount_net DECIMAL(12,2) DEFAULT 0,          -- Net amount (exc VAT)
    revenue_type VARCHAR(30),                    -- 'accommodation', 'food', 'beverage', 'other' (derived from config)
    fetched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, gl_account_id)
);

CREATE INDEX idx_earned_revenue_date ON newbook_earned_revenue(date);
CREATE INDEX idx_earned_revenue_type ON newbook_earned_revenue(date, revenue_type);

-- View to get daily accommodation revenue totals
CREATE VIEW daily_accommodation_revenue AS
SELECT
    date,
    SUM(amount_gross) as total_gross,
    SUM(amount_net) as total_net
FROM newbook_earned_revenue
WHERE revenue_type = 'accommodation'
GROUP BY date;

-- Cache GL accounts from Newbook for easier configuration in Settings
-- Populated automatically during earned revenue sync or manual fetch
CREATE TABLE newbook_gl_accounts (
    id SERIAL PRIMARY KEY,
    gl_account_id VARCHAR(50) NOT NULL UNIQUE,  -- Newbook's internal GL account ID
    gl_code VARCHAR(50),                         -- GL account code (e.g., "4100")
    gl_name VARCHAR(255),                        -- Human-readable name
    gl_group_id VARCHAR(50),                     -- Parent group ID from Newbook
    gl_group_name VARCHAR(255),                  -- Parent group name (e.g., "FNB - Food & Beverage")
    department VARCHAR(20),                      -- Revenue department: 'accommodation', 'dry', 'wet', or null
    last_seen_date DATE,                         -- Most recent date this GL appeared
    total_amount DECIMAL(14,2) DEFAULT 0,        -- Running total (for reference)
    is_active BOOLEAN DEFAULT TRUE,
    fetched_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- AGGREGATED DATA (for dashboards & forecasting)
-- ============================================

-- Aggregated daily hotel stats
CREATE TABLE daily_occupancy (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    -- Room availability (from newbook_occupancy_report - preferred source)
    total_rooms INTEGER,                       -- Total rooms available (from occupancy report or config fallback)
    available_rooms INTEGER,                   -- Rooms available after maintenance (from occupancy report)
    maintenance_rooms INTEGER,                 -- Rooms offline for maintenance
    occupied_rooms INTEGER,                    -- Rooms occupied (from booking data)
    occupancy_pct DECIMAL(5,2),               -- Calculated: occupied/available * 100
    -- Official Newbook figures (from occupancy report)
    newbook_occupied INTEGER,                  -- Official occupied per Newbook report
    newbook_occupancy_pct DECIMAL(5,2),       -- Official occupancy % from Newbook
    newbook_revenue_gross DECIMAL(12,2),      -- Official gross revenue from Newbook
    newbook_revenue_net DECIMAL(12,2),        -- Official net revenue from Newbook
    -- Guest counts (from booking data)
    total_guests INTEGER,
    total_adults INTEGER,
    total_children INTEGER,
    total_infants INTEGER,
    arrival_count INTEGER,
    -- Booking movement stats
    total_bookings INTEGER,                    -- Active bookings (confirmed, unconfirmed, arrived)
    cancelled_bookings INTEGER,                -- Cancelled bookings that would have stayed
    no_show_bookings INTEGER,                  -- No-shows for this date
    -- Revenue metrics (calculated from booking data - NET values)
    room_revenue DECIMAL(12,2),               -- NET room revenue (charge_amount / 1+VAT)
    adr DECIMAL(12,2),                        -- Average Daily Rate (NET)
    revpar DECIMAL(12,2),                     -- Revenue Per Available Room (NET)
    agr DECIMAL(12,2),                        -- Actual Guest Rate (gross, from calculated_amount)
    -- Meal allocations (from inventory items)
    breakfast_allocation_qty INTEGER,
    breakfast_allocation_value DECIMAL(12,2),
    dinner_allocation_qty INTEGER,
    dinner_allocation_value DECIMAL(12,2),
    -- Breakdown by room type: {"Double": {"rooms": 15, "guests": 28, "adults": 25, "children": 3}, ...}
    by_room_type JSONB,
    -- Revenue breakdown by room type: {"Double": {"revenue_net": 1500, "adr_net": 100, "agr_total": 1800, "agr_avg": 120}, ...}
    revenue_by_room_type JSONB,
    fetched_at TIMESTAMP DEFAULT NOW()
);

-- Aggregated daily restaurant stats
CREATE TABLE daily_covers (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    service_period VARCHAR(20) NOT NULL,
    total_bookings INTEGER,
    total_covers INTEGER,
    avg_party_size DECIMAL(4,2),
    hotel_guest_covers INTEGER,
    external_covers INTEGER,
    dbb_covers INTEGER,
    package_covers INTEGER,
    -- Hotel occupancy correlation (for forecasting)
    -- Links restaurant covers to hotel occupancy for predictive modeling
    total_hotel_residents INTEGER,             -- Hotel guests staying that night (from daily_occupancy)
    hotel_guest_dining_rate DECIMAL(5,2),      -- % of residents who dined: hotel_guest_covers / total_hotel_residents * 100
    -- Booking movement stats
    cancelled_bookings INTEGER,
    cancelled_covers INTEGER,
    no_show_bookings INTEGER,
    no_show_covers INTEGER,
    -- Source breakdown: {"website": {"bookings": 10, "covers": 25}, "phone": {...}}
    by_source JSONB,
    fetched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, service_period)
);

-- Revenue by GL account
CREATE TABLE daily_revenue (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    department VARCHAR(50) NOT NULL,
    gl_account_id VARCHAR(50),
    gl_account_name VARCHAR(255),
    amount_net DECIMAL(12,2),
    amount_gross DECIMAL(12,2),
    fetched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, department, gl_account_id)
);

-- Unified daily actuals for all forecast metrics
CREATE TABLE daily_metrics (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    metric_code VARCHAR(50) NOT NULL,
    actual_value DECIMAL(14,2),
    detail JSONB,
    source VARCHAR(30),
    calculated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, metric_code)
);

-- Historical avg spend for revenue calculations
CREATE TABLE avg_spend_rates (
    id SERIAL PRIMARY KEY,
    period_type VARCHAR(20) NOT NULL,
    period_value VARCHAR(20) NOT NULL,
    metric_code VARCHAR(50) NOT NULL,
    avg_value DECIMAL(10,2) NOT NULL,
    sample_count INTEGER,
    calculated_from DATE,
    calculated_to DATE,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(period_type, period_value, metric_code)
);

-- ============================================
-- FORECASTING TABLES
-- ============================================

-- Configuration of what we forecast
CREATE TABLE forecast_metrics (
    id SERIAL PRIMARY KEY,
    metric_code VARCHAR(50) NOT NULL UNIQUE,
    metric_name VARCHAR(100) NOT NULL,
    category VARCHAR(30) NOT NULL,
    unit VARCHAR(20) NOT NULL,
    use_prophet BOOLEAN DEFAULT TRUE,
    use_xgboost BOOLEAN DEFAULT TRUE,
    use_pickup BOOLEAN DEFAULT TRUE,
    is_derived BOOLEAN DEFAULT FALSE,
    derivation_formula TEXT,
    display_order INTEGER,
    show_in_dashboard BOOLEAN DEFAULT TRUE,
    decimal_places INTEGER DEFAULT 0,
    alert_change_threshold DECIMAL(8,2),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Seed forecast metrics
INSERT INTO forecast_metrics (metric_code, metric_name, category, unit, use_prophet, use_xgboost, use_pickup, display_order) VALUES
('hotel_room_nights', 'Room Nights', 'hotel', 'count', true, true, true, 1),
('hotel_occupancy_pct', 'Occupancy %', 'hotel', 'percent', true, true, true, 2),
('hotel_guests', 'Total Guests', 'hotel', 'count', true, true, true, 3),
('hotel_arrivals', 'Arrivals', 'hotel', 'count', true, true, true, 4),
('hotel_adr', 'Average Daily Rate', 'hotel', 'currency', true, true, false, 5),
('hotel_revpar', 'RevPAR', 'hotel', 'currency', true, true, false, 6),
('hotel_avg_los', 'Avg Length of Stay', 'hotel', 'decimal', true, true, false, 7),
('hotel_avg_lead_time', 'Avg Lead Time', 'hotel', 'days', true, true, false, 8),
('hotel_breakfast_qty', 'Breakfast Allocation', 'hotel', 'count', true, true, true, 9),
('hotel_dinner_qty', 'Dinner Allocation', 'hotel', 'count', true, true, true, 10),
('resos_lunch_bookings', 'Lunch Bookings', 'restaurant', 'count', true, true, true, 11),
('resos_lunch_covers', 'Lunch Covers', 'restaurant', 'count', true, true, true, 12),
('resos_dinner_bookings', 'Dinner Bookings', 'restaurant', 'count', true, true, true, 13),
('resos_dinner_covers', 'Dinner Covers', 'restaurant', 'count', true, true, true, 14),
('resos_lunch_party_size', 'Avg Party Size (Lunch)', 'restaurant', 'decimal', true, true, false, 15),
('resos_dinner_party_size', 'Avg Party Size (Dinner)', 'restaurant', 'decimal', true, true, false, 16),
('resos_avg_lead_time', 'Resos Avg Lead Time', 'restaurant', 'days', true, true, false, 17),
('revenue_rooms', 'Room Revenue', 'revenue', 'currency', true, true, false, 20),
('revenue_food_lunch', 'Food Revenue (Lunch)', 'revenue', 'currency', true, true, false, 21),
('revenue_food_dinner', 'Food Revenue (Dinner)', 'revenue', 'currency', true, true, false, 22),
('revenue_beverage', 'Beverage Revenue', 'revenue', 'currency', true, true, false, 23),
('revenue_fb_total', 'Total F&B Revenue', 'revenue', 'currency', true, true, false, 24);

-- Generated predictions (multi-model)
CREATE TABLE forecasts (
    id SERIAL PRIMARY KEY,
    forecast_date DATE NOT NULL,
    forecast_type VARCHAR(30) NOT NULL,
    model_type VARCHAR(20) NOT NULL,
    predicted_value DECIMAL(12,2) NOT NULL,
    lower_bound DECIMAL(12,2),
    upper_bound DECIMAL(12,2),
    confidence_pct INTEGER DEFAULT 80,
    model_version VARCHAR(50),
    generated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(forecast_date, forecast_type, model_type, generated_at)
);

-- Metadata for each forecast generation
CREATE TABLE forecast_runs (
    id SERIAL PRIMARY KEY,
    run_id UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    run_type VARCHAR(20) NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status VARCHAR(20) NOT NULL,
    forecast_from DATE NOT NULL,
    forecast_to DATE NOT NULL,
    training_from DATE,
    training_to DATE,
    training_rows INTEGER,
    models_run JSONB,
    error_message TEXT,
    triggered_by VARCHAR(100),
    notes TEXT
);

-- Full audit trail (keeps ALL forecasts ever made)
CREATE TABLE forecast_history (
    id SERIAL PRIMARY KEY,
    run_id UUID REFERENCES forecast_runs(run_id),
    forecast_date DATE NOT NULL,
    forecast_type VARCHAR(30) NOT NULL,
    model_type VARCHAR(20) NOT NULL,
    predicted_value DECIMAL(12,2) NOT NULL,
    lower_bound DECIMAL(12,2),
    upper_bound DECIMAL(12,2),
    confidence_pct INTEGER,
    horizon_days INTEGER,
    horizon_bucket VARCHAR(20),
    previous_value DECIMAL(12,2),
    change_amount DECIMAL(12,2),
    change_pct DECIMAL(8,4),
    change_reason VARCHAR(100),
    is_latest BOOLEAN DEFAULT TRUE,
    generated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_forecast_latest ON forecast_history (forecast_date, forecast_type, model_type, is_latest);
CREATE INDEX idx_forecast_evolution ON forecast_history (forecast_date, forecast_type, model_type, generated_at);

-- Detailed change tracking with reasons
CREATE TABLE forecast_change_log (
    id SERIAL PRIMARY KEY,
    forecast_date DATE NOT NULL,
    forecast_type VARCHAR(30) NOT NULL,
    model_type VARCHAR(20) NOT NULL,
    changed_at TIMESTAMP NOT NULL,
    run_id UUID REFERENCES forecast_runs(run_id),
    old_value DECIMAL(12,2),
    new_value DECIMAL(12,2),
    change_amount DECIMAL(12,2),
    change_pct DECIMAL(8,4),
    change_category VARCHAR(30) NOT NULL,
    change_reason TEXT,
    bookings_added INTEGER,
    bookings_cancelled INTEGER,
    covers_change INTEGER,
    days_out INTEGER,
    otb_at_change DECIMAL(12,2)
);

CREATE INDEX idx_change_date ON forecast_change_log (forecast_date, forecast_type);
CREATE INDEX idx_change_time ON forecast_change_log (changed_at);

-- Configuration for update frequency
CREATE TABLE forecast_schedule (
    id SERIAL PRIMARY KEY,
    schedule_name VARCHAR(50) NOT NULL UNIQUE,
    is_active BOOLEAN DEFAULT TRUE,
    horizon_min_days INTEGER NOT NULL,
    horizon_max_days INTEGER NOT NULL,
    frequency VARCHAR(20) NOT NULL,
    run_time TIME,
    run_day_of_week INTEGER,
    models JSONB NOT NULL,
    forecast_types JSONB NOT NULL,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Default schedules
INSERT INTO forecast_schedule (schedule_name, horizon_min_days, horizon_max_days, frequency, run_time, models, forecast_types) VALUES
('daily_forecast', 0, 28, 'daily', '06:00', '["prophet", "xgboost", "pickup"]', '["hotel_occupancy_pct", "hotel_guests", "resos_lunch_covers", "resos_dinner_covers"]'),
('weekly_forecast', 29, 365, 'weekly', '06:30', '["prophet", "xgboost"]', '["hotel_occupancy_pct", "hotel_guests", "resos_lunch_covers", "resos_dinner_covers"]');

-- ============================================
-- MODEL EXPLAINABILITY
-- ============================================

-- Prophet model component breakdown
CREATE TABLE prophet_decomposition (
    id SERIAL PRIMARY KEY,
    run_id UUID REFERENCES forecast_runs(run_id),
    forecast_date DATE NOT NULL,
    forecast_type VARCHAR(30) NOT NULL,
    trend DECIMAL(12,4),
    yearly_seasonality DECIMAL(12,4),
    weekly_seasonality DECIMAL(12,4),
    daily_seasonality DECIMAL(12,4),
    holiday_effects JSONB,
    regressor_effects JSONB,
    generated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(run_id, forecast_date, forecast_type)
);

-- XGBoost feature contributions (SHAP values)
CREATE TABLE xgboost_explanations (
    id SERIAL PRIMARY KEY,
    run_id UUID REFERENCES forecast_runs(run_id),
    forecast_date DATE NOT NULL,
    forecast_type VARCHAR(30) NOT NULL,
    base_value DECIMAL(12,4),
    feature_values JSONB,
    shap_values JSONB,
    top_positive JSONB,
    top_negative JSONB,
    generated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(run_id, forecast_date, forecast_type)
);

-- Pickup model calculation breakdown
CREATE TABLE pickup_explanations (
    id SERIAL PRIMARY KEY,
    run_id UUID REFERENCES forecast_runs(run_id),
    forecast_date DATE NOT NULL,
    forecast_type VARCHAR(30) NOT NULL,
    current_otb DECIMAL(12,2),
    days_out INTEGER,
    comparison_date DATE,
    comparison_otb DECIMAL(12,2),
    comparison_final DECIMAL(12,2),
    pickup_curve_pct DECIMAL(8,4),
    pickup_curve_stddev DECIMAL(8,4),
    pace_vs_prior_pct DECIMAL(8,2),
    projection_method VARCHAR(20),
    projected_value DECIMAL(12,2),
    confidence_note TEXT,
    generated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(run_id, forecast_date, forecast_type)
);

-- When models were retrained
CREATE TABLE model_training_log (
    id SERIAL PRIMARY KEY,
    model_type VARCHAR(20) NOT NULL,
    forecast_type VARCHAR(30) NOT NULL,
    training_from DATE NOT NULL,
    training_to DATE NOT NULL,
    training_rows INTEGER,
    hyperparameters JSONB,
    feature_list JSONB,
    validation_from DATE,
    validation_to DATE,
    mae DECIMAL(12,4),
    rmse DECIMAL(12,4),
    mape DECIMAL(8,4),
    model_version VARCHAR(50),
    model_path VARCHAR(500),
    trained_at TIMESTAMP DEFAULT NOW(),
    trained_by VARCHAR(100)
);

-- ============================================
-- PICKUP MODEL TABLES
-- ============================================

-- On-the-books snapshots for pickup model
CREATE TABLE pickup_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    stay_date DATE NOT NULL,
    days_out INTEGER NOT NULL,
    metric_type VARCHAR(30) NOT NULL,
    otb_value DECIMAL(12,2) NOT NULL,
    otb_bookings INTEGER,
    prior_year_otb DECIMAL(12,2),
    prior_year_final DECIMAL(12,2),
    pace_vs_prior_pct DECIMAL(8,2),
    projected_final DECIMAL(12,2),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(snapshot_date, stay_date, metric_type)
);

-- Historical pickup patterns (aggregated)
CREATE TABLE pickup_curves (
    id SERIAL PRIMARY KEY,
    day_of_week INTEGER NOT NULL,
    season VARCHAR(20) NOT NULL,
    metric_type VARCHAR(30) NOT NULL,
    days_out INTEGER NOT NULL,
    avg_pct_of_final DECIMAL(8,4) NOT NULL,
    std_dev DECIMAL(8,4),
    sample_count INTEGER,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(day_of_week, season, metric_type, days_out)
);

-- ============================================
-- BUDGET TABLES
-- ============================================

-- FD budget targets
CREATE TABLE monthly_budgets (
    id SERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    budget_type VARCHAR(30) NOT NULL,
    budget_value DECIMAL(14,2) NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(year, month, budget_type)
);

-- Distributed budget (calculated)
CREATE TABLE daily_budgets (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    budget_type VARCHAR(30) NOT NULL,
    budget_value DECIMAL(12,2) NOT NULL,
    distribution_method VARCHAR(20) NOT NULL,
    prior_year_pct DECIMAL(8,4),
    monthly_budget_id INTEGER REFERENCES monthly_budgets(id),
    calculated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, budget_type)
);

-- Prior year actuals for budget distribution
CREATE TABLE prior_year_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    metric_type VARCHAR(30) NOT NULL,
    actual_value DECIMAL(12,2) NOT NULL,
    month_total DECIMAL(14,2),
    pct_of_month DECIMAL(8,4),
    fetched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, metric_type)
);

-- ============================================
-- CROSS-REFERENCE VALIDATION
-- ============================================

-- Configuration for cross-reference checks
CREATE TABLE cross_reference_config (
    id SERIAL PRIMARY KEY,
    check_name VARCHAR(50) NOT NULL UNIQUE,
    check_category VARCHAR(30) NOT NULL,
    description TEXT,
    formula TEXT NOT NULL,
    compares_to VARCHAR(50) NOT NULL,
    tolerance_pct DECIMAL(8,4) NOT NULL,
    input_metrics JSONB NOT NULL,
    is_correlation_check BOOLEAN DEFAULT FALSE,
    expected_correlation DECIMAL(4,2),
    is_active BOOLEAN DEFAULT TRUE,
    display_order INTEGER
);

-- Seed cross-reference checks
INSERT INTO cross_reference_config (check_name, check_category, formula, compares_to, tolerance_pct, input_metrics, display_order) VALUES
('revenue_check', 'hotel', 'hotel_room_nights * hotel_adr', 'revenue_rooms', 5.0, '["hotel_room_nights", "hotel_adr"]', 1),
('guest_check', 'hotel', 'hotel_room_nights * avg_guests_per_room', 'hotel_guests', 10.0, '["hotel_room_nights"]', 2),
('occupancy_check', 'hotel', 'hotel_room_nights / total_rooms * 100', 'hotel_occupancy_pct', 2.0, '["hotel_room_nights"]', 3),
('revpar_check', 'hotel', 'hotel_adr * hotel_occupancy_pct / 100', 'hotel_revpar', 0.1, '["hotel_adr", "hotel_occupancy_pct"]', 4),
('covers_lunch_check', 'restaurant', 'resos_lunch_bookings * resos_lunch_party_size', 'resos_lunch_covers', 10.0, '["resos_lunch_bookings", "resos_lunch_party_size"]', 10),
('covers_dinner_check', 'restaurant', 'resos_dinner_bookings * resos_dinner_party_size', 'resos_dinner_covers', 10.0, '["resos_dinner_bookings", "resos_dinner_party_size"]', 11),
('food_revenue_lunch', 'restaurant', 'resos_lunch_covers * avg_spend_lunch', 'revenue_food_lunch', 10.0, '["resos_lunch_covers"]', 12),
('food_revenue_dinner', 'restaurant', 'resos_dinner_covers * avg_spend_dinner', 'revenue_food_dinner', 10.0, '["resos_dinner_covers"]', 13),
('total_fb_check', 'restaurant', 'revenue_food_lunch + revenue_food_dinner + revenue_beverage', 'revenue_fb_total', 5.0, '["revenue_food_lunch", "revenue_food_dinner", "revenue_beverage"]', 14);

-- Cross-reference validation results
CREATE TABLE forecast_cross_reference (
    id SERIAL PRIMARY KEY,
    run_id UUID REFERENCES forecast_runs(run_id),
    forecast_date DATE NOT NULL,
    check_name VARCHAR(50) NOT NULL,
    check_category VARCHAR(30) NOT NULL,
    calculated_value DECIMAL(14,2),
    forecasted_value DECIMAL(14,2),
    formula_used TEXT,
    input_values JSONB,
    difference DECIMAL(14,2),
    difference_pct DECIMAL(8,4),
    tolerance_pct DECIMAL(8,4),
    status VARCHAR(20) NOT NULL,
    possible_causes JSONB,
    recommendation TEXT,
    calculated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(run_id, forecast_date, check_name)
);

-- ============================================
-- BACKTESTING
-- ============================================

-- Store backtest results for model accuracy evaluation
-- Backtesting simulates historical forecasts using only data available at the time
CREATE TABLE backtest_results (
    id SERIAL PRIMARY KEY,
    target_date DATE NOT NULL,
    metric_code VARCHAR(50) NOT NULL,
    lead_time INTEGER NOT NULL,              -- Days out from simulated today
    simulated_today DATE,                    -- The date we pretended "today" was
    current_otb DECIMAL(12,2),               -- OTB value at simulated_today
    prior_otb DECIMAL(12,2),                 -- Prior year OTB at same lead time
    prior_final DECIMAL(12,2),               -- Prior year actual final value
    projected_value DECIMAL(12,2),           -- What the model would have predicted
    actual_value DECIMAL(12,2),              -- What actually happened
    error DECIMAL(12,2),                     -- projected - actual
    abs_error DECIMAL(12,2),                 -- |error|
    pct_error DECIMAL(8,2),                  -- (error / actual) * 100
    abs_pct_error DECIMAL(8,2),              -- |pct_error|
    projection_method VARCHAR(30),           -- additive, additive_floor, implied_additive, etc.
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(target_date, metric_code, lead_time)
);

CREATE INDEX idx_backtest_metric ON backtest_results(metric_code);
CREATE INDEX idx_backtest_date ON backtest_results(target_date);
CREATE INDEX idx_backtest_lead ON backtest_results(lead_time);

-- ============================================
-- ACCURACY TRACKING
-- ============================================

-- Track accuracy over time
CREATE TABLE actual_vs_forecast (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    metric_type VARCHAR(30) NOT NULL,
    actual_value DECIMAL(12,2),
    prophet_forecast DECIMAL(12,2),
    prophet_lower DECIMAL(12,2),
    prophet_upper DECIMAL(12,2),
    xgboost_forecast DECIMAL(12,2),
    pickup_forecast DECIMAL(12,2),
    budget_value DECIMAL(12,2),
    prophet_error DECIMAL(12,4),
    prophet_pct_error DECIMAL(8,4),
    xgboost_error DECIMAL(12,4),
    xgboost_pct_error DECIMAL(8,4),
    pickup_error DECIMAL(12,4),
    pickup_pct_error DECIMAL(8,4),
    best_model VARCHAR(20),
    calculated_at TIMESTAMP,
    UNIQUE(date, metric_type)
);

-- ============================================
-- SYNC LOGGING
-- ============================================

CREATE TABLE sync_log (
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
-- SYSTEM CONFIGURATION
-- ============================================

-- Store API credentials and system settings
CREATE TABLE system_config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT,
    is_encrypted BOOLEAN DEFAULT FALSE,
    description TEXT,
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by VARCHAR(100)
);

-- Default config entries (values to be set via GUI)
INSERT INTO system_config (config_key, description) VALUES
('newbook_api_key', 'Newbook API Key'),
('newbook_username', 'Newbook Username'),
('newbook_password', 'Newbook Password'),
('newbook_region', 'Newbook Region Code'),
('resos_api_key', 'Resos API Key'),
('total_rooms', 'Total number of hotel rooms (for occupancy calculation)'),
('hotel_name', 'Hotel/Property Name'),
('timezone', 'Local timezone (e.g., Europe/London)'),
-- GL account mapping for inventory items (breakfast/dinner identification)
('newbook_breakfast_gl_codes', 'Comma-separated list of GL codes for breakfast items'),
('newbook_dinner_gl_codes', 'Comma-separated list of GL codes for dinner items'),
('newbook_breakfast_vat_rate', 'VAT rate for breakfast items (e.g., 0.20 for 20%)'),
('newbook_dinner_vat_rate', 'VAT rate for dinner items (e.g., 0.20 for 20%)'),
-- Accommodation VAT rate for room revenue calculations
('accommodation_vat_rate', 'VAT rate for accommodation/room revenue (e.g., 0.20 for 20%)'),
-- Accommodation GL codes for earned revenue sync (identifies which GL accounts are room revenue)
('accommodation_gl_codes', 'Comma-separated list of GL codes for accommodation/room revenue'),
-- Sync schedule enable/disable
('sync_newbook_enabled', 'Enable automatic Newbook sync (true/false)'),
('sync_resos_enabled', 'Enable automatic Resos sync (true/false)'),
('sync_schedule_time', 'Time for daily sync (HH:MM format, e.g., 05:00)');

-- Set default values
UPDATE system_config SET config_value = '80' WHERE config_key = 'total_rooms';
UPDATE system_config SET config_value = 'Europe/London' WHERE config_key = 'timezone';
UPDATE system_config SET config_value = '0.20' WHERE config_key = 'newbook_breakfast_vat_rate';
UPDATE system_config SET config_value = '0.20' WHERE config_key = 'newbook_dinner_vat_rate';
UPDATE system_config SET config_value = '0.20' WHERE config_key = 'accommodation_vat_rate';
-- Sync schedules disabled by default for initial testing
UPDATE system_config SET config_value = 'false' WHERE config_key = 'sync_newbook_enabled';
UPDATE system_config SET config_value = 'false' WHERE config_key = 'sync_resos_enabled';
UPDATE system_config SET config_value = '05:00' WHERE config_key = 'sync_schedule_time';

-- ============================================
-- AGGREGATION QUEUE
-- ============================================

-- Track dates that need re-aggregation after booking changes
-- Sync jobs populate this; aggregation job processes and clears it
CREATE TABLE aggregation_queue (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    source VARCHAR(20) NOT NULL,               -- 'newbook' or 'resos'
    reason VARCHAR(50),                        -- 'booking_created', 'booking_modified', 'booking_cancelled'
    booking_id VARCHAR(100),                   -- Reference to the booking that triggered this
    queued_at TIMESTAMP DEFAULT NOW(),
    aggregated_at TIMESTAMP,                   -- NULL = pending, set when processed
    UNIQUE(date, source, booking_id)           -- Prevent duplicate entries for same booking/date
);

CREATE INDEX idx_aggregation_pending ON aggregation_queue (source, aggregated_at) WHERE aggregated_at IS NULL;
CREATE INDEX idx_aggregation_date ON aggregation_queue (date);

-- ============================================
-- BACKFILL TRACKING
-- ============================================

-- Track historical data backfill progress
CREATE TABLE backfill_jobs (
    id SERIAL PRIMARY KEY,
    job_id UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    source VARCHAR(20) NOT NULL,
    from_date DATE NOT NULL,
    to_date DATE NOT NULL,
    chunk_months INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    current_chunk_start DATE,
    current_chunk_end DATE,
    chunks_total INTEGER,
    chunks_completed INTEGER DEFAULT 0,
    records_total INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    triggered_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_backfill_status ON backfill_jobs (status);
CREATE INDEX idx_backfill_source ON backfill_jobs (source);
