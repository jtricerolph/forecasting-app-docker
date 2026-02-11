-- Budget tables migration

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

-- Add missing columns to daily_budgets if they don't exist
DO $$
BEGIN
    -- Add distribution_method column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'daily_budgets' AND column_name = 'distribution_method') THEN
        ALTER TABLE daily_budgets ADD COLUMN distribution_method VARCHAR(50);
    END IF;

    -- Add prior_year_pct column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'daily_budgets' AND column_name = 'prior_year_pct') THEN
        ALTER TABLE daily_budgets ADD COLUMN prior_year_pct DECIMAL(10,6);
    END IF;

    -- Add monthly_budget_id column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'daily_budgets' AND column_name = 'monthly_budget_id') THEN
        ALTER TABLE daily_budgets ADD COLUMN monthly_budget_id INTEGER REFERENCES monthly_budgets(id);
    END IF;

    -- Add calculated_at column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'daily_budgets' AND column_name = 'calculated_at') THEN
        ALTER TABLE daily_budgets ADD COLUMN calculated_at TIMESTAMP;
    END IF;

    -- Add updated_at column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'daily_budgets' AND column_name = 'updated_at') THEN
        ALTER TABLE daily_budgets ADD COLUMN updated_at TIMESTAMP;
    END IF;
END $$;
