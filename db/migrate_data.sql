--
-- PostgreSQL database dump
--

\restrict R8nlCYFfDwgbBjnzJaP0bZEJU1LQC0DfcAqdc0eqA4M2I0Ec7NuCl0kBIZNPR3T

-- Dumped from database version 15.15
-- Dumped by pg_dump version 15.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: newbook_gl_accounts; Type: TABLE DATA; Schema: public; Owner: forecast
--

INSERT INTO public.newbook_gl_accounts VALUES (140, '7', '1201', 'Accommodation Allowance Credits', true, '2026-01-31 11:17:28.833621', '2025-12-14', -19159.47, '7', '6000 - Allowances', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (203, '26', '1302', 'Best Loved Discount Code', true, '2026-01-31 11:17:28.833621', NULL, 0.00, '1', '1000 - Accommodation', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (145, '22', '9001', 'Admin', true, '2026-01-31 11:17:28.833621', '2025-11-07', 3892.22, '10', '9000 - Administration', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (1, '20', '7001', 'Agent Commission', true, '2026-01-31 11:17:28.833621', '2026-01-29', -109262.81, '8', '7000 - Commission', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (168, '54', '9201', 'Bad Debt', true, '2026-01-31 11:17:28.833621', '2021-11-13', -2970.00, '10', '9000 - Administration', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (141, '13', '3201', 'Dry Allowance Credits', true, '2026-01-31 11:17:28.833621', '2025-12-14', -15454.60, '7', '6000 - Allowances', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (162, '51', '3401', 'Eat out to Help Out Discount', true, '2026-01-31 11:17:28.833621', '2020-08-31', 18.40, '10', '9000 - Administration', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (163, '52', '3306', 'EPOS 30% Off Lunch Discount Dry', true, '2026-01-31 11:17:28.833621', '2025-06-17', -2605.80, '6', '5000 - Discounts', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (209, '48', '5101EPOS', 'EPOS Cash Sale Discount/Rounding', true, '2026-01-31 11:17:28.833621', NULL, 0.00, '6', '5000 - Discounts', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (212, '45', '9104', 'EPOS Inter Hotel Transfer (IN)', true, '2026-01-31 11:17:28.833621', NULL, 0.00, '10', '9000 - Administration', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (204, '56', '1101', 'Cancellation Charge', true, '2026-01-31 11:17:28.833621', NULL, 0.00, '1', '1000 - Accommodation', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (165, '27', '1005', 'Cottage', true, '2026-01-31 11:17:28.833621', '2025-02-01', 199634.58, '1', '1000 - Accommodation', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (18, '36', '3301', 'EPOS General Discount Dry', true, '2026-01-31 11:17:28.833621', '2026-01-27', -1748.35, '3', '3000 - Dry', 'dry');
INSERT INTO public.newbook_gl_accounts VALUES (215, '37', '3302', 'EPOS Loyalty Discount Dry', true, '2026-01-31 11:17:28.833621', NULL, 0.00, '3', '3000 - Dry', 'dry');
INSERT INTO public.newbook_gl_accounts VALUES (154, '41', '3305', 'EPOS Offer Discount Dry', true, '2026-01-31 11:17:28.833621', '2025-12-07', -2491.70, '3', '3000 - Dry', 'dry');
INSERT INTO public.newbook_gl_accounts VALUES (5, '38', '3303', 'EPOS Regular Discount Dry', true, '2026-01-31 11:17:28.833621', '2026-01-24', -728.30, '3', '3000 - Dry', 'dry');
INSERT INTO public.newbook_gl_accounts VALUES (9, '12', '3101POST', 'EPOS Room Post Dry', true, '2026-01-31 11:17:28.833621', '2026-01-29', 803581.99, '3', '3000 - Dry', 'dry');
INSERT INTO public.newbook_gl_accounts VALUES (7, '11', '3101EPOS', 'EPOS Sales Dry', true, '2026-01-31 11:17:28.833621', '2026-01-29', 676296.31, '3', '3000 - Dry', 'dry');
INSERT INTO public.newbook_gl_accounts VALUES (21, '39', '3304', 'EPOS Staff Discount Dry', true, '2026-01-31 11:17:28.833621', '2026-01-25', -3481.35, '3', '3000 - Dry', 'dry');
INSERT INTO public.newbook_gl_accounts VALUES (19, '32', '2301', 'EPOS General Discount Wet', true, '2026-01-31 11:17:28.833621', '2026-01-27', -380.85, '2', '2000 - Wet 20%', 'wet');
INSERT INTO public.newbook_gl_accounts VALUES (216, '33', '2302', 'EPOS Loyalty Discount Wet', true, '2026-01-31 11:17:28.833621', NULL, 0.00, '2', '2000 - Wet 20%', 'wet');
INSERT INTO public.newbook_gl_accounts VALUES (6, '34', '2303', 'EPOS Regular Discount Wet', true, '2026-01-31 11:17:28.833621', '2026-01-24', -110.25, '2', '2000 - Wet 20%', 'wet');
INSERT INTO public.newbook_gl_accounts VALUES (4, '6', '2101POST', 'EPOS Room Post Wet', true, '2026-01-31 11:17:28.833621', '2026-01-28', 158125.10, '2', '2000 - Wet 20%', 'wet');
INSERT INTO public.newbook_gl_accounts VALUES (11, '50', '2102POST', 'EPOS Room Post Wet Alcohol', true, '2026-01-31 11:17:28.833621', '2026-01-29', 395086.60, '2', '2000 - Wet 20%', 'wet');
INSERT INTO public.newbook_gl_accounts VALUES (213, '44', '9103', 'EPOS Inter Hotel Transfer (OUT)', true, '2026-01-31 11:17:28.833621', NULL, 0.00, '10', '9000 - Administration', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (214, '43', '9102', 'EPOS Itemised Internal Transfer', true, '2026-01-31 11:17:28.833621', NULL, 0.00, '10', '9000 - Administration', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (220, '19', '5101POST', 'EPOS Room Post Discount/Rounding', true, '2026-01-31 11:17:28.833621', NULL, 0.00, '6', '5000 - Discounts', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (160, '17', '4601POST', 'EPOS Room Post Sundries (VAT)', true, '2026-01-31 11:17:28.833621', '2020-07-19', 30.00, '5', '4500 - Sundries VAT', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (2, '5', '2101EPOS', 'EPOS Sales Wet', true, '2026-01-31 11:17:28.833621', '2026-01-27', 126254.70, '2', '2000 - Wet 20%', 'wet');
INSERT INTO public.newbook_gl_accounts VALUES (12, '49', '2102EPOS', 'EPOS Sales Wet Alcohol', true, '2026-01-31 11:17:28.833621', '2026-01-29', 249033.80, '2', '2000 - Wet 20%', 'wet');
INSERT INTO public.newbook_gl_accounts VALUES (17, '35', '2304', 'EPOS Staff Discount Wet', true, '2026-01-31 11:17:28.833621', '2026-01-28', -1833.40, '2', '2000 - Wet 20%', 'wet');
INSERT INTO public.newbook_gl_accounts VALUES (149, '18', '5101', 'EPOS Sales Discount/Rounding', true, '2026-01-31 11:17:28.833621', '2024-03-10', -101.73, '6', '5000 - Discounts', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (169, '16', '4601EPOS', 'EPOS Sales Sundries (VAT)', true, '2026-01-31 11:17:28.833621', '2023-02-12', 105.42, '5', '4500 - Sundries VAT', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (232, '46', '4201EPOS', 'EPOS Unspecified GL Account', true, '2026-01-31 11:17:28.833621', NULL, 0.00, '10', '9000 - Administration', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (233, '47', '4201POST', 'EPOS Unspecified GL Account', true, '2026-01-31 11:17:28.833621', NULL, 0.00, '10', '9000 - Administration', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (152, '31', '9001EPOS', 'EPOS without GL Account', true, '2026-01-31 11:17:28.833621', '2019-03-14', 2.50, '10', '9000 - Administration', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (235, '30', '9001POST', 'EPOS without GL Account', true, '2026-01-31 11:17:28.833621', NULL, 0.00, '10', '9000 - Administration', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (151, '29', '4502', 'Function Room Hire', true, '2026-01-31 11:17:28.833621', '2022-11-15', 1761.00, '5', '4500 - Sundries VAT', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (144, '14', '4001', 'General Sundries (NO VAT)', true, '2026-01-31 11:17:28.833621', '2025-09-17', 380.80, '4', '4000 - Sundries NO VAT', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (20, '15', '4501', 'General Sundries (VAT)', true, '2026-01-31 11:17:28.833621', '2026-01-27', 48236.12, '5', '4500 - Sundries VAT', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (3, '57', '4501EPOS', 'General Sundries (VAT)', true, '2026-01-31 11:17:28.833621', '2026-01-23', 340.00, '5', '4500 - Sundries VAT', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (26, '58', '4501POST', 'General Sundries (VAT)', true, '2026-01-31 11:17:28.833621', '2026-01-28', 48.98, '5', '4500 - Sundries VAT', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (146, '24', '9002', 'Gratuity', true, '2026-01-31 11:17:28.833621', '2025-07-07', 269.17, '12', '9001 - Gratuity', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (8, '40', '9101', 'Optional Gratuity', true, '2026-01-31 11:17:28.833621', '2026-01-29', 153516.57, '12', '9001 - Gratuity', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (23, '21', '8001', 'Petty Cash', true, '2026-01-31 11:17:28.833621', '2026-01-18', -62582.66, '9', '8000 - Petty Cash', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (24, '53', '4301', 'Room Phone Call Charge', true, '2026-01-31 11:17:28.833621', '2026-01-23', 15.05, '5', '4500 - Sundries VAT', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (142, '23', '2201', 'Wet Allowance Credits', true, '2026-01-31 11:17:28.833621', '2025-12-14', -12861.95, '7', '6000 - Allowances', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (15, '55', '1003', 'Exec Double', true, '2026-01-31 11:17:28.833621', '2026-01-29', 390697.46, '1', '1000 - Accommodation', 'accommodation');
INSERT INTO public.newbook_gl_accounts VALUES (237, '2', '1002', 'Executive', true, '2026-01-31 11:17:28.833621', NULL, 0.00, '1', '1000 - Accommodation', 'accommodation');
INSERT INTO public.newbook_gl_accounts VALUES (16, '1', '1001', 'Standard', true, '2026-01-31 11:17:28.833621', '2026-01-29', 3366827.21, '1', '1000 - Accommodation', 'accommodation');
INSERT INTO public.newbook_gl_accounts VALUES (13, '3', '1004', 'Suite', true, '2026-01-31 11:17:28.833621', '2026-01-30', 1530959.77, '1', '1000 - Accommodation', 'accommodation');
INSERT INTO public.newbook_gl_accounts VALUES (22, '42', '1009', 'Overflow', true, '2026-01-31 11:17:28.833621', '2026-01-25', 13339.10, '1', '1000 - Accommodation', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (252, '25', '1301', 'Promotional Discount Code', true, '2026-01-31 11:17:28.833621', NULL, 0.00, '1', '1000 - Accommodation', NULL);
INSERT INTO public.newbook_gl_accounts VALUES (25, '28', '3102', 'Function Food', true, '2026-01-31 11:17:28.833621', '2026-01-25', 18817.91, '3', '3000 - Dry', 'dry');
INSERT INTO public.newbook_gl_accounts VALUES (10, '8', '3001', 'Meal Plan Breakfast', true, '2026-01-31 11:17:28.833621', '2026-01-30', 661543.32, '3', '3000 - Dry', 'dry');
INSERT INTO public.newbook_gl_accounts VALUES (14, '9', '3002', 'Meal Plan Dinner', true, '2026-01-31 11:17:28.833621', '2026-01-26', 204389.45, '3', '3000 - Dry', 'dry');
INSERT INTO public.newbook_gl_accounts VALUES (148, '10', '3003', 'Meal Plan Lunch', true, '2026-01-31 11:17:28.833621', '2025-12-26', 46241.50, '3', '3000 - Dry', 'dry');
INSERT INTO public.newbook_gl_accounts VALUES (131, '4', '2001', 'Meal Plan Wet', true, '2026-01-31 11:17:28.833621', '2025-06-10', 149.85, '2', '2000 - Wet 20%', 'wet');


--
-- Data for Name: newbook_room_categories; Type: TABLE DATA; Schema: public; Owner: forecast
--

INSERT INTO public.newbook_room_categories VALUES (2, 'Standard', 'Standard', 'Standard', 16, true, 0, '2026-01-31 10:40:40.357966');
INSERT INTO public.newbook_room_categories VALUES (3, 'Executive Double', 'Executive Double', 'Executive Double', 3, true, 0, '2026-01-31 10:40:40.357966');
INSERT INTO public.newbook_room_categories VALUES (4, 'Suite', 'Suite', 'Suite', 4, true, 0, '2026-01-31 10:40:40.357966');
INSERT INTO public.newbook_room_categories VALUES (5, 'Suite - Family Room', 'Suite - Family Room', 'Suite - Family Room', 1, true, 0, '2026-01-31 10:40:40.357966');
INSERT INTO public.newbook_room_categories VALUES (6, 'Accessible Room', 'Accessible Room', 'Accessible Room', 1, true, 0, '2026-01-31 10:40:40.357966');
INSERT INTO public.newbook_room_categories VALUES (7, 'Overflow', 'Overflow', 'Overflow', 1, false, 0, '2026-01-31 10:40:40.357966');


--
-- Data for Name: system_config; Type: TABLE DATA; Schema: public; Owner: forecast
--

INSERT INTO public.system_config VALUES (12, 'newbook_dinner_vat_rate', '0.2', false, 'VAT rate for dinner items (e.g., 0.20 for 20%)', '2026-01-29 20:27:05.636858', 'admin');
INSERT INTO public.system_config VALUES (7, 'hotel_name', 'Number Four at Stow', false, 'Hotel/Property Name', '2026-01-29 20:27:23.888995', 'admin');
INSERT INTO public.system_config VALUES (6, 'total_rooms', '25', false, 'Total number of hotel rooms (for occupancy calculation)', '2026-01-29 20:27:23.902765', 'admin');
INSERT INTO public.system_config VALUES (8, 'timezone', 'Europe/London', false, 'Local timezone (e.g., Europe/London)', '2026-01-29 20:27:23.916884', 'admin');
INSERT INTO public.system_config VALUES (18, 'accommodation_gl_codes', '1001,1002,1003,1004,1005', false, 'Comma-separated list of GL codes for accommodation/room revenue', '2026-01-29 22:10:31.599973', 'admin');
INSERT INTO public.system_config VALUES (17, 'accommodation_vat_rate', '0.2', false, 'VAT rate for accommodation (0.20 = 20%)', '2026-01-29 22:10:31.616104', 'admin');
INSERT INTO public.system_config VALUES (5, 'resos_api_key', 'Ry1qV1dGVUV1a0s5akRJR0hXR2dMTl9nZlR5WlpTYkRLcTUzQ3ZlUmI0bA==', true, 'Resos API Key', '2026-01-30 00:21:26.623234', 'admin');
INSERT INTO public.system_config VALUES (13, 'sync_newbook_enabled', 'true', false, 'Enable automatic Newbook sync (true/false)', '2026-01-30 01:42:13.640274', 'admin');
INSERT INTO public.system_config VALUES (14, 'sync_resos_enabled', 'true', false, 'Enable automatic Resos sync (true/false)', '2026-01-30 01:42:13.654357', 'admin');
INSERT INTO public.system_config VALUES (15, 'sync_schedule_time', '05:00', false, 'Time for daily sync (HH:MM format)', '2026-01-30 01:42:13.667395', 'admin');
INSERT INTO public.system_config VALUES (1, 'newbook_api_key', 'aW5zdGFuY2VzXzI3NGE3NWU3ZTlhYjZiMjAzZWVhODFmYmI2NmJlNzVh', true, 'Newbook API Key', '2026-01-29 18:55:23.474785', 'admin');
INSERT INTO public.system_config VALUES (2, 'newbook_username', 'sambapos_nf', false, 'Newbook Username', '2026-01-29 18:55:23.488724', 'admin');
INSERT INTO public.system_config VALUES (3, 'newbook_password', 'cDU4d2k3bFh0YTI1Z0cxdg==', true, 'Newbook Password', '2026-01-29 18:55:23.503589', 'admin');
INSERT INTO public.system_config VALUES (4, 'newbook_region', 'eu', false, 'Newbook Region Code', '2026-01-29 18:55:23.517114', 'admin');
INSERT INTO public.system_config VALUES (9, 'newbook_breakfast_gl_codes', '3001', false, 'Comma-separated list of GL codes for breakfast items', '2026-01-29 20:27:05.593479', 'admin');
INSERT INTO public.system_config VALUES (10, 'newbook_dinner_gl_codes', '3003', false, 'Comma-separated list of GL codes for dinner items', '2026-01-29 20:27:05.608016', 'admin');
INSERT INTO public.system_config VALUES (11, 'newbook_breakfast_vat_rate', '0.2', false, 'VAT rate for breakfast items (e.g., 0.20 for 20%)', '2026-01-29 20:27:05.624041', 'admin');


--
-- Name: newbook_gl_accounts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: forecast
--

SELECT pg_catalog.setval('public.newbook_gl_accounts_id_seq', 314, true);


--
-- Name: newbook_room_categories_id_seq; Type: SEQUENCE SET; Schema: public; Owner: forecast
--

SELECT pg_catalog.setval('public.newbook_room_categories_id_seq', 7, true);


--
-- Name: system_config_id_seq; Type: SEQUENCE SET; Schema: public; Owner: forecast
--

SELECT pg_catalog.setval('public.system_config_id_seq', 19, true);


--
-- PostgreSQL database dump complete
--

\unrestrict R8nlCYFfDwgbBjnzJaP0bZEJU1LQC0DfcAqdc0eqA4M2I0Ec7NuCl0kBIZNPR3T

