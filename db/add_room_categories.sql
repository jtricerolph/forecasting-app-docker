-- Add newbook_room_categories table for room type selection
-- Run this manually if the table doesn't exist

CREATE TABLE IF NOT EXISTS newbook_room_categories (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(50) NOT NULL UNIQUE,       -- Room type identifier from Newbook
    site_name VARCHAR(255) NOT NULL,           -- Room type name (e.g., "Standard Room")
    site_type VARCHAR(100),                    -- Type classification
    room_count INTEGER DEFAULT 0,              -- Number of rooms of this type
    is_included BOOLEAN DEFAULT TRUE,          -- Include in occupancy/guest calculations
    display_order INTEGER DEFAULT 0,
    fetched_at TIMESTAMP DEFAULT NOW()
);
