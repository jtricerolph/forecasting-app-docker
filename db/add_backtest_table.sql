-- Add backtest_results table to existing database
-- Run this if the database was created before the backtest feature was added

CREATE TABLE IF NOT EXISTS backtest_results (
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

CREATE INDEX IF NOT EXISTS idx_backtest_metric ON backtest_results(metric_code);
CREATE INDEX IF NOT EXISTS idx_backtest_date ON backtest_results(target_date);
CREATE INDEX IF NOT EXISTS idx_backtest_lead ON backtest_results(lead_time);
