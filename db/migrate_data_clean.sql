-- Migration script: Import data from old database to new forecast_data database
-- Run this AFTER the init_clean.sql has created the schema

-- ============================================
-- SYSTEM CONFIG
-- ============================================

-- Clear default values first
DELETE FROM system_config;

INSERT INTO system_config (id, config_key, config_value, is_encrypted, description, updated_at, updated_by) VALUES
(1, 'newbook_api_key', 'aW5zdGFuY2VzXzI3NGE3NWU3ZTlhYjZiMjAzZWVhODFmYmI2NmJlNzVh', true, 'Newbook API Key', '2026-01-29 18:55:23.474785', 'admin'),
(2, 'newbook_username', 'sambapos_nf', false, 'Newbook Username', '2026-01-29 18:55:23.488724', 'admin'),
(3, 'newbook_password', 'cDU4d2k3bFh0YTI1Z0cxdg==', true, 'Newbook Password', '2026-01-29 18:55:23.503589', 'admin'),
(4, 'newbook_region', 'eu', false, 'Newbook Region Code', '2026-01-29 18:55:23.517114', 'admin'),
(5, 'resos_api_key', 'Ry1qV1dGVUV1a0s5akRJR0hXR2dMTl9nZlR5WlpTYkRLcTUzQ3ZlUmI0bA==', true, 'Resos API Key', '2026-01-30 00:21:26.623234', 'admin'),
(6, 'total_rooms', '25', false, 'Total number of hotel rooms', '2026-01-29 20:27:23.902765', 'admin'),
(7, 'hotel_name', 'Number Four at Stow', false, 'Hotel/Property Name', '2026-01-29 20:27:23.888995', 'admin'),
(8, 'timezone', 'Europe/London', false, 'Local timezone (e.g., Europe/London)', '2026-01-29 20:27:23.916884', 'admin'),
(9, 'accommodation_vat_rate', '0.2', false, 'VAT rate for accommodation (0.20 = 20%)', '2026-01-29 22:10:31.616104', 'admin'),
(10, 'sync_newbook_enabled', 'true', false, 'Enable automatic Newbook sync (true/false)', '2026-01-30 01:42:13.640274', 'admin'),
(11, 'sync_resos_enabled', 'true', false, 'Enable automatic Resos sync (true/false)', '2026-01-30 01:42:13.654357', 'admin'),
(12, 'sync_schedule_time', '05:00', false, 'Time for daily sync (HH:MM format)', '2026-01-30 01:42:13.667395', 'admin');

SELECT setval('system_config_id_seq', 12, true);

-- ============================================
-- ROOM CATEGORIES
-- ============================================

INSERT INTO newbook_room_categories (id, site_id, site_name, site_type, room_count, is_included, display_order, fetched_at) VALUES
(2, 'Standard', 'Standard', 'Standard', 16, true, 0, '2026-01-31 10:40:40.357966'),
(3, 'Executive Double', 'Executive Double', 'Executive Double', 3, true, 0, '2026-01-31 10:40:40.357966'),
(4, 'Suite', 'Suite', 'Suite', 4, true, 0, '2026-01-31 10:40:40.357966'),
(5, 'Suite - Family Room', 'Suite - Family Room', 'Suite - Family Room', 1, true, 0, '2026-01-31 10:40:40.357966'),
(6, 'Accessible Room', 'Accessible Room', 'Accessible Room', 1, true, 0, '2026-01-31 10:40:40.357966'),
(7, 'Overflow', 'Overflow', 'Overflow', 1, false, 0, '2026-01-31 10:40:40.357966');

SELECT setval('newbook_room_categories_id_seq', 7, true);

-- ============================================
-- GL ACCOUNTS (with department mappings)
-- ============================================

-- Accommodation GL accounts
INSERT INTO newbook_gl_accounts (gl_account_id, gl_code, gl_name, gl_group_id, gl_group_name, department, is_active) VALUES
('1', '1001', 'Standard', '1', '1000 - Accommodation', 'accommodation', true),
('2', '1002', 'Executive', '1', '1000 - Accommodation', 'accommodation', true),
('55', '1003', 'Exec Double', '1', '1000 - Accommodation', 'accommodation', true),
('3', '1004', 'Suite', '1', '1000 - Accommodation', 'accommodation', true),
('27', '1005', 'Cottage', '1', '1000 - Accommodation', NULL, true),
('42', '1009', 'Overflow', '1', '1000 - Accommodation', NULL, true),
('56', '1101', 'Cancellation Charge', '1', '1000 - Accommodation', NULL, true),
('25', '1301', 'Promotional Discount Code', '1', '1000 - Accommodation', NULL, true),
('26', '1302', 'Best Loved Discount Code', '1', '1000 - Accommodation', NULL, true);

-- Dry (Food) GL accounts
INSERT INTO newbook_gl_accounts (gl_account_id, gl_code, gl_name, gl_group_id, gl_group_name, department, is_active) VALUES
('8', '3001', 'Meal Plan Breakfast', '3', '3000 - Dry', 'dry', true),
('9', '3002', 'Meal Plan Dinner', '3', '3000 - Dry', 'dry', true),
('10', '3003', 'Meal Plan Lunch', '3', '3000 - Dry', 'dry', true),
('28', '3102', 'Function Food', '3', '3000 - Dry', 'dry', true),
('11', '3101EPOS', 'EPOS Sales Dry', '3', '3000 - Dry', 'dry', true),
('12', '3101POST', 'EPOS Room Post Dry', '3', '3000 - Dry', 'dry', true),
('36', '3301', 'EPOS General Discount Dry', '3', '3000 - Dry', 'dry', true),
('37', '3302', 'EPOS Loyalty Discount Dry', '3', '3000 - Dry', 'dry', true),
('38', '3303', 'EPOS Regular Discount Dry', '3', '3000 - Dry', 'dry', true),
('39', '3304', 'EPOS Staff Discount Dry', '3', '3000 - Dry', 'dry', true),
('41', '3305', 'EPOS Offer Discount Dry', '3', '3000 - Dry', 'dry', true),
('52', '3306', 'EPOS 30% Off Lunch Discount Dry', '6', '5000 - Discounts', NULL, true);

-- Wet (Beverage) GL accounts
INSERT INTO newbook_gl_accounts (gl_account_id, gl_code, gl_name, gl_group_id, gl_group_name, department, is_active) VALUES
('4', '2001', 'Meal Plan Wet', '2', '2000 - Wet 20%', 'wet', true),
('5', '2101EPOS', 'EPOS Sales Wet', '2', '2000 - Wet 20%', 'wet', true),
('6', '2101POST', 'EPOS Room Post Wet', '2', '2000 - Wet 20%', 'wet', true),
('49', '2102EPOS', 'EPOS Sales Wet Alcohol', '2', '2000 - Wet 20%', 'wet', true),
('50', '2102POST', 'EPOS Room Post Wet Alcohol', '2', '2000 - Wet 20%', 'wet', true),
('32', '2301', 'EPOS General Discount Wet', '2', '2000 - Wet 20%', 'wet', true),
('33', '2302', 'EPOS Loyalty Discount Wet', '2', '2000 - Wet 20%', 'wet', true),
('34', '2303', 'EPOS Regular Discount Wet', '2', '2000 - Wet 20%', 'wet', true),
('35', '2304', 'EPOS Staff Discount Wet', '2', '2000 - Wet 20%', 'wet', true);

-- Sundries & Other GL accounts
INSERT INTO newbook_gl_accounts (gl_account_id, gl_code, gl_name, gl_group_id, gl_group_name, department, is_active) VALUES
('14', '4001', 'General Sundries (NO VAT)', '4', '4000 - Sundries NO VAT', NULL, true),
('15', '4501', 'General Sundries (VAT)', '5', '4500 - Sundries VAT', NULL, true),
('57', '4501EPOS', 'General Sundries (VAT)', '5', '4500 - Sundries VAT', NULL, true),
('58', '4501POST', 'General Sundries (VAT)', '5', '4500 - Sundries VAT', NULL, true),
('53', '4301', 'Room Phone Call Charge', '5', '4500 - Sundries VAT', NULL, true),
('29', '4502', 'Function Room Hire', '5', '4500 - Sundries VAT', NULL, true),
('16', '4601EPOS', 'EPOS Sales Sundries (VAT)', '5', '4500 - Sundries VAT', NULL, true),
('17', '4601POST', 'EPOS Room Post Sundries (VAT)', '5', '4500 - Sundries VAT', NULL, true),
('46', '4201EPOS', 'EPOS Unspecified GL Account', '10', '9000 - Administration', NULL, true),
('47', '4201POST', 'EPOS Unspecified GL Account', '10', '9000 - Administration', NULL, true);

-- Discounts GL accounts
INSERT INTO newbook_gl_accounts (gl_account_id, gl_code, gl_name, gl_group_id, gl_group_name, department, is_active) VALUES
('18', '5101', 'EPOS Sales Discount/Rounding', '6', '5000 - Discounts', NULL, true),
('48', '5101EPOS', 'EPOS Cash Sale Discount/Rounding', '6', '5000 - Discounts', NULL, true),
('19', '5101POST', 'EPOS Room Post Discount/Rounding', '6', '5000 - Discounts', NULL, true);

-- Allowances GL accounts
INSERT INTO newbook_gl_accounts (gl_account_id, gl_code, gl_name, gl_group_id, gl_group_name, department, is_active) VALUES
('7', '1201', 'Accommodation Allowance Credits', '7', '6000 - Allowances', NULL, true),
('13', '3201', 'Dry Allowance Credits', '7', '6000 - Allowances', NULL, true),
('23', '2201', 'Wet Allowance Credits', '7', '6000 - Allowances', NULL, true);

-- Commission GL accounts
INSERT INTO newbook_gl_accounts (gl_account_id, gl_code, gl_name, gl_group_id, gl_group_name, department, is_active) VALUES
('20', '7001', 'Agent Commission', '8', '7000 - Commission', NULL, true);

-- Petty Cash GL accounts
INSERT INTO newbook_gl_accounts (gl_account_id, gl_code, gl_name, gl_group_id, gl_group_name, department, is_active) VALUES
('21', '8001', 'Petty Cash', '9', '8000 - Petty Cash', NULL, true);

-- Administration GL accounts
INSERT INTO newbook_gl_accounts (gl_account_id, gl_code, gl_name, gl_group_id, gl_group_name, department, is_active) VALUES
('22', '9001', 'Admin', '10', '9000 - Administration', NULL, true),
('31', '9001EPOS', 'EPOS without GL Account', '10', '9000 - Administration', NULL, true),
('30', '9001POST', 'EPOS without GL Account', '10', '9000 - Administration', NULL, true),
('43', '9102', 'EPOS Itemised Internal Transfer', '10', '9000 - Administration', NULL, true),
('44', '9103', 'EPOS Inter Hotel Transfer (OUT)', '10', '9000 - Administration', NULL, true),
('45', '9104', 'EPOS Inter Hotel Transfer (IN)', '10', '9000 - Administration', NULL, true),
('54', '9201', 'Bad Debt', '10', '9000 - Administration', NULL, true),
('51', '3401', 'Eat out to Help Out Discount', '10', '9000 - Administration', NULL, true);

-- Gratuity GL accounts
INSERT INTO newbook_gl_accounts (gl_account_id, gl_code, gl_name, gl_group_id, gl_group_name, department, is_active) VALUES
('24', '9002', 'Gratuity', '12', '9001 - Gratuity', NULL, true),
('40', '9101', 'Optional Gratuity', '12', '9001 - Gratuity', NULL, true);
