# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hotel forecasting application with React frontend, FastAPI backend, and PostgreSQL database. Integrates with Newbook PMS, Resos restaurant booking systems, and Booking.com rate scraping. All external API integrations are **READ-ONLY** - never make write operations to production systems.

## Commands

```bash
# Start all services
docker-compose up -d

# Rebuild after code changes (backend auto-reloads, frontend needs rebuild)
docker-compose up -d --build backend
docker-compose up -d --build frontend

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Database backup/restore
docker exec forecasting-db pg_dump -U forecast forecast_data > backup.sql
docker exec -i forecasting-db psql -U forecast forecast_data < backup.sql

# Frontend development (if running outside Docker)
cd frontend && npm install && npm run dev

# Backend tests (inside container)
docker exec -it forecasting-backend pytest
```

## Access Points

- Frontend: http://localhost:3081
- Backend API: http://localhost:8001
- Swagger Docs: http://localhost:8001/docs
- Adminer (DB): http://localhost:8082
- Default login: admin / admin123

## Architecture

### Data Flow
```
Newbook/Resos APIs → Raw Data Tables → Aggregation Jobs → daily_metrics → Forecasting Models → forecasts table
                                                                                              ↓
                                                              actual_vs_forecast ← Accuracy Calculation

Newbook Rates API → newbook_current_rates → Bookability Rate Matrix
Booking.com Scraper → booking_com_rates → Competitor Rates Matrix
```

### Forecasting Models (backend/services/forecasting/)
- **Prophet**: Time series with seasonality, holidays, trend detection. Outputs confidence intervals.
- **XGBoost/CatBoost**: Gradient boosting with engineered features (DOW, month, lags, rolling averages).
- **Pickup**: Hotel industry pace model using booking lead-time snapshots from `newbook_booking_pace` table.
- **Pickup v2**: Enhanced pickup model with confidence shading using rack rate upper bounds from `newbook_current_rates`.
- **Blended**: Weighted combination of models based on historical accuracy.

### API Modules (backend/api/)
- `forecast.py` - Forecast data endpoints
- `sync_bookings.py` - Newbook data sync (bookings, occupancy, revenue, rates)
- `bookability.py` - Rate matrix, tariff availability, single-date refresh
- `competitor_rates.py` - Booking.com scraper management, competitor rate matrix
- `config.py`, `accuracy.py`, `budget.py`, `explain.py` - System config, model accuracy, budgets, explainability

### Services (backend/services/)
- `newbook_client.py` - Newbook PMS API (bookings, occupancy, revenue)
- `newbook_rates_client.py` - Newbook Rates API (rack rates, tariff availability, multi-night verification)
- `booking_scraper.py` - Booking.com rate scraper with queue-based processing
- `scraper_backends/` - Scraper backend implementations
- `resos_client.py` - Resos restaurant booking API
- `forecasting/` - ML model implementations

### Scheduled Jobs (backend/jobs/)
Jobs run via APScheduler configured in `scheduler.py`. Main jobs:
- `data_sync.py` - Fetch data from Newbook/Resos (05:00-05:15)
- `aggregation.py`, `bookings_aggregation.py` - Calculate daily stats
- `fetch_current_rates.py` - Fetch Newbook rack rates for 720 days (05:20)
- `scrape_booking_rates.py` - Booking.com competitor rate scraping (configurable, default 05:30)
- `pace_snapshot_v2.py` - Enhanced booking pace snapshots
- `forecast_daily.py` - Run all enabled models (06:00)
- `accuracy_calc.py` - Compare forecasts to actuals
- `weekly_forecast_snapshot.py` - Weekly forecast snapshots

### Key Tables
- `newbook_bookings_data` - Raw booking records
- `newbook_bookings_stats` - Daily aggregated occupancy stats
- `newbook_booking_pace` - Lead-time snapshots (d365 through d0)
- `newbook_current_rates` - Rack rates from Newbook (snapshot model, 720-day horizon)
- `daily_metrics` - Training data for models
- `forecasts` - Model predictions
- `actual_vs_forecast` - Accuracy tracking with per-model errors
- `booking_com_hotels` - Competitor hotel configuration (own, competitor, market tiers)
- `booking_com_rates` - Scraped competitor rates
- `booking_scrape_queue` - Priority-based scrape queue (high/medium/low tiers)

## Development Notes

- Frontend styling should match the Kitchen Flash Invoice app design system (see `frontend/src/utils/theme.ts`)
- Reference Kitchen Flash app for API request/response formatting when uncertain
- Don't guess API field names - check actual Newbook/Resos responses or evaluate sample data
- Prophet requires sync database access (see `database.py` for `sync_engine` usage)
- Container rebuilds happen automatically when needed - check logs without asking
- Frontend is served from Docker nginx container - `npm run build` alone won't update it, must rebuild the container
- Windows bash paths use Unix-style in Git Bash: `/c/Users/...` not `c:\Users\...`

## Documentation

Detailed docs in `/docs`:
- [FRONTEND.md](docs/FRONTEND.md) - React components, routing, theme
- [BACKEND.md](docs/BACKEND.md) - FastAPI, services, jobs, auth
- [API.md](docs/API.md) - All endpoints
- [DATABASE.md](docs/DATABASE.md) - Schema, tables, data flow
