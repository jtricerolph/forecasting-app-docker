# API Documentation

## Overview

The Forecasting App API is a RESTful API built with FastAPI. All endpoints require JWT authentication via Bearer token except for `/auth/login` and health checks.

**Base URL:** `/api`

**Authentication:** Bearer token in Authorization header
```
Authorization: Bearer <access_token>
```

---

## Authentication

### POST `/auth/login`

Authenticate user and receive JWT token.

**Request Body:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Errors:**
- `401 Unauthorized` - Invalid credentials

---

### GET `/auth/me`

Get current authenticated user.

**Response:** `200 OK`
```json
{
  "id": 1,
  "username": "admin",
  "display_name": "Administrator",
  "is_active": true
}
```

---

### GET `/auth/users`

List all users.

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "username": "admin",
    "display_name": "Administrator",
    "is_active": true,
    "created_at": "2024-01-01T00:00:00"
  }
]
```

---

### POST `/auth/users`

Create new user.

**Request Body:**
```json
{
  "username": "string",
  "password": "string",
  "display_name": "string (optional)"
}
```

**Response:** `200 OK`
```json
{
  "id": 2,
  "username": "newuser",
  "display_name": "New User",
  "is_active": true,
  "created_at": "2024-01-15T10:30:00"
}
```

---

### DELETE `/auth/users/{user_id}`

Delete user by ID.

**Response:** `200 OK`
```json
{
  "status": "deleted"
}
```

---

## Forecasts

### GET `/forecast/daily`

Get daily forecasts with all models side-by-side.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_date` | date | No | today | Start date (YYYY-MM-DD) |
| `to_date` | date | No | +14 days | End date (YYYY-MM-DD) |
| `metric` | string | No | all | Filter by metric code |
| `model` | string | No | all | Filter by model: prophet, xgboost, pickup, catboost |

**Response:** `200 OK`
```json
[
  {
    "date": "2024-01-15",
    "metric_code": "hotel_occupancy_pct",
    "metric_name": "Hotel Occupancy %",
    "prophet_value": 78.5,
    "prophet_lower": 72.0,
    "prophet_upper": 85.0,
    "xgboost_value": 76.2,
    "pickup_value": 80.0,
    "current_otb": 65.0,
    "budget_value": 75.0
  }
]
```

---

### GET `/forecast/weekly`

Get weekly summary forecast aggregated by week.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `weeks` | integer | No | 8 | Number of weeks to forecast |

**Response:** `200 OK`
```json
[
  {
    "week_start": "2024-01-15",
    "metric_code": "hotel_occupancy_pct",
    "metric_name": "Hotel Occupancy %",
    "unit": "percent",
    "forecast_value": 78.5,
    "budget_value": 75.0,
    "variance": 3.5,
    "variance_pct": 4.67
  }
]
```

---

### GET `/forecast/comparison`

Get side-by-side comparison of all models for a specific metric.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_date` | date | No | today | Start date |
| `to_date` | date | No | +28 days | End date |
| `metric` | string | **Yes** | - | Metric code to compare |

**Response:** `200 OK`
```json
[
  {
    "date": "2024-01-15",
    "actual": 82.0,
    "current_otb": 75.0,
    "budget": 80.0,
    "prior_year_actual": 78.0,
    "prior_year_otb": 70.0,
    "models": {
      "prophet": {
        "value": 79.5,
        "lower": 74.0,
        "upper": 85.0
      },
      "xgboost": {
        "value": 78.0,
        "lower": null,
        "upper": null
      },
      "pickup": {
        "value": 81.0,
        "lower": null,
        "upper": null
      },
      "catboost": {
        "value": 77.5,
        "lower": null,
        "upper": null
      }
    }
  }
]
```

---

### POST `/forecast/regenerate`

Force regenerate forecasts for a date range.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_date` | date | No | today | Start date |
| `to_date` | date | No | +14 days | End date |
| `models` | array | No | all | Models to run: prophet, xgboost, pickup, catboost |

**Response:** `200 OK`
```json
{
  "status": "triggered",
  "from_date": "2024-01-15",
  "to_date": "2024-01-29",
  "models": ["prophet", "xgboost", "pickup", "catboost"],
  "message": "Forecast regeneration started in background"
}
```

---

### GET `/forecast/metrics`

Get list of all available forecast metrics.

**Response:** `200 OK`
```json
[
  {
    "metric_code": "hotel_occupancy_pct",
    "metric_name": "Hotel Occupancy %",
    "category": "hotel",
    "unit": "percent",
    "models": {
      "prophet": true,
      "xgboost": true,
      "pickup": true
    },
    "is_derived": false,
    "display_order": 1
  }
]
```

---

## Data Sync

### GET `/sync/status`

Get last sync times and status for all data sources.

**Response:** `200 OK`
```json
{
  "newbook_bookings": {
    "source": "newbook",
    "sync_type": "bookings",
    "last_sync": "2024-01-15T05:00:00",
    "status": "completed",
    "records_fetched": 150,
    "records_created": 10,
    "date_from": "2024-01-01",
    "date_to": "2024-12-31"
  },
  "newbook_earned_revenue": {
    "source": "newbook",
    "sync_type": "earned_revenue",
    "last_sync": "2024-01-15T05:10:00",
    "status": "completed",
    "records_fetched": 500,
    "records_created": 50
  }
}
```

---

### POST `/sync/newbook`

Trigger manual Newbook booking sync.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `full_sync` | boolean | No | false | Fetch all bookings vs incremental |
| `from_date` | date | No | null | Filter by stay period start |
| `to_date` | date | No | null | Filter by stay period end |

**Response:** `200 OK`
```json
{
  "status": "started",
  "source": "newbook",
  "full_sync": false,
  "from_date": null,
  "to_date": null,
  "message": "Newbook incremental sync started in background"
}
```

---

### POST `/sync/newbook/occupancy-report`

Trigger Newbook occupancy report sync.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_date` | date | No | -90 days | Report start date |
| `to_date` | date | No | +30 days | Report end date |

**Response:** `200 OK`
```json
{
  "status": "started",
  "source": "newbook_occupancy_report",
  "from_date": "2023-10-15",
  "to_date": "2024-02-15",
  "message": "Newbook occupancy report sync started"
}
```

---

### POST `/sync/newbook/earned-revenue`

Trigger Newbook earned revenue sync.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_date` | date | No | -7 days | Revenue start date |
| `to_date` | date | No | today | Revenue end date |

**Response:** `200 OK`
```json
{
  "status": "started",
  "source": "newbook_earned_revenue",
  "from_date": "2024-01-08",
  "to_date": "2024-01-15",
  "message": "Newbook earned revenue sync started"
}
```

---

### POST `/sync/resos`

Trigger Resos restaurant booking sync.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_date` | date | No | -7 days | Booking start date |
| `to_date` | date | No | +365 days | Booking end date |

**Response:** `200 OK`
```json
{
  "status": "started",
  "source": "resos",
  "from_date": "2024-01-08",
  "to_date": "2025-01-15",
  "message": "Resos sync started in background"
}
```

---

### POST `/sync/full`

Trigger full sync from all sources.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `full_sync` | boolean | No | false | Full vs incremental sync |

**Response:** `200 OK`
```json
{
  "status": "started",
  "sources": ["newbook", "newbook_occupancy_report", "resos"],
  "full_sync": false,
  "message": "Full incremental sync started in background"
}
```

---

### POST `/sync/aggregate`

Trigger manual data aggregation.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source` | string | No | all | Filter: newbook, resos |

**Response:** `200 OK`
```json
{
  "status": "started",
  "source": "all",
  "message": "Aggregation started for all sources"
}
```

---

### GET `/sync/aggregate/status`

Get aggregation queue status.

**Response:** `200 OK`
```json
{
  "pending": {
    "total": 5,
    "by_source": {
      "newbook": {
        "count": 3,
        "earliest": "2024-01-10",
        "latest": "2024-01-12"
      }
    }
  },
  "aggregated": {
    "daily_occupancy": {
      "count": 365,
      "earliest": "2023-01-01",
      "latest": "2024-01-15"
    }
  },
  "last_aggregation": "2024-01-15T05:30:00"
}
```

---

## Historical Data

### GET `/historical/occupancy`

Get historical occupancy data.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_date` | date | No | -30 days | Start date |
| `to_date` | date | No | today | End date |

**Response:** `200 OK`
```json
[
  {
    "date": "2024-01-15",
    "total_rooms": 80,
    "occupied_rooms": 65,
    "occupancy_pct": 81.25,
    "total_guests": 120,
    "total_adults": 100,
    "total_children": 15,
    "total_infants": 5,
    "arrival_count": 20,
    "room_revenue": 12500.00,
    "adr": 192.31,
    "revpar": 156.25,
    "agr": 104.17,
    "by_room_type": {"standard": 40, "deluxe": 25},
    "revenue_by_room_type": {"standard": 6000, "deluxe": 6500}
  }
]
```

---

### GET `/historical/covers`

Get historical restaurant covers data.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_date` | date | No | -30 days | Start date |
| `to_date` | date | No | today | End date |
| `service_period` | string | No | all | Filter: lunch, dinner |

**Response:** `200 OK`
```json
[
  {
    "date": "2024-01-15",
    "service_period": "dinner",
    "total_bookings": 25,
    "total_covers": 85,
    "avg_party_size": 3.4,
    "hotel_guest_covers": 60,
    "external_covers": 25,
    "dbb_covers": 40,
    "cancelled_bookings": 2,
    "no_show_bookings": 1
  }
]
```

---

### GET `/historical/summary`

Get combined daily summary with occupancy and covers.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_date` | date | No | -30 days | Start date |
| `to_date` | date | No | today | End date |

**Response:** `200 OK`
```json
[
  {
    "date": "2024-01-15",
    "day_of_week": "Mon",
    "total_rooms": 80,
    "available_rooms": 78,
    "occupied_rooms": 65,
    "occupancy_pct": 83.33,
    "total_guests": 120,
    "room_revenue": 12500.00,
    "adr": 192.31,
    "revpar": 160.26,
    "lunch_covers": 45,
    "dinner_covers": 85,
    "lunch_bookings": 15,
    "dinner_bookings": 25
  }
]
```

---

## Accuracy

### GET `/accuracy/summary`

Get model accuracy comparison over date range.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `from_date` | date | **Yes** | Start date |
| `to_date` | date | **Yes** | End date |

**Response:** `200 OK`
```json
[
  {
    "metric_type": "hotel_occupancy_pct",
    "sample_count": 30,
    "prophet": {
      "mae": 3.5,
      "rmse": 4.2,
      "mape": 4.8,
      "wins": 12
    },
    "xgboost": {
      "mae": 3.8,
      "rmse": 4.5,
      "mape": 5.1,
      "wins": 8
    },
    "catboost": {
      "mae": 3.6,
      "rmse": 4.3,
      "mape": 4.9,
      "wins": 6
    },
    "pickup": {
      "mae": 3.2,
      "rmse": 3.9,
      "mape": 4.3,
      "wins": 4
    }
  }
]
```

---

### GET `/accuracy/by-model`

Get detailed accuracy for a specific model.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | **Yes** | Model: prophet, xgboost, catboost, pickup |
| `from_date` | date | **Yes** | Start date |
| `to_date` | date | **Yes** | End date |
| `metric_type` | string | No | Filter by metric |

**Response:** `200 OK`
```json
[
  {
    "date": "2024-01-15",
    "metric_type": "hotel_occupancy_pct",
    "actual": 82.0,
    "forecast": 79.5,
    "error": -2.5,
    "pct_error": -3.05,
    "was_best": true
  }
]
```

---

### GET `/accuracy/by-lead-time`

Get accuracy aggregated by forecast lead time.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_date` | date | No | -365 days | Start date |
| `to_date` | date | No | today | End date |
| `metric_code` | string | No | all | Filter by metric |

**Response:** `200 OK`
```json
[
  {
    "lead_time": "1 week",
    "model": "prophet",
    "metric_code": "hotel_occupancy_pct",
    "mape": 3.5,
    "mae": 2.8,
    "sample_count": 52
  },
  {
    "lead_time": "1 month",
    "model": "prophet",
    "metric_code": "hotel_occupancy_pct",
    "mape": 5.2,
    "mae": 4.1,
    "sample_count": 12
  }
]
```

---

### GET `/accuracy/best-model`

Analyze which model performs best by metric and time period.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `from_date` | date | **Yes** | Start date |
| `to_date` | date | **Yes** | End date |

**Response:** `200 OK`
```json
[
  {
    "metric_type": "hotel_occupancy_pct",
    "week": "2024-01-08",
    "best_model": "pickup",
    "count": 4,
    "percentage": 57.1
  }
]
```

---

## Configuration

### GET `/config/settings/newbook`

Get Newbook integration settings.

**Response:** `200 OK`
```json
{
  "newbook_api_key": null,
  "newbook_api_key_set": true,
  "newbook_username": "api_user",
  "newbook_password_set": true,
  "newbook_region": "au"
}
```

---

### POST `/config/settings/newbook`

Update Newbook settings.

**Request Body:**
```json
{
  "newbook_api_key": "string (optional)",
  "newbook_username": "string (optional)",
  "newbook_password": "string (optional)",
  "newbook_region": "string (optional)"
}
```

**Response:** `200 OK`
```json
{
  "status": "saved",
  "message": "Newbook settings updated"
}
```

---

### POST `/config/settings/newbook/test`

Test Newbook connection with current settings.

**Response:** `200 OK`
```json
{
  "status": "success",
  "message": "Connection successful"
}
```

---

### GET `/config/room-categories`

Get all room categories.

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "site_id": "56",
    "site_name": "Standard Room",
    "site_type": "Standard Room",
    "room_count": 40,
    "is_included": true,
    "display_order": 1
  }
]
```

---

### POST `/config/room-categories/fetch`

Fetch room categories from Newbook API.

**Response:** `200 OK`
```json
{
  "status": "success",
  "count": 5,
  "message": "Updated 5 room categories (80 total rooms from API)"
}
```

---

### PATCH `/config/room-categories/bulk-update`

Bulk update room category inclusion flags.

**Request Body:**
```json
{
  "updates": [
    {"id": 1, "is_included": true},
    {"id": 2, "is_included": false}
  ]
}
```

**Response:** `200 OK`
```json
{
  "status": "updated",
  "count": 2
}
```

---

### GET `/config/gl-accounts`

Get all GL accounts with department mappings.

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "gl_account_id": "4010",
    "gl_code": "4010",
    "gl_name": "Room Revenue",
    "gl_group_name": "Accommodation",
    "department": "accommodation",
    "is_active": true
  }
]
```

---

### POST `/config/gl-accounts/fetch`

Fetch GL accounts from Newbook earned revenue data.

**Response:** `200 OK`
```json
{
  "status": "success",
  "count": 25,
  "message": "Discovered 25 GL accounts from revenue data"
}
```

---

### PATCH `/config/gl-accounts/bulk-update`

Bulk update GL account department mappings.

**Request Body:**
```json
{
  "updates": [
    {"id": 1, "department": "accommodation"},
    {"id": 2, "department": "dry"},
    {"id": 3, "department": "wet"}
  ]
}
```

**Response:** `200 OK`
```json
{
  "status": "updated",
  "count": 3
}
```

---

## Special Dates

### GET `/settings/special-dates`

Get all configured special dates/holidays.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `active_only` | boolean | No | true | Only return active dates |

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "name": "Christmas Day",
    "pattern_type": "fixed",
    "fixed_month": 12,
    "fixed_day": 25,
    "duration_days": 1,
    "is_recurring": true,
    "is_active": true,
    "created_at": "2024-01-01T00:00:00"
  },
  {
    "id": 2,
    "name": "Spring Bank Holiday",
    "pattern_type": "nth_weekday",
    "nth_week": -1,
    "weekday": 0,
    "month": 5,
    "duration_days": 1,
    "is_recurring": true,
    "is_active": true
  }
]
```

---

### POST `/settings/special-dates`

Create new special date.

**Request Body:**
```json
{
  "name": "Valentine's Day",
  "pattern_type": "fixed",
  "fixed_month": 2,
  "fixed_day": 14,
  "duration_days": 1,
  "is_recurring": true,
  "is_active": true
}
```

**Pattern Types:**
- `fixed` - Fixed date each year (requires `fixed_month`, `fixed_day`)
- `nth_weekday` - Nth weekday of month (requires `nth_week`, `weekday`, `month`)
- `relative_to_date` - Weekday relative to fixed date

**Response:** `200 OK`
```json
{
  "id": 3,
  "name": "Valentine's Day",
  "pattern_type": "fixed",
  "fixed_month": 2,
  "fixed_day": 14,
  "duration_days": 1,
  "is_recurring": true,
  "is_active": true,
  "created_at": "2024-01-15T10:30:00"
}
```

---

### PUT `/settings/special-dates/{id}`

Update special date.

**Request Body:** Same as POST

**Response:** `200 OK`
```json
{
  "id": 3,
  "name": "Valentine's Day Weekend",
  "pattern_type": "fixed",
  "fixed_month": 2,
  "fixed_day": 14,
  "duration_days": 3,
  "is_recurring": true,
  "is_active": true,
  "created_at": "2024-01-15T10:30:00"
}
```

---

### DELETE `/settings/special-dates/{id}`

Delete special date.

**Response:** `200 OK`
```json
{
  "status": "deleted"
}
```

---

### GET `/settings/special-dates/resolve`

Resolve special dates for a year to actual dates.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `year` | integer | No | current | Year to resolve |

**Response:** `200 OK`
```json
[
  {
    "name": "Christmas Day",
    "date": "2024-12-25",
    "day_of_week": "Wed"
  },
  {
    "name": "Spring Bank Holiday",
    "date": "2024-05-27",
    "day_of_week": "Mon"
  }
]
```

---

## Budget

Budget management for revenue targets. Upload monthly budgets from FD spreadsheets and distribute to daily values for forecast comparison.

### GET `/budget/monthly`

Get monthly budgets for a year.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `year` | integer | **Yes** | Year to get budgets for |
| `budget_type` | string | No | Filter by type (net_accom, net_dry, net_wet) |

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "year": 2025,
    "month": 1,
    "budget_type": "net_accom",
    "budget_value": 150000.00,
    "notes": null,
    "created_at": "2024-01-15T10:00:00",
    "updated_at": "2024-01-15T10:00:00"
  }
]
```

---

### POST `/budget/monthly`

Create or update a single monthly budget entry.

**Request Body:**
```json
{
  "year": 2025,
  "month": 1,
  "budget_type": "net_accom",
  "budget_value": 150000.00,
  "notes": "Optional notes"
}
```

**Response:** `200 OK`
```json
{
  "id": 1,
  "status": "saved",
  "year": 2025,
  "month": 1,
  "budget_type": "net_accom",
  "budget_value": 150000.00
}
```

---

### GET `/budget/daily`

Get daily distributed budget values for a date range.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `from_date` | date | **Yes** | Start date (YYYY-MM-DD) |
| `to_date` | date | **Yes** | End date (YYYY-MM-DD) |
| `budget_type` | string | No | Filter by type (net_accom, net_dry, net_wet) |

**Response:** `200 OK`
```json
[
  {
    "date": "2025-01-01",
    "budget_type": "net_accom",
    "budget_value": 4838.71,
    "distribution_method": "dow_aligned",
    "prior_year_pct": 0.032258
  }
]
```

---

### POST `/budget/distribute`

Distribute monthly budget to daily values using prior year patterns with DOW alignment (364-day offset).

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `year` | integer | **Yes** | Year to distribute |
| `month` | integer | **Yes** | Month (1-12) |
| `budget_type` | string | No | Specific type, or all if not specified |

**Response:** `200 OK`
```json
{
  "status": "distributed",
  "year": 2025,
  "month": 1,
  "budget_type": "all",
  "days_distributed": 93
}
```

---

### POST `/budget/upload`

Upload budget spreadsheet (CSV or Excel) in bulk format.

**Expected Format:**
```
Type    | 01/25   | 02/25   | 03/25   | ...
accom   | 150000  | 145000  | 160000  | ...
dry     | 45000   | 42000   | 48000   | ...
wet     | 35000   | 32000   | 38000   | ...
```

**Request:** Multipart form with file
- Accepts `.csv`, `.xlsx`, `.xls` files
- Row labels: `accom` (or `accommodation`), `dry` (or `food`), `wet` (or `beverage`)
- Month headers: `mm/yy` format (e.g., `01/25`, `02/25`)

**Response:** `200 OK`
```json
{
  "status": "success",
  "filename": "budget_2025.xlsx",
  "records_created": 24,
  "records_updated": 12,
  "total_records": 36,
  "errors": null
}
```

**Errors:**
- `400 Bad Request` - Invalid file type or format
- `400 Bad Request` - No valid month headers found

---

### GET `/budget/template`

Download empty budget template Excel file.

**Response:** Excel file download (`budget_template_2025.xlsx`)

Pre-filled with:
- Row labels: accom, dry, wet
- Month headers for current and next year

---

### GET `/budget/variance`

Get forecast vs budget vs actual variance comparison.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `from_date` | date | **Yes** | Start date |
| `to_date` | date | **Yes** | End date |

**Response:** `200 OK`
```json
[
  {
    "date": "2025-01-15",
    "budget_type": "net_accom",
    "budget": 5000.00,
    "forecast": 5200.00,
    "actual": 5150.00,
    "forecast_vs_budget": 200.00,
    "forecast_vs_budget_pct": 4.00,
    "actual_vs_budget": 150.00,
    "actual_vs_budget_pct": 3.00
  }
]
```

---

## Export

### GET `/export/forecasts`

Export forecast data as CSV.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_date` | date | No | today | Start date |
| `to_date` | date | No | +30 days | End date |
| `format` | string | No | csv | Export format: csv, json |

**Response:** CSV file download

---

### GET `/export/historical`

Export historical data as CSV.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_date` | date | No | -365 days | Start date |
| `to_date` | date | No | today | End date |

**Response:** CSV file download

---

## Explain

### GET `/explain/prophet/{date}`

Get Prophet forecast decomposition for a date.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `metric` | string | **Yes** | Metric code |

**Response:** `200 OK`
```json
{
  "date": "2024-01-15",
  "metric": "hotel_occupancy_pct",
  "trend": 72.5,
  "yearly_seasonality": 5.2,
  "weekly_seasonality": 1.8,
  "holiday_effects": {
    "Christmas": 3.5
  }
}
```

---

### GET `/explain/xgboost/{date}`

Get XGBoost SHAP explanations for a date.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `metric` | string | **Yes** | Metric code |

**Response:** `200 OK`
```json
{
  "date": "2024-01-15",
  "metric": "hotel_occupancy_pct",
  "base_value": 75.0,
  "predicted_value": 82.0,
  "shap_values": {
    "day_of_week": 2.5,
    "is_weekend": 3.0,
    "prior_year": 1.5
  },
  "top_positive": ["is_weekend", "prior_year"],
  "top_negative": ["month"]
}
```

---

### GET `/explain/pickup/{date}`

Get Pickup model explanation for a date.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `metric` | string | **Yes** | Metric code |

**Response:** `200 OK`
```json
{
  "date": "2024-01-15",
  "metric": "hotel_occupancy_pct",
  "current_otb": 65.0,
  "days_out": 7,
  "comparison_date": "2023-01-16",
  "comparison_otb": 60.0,
  "comparison_final": 82.0,
  "pickup_curve_pct": 73.2,
  "pace_vs_prior_pct": 108.3,
  "projected_value": 88.8,
  "projection_method": "additive",
  "confidence_note": "Pace ahead of prior year"
}
```

---

## Health Checks

### GET `/health`

Basic health check.

**Response:** `200 OK`
```json
{
  "status": "healthy"
}
```

---

### GET `/health/db`

Database connectivity check.

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "database": "connected"
}
```

---

## Error Responses

All endpoints return errors in this format:

```json
{
  "detail": "Error message description"
}
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Invalid/missing token |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Resource doesn't exist |
| 422 | Validation Error - Invalid parameters |
| 500 | Internal Server Error |

---

## Bookability

Rate availability matrix and rack rate management. Prefix: `/bookability`

### GET `/bookability/rate-matrix`

Get rate matrix showing Newbook rack rates per category and date.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_date` | date | No | today | Start date |
| `to_date` | date | No | +30 days | End date |

**Response:** `200 OK`
```json
{
  "categories": [
    {
      "category_id": "1",
      "category_name": "Standard Room",
      "room_count": 16
    }
  ],
  "dates": ["2025-03-01", "2025-03-02"],
  "matrix": {
    "1": {
      "2025-03-01": {
        "rate_gross": 150.00,
        "rate_net": 125.00,
        "tariffs": [
          {
            "name": "Best Available",
            "rate": 150.00,
            "available": true,
            "min_stay": null,
            "available_for_min_stay": null
          }
        ],
        "occupancy": {
          "available": 16,
          "occupied": 10,
          "maintenance": 0
        },
        "snapshot_time": "2025-03-01T05:20:00"
      }
    }
  }
}
```

---

### GET `/bookability/rate-matrix/summary`

Get summary statistics for the rate matrix.

**Query Parameters:** Same as rate-matrix

**Response:** `200 OK`
```json
{
  "totalDates": 31,
  "totalCategories": 3,
  "unbookableDateCategories": 5,
  "totalIssues": 5
}
```

---

### GET `/bookability/rate-history/{category_id}/{rate_date}`

Get rate change history for a specific category and date.

**Response:** `200 OK` - Array of rate snapshots ordered by valid_from.

---

### GET `/bookability/rate-changes`

Get recent rate changes across all categories.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `days` | integer | No | 7 | Look back period |

---

### POST `/bookability/refresh-rates`

Trigger a full refresh of all Newbook rack rates. Runs in background.

**Response:** `200 OK`
```json
{
  "status": "success",
  "message": "Rates refresh completed"
}
```

---

### POST `/bookability/refresh-date/{rate_date}`

Trigger a refresh of rates for a single date. Runs in background.

**Response:** `200 OK`
```json
{
  "status": "queued",
  "date": "2025-03-15",
  "message": "Refreshing rates for 2025-03-15"
}
```

---

## Competitor Rates

Booking.com competitor rate scraping and comparison. Prefix: `/competitor-rates`

### GET `/competitor-rates/status`

Get scraper status (enabled/paused/blocked).

**Response:** `200 OK`
```json
{
  "enabled": true,
  "paused": false,
  "pause_until": null,
  "location_configured": true,
  "location_name": "Grasmere",
  "last_scrape": "2025-03-01T05:30:00"
}
```

---

### POST `/competitor-rates/config/location`

Configure scrape location.

**Request Body:**
```json
{
  "location_name": "Grasmere",
  "pages_to_scrape": 2,
  "adults": 2
}
```

---

### POST `/competitor-rates/config/enable`

Enable or disable the scraper.

**Request Body:**
```json
{ "enabled": true }
```

---

### POST `/competitor-rates/config/unpause`

Unpause the scraper after a block.

---

### POST `/competitor-rates/scrape`

Trigger a manual scrape for a date range.

**Request Body:**
```json
{
  "from_date": "2025-03-01",
  "to_date": "2025-03-07"
}
```

---

### GET `/competitor-rates/hotels`

List all tracked competitor hotels.

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "name": "Hotel Name",
    "tier": "competitor",
    "display_order": 1,
    "star_rating": 4,
    "review_score": 8.5,
    "booking_com_url": "https://...",
    "is_active": true
  }
]
```

---

### PUT `/competitor-rates/hotels/{hotel_id}/tier`

Update a hotel's tier classification.

**Request Body:**
```json
{ "tier": "competitor" }
```

Valid tiers: `own`, `competitor`, `market`

---

### GET `/competitor-rates/matrix`

Get competitor rate comparison matrix.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_date` | date | Yes | - | Start date |
| `to_date` | date | Yes | - | End date |
| `include_market` | boolean | No | false | Include market-tier hotels |

**Response:** `200 OK`
```json
{
  "dates": ["2025-03-01", "2025-03-02"],
  "hotels": [{"id": 1, "name": "Hotel", "tier": "own", "star_rating": 4}],
  "rates": {
    "1": {
      "2025-03-01": {
        "availability_status": "available",
        "rate_gross": 150.00,
        "room_type": "Standard Double",
        "breakfast_included": true,
        "free_cancellation": true,
        "rooms_left": 3,
        "scraped_at": "2025-03-01T05:30:00"
      }
    }
  }
}
```

---

### GET `/competitor-rates/parity`

Get rate parity comparison between own rack rates and Booking.com rates.

---

### GET `/competitor-rates/parity/alerts`

Get rate parity alerts.

---

### GET `/competitor-rates/queue-status`

Get current scrape queue status (pending, completed, failed counts).

---

### GET `/competitor-rates/schedule-info`

Get scraping schedule information (daily time, tier breakdown, date counts).

---

### GET `/competitor-rates/scrape-coverage`

Get 365-day scrape coverage showing freshness per date.

---

### GET `/competitor-rates/booking-availability`

Get own hotel's Booking.com availability for a date range.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_date` | date | No | today | Start date |
| `to_date` | date | No | +30 days | End date |

---

### GET `/competitor-rates/scrape-history`

Get scrape batch history.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 20 | Max results |

---

## Rate Limiting

No rate limiting is currently implemented. Background sync operations are queued to prevent overload.

---

## Pagination

Large list endpoints do not currently implement pagination. Consider adding `limit` and `offset` parameters for large datasets.
