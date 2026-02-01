-- Add TFT model storage and configurable settings
-- Run this migration to enable model persistence and export/import

-- TFT trained models storage
CREATE TABLE IF NOT EXISTS tft_models (
    id SERIAL PRIMARY KEY,
    metric_code VARCHAR(50) NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    file_path VARCHAR(500),
    file_size_bytes BIGINT,
    trained_at TIMESTAMP DEFAULT NOW(),
    training_config JSONB,
    training_time_seconds INTEGER,
    validation_loss DECIMAL(12,6),
    epochs_completed INTEGER,
    is_active BOOLEAN DEFAULT FALSE,
    created_by VARCHAR(100),
    notes TEXT,
    UNIQUE(metric_code, model_name)
);

CREATE INDEX IF NOT EXISTS idx_tft_models_metric
ON tft_models(metric_code, is_active);

CREATE INDEX IF NOT EXISTS idx_tft_models_active
ON tft_models(is_active) WHERE is_active = TRUE;

-- TFT training settings in system_config
INSERT INTO system_config (config_key, config_value, description) VALUES
-- Model Architecture
('tft_encoder_length', '90', 'Historical context window (days)'),
('tft_prediction_length', '28', 'Forecast horizon (days)'),
('tft_hidden_size', '64', 'Model hidden layer size'),
('tft_attention_heads', '4', 'Number of attention heads'),
('tft_dropout', '0.1', 'Dropout rate'),
-- Training Parameters
('tft_learning_rate', '0.001', 'Training learning rate'),
('tft_batch_size', '128', 'Training batch size'),
('tft_max_epochs', '100', 'Maximum training epochs'),
('tft_training_days', '2555', 'Days of historical data to use'),
-- Early Stopping
('tft_early_stop_patience', '10', 'Epochs without improvement before stopping'),
('tft_early_stop_min_delta', '0.0001', 'Minimum loss improvement to count as progress'),
-- Feature Options
('tft_use_special_dates', 'true', 'Include special dates/holidays as features'),
('tft_use_otb_data', 'true', 'Include OTB (On-The-Books) pickup data as features'),
-- Runtime Options
('tft_use_gpu', 'false', 'Use GPU for training'),
('tft_cpu_threads', '2', 'Max CPU threads for training (prevents container lockup)'),
('tft_use_cached_model', 'true', 'Use cached model for live preview'),
('tft_auto_retrain', 'true', 'Enable weekly auto-retrain')
ON CONFLICT (config_key) DO NOTHING;

-- Training job status table
CREATE TABLE IF NOT EXISTS tft_training_jobs (
    id SERIAL PRIMARY KEY,
    job_id UUID UNIQUE NOT NULL,
    metric_code VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, running, completed, failed
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    progress_pct INTEGER DEFAULT 0,
    current_epoch INTEGER DEFAULT 0,
    total_epochs INTEGER,
    error_message TEXT,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tft_training_jobs_status
ON tft_training_jobs(status, created_at DESC);
