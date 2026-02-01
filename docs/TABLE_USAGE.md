# System Usage Tracking - New UI vs Old Dashboard

This document tracks which database tables, backend endpoints, and features are used by the new React UI vs the old Streamlit dashboard. Use this to identify redundant code for cleanup.

---

# DATABASE TABLES

## Tables Used by NEW UI (React Frontend)

| Table | Used For | Status |
|-------|----------|--------|
| `users` | User authentication and management | Active |
| `system_config` | Newbook/Resos API settings, GL codes, sync settings | Active |
| `newbook_room_categories` | Room type selection for occupancy (NEW) | Active |
| `newbook_gl_accounts` | GL account fetch, grouping, and revenue department mapping (NEW fields: gl_group_id, gl_group_name, department) | Active |

## Tables Used by OLD Dashboard (Streamlit)

| Table | Used For | Status |
|-------|----------|--------|
| `users` | User authentication | Keep |
| `system_config` | All settings storage | Keep |
| `newbook_bookings` | Hotel booking data | Keep (data sync) |
| `newbook_booking_nights` | Per-night tariff breakdown | Keep (data sync) |
| `newbook_occupancy_report` | Occupancy report data | Keep (data sync) |
| `newbook_earned_revenue` | Revenue by GL account | Keep (data sync) |
| `newbook_gl_accounts` | GL account cache | Keep |
| `resos_bookings` | Restaurant booking data | Keep (data sync) |
| `daily_occupancy` | Aggregated hotel stats | Keep (forecasting) |
| `daily_covers` | Aggregated restaurant stats | Keep (forecasting) |
| `daily_revenue` | Revenue by GL account | Keep (forecasting) |
| `daily_metrics` | Unified daily actuals | Keep (forecasting) |
| `forecasts` | Generated predictions | Keep (forecasting) |
| `forecast_runs` | Forecast metadata | Keep (forecasting) |
| `forecast_history` | Full audit trail | Keep (forecasting) |
| `pickup_snapshots` | OTB snapshots for pickup model | Keep (forecasting) |
| `monthly_budgets` | FD budget targets | Keep (budgeting) |
| `daily_budgets` | Distributed budget | Keep (budgeting) |
| `sync_log` | Sync history | Keep (monitoring) |
| `aggregation_queue` | Pending aggregations | Keep (processing) |
| `room_categories` | Auto-populated from booking data | Review - may be redundant |

## Tables to Potentially Remove

| Table | Reason |
|-------|--------|
| `room_categories` | Replaced by `newbook_room_categories` which has `is_included` flag |

## Table Migration Notes

- The `newbook_room_categories` table was added to support user selection of which room types to include in occupancy calculations
- The old `room_categories` table was auto-populated from booking data but had no selection capability
- Consider migrating any useful data from `room_categories` to `newbook_room_categories` before removal
- The `newbook_gl_accounts` table was extended with `gl_group_id`, `gl_group_name`, and `department` fields for revenue mapping
- Run `db/add_gl_account_fields.sql` on existing databases to add the new columns

---

# BACKEND ENDPOINTS

## Endpoints Used by NEW UI (React Frontend)

### Authentication (`/api/auth/`)
| Endpoint | Method | Used For | File |
|----------|--------|----------|------|
| `/api/auth/login` | POST | User login | `backend/api/auth.py` |
| `/api/auth/me` | GET | Get current user | `backend/api/auth.py` |
| `/api/auth/users` | GET | List all users | `backend/api/auth.py` |
| `/api/auth/users` | POST | Create new user | `backend/api/auth.py` |
| `/api/auth/users/{id}` | DELETE | Delete user | `backend/api/auth.py` |

### Config/Settings (`/api/config/`)
| Endpoint | Method | Used For | File |
|----------|--------|----------|------|
| `/api/config/settings/newbook` | GET | Get Newbook API settings | `backend/api/config.py` |
| `/api/config/settings/newbook` | POST | Save Newbook API settings | `backend/api/config.py` |
| `/api/config/settings/newbook/test` | POST | Test Newbook connection | `backend/api/config.py` |
| `/api/config/room-categories` | GET | List room categories | `backend/api/config.py` |
| `/api/config/room-categories/fetch` | POST | Fetch room categories from Newbook | `backend/api/config.py` |
| `/api/config/room-categories/bulk-update` | PATCH | Update room category is_included | `backend/api/config.py` |
| `/api/config/gl-accounts` | GET | List GL accounts | `backend/api/config.py` |
| `/api/config/gl-accounts/fetch` | POST | Fetch GL accounts from Newbook | `backend/api/config.py` |
| `/api/config/gl-accounts/department` | PATCH | Update GL department mappings | `backend/api/config.py` |

## Endpoints Used by OLD Dashboard (Streamlit)

### Sync Endpoints (`/api/sync/`)
| Endpoint | Method | Used For | Status |
|----------|--------|----------|--------|
| `/api/sync/newbook/bookings` | POST | Sync hotel bookings | Keep (data sync) |
| `/api/sync/newbook/occupancy` | POST | Sync occupancy report | Keep (data sync) |
| `/api/sync/newbook/revenue` | POST | Sync earned revenue | Keep (data sync) |
| `/api/sync/resos/bookings` | POST | Sync restaurant bookings | Keep (data sync) |
| `/api/sync/aggregate` | POST | Run aggregation | Keep (processing) |

### Dashboard Data Endpoints
| Endpoint | Method | Used For | Status |
|----------|--------|----------|--------|
| `/api/dashboard/occupancy` | GET | Get occupancy data | Review |
| `/api/dashboard/revenue` | GET | Get revenue data | Review |
| `/api/dashboard/forecasts` | GET | Get forecast data | Review |
| `/api/budgets/*` | Various | Budget management | Review |

## Endpoints to Potentially Remove

| Endpoint | Reason |
|----------|--------|
| TBD | Review after new UI is complete |

---

# BACKEND SERVICES & FEATURES

## Services Used by NEW UI

| Service/Feature | File | Description |
|-----------------|------|-------------|
| User authentication | `backend/api/auth.py` | JWT-based auth |
| Config management | `backend/api/config.py` | System settings CRUD |
| Newbook API client | `backend/api/config.py` | Direct API calls for settings |

## Services Used by OLD Dashboard

| Service/Feature | File | Description | Status |
|-----------------|------|-------------|--------|
| Newbook sync service | `backend/services/newbook_sync.py` | Full booking/revenue sync | Keep |
| Resos sync service | `backend/services/resos_sync.py` | Restaurant booking sync | Keep |
| Aggregation service | `backend/services/aggregation.py` | Daily metric aggregation | Keep |
| Forecast engine | `backend/services/forecast.py` | ML forecasting | Keep |
| Budget service | `backend/services/budget.py` | Budget distribution | Keep |

## Services to Potentially Remove

| Service | Reason |
|---------|--------|
| TBD | Review after new UI is complete |

---

# FRONTEND PAGES/COMPONENTS

## Pages in NEW UI (React)

| Page/Component | File | Features |
|----------------|------|----------|
| Login | `frontend/src/pages/Login.tsx` | User authentication |
| Settings | `frontend/src/pages/Settings.tsx` | Newbook config, Users, Database browser |
| Settings > Newbook | `frontend/src/pages/Settings.tsx` | API config, Room categories, GL mapping |

## Pages in OLD Dashboard (Streamlit)

| Page | File | Status |
|------|------|--------|
| Dashboard | `dashboard/pages/dashboard.py` | Review - may move to new UI |
| Forecasts | `dashboard/pages/forecasts.py` | Review - may move to new UI |
| Budgets | `dashboard/pages/budgets.py` | Review - may move to new UI |
| Sync Status | `dashboard/pages/sync.py` | Review - may move to new UI |
| Settings | `dashboard/pages/settings.py` | Being replaced by new UI |

---

Last updated: 2026-01-31
