-- Add CatBoost columns to actual_vs_forecast table
-- Run this migration to enable CatBoost accuracy tracking

-- Add CatBoost forecast and error columns
ALTER TABLE actual_vs_forecast
ADD COLUMN IF NOT EXISTS catboost_forecast DECIMAL(12,2),
ADD COLUMN IF NOT EXISTS catboost_error DECIMAL(12,4),
ADD COLUMN IF NOT EXISTS catboost_pct_error DECIMAL(8,4);

-- Create index for catboost queries
CREATE INDEX IF NOT EXISTS idx_actual_vs_forecast_catboost
ON actual_vs_forecast(date, catboost_error) WHERE catboost_error IS NOT NULL;
