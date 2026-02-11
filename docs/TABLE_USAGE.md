# System Database & API Reference

This document tracks the database tables and backend endpoints used by the forecasting application.

---

# DATABASE TABLES

## Database: `forecast_data`

### Core Tables

| Table | Used For |
|-------|----------|
| `users` | User authentication and management |
| `system_config` | Newbook/Resos API settings, GL codes, sync settings |
| `newbook_room_categories` | Room type selection for occupancy calculations |
| `newbook_gl_accounts` | GL account fetch, grouping, and revenue department mapping |

### Newbook Data Tables

| Table | Used For |
|-------|----------|
| `newbook_bookings_data` | Historical hotel booking data |
| `newbook_earned_revenue_data` | Historical revenue by GL account |
| `newbook_net_revenue_data` | Aggregated revenue by department |
| `newbook_occupancy_report_data` | Official capacity & occupancy from Newbook |
| `newbook_bookings_stats` | Aggregated daily booking statistics |
| `newbook_booking_pace` | Lead-time snapshots for forecasting |
| `newbook_booking_pace_v2` | Enhanced pace snapshots with additional metrics |
| `newbook_current_rates` | Rack rates from Newbook API (snapshot model, 720-day horizon) |

### Forecasting Tables

| Table | Used For |
|-------|----------|
| `forecast_metrics` | Metric configuration for forecasting models |
| `daily_metrics` | Actual values storage (populated from stats) |
| `forecasts` | Generated predictions from all models |
| `actual_vs_forecast` | Comparison of actuals vs predictions |
| `forecast_snapshots` | Tracking forecast evolution over time |
| `weekly_forecast_snapshots` | Weekly point-in-time forecast snapshots |
| `daily_budgets` | Budget targets |

### Model-Specific Tables

| Table | Used For |
|-------|----------|
| `prophet_decomposition` | Prophet trend/seasonality breakdown |
| `xgboost_explanations` | XGBoost SHAP values |
| `pickup_explanations` | Pickup model reasoning |

### Competitor Rate Tables

| Table | Used For |
|-------|----------|
| `booking_com_hotels` | Tracked competitor hotels (own/competitor/market tiers) |
| `booking_com_rates` | Scraped competitor rates from Booking.com |
| `booking_scrape_log` | Scrape batch history and status tracking |
| `booking_scrape_queue` | Priority-based scrape queue (high/medium/low) |
| `booking_scrape_config` | Scraper configuration (location, pages, adults) |
| `rate_parity_alerts` | Rate parity discrepancy alerts |

### System Tables

| Table | Used For |
|-------|----------|
| `sync_log` | Sync operation history |

---

# BACKEND ENDPOINTS

## Authentication (`/auth/`)

| Endpoint | Method | Used For |
|----------|--------|----------|
| `/auth/login` | POST | User login |
| `/auth/me` | GET | Get current user |
| `/auth/users` | GET | List all users |
| `/auth/users` | POST | Create new user |
| `/auth/users/{id}` | DELETE | Delete user |

## Config/Settings (`/config/`)

| Endpoint | Method | Used For |
|----------|--------|----------|
| `/config/settings/newbook` | GET | Get Newbook API settings |
| `/config/settings/newbook` | POST | Save Newbook API settings |
| `/config/settings/newbook/test` | POST | Test Newbook connection |
| `/config/room-categories` | GET | List room categories |
| `/config/room-categories/fetch` | POST | Fetch room categories from Newbook |
| `/config/room-categories/bulk-update` | PATCH | Update room category inclusion |
| `/config/gl-accounts` | GET | List GL accounts |
| `/config/gl-accounts/fetch` | POST | Fetch GL accounts from Newbook |
| `/config/gl-accounts/department` | PATCH | Update GL department mappings |

## Sync (`/sync/`)

| Endpoint | Method | Used For |
|----------|--------|----------|
| `/sync/newbook/bookings` | POST | Sync hotel bookings |
| `/sync/newbook/occupancy` | POST | Sync occupancy report |
| `/sync/newbook/revenue` | POST | Sync earned revenue |
| `/sync/resos/bookings` | POST | Sync restaurant bookings |

## Forecast (`/forecast/`)

| Endpoint | Method | Used For |
|----------|--------|----------|
| `/forecast/generate` | POST | Generate forecasts |
| `/forecast/data` | GET | Get forecast data |

## Bookability (`/bookability/`)

| Endpoint | Method | Used For |
|----------|--------|----------|
| `/bookability/rate-matrix` | GET | Rate matrix with tariff availability |
| `/bookability/rate-matrix/summary` | GET | Summary stats (unbookable counts) |
| `/bookability/rate-history/{cat}/{date}` | GET | Rate change history |
| `/bookability/rate-changes` | GET | Recent rate changes |
| `/bookability/refresh-rates` | POST | Full rate refresh (background) |
| `/bookability/refresh-date/{date}` | POST | Single-date refresh (background) |

## Competitor Rates (`/competitor-rates/`)

| Endpoint | Method | Used For |
|----------|--------|----------|
| `/competitor-rates/status` | GET | Scraper status |
| `/competitor-rates/config/location` | POST | Configure scrape location |
| `/competitor-rates/config/enable` | POST | Enable/disable scraper |
| `/competitor-rates/config/unpause` | POST | Unpause after block |
| `/competitor-rates/scrape` | POST | Trigger manual scrape |
| `/competitor-rates/hotels` | GET | List tracked hotels |
| `/competitor-rates/hotels/{id}/tier` | PUT | Update hotel tier |
| `/competitor-rates/matrix` | GET | Competitor rate matrix |
| `/competitor-rates/parity` | GET | Rate parity comparison |
| `/competitor-rates/parity/alerts` | GET | Parity alerts |
| `/competitor-rates/queue-status` | GET | Scrape queue status |
| `/competitor-rates/schedule-info` | GET | Schedule information |
| `/competitor-rates/scrape-coverage` | GET | 365-day coverage view |
| `/competitor-rates/booking-availability` | GET | Own hotel Booking.com availability |
| `/competitor-rates/scrape-history` | GET | Scrape batch history |

## Reports (`/reports/`)

| Endpoint | Method | Used For |
|----------|--------|----------|
| `/reports/*` | Various | Report generation |

## Other Endpoints

- `/accuracy/*` - Forecast accuracy metrics
- `/backtest/*` - Backtesting operations
- `/budget/*` - Budget management
- `/explain/*` - Model explanations
- `/historical/*` - Historical data queries
- `/resos/*` - Resos mapping
- `/settings/*` - Special dates configuration

---

# SERVICES

| Service | File | Description |
|---------|------|-------------|
| Newbook client | `backend/services/newbook_client.py` | Newbook PMS API (bookings, occupancy, revenue) |
| Newbook rates client | `backend/services/newbook_rates_client.py` | Newbook Rates API (rack rates, tariff availability) |
| Booking scraper | `backend/services/booking_scraper.py` | Booking.com rate scraper (queue-based) |
| Scraper backends | `backend/services/scraper_backends/` | Scraper backend implementations |
| Resos client | `backend/services/resos_client.py` | Resos API integration |
| Backup service | `backend/services/backup_service.py` | Database backup/restore |
| Forecasting | `backend/services/forecasting/` | ML forecasting engines |

---

Last updated: 2025-02-11
