# Database Documentation

## Overview

The Forecasting App uses PostgreSQL 15+ as its database. The schema is designed to support:
- User authentication
- System configuration
- External data storage (Newbook, Resos)
- Aggregated statistics
- Forecasting model outputs
- Accuracy tracking

## Database Connection

```
Host: db (Docker) or localhost
Port: 5432
Database: forecast_data
User: forecast
Password: forecast_secret (change in production!)
```

## Schema Diagram

```
┌─────────────────────┐     ┌──────────────────────┐
│       users         │     │    system_config     │
├─────────────────────┤     ├──────────────────────┤
│ id (PK)             │     │ id (PK)              │
│ username (UNIQUE)   │     │ config_key (UNIQUE)  │
│ password_hash       │     │ config_value         │
│ display_name        │     │ is_encrypted         │
│ is_active           │     │ description          │
│ created_at          │     │ updated_at           │
└─────────────────────┘     └──────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                    NEWBOOK RAW DATA                           │
├─────────────────────────┬─────────────────────────────────────┤
│ newbook_bookings_data   │ newbook_earned_revenue_data         │
│ newbook_room_categories │ newbook_occupancy_report_data       │
│ newbook_gl_accounts     │ newbook_net_revenue_data            │
└─────────────────────────┴─────────────────────────────────────┘
           │                             │
           ▼                             ▼
┌───────────────────────────────────────────────────────────────┐
│                  AGGREGATED STATISTICS                        │
├─────────────────────────┬─────────────────────────────────────┤
│ newbook_bookings_stats  │ daily_metrics                       │
│ newbook_booking_pace    │ daily_budgets                       │
└─────────────────────────┴─────────────────────────────────────┘
           │                             │
           ▼                             ▼
┌───────────────────────────────────────────────────────────────┐
│                    FORECASTING                                │
├─────────────────────────┬─────────────────────────────────────┤
│ forecast_metrics        │ forecasts                           │
│ actual_vs_forecast      │ forecast_snapshots                  │
│ prophet_decomposition   │ pickup_explanations                 │
│ xgboost_explanations    │                                     │
└─────────────────────────┴─────────────────────────────────────┘
```

---

## Tables

### Authentication & Configuration

#### `users`

Stores user accounts for authentication.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `username` | VARCHAR(50) | UNIQUE NOT NULL | Login username |
| `password_hash` | VARCHAR(255) | NOT NULL | bcrypt hashed password |
| `display_name` | VARCHAR(100) | | User's display name |
| `is_active` | BOOLEAN | DEFAULT TRUE | Account status |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Account creation time |

**Default Data:**
- Username: `admin`, Password: `admin123` (change in production!)

**Populated By:** User registration via API or SQL insert

---

#### `system_config`

Key-value store for system configuration.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `config_key` | VARCHAR(100) | UNIQUE NOT NULL | Configuration key |
| `config_value` | TEXT | | Configuration value |
| `is_encrypted` | BOOLEAN | DEFAULT FALSE | Whether value is encrypted |
| `description` | TEXT | | Human-readable description |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | Last update time |
| `updated_by` | VARCHAR(100) | | Username who updated |

**Common Config Keys:**

| Key | Description | Default |
|-----|-------------|---------|
| `newbook_api_key` | Newbook API key (encrypted) | null |
| `newbook_username` | Newbook API username | null |
| `newbook_password` | Newbook API password (encrypted) | null |
| `newbook_region` | Newbook region code | null |
| `resos_api_key` | Resos API key (encrypted) | null |
| `total_rooms` | Total hotel rooms | 80 |
| `timezone` | Local timezone | Europe/London |
| `accommodation_vat_rate` | VAT rate for accommodation | 0.20 |
| `sync_newbook_enabled` | Enable auto Newbook sync | false |
| `sync_newbook_bookings_time` | Booking sync time (HH:MM) | 05:00 |
| `sync_newbook_earned_revenue_enabled` | Enable revenue sync | false |
| `sync_newbook_earned_revenue_time` | Revenue sync time | 05:10 |

**Populated By:** UI settings page, initial SQL script

---

### Newbook Raw Data

#### `newbook_room_categories`

Room categories fetched from Newbook site_list API.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `site_id` | VARCHAR(50) | UNIQUE NOT NULL | Newbook category ID |
| `site_name` | VARCHAR(255) | NOT NULL | Category name |
| `site_type` | VARCHAR(100) | | Category type |
| `room_count` | INTEGER | DEFAULT 0 | Number of rooms in category |
| `is_included` | BOOLEAN | DEFAULT TRUE | Include in occupancy calcs |
| `display_order` | INTEGER | DEFAULT 0 | Display sort order |
| `fetched_at` | TIMESTAMP | DEFAULT NOW() | Last fetch time |

**Populated By:** `/config/room-categories/fetch` API endpoint

**Used By:** Occupancy calculations, room filtering

---

#### `newbook_gl_accounts`

GL accounts discovered from earned revenue data.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `gl_account_id` | VARCHAR(50) | UNIQUE NOT NULL | Newbook GL account ID |
| `gl_code` | VARCHAR(50) | | GL code |
| `gl_name` | VARCHAR(255) | | Account name |
| `gl_group_id` | VARCHAR(50) | | GL group ID |
| `gl_group_name` | VARCHAR(255) | | GL group name |
| `department` | VARCHAR(20) | | Department: accommodation, dry, wet |
| `last_seen_date` | DATE | | Last date with activity |
| `total_amount` | DECIMAL(14,2) | DEFAULT 0 | Total amount seen |
| `is_active` | BOOLEAN | DEFAULT TRUE | Account active status |
| `fetched_at` | TIMESTAMP | DEFAULT NOW() | Last fetch time |

**Department Values:**
- `accommodation` - Room revenue
- `dry` - Food revenue
- `wet` - Beverage revenue
- `null` - Unmapped/other

**Populated By:** `/config/gl-accounts/fetch` API endpoint, revenue sync

**Used By:** Revenue aggregation by department

---

#### `newbook_bookings_data`

Raw booking data from Newbook booking_search API.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `newbook_id` | VARCHAR(50) | UNIQUE NOT NULL | Newbook booking ID |
| `booking_reference` | VARCHAR(100) | | Booking reference number |
| `bookings_group_id` | VARCHAR(50) | | Group booking ID |
| `booking_placed` | TIMESTAMP | | When booking was created |
| `arrival_date` | DATE | NOT NULL | Check-in date |
| `departure_date` | DATE | NOT NULL | Check-out date |
| `nights` | INTEGER | | Number of nights |
| `adults` | INTEGER | DEFAULT 0 | Number of adults |
| `children` | INTEGER | DEFAULT 0 | Number of children |
| `infants` | INTEGER | DEFAULT 0 | Number of infants |
| `total_guests` | INTEGER | | Total guest count |
| `category_id` | VARCHAR(50) | | Room category ID |
| `room_type` | VARCHAR(100) | | Room type name |
| `site_id` | VARCHAR(50) | | Room site ID |
| `room_number` | VARCHAR(50) | | Room number |
| `status` | VARCHAR(50) | | Booking status |
| `total_amount` | DECIMAL(12,2) | | Total booking amount |
| `tariff_name` | VARCHAR(255) | | Rate plan name |
| `tariff_total` | DECIMAL(12,2) | | Tariff total |
| `travel_agent_id` | VARCHAR(50) | | Travel agent ID |
| `travel_agent_name` | VARCHAR(255) | | Travel agent name |
| `travel_agent_commission` | DECIMAL(12,2) | | Commission amount |
| `booking_source_id` | VARCHAR(50) | | Booking source ID |
| `booking_source_name` | VARCHAR(255) | | Booking source name |
| `booking_parent_source_id` | VARCHAR(50) | | Parent source ID |
| `booking_parent_source_name` | VARCHAR(255) | | Parent source name |
| `booking_method_id` | VARCHAR(50) | | Booking method ID |
| `booking_method_name` | VARCHAR(100) | | Booking method name |
| `raw_json` | JSONB | | Full API response |
| `fetched_at` | TIMESTAMP | DEFAULT NOW() | Last fetch time |

**Indices:**
- `idx_bookings_arrival` on `arrival_date`
- `idx_bookings_status` on `status`
- `idx_bookings_placed` on `booking_placed`

**Populated By:** `/sync/newbook` API endpoint, scheduled sync

**Used By:** Booking aggregation, pace calculations, lead time analysis

---

#### `newbook_earned_revenue_data`

Revenue data from Newbook report_earned_revenue API.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `date` | DATE | NOT NULL | Revenue date |
| `gl_account_id` | VARCHAR(50) | | GL account ID |
| `gl_code` | VARCHAR(50) | | GL code |
| `gl_name` | VARCHAR(255) | | Account name |
| `amount_gross` | DECIMAL(12,2) | DEFAULT 0 | Gross amount |
| `amount_net` | DECIMAL(12,2) | DEFAULT 0 | Net amount (ex VAT) |
| `revenue_type` | VARCHAR(30) | | Derived revenue type |
| `fetched_at` | TIMESTAMP | DEFAULT NOW() | Last fetch time |

**Constraints:** UNIQUE(date, gl_account_id)

**Indices:**
- `idx_earned_revenue_data_date` on `date`
- `idx_earned_revenue_data_type` on `date, revenue_type`

**Populated By:** `/sync/newbook/earned-revenue` API endpoint

**Used By:** Revenue aggregation, financial reporting

---

#### `newbook_net_revenue_data`

Aggregated net revenue by department.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `date` | DATE | UNIQUE NOT NULL | Revenue date |
| `accommodation` | DECIMAL(12,2) | DEFAULT 0 | Net accommodation revenue |
| `dry` | DECIMAL(12,2) | DEFAULT 0 | Net food revenue |
| `wet` | DECIMAL(12,2) | DEFAULT 0 | Net beverage revenue |
| `aggregated_at` | TIMESTAMP | DEFAULT NOW() | Aggregation time |

**Populated By:** Revenue aggregation job (aggregates from earned_revenue_data using GL account mappings)

**Used By:** Historical analysis, forecasting

---

#### `newbook_occupancy_report_data`

Official occupancy data from Newbook report_occupancy API.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `date` | DATE | NOT NULL | Report date |
| `category_id` | VARCHAR(50) | NOT NULL | Room category ID |
| `category_name` | VARCHAR(255) | | Category name |
| `available` | INTEGER | DEFAULT 0 | Total configured rooms |
| `occupied` | INTEGER | DEFAULT 0 | Official occupied count |
| `maintenance` | INTEGER | DEFAULT 0 | Rooms offline |
| `allotted` | INTEGER | DEFAULT 0 | Block allocations |
| `revenue_gross` | DECIMAL(12,2) | DEFAULT 0 | Gross revenue |
| `revenue_net` | DECIMAL(12,2) | DEFAULT 0 | Net revenue |
| `occupancy_pct` | DECIMAL(5,2) | | Occupancy percentage |
| `fetched_at` | TIMESTAMP | DEFAULT NOW() | Last fetch time |

**Constraints:** UNIQUE(date, category_id)

**Index:** `idx_occupancy_report_data_date` on `date`

**Populated By:** `/sync/newbook/occupancy-report` API endpoint

**Used By:** Accurate occupancy calculations accounting for maintenance

---

### Aggregated Statistics

#### `newbook_bookings_stats`

Daily aggregated booking statistics.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `date` | DATE | UNIQUE NOT NULL | Stats date |
| `rooms_count` | INTEGER | DEFAULT 0 | Total available rooms |
| `maintenance_count` | INTEGER | DEFAULT 0 | Rooms in maintenance |
| `bookable_count` | INTEGER | DEFAULT 0 | Bookable rooms |
| `booking_count` | INTEGER | DEFAULT 0 | Occupied rooms |
| `guests_count` | INTEGER | DEFAULT 0 | Total guests |
| `adults_count` | INTEGER | DEFAULT 0 | Adult guests |
| `children_count` | INTEGER | DEFAULT 0 | Child guests |
| `infants_count` | INTEGER | DEFAULT 0 | Infant guests |
| `total_occupancy_pct` | DECIMAL(5,2) | | booking_count / rooms_count |
| `bookable_occupancy_pct` | DECIMAL(5,2) | | booking_count / bookable_count |
| `guest_rate_total` | DECIMAL(12,2) | DEFAULT 0 | Total gross revenue |
| `net_booking_rev_total` | DECIMAL(12,2) | DEFAULT 0 | Total net revenue |
| `occupancy_by_category` | JSONB | DEFAULT '{}' | Per-category occupancy |
| `revenue_by_category` | JSONB | DEFAULT '{}' | Per-category revenue |
| `availability_by_category` | JSONB | DEFAULT '{}' | Per-category availability |
| `aggregated_at` | TIMESTAMP | DEFAULT NOW() | Aggregation time |

**JSONB Structure Example:**
```json
{
  "occupancy_by_category": {
    "56": {"occupied": 25, "available": 30},
    "57": {"occupied": 15, "available": 20}
  }
}
```

**Index:** `idx_bookings_stats_date` on `date`

**Populated By:** Booking aggregation job

**Calculated Fields:**
- `total_occupancy_pct` = `booking_count` / `rooms_count` * 100
- `bookable_occupancy_pct` = `booking_count` / `bookable_count` * 100

**Used By:** Historical display, forecast training data

---

#### `newbook_booking_pace`

Lead-time snapshots for pickup forecasting.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `arrival_date` | DATE | UNIQUE NOT NULL | Target arrival date |
| `d365` | INTEGER | | Bookings 365 days out |
| `d330` | INTEGER | | Bookings 330 days out |
| `d300` | INTEGER | | Bookings 300 days out |
| ... | | | (Monthly intervals) |
| `d37` | INTEGER | | Bookings 37 days out |
| `d30` | INTEGER | | Bookings 30 days out |
| `d29` | INTEGER | | Bookings 29 days out |
| ... | | | (Daily intervals) |
| `d0` | INTEGER | | Bookings on arrival day |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | Last update |

**Lead Time Columns (58 total):**
- Monthly (6): d365, d330, d300, d270, d240, d210
- Weekly (21): d177, d170, ..., d37
- Daily (31): d30, d29, ..., d0

**Index:** `idx_booking_pace_arrival` on `arrival_date`

**Populated By:** Pickup snapshot job (runs daily, captures current OTB)

**Used By:** Pickup forecasting model

---

### Forecasting Tables

#### `forecast_metrics`

Configuration of forecastable metrics.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `metric_code` | VARCHAR(50) | UNIQUE NOT NULL | Metric identifier |
| `metric_name` | VARCHAR(100) | NOT NULL | Display name |
| `description` | TEXT | | Metric description |
| `unit` | VARCHAR(20) | | Unit: percent, rooms, guests |
| `is_active` | BOOLEAN | DEFAULT TRUE | Metric enabled |
| `use_prophet` | BOOLEAN | DEFAULT TRUE | Use Prophet model |
| `use_xgboost` | BOOLEAN | DEFAULT TRUE | Use XGBoost model |
| `use_pickup` | BOOLEAN | DEFAULT FALSE | Use Pickup model |
| `use_catboost` | BOOLEAN | DEFAULT TRUE | Use CatBoost model |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Creation time |

**Default Metrics:**

| Code | Name | Unit | Models |
|------|------|------|--------|
| `hotel_occupancy_pct` | Hotel Occupancy % | percent | All |
| `hotel_room_nights` | Room Nights | rooms | All |
| `hotel_guests` | Guest Count | guests | Prophet, XGBoost, CatBoost |
| `hotel_arrivals` | Arrivals | arrivals | Prophet, XGBoost, CatBoost |

**Populated By:** Initial SQL script, admin configuration

---

#### `daily_metrics`

Actual values for metrics (training data for models).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `date` | DATE | NOT NULL | Metric date |
| `metric_code` | VARCHAR(50) | NOT NULL | Metric identifier |
| `actual_value` | DECIMAL(12,2) | | Actual value |
| `source` | VARCHAR(50) | DEFAULT 'newbook' | Data source |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | Last update |

**Constraints:** UNIQUE(date, metric_code)

**Indices:**
- `idx_daily_metrics_date` on `date`
- `idx_daily_metrics_code` on `metric_code, date`

**Populated By:** Metrics aggregation job (from bookings_stats)

**Used By:** Model training, accuracy calculations

---

#### `forecasts`

Generated forecast values.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `run_id` | UUID | | Forecast run identifier |
| `forecast_date` | DATE | NOT NULL | Date being forecast |
| `forecast_type` | VARCHAR(50) | NOT NULL | Metric code |
| `model_type` | VARCHAR(20) | NOT NULL | Model: prophet, xgboost, pickup, catboost |
| `predicted_value` | DECIMAL(12,2) | NOT NULL | Forecast value |
| `lower_bound` | DECIMAL(12,2) | | Lower confidence bound |
| `upper_bound` | DECIMAL(12,2) | | Upper confidence bound |
| `generated_at` | TIMESTAMP | DEFAULT NOW() | Generation time |

**Constraints:** UNIQUE(forecast_date, forecast_type, model_type, generated_at)

**Indices:**
- `idx_forecasts_date` on `forecast_date`
- `idx_forecasts_type` on `forecast_type, model_type`
- `idx_forecasts_generated` on `generated_at DESC`

**Populated By:** Forecast daily job, `/forecast/regenerate` API

**Used By:** Forecast display, comparison

---

#### `actual_vs_forecast`

Comparison of forecasts to actuals for accuracy tracking.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `date` | DATE | NOT NULL | Comparison date |
| `metric_type` | VARCHAR(50) | NOT NULL | Metric code |
| `actual_value` | DECIMAL(12,2) | | Actual value |
| `budget_value` | DECIMAL(12,2) | | Budget value |
| `prophet_forecast` | DECIMAL(12,2) | | Prophet prediction |
| `prophet_lower` | DECIMAL(12,2) | | Prophet lower bound |
| `prophet_upper` | DECIMAL(12,2) | | Prophet upper bound |
| `prophet_error` | DECIMAL(12,4) | | Prophet error |
| `prophet_pct_error` | DECIMAL(8,4) | | Prophet % error |
| `xgboost_forecast` | DECIMAL(12,2) | | XGBoost prediction |
| `xgboost_error` | DECIMAL(12,4) | | XGBoost error |
| `xgboost_pct_error` | DECIMAL(8,4) | | XGBoost % error |
| `pickup_forecast` | DECIMAL(12,2) | | Pickup prediction |
| `pickup_error` | DECIMAL(12,4) | | Pickup error |
| `pickup_pct_error` | DECIMAL(8,4) | | Pickup % error |
| `catboost_forecast` | DECIMAL(12,2) | | CatBoost prediction |
| `catboost_error` | DECIMAL(12,4) | | CatBoost error |
| `catboost_pct_error` | DECIMAL(8,4) | | CatBoost % error |
| `best_model` | VARCHAR(20) | | Model with lowest error |
| `calculated_at` | TIMESTAMP | DEFAULT NOW() | Calculation time |

**Constraints:** UNIQUE(date, metric_type)

**Indices:**
- `idx_actual_vs_forecast_date` on `date`
- `idx_actual_vs_forecast_type` on `metric_type`

**Calculated Fields:**
- `*_error` = `*_forecast` - `actual_value`
- `*_pct_error` = `*_error` / `actual_value` * 100
- `best_model` = model with minimum absolute error

**Populated By:** Accuracy calculation job

**Used By:** Accuracy display, model comparison

---

#### `daily_budgets`

Budget values for comparison.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `date` | DATE | NOT NULL | Budget date |
| `budget_type` | VARCHAR(50) | NOT NULL | Metric code |
| `budget_value` | DECIMAL(12,2) | | Budget value |

**Constraints:** UNIQUE(date, budget_type)

**Index:** `idx_daily_budgets_date` on `date`

**Populated By:** CSV upload via `/budget/upload` API

---

#### `forecast_snapshots`

Historical forecasts for backtesting accuracy by lead time.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `snapshot_date` | DATE | | When forecast was made |
| `target_date` | DATE | NOT NULL | Date being forecast |
| `metric_code` | VARCHAR(50) | NOT NULL | Metric identifier |
| `days_out` | INTEGER | | Lead time in days |
| `model` | VARCHAR(20) | | Model type |
| `forecast_value` | DECIMAL(12,2) | | Predicted value |
| `actual_value` | DECIMAL(12,2) | | Actual value (filled later) |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Creation time |

**Constraints:** UNIQUE(snapshot_date, target_date, metric_code, model)

**Index:** `idx_forecast_snapshots_target` on `target_date`

**Populated By:** Daily forecast job (captures point-in-time forecasts)

**Used By:** Accuracy by lead time analysis

---

### Model Explanations

#### `prophet_decomposition`

Prophet model component breakdown.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `run_id` | UUID | | Forecast run ID |
| `forecast_date` | DATE | NOT NULL | Forecast date |
| `forecast_type` | VARCHAR(50) | NOT NULL | Metric code |
| `trend` | DECIMAL(12,4) | | Trend component |
| `yearly_seasonality` | DECIMAL(12,4) | | Yearly pattern |
| `weekly_seasonality` | DECIMAL(12,4) | | Weekly pattern |
| `daily_seasonality` | DECIMAL(12,4) | | Daily pattern |
| `holiday_effects` | JSONB | | Holiday contributions |
| `regressor_effects` | JSONB | | External regressor effects |

**Populated By:** Prophet forecasting job

---

#### `xgboost_explanations`

XGBoost SHAP value explanations.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `run_id` | UUID | | Forecast run ID |
| `forecast_date` | DATE | NOT NULL | Forecast date |
| `forecast_type` | VARCHAR(50) | NOT NULL | Metric code |
| `base_value` | DECIMAL(12,4) | | SHAP base value |
| `feature_values` | JSONB | | Input feature values |
| `shap_values` | JSONB | | SHAP values per feature |
| `top_positive` | JSONB | | Top positive contributors |
| `top_negative` | JSONB | | Top negative contributors |
| `generated_at` | TIMESTAMP | DEFAULT NOW() | Generation time |

**JSONB Structure:**
```json
{
  "shap_values": {
    "day_of_week": 2.5,
    "is_weekend": 3.0,
    "lag_7": -1.2
  },
  "top_positive": ["is_weekend", "day_of_week"],
  "top_negative": ["lag_7"]
}
```

**Populated By:** XGBoost forecasting job with SHAP

---

#### `pickup_explanations`

Pickup model forecast explanations.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `run_id` | UUID | | Forecast run ID |
| `forecast_date` | DATE | NOT NULL | Forecast date |
| `forecast_type` | VARCHAR(50) | NOT NULL | Metric code |
| `current_otb` | DECIMAL(12,2) | | Current on-the-books |
| `days_out` | INTEGER | | Days until arrival |
| `comparison_date` | DATE | | Prior year comparison date |
| `comparison_otb` | DECIMAL(12,2) | | Prior year OTB at same lead |
| `comparison_final` | DECIMAL(12,2) | | Prior year final value |
| `pickup_curve_pct` | DECIMAL(8,4) | | Expected remaining pickup % |
| `pickup_curve_stddev` | DECIMAL(8,4) | | Pickup curve std deviation |
| `pace_vs_prior_pct` | DECIMAL(8,4) | | Current vs prior year pace |
| `projection_method` | VARCHAR(50) | | Method used (additive) |
| `projected_value` | DECIMAL(12,2) | | Final projection |
| `confidence_note` | TEXT | | Human-readable confidence |

**Populated By:** Pickup forecasting job

---

### Logging

#### `sync_log`

Data synchronization audit log.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `sync_type` | VARCHAR(30) | NOT NULL | Sync type (bookings, revenue, etc.) |
| `source` | VARCHAR(20) | NOT NULL | Data source (newbook, resos) |
| `started_at` | TIMESTAMP | NOT NULL | Start time |
| `completed_at` | TIMESTAMP | | Completion time |
| `status` | VARCHAR(20) | NOT NULL | Status (started, completed, failed) |
| `records_fetched` | INTEGER | | Records from API |
| `records_created` | INTEGER | | New records |
| `records_updated` | INTEGER | | Updated records |
| `date_from` | DATE | | Query start date |
| `date_to` | DATE | | Query end date |
| `error_message` | TEXT | | Error details if failed |
| `triggered_by` | VARCHAR(100) | | Who/what triggered sync |

**Populated By:** All sync operations

**Used By:** Sync status display, debugging

---

#### `special_dates`

Custom holidays/events for forecasting models.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-increment ID |
| `name` | VARCHAR(100) | NOT NULL | Holiday/event name |
| `pattern_type` | VARCHAR(20) | NOT NULL | fixed, nth_weekday, relative_to_date |
| `fixed_month` | INTEGER | | Month for fixed pattern (1-12) |
| `fixed_day` | INTEGER | | Day for fixed pattern (1-31) |
| `nth_week` | INTEGER | | Week number (1-5 or -1 for last) |
| `weekday` | INTEGER | | Day of week (0=Mon, 6=Sun) |
| `month` | INTEGER | | Month for nth_weekday |
| `relative_to_month` | INTEGER | | Reference month |
| `relative_to_day` | INTEGER | | Reference day |
| `relative_weekday` | INTEGER | | Target weekday |
| `relative_direction` | VARCHAR(10) | | before or after |
| `duration_days` | INTEGER | DEFAULT 1 | Event duration |
| `is_recurring` | BOOLEAN | DEFAULT TRUE | Repeats yearly |
| `one_off_year` | INTEGER | | Year for non-recurring |
| `is_active` | BOOLEAN | DEFAULT TRUE | Include in forecasts |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Creation time |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | Last update |

**Pattern Type Examples:**
- `fixed`: Christmas (Dec 25)
- `nth_weekday`: Thanksgiving (4th Thursday of November)
- `relative_to_date`: Good Friday (Friday before Easter Sunday)

**Populated By:** Settings UI special dates management

**Used By:** Prophet holiday effects, XGBoost features

---

## Indices Summary

| Table | Index | Columns |
|-------|-------|---------|
| newbook_gl_accounts | idx_gl_accounts_department | department |
| newbook_gl_accounts | idx_gl_accounts_group | gl_group_name |
| newbook_bookings_data | idx_bookings_arrival | arrival_date |
| newbook_bookings_data | idx_bookings_status | status |
| newbook_bookings_data | idx_bookings_placed | booking_placed |
| newbook_earned_revenue_data | idx_earned_revenue_data_date | date |
| newbook_earned_revenue_data | idx_earned_revenue_data_type | date, revenue_type |
| newbook_net_revenue_data | idx_net_revenue_data_date | date |
| newbook_occupancy_report_data | idx_occupancy_report_data_date | date |
| newbook_bookings_stats | idx_bookings_stats_date | date |
| newbook_booking_pace | idx_booking_pace_arrival | arrival_date |
| daily_metrics | idx_daily_metrics_date | date |
| daily_metrics | idx_daily_metrics_code | metric_code, date |
| forecasts | idx_forecasts_date | forecast_date |
| forecasts | idx_forecasts_type | forecast_type, model_type |
| forecasts | idx_forecasts_generated | generated_at DESC |
| actual_vs_forecast | idx_actual_vs_forecast_date | date |
| actual_vs_forecast | idx_actual_vs_forecast_type | metric_type |
| daily_budgets | idx_daily_budgets_date | date |
| forecast_snapshots | idx_forecast_snapshots_target | target_date |

---

## Data Flow

```
External APIs (Newbook, Resos)
         │
         ▼
    Raw Data Tables
    (bookings_data, earned_revenue_data, etc.)
         │
         ▼
    Aggregation Jobs
         │
         ▼
    Stats Tables
    (bookings_stats, net_revenue_data, booking_pace)
         │
         ▼
    daily_metrics
         │
         ▼
    Forecasting Jobs
         │
         ▼
    forecasts + explanations
         │
         ▼
    Accuracy Calculation
         │
         ▼
    actual_vs_forecast
```

---

## Backup & Maintenance

### Backup

```bash
# Docker backup
docker exec forecasting-db pg_dump -U forecast forecast_data > backup.sql

# Restore
docker exec -i forecasting-db psql -U forecast forecast_data < backup.sql
```

### Common Queries

```sql
-- Check sync status
SELECT source, sync_type, status, completed_at
FROM sync_log
ORDER BY completed_at DESC
LIMIT 10;

-- Check occupancy data coverage
SELECT MIN(date), MAX(date), COUNT(*)
FROM newbook_bookings_stats;

-- Check forecast freshness
SELECT forecast_type, model_type, MAX(generated_at)
FROM forecasts
GROUP BY forecast_type, model_type;

-- Model accuracy comparison
SELECT metric_type,
       AVG(ABS(prophet_pct_error)) as prophet_mape,
       AVG(ABS(xgboost_pct_error)) as xgboost_mape,
       AVG(ABS(pickup_pct_error)) as pickup_mape
FROM actual_vs_forecast
WHERE actual_value IS NOT NULL
GROUP BY metric_type;
```
