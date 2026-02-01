-- Add new fields to newbook_gl_accounts for grouping and department mapping
-- Run this manually if the columns don't exist

-- Add group fields for modal grouping
ALTER TABLE newbook_gl_accounts ADD COLUMN IF NOT EXISTS gl_group_id VARCHAR(50);
ALTER TABLE newbook_gl_accounts ADD COLUMN IF NOT EXISTS gl_group_name VARCHAR(255);

-- Add department field for revenue categorization
-- Values: 'accommodation', 'dry', 'wet', or NULL (not mapped)
ALTER TABLE newbook_gl_accounts ADD COLUMN IF NOT EXISTS department VARCHAR(20);

