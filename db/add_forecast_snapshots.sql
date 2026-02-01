-- Forecast Snapshots Table
-- Stores forecasts from multiple perception dates for accuracy analysis and model weighting

CREATE TABLE IF NOT EXISTS forecast_snapshots (
    id SERIAL PRIMARY KEY,
    perception_date DATE NOT NULL,      -- Date forecast was run "as of"
    target_date DATE NOT NULL,          -- Date being forecasted
    model VARCHAR(20) NOT NULL,         -- 'prophet', 'xgboost', 'pickup'
    metric_code VARCHAR(50) NOT NULL,   -- 'occupancy', 'rooms', etc.
    days_out INTEGER NOT NULL,          -- target_date - perception_date
    forecast_value DECIMAL(12,2),
    actual_value DECIMAL(12,2),         -- Filled in once target_date passes
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(perception_date, target_date, model, metric_code)
);

-- Index for accuracy queries by lead time bracket
CREATE INDEX IF NOT EXISTS idx_snapshots_accuracy
    ON forecast_snapshots(metric_code, days_out, model);

-- Index for querying by perception date
CREATE INDEX IF NOT EXISTS idx_snapshots_perception
    ON forecast_snapshots(perception_date);

-- Index for backfilling actuals
CREATE INDEX IF NOT EXISTS idx_snapshots_target_date
    ON forecast_snapshots(target_date)
    WHERE actual_value IS NULL;

COMMENT ON TABLE forecast_snapshots IS 'Stores forecasts from multiple perception dates for accuracy analysis by lead time';
COMMENT ON COLUMN forecast_snapshots.perception_date IS 'The date the forecast was run from (simulated "today")';
COMMENT ON COLUMN forecast_snapshots.days_out IS 'Lead time: target_date - perception_date';
COMMENT ON COLUMN forecast_snapshots.actual_value IS 'Filled in after target_date passes, from newbook_bookings_stats';
