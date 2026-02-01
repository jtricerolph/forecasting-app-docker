-- Add TFT (Temporal Fusion Transformer) model support
-- Run this migration to enable TFT forecasting

-- Add use_tft column to forecast_metrics table
ALTER TABLE forecast_metrics ADD COLUMN IF NOT EXISTS use_tft BOOLEAN DEFAULT FALSE;

-- Enable TFT for key hotel metrics where it adds value
UPDATE forecast_metrics SET use_tft = TRUE
WHERE metric_code IN (
    'hotel_occupancy_pct',
    'hotel_room_nights',
    'hotel_guests',
    'hotel_arrivals',
    'resos_dinner_covers',
    'resos_lunch_covers'
);

-- TFT attention-based explanations table
CREATE TABLE IF NOT EXISTS tft_explanations (
    id SERIAL PRIMARY KEY,
    run_id UUID,
    forecast_date DATE NOT NULL,
    forecast_type VARCHAR(50) NOT NULL,
    -- Attention-based feature importance
    encoder_attention JSONB,             -- Historical feature importance
    decoder_attention JSONB,             -- Future feature importance
    variable_importance JSONB,           -- Static/time-varying importance
    -- Quantile predictions
    quantile_10 DECIMAL(12,2),
    quantile_50 DECIMAL(12,2),           -- Median prediction
    quantile_90 DECIMAL(12,2),
    -- Interpretation
    top_historical_drivers JSONB,        -- Most influential past features
    top_future_drivers JSONB,            -- Most influential known future inputs
    generated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tft_explanations_date
ON tft_explanations(forecast_date, forecast_type);

CREATE INDEX IF NOT EXISTS idx_tft_explanations_generated
ON tft_explanations(generated_at DESC);

-- TFT model training log (track training runs and model persistence)
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
    encoder_length INTEGER,              -- Historical lookback
    prediction_length INTEGER,           -- Forecast horizon
    model_path VARCHAR(500),
    training_time_seconds INTEGER,
    gpu_used BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_tft_training_log_type
ON tft_training_log(forecast_type, trained_at DESC);

-- Add TFT columns to actual_vs_forecast table
ALTER TABLE actual_vs_forecast
ADD COLUMN IF NOT EXISTS tft_forecast DECIMAL(12,2),
ADD COLUMN IF NOT EXISTS tft_lower DECIMAL(12,2),
ADD COLUMN IF NOT EXISTS tft_upper DECIMAL(12,2),
ADD COLUMN IF NOT EXISTS tft_error DECIMAL(12,4),
ADD COLUMN IF NOT EXISTS tft_pct_error DECIMAL(8,4);
