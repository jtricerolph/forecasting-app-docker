# Backend Documentation

## Overview

The backend is a FastAPI-based Python application that provides REST APIs for forecasting, data synchronization, and system configuration. It integrates with external systems (Newbook PMS, Resos) and implements multiple ML forecasting models.

## Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| FastAPI | 0.109.0 | Async web framework |
| Uvicorn | 0.27.0 | ASGI server |
| SQLAlchemy | 2.0.25 | ORM (async support) |
| PostgreSQL | 15+ | Database |
| asyncpg | 0.29.0 | Async PostgreSQL driver |
| Prophet | 1.1.4 | Time series forecasting |
| XGBoost | 2.0.3 | Gradient boosting |
| CatBoost | 1.2.7 | Gradient boosting alternative |
| Chronos | 1.4.1 | Transformer-based forecasting |
| APScheduler | 3.10.4 | Job scheduling |
| SHAP | 0.44.1 | Model explainability |
| pandas | 2.2.0 | Data manipulation |
| PyTorch | 2.0+ (CPU) | Deep learning framework |

## Project Structure

```
backend/
├── main.py                 # FastAPI app setup, routers, lifespan
├── database.py             # SQLAlchemy engine & session config
├── auth.py                 # JWT authentication
├── scheduler.py            # APScheduler job configuration
├── api/                    # API endpoint modules
│   ├── forecast.py         # Forecast data endpoints
│   ├── sync.py             # Data synchronization
│   ├── sync_bookings.py    # Booking sync (bookings, occupancy, revenue, rates)
│   ├── bookability.py      # Rate matrix, tariff availability, single-date refresh
│   ├── competitor_rates.py # Booking.com scraper management, competitor matrix
│   ├── config.py           # System configuration
│   ├── accuracy.py         # Model accuracy metrics
│   ├── backtest.py         # Backtesting operations
│   ├── budget.py           # Budget management
│   ├── evolution.py        # Forecast evolution tracking
│   ├── explain.py          # Model interpretability
│   ├── export.py           # Data export
│   ├── historical.py       # Historical data queries
│   ├── crossref.py         # Cross-reference data
│   ├── reports.py          # Report generation
│   ├── backup.py           # Database backup/restore
│   ├── resos_sync.py       # Resos data sync
│   ├── public.py           # Public endpoints (health, etc.)
│   └── special_dates.py    # Holiday/event configuration
├── services/               # Business logic
│   ├── forecasting/        # ML model implementations
│   │   ├── prophet_model.py
│   │   ├── xgboost_model.py
│   │   ├── catboost_model.py
│   │   ├── pickup_model.py
│   │   ├── pickup_v2_model.py  # Enhanced pickup with rate-based confidence
│   │   ├── blended_model.py    # Weighted model ensemble
│   │   ├── covers_model.py     # Restaurant covers forecasting
│   │   ├── chronos_model.py
│   │   ├── historical_forecast.py
│   │   ├── backtest.py
│   │   └── budget_service.py
│   ├── newbook_client.py       # Newbook PMS API (bookings, occupancy, revenue)
│   ├── newbook_rates_client.py # Newbook Rates API (rack rates, tariff availability)
│   ├── booking_scraper.py      # Booking.com rate scraper (queue-based)
│   ├── scraper_backends/       # Scraper backend implementations
│   ├── backup_service.py       # Database backup service
│   └── resos_client.py         # Resos API client
├── jobs/                   # Scheduled background jobs
│   ├── data_sync.py        # External data fetching
│   ├── aggregation.py      # Daily summary calculations
│   ├── forecast_daily.py   # Run forecasting models
│   ├── fetch_current_rates.py  # Newbook rack rates (720-day horizon)
│   ├── scrape_booking_rates.py # Booking.com competitor scraping
│   ├── pickup_snapshot.py  # Booking pace snapshots
│   ├── pace_snapshot_v2.py # Enhanced pace snapshots
│   ├── weekly_forecast_snapshot.py # Weekly forecast snapshots
│   ├── accuracy_calc.py    # Calculate forecast accuracy
│   ├── batch_backtest.py   # Backtesting batches
│   ├── bookings_aggregation.py
│   ├── metrics_aggregation.py
│   ├── revenue_aggregation.py
│   └── resos_aggregation.py    # Resos data aggregation
├── utils/                  # Utilities
│   ├── time_alignment.py   # Date/time alignment
│   └── capacity.py         # Room capacity utilities
├── Dockerfile              # Container build
└── requirements.txt        # Python dependencies
```

## Application Startup

The FastAPI app uses a lifespan context manager for initialization:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting application...")

    # Initialize scheduler
    await init_scheduler()

    yield

    # Shutdown
    logger.info("Shutting down...")
    scheduler.shutdown()
```

## Authentication

### JWT Configuration

```python
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
```

### Password Hashing

Uses bcrypt with 12 rounds:

```python
def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
```

### Auth Dependency

Protected endpoints use the `get_current_user` dependency:

```python
from auth import get_current_user

@router.get("/protected")
async def protected_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return {"user": current_user}
```

## Database Connection

### Async Engine

```python
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://...")

async_engine = create_async_engine(DATABASE_URL, echo=False)

async_session = sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db():
    async with async_session() as session:
        yield session
```

### Sync Engine (for ML jobs)

Some operations require synchronous database access:

```python
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")
sync_engine = create_engine(SYNC_DATABASE_URL)
SyncSessionLocal = sessionmaker(bind=sync_engine)
```

## Forecasting Models

### Prophet Model

Facebook's Prophet for time series forecasting with trend, seasonality, and holiday effects:

```python
# Configuration
model = Prophet(
    yearly_seasonality=True,
    weekly_seasonality=True,
    daily_seasonality=False,
    holidays=custom_holidays_df,
    changepoint_prior_scale=0.05,
    seasonality_prior_scale=10.0,
)

# Features
- Trend detection with changepoints
- Yearly/weekly seasonality
- Holiday effects (special dates)
- Uncertainty intervals (lower/upper bounds)
```

**Output fields:**
- `predicted_value` - Point forecast
- `lower_bound` - Lower 80% interval
- `upper_bound` - Upper 80% interval

### XGBoost Model

Gradient boosting with feature engineering:

```python
# Features engineered:
- day_of_week (0-6)
- month (1-12)
- day_of_month (1-31)
- week_of_year (1-52)
- is_weekend (0/1)
- is_holiday (0/1)
- lag features (lag_7, lag_14, lag_28)
- rolling averages (rolling_7, rolling_14)
- prior year same DOW value

# Model parameters
params = {
    'max_depth': 6,
    'learning_rate': 0.1,
    'n_estimators': 100,
    'min_child_weight': 1,
    'objective': 'reg:squarederror'
}
```

**Output fields:**
- `predicted_value` - Point forecast
- SHAP values for explainability

### CatBoost Model

Alternative gradient boosting with categorical feature handling:

```python
# Similar feature set to XGBoost
# Handles categorical features natively
# Often performs well with less tuning
```

### Pickup Model

Hotel industry pace model using booking lead times:

```python
# Method: Additive pickup
# Uses newbook_booking_pace table with lead time snapshots

# Process:
1. Get current OTB (on-the-books) value
2. Find same DOW from prior year
3. Compare current pace vs prior year pace
4. Project final based on historical pickup patterns

# Output includes:
- projected_value
- current_otb
- prior_year_otb
- prior_year_final
- pace_vs_prior_pct
- confidence_note
```

### Chronos Model

Amazon's transformer-based time series model:

```python
# Uses pre-trained transformer for zero-shot forecasting
# Good for edge cases and small datasets
# Requires PyTorch
```

## Scheduled Jobs

Jobs are managed by APScheduler and configured in `scheduler.py`:

### Data Sync Jobs

| Job | Default Time | Description |
|-----|--------------|-------------|
| `sync_newbook_bookings` | 05:00 | Fetch booking data |
| `sync_newbook_occupancy` | 05:05 | Fetch occupancy report |
| `sync_newbook_revenue` | 05:10 | Fetch earned revenue |
| `sync_resos` | 05:15 | Fetch restaurant bookings |
| `fetch_current_rates` | 05:20 | Fetch Newbook rack rates (720-day horizon) |
| `booking_scrape` | 05:30 | Booking.com competitor rate scraping (configurable) |

### Aggregation Jobs

| Job | Trigger | Description |
|-----|---------|-------------|
| `aggregate_bookings` | After sync | Calculate daily stats |
| `aggregate_revenue` | After sync | Calculate revenue by department |
| `update_metrics` | After aggregation | Update daily_metrics table |

### Forecasting Jobs

| Job | Trigger | Description |
|-----|---------|-------------|
| `run_daily_forecast` | 06:00 | Run all enabled models (0-28 day horizon) |
| `capture_pickup_snapshot` | Daily | Store OTB snapshots |
| `pace_snapshot_v2` | Daily | Enhanced pace snapshots |
| `weekly_forecast_snapshot` | Weekly (Sun) | Weekly forecast snapshots |
| `calculate_accuracy` | Daily | Compare forecasts to actuals |

## External API Clients

### Newbook Client

READ-ONLY integration with Newbook PMS:

```python
class NewbookClient:
    def __init__(self, api_key, username, password, region):
        self.base_url = "https://api.newbook.cloud/rest"

    async def get_bookings(self, from_date, to_date, modified_since=None):
        """Fetch booking data"""

    async def get_occupancy_report(self, from_date, to_date):
        """Fetch official occupancy numbers"""

    async def get_earned_revenue(self, from_date, to_date):
        """Fetch GL-based revenue"""

    async def get_site_list(self):
        """Fetch room categories"""
```

**Important:** The integration is READ-ONLY. No write operations to Newbook.

### Newbook Rates Client

Rack rate and tariff availability from Newbook:

```python
class NewbookRatesClient:
    def __init__(self, api_key, username, password, region, vat_rate):
        self.base_url = "https://api.newbook.cloud/rest"

    async def get_all_categories_single_night_rates(self, from_date, to_date):
        """Fetch rack rates for ALL categories in one API call per date"""

    async def get_multi_night_availability(self, dates_by_nights):
        """Verify multi-night stay availability for tariffs with min_stay > 1"""
```

Key features:
- Optimized batch fetching: all categories in one API call per date
- Multi-night verification for minimum stay tariffs
- Snapshot model: only stores new rows when rates change
- 720-day forecast horizon

### Booking.com Scraper

Queue-based competitor rate scraping:

```python
# Priority tiers (all queued daily):
# - High (priority 10): next 30 days
# - Medium (priority 5): days 31-180
# - Low (priority 2): days 181-365

async def process_queue(db) -> Dict:
    """Process pending items in priority order"""

async def scrape_date(db, rate_date, backend, config, batch_id) -> Dict:
    """Scrape a single date from Booking.com"""
```

Key features:
- Priority-based queue processing
- Anti-blocking with cooldown/pause
- Retry logic (up to 3 attempts)
- Batch tracking with scrape log

### Resos Client

Restaurant booking system integration:

```python
class ResosClient:
    def __init__(self, api_key):
        self.base_url = "https://api.resos.com"

    async def get_bookings(self, from_date, to_date):
        """Fetch restaurant bookings"""
```

## Configuration Management

System configuration is stored in `system_config` table:

```python
async def get_config_value(db, key: str) -> Optional[str]:
    """Get decrypted config value"""

async def set_config_value(db, key: str, value: str, encrypt: bool = False):
    """Set config value, optionally encrypting"""
```

### Sensitive Values

API keys and passwords are encrypted using simple base64 encoding (configurable):

```python
def simple_encrypt(value: str) -> str:
    return base64.b64encode(value.encode()).decode()

def simple_decrypt(value: str) -> str:
    return base64.b64decode(value.encode()).decode()
```

## Background Tasks

Long-running operations use FastAPI's BackgroundTasks:

```python
@router.post("/sync/newbook")
async def trigger_sync(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    background_tasks.add_task(sync_newbook_data)
    return {"status": "started"}
```

## Error Handling

Standardized error responses:

```python
from fastapi import HTTPException

# Client error
raise HTTPException(status_code=400, detail="Invalid date range")

# Auth error
raise HTTPException(status_code=401, detail="Invalid credentials")

# Not found
raise HTTPException(status_code=404, detail="Resource not found")

# Server error
raise HTTPException(status_code=500, detail="Internal error")
```

## Logging

Structured logging throughout:

```python
import logging

logger = logging.getLogger(__name__)

logger.info("Starting sync", extra={"source": "newbook", "type": "bookings"})
logger.warning("Missing data", extra={"date": date_str})
logger.error("Sync failed", exc_info=True)
```

## Health Checks

```python
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/health/db")
async def db_health(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "healthy", "database": "connected"}
```

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

# Install C++ build tools for Prophet (CmdStan)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build CmdStan for Prophet
RUN python -c "from prophet.models import StanBackendEnum; print('Prophet ready')"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Resource Limits

Recommended Docker resource limits:
- CPU: 0.5 - 2.0 cores
- Memory: 512MB - 4GB (Prophet/XGBoost can be memory intensive)

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `JWT_SECRET` | Yes | Secret key for JWT tokens |
| `NEWBOOK_API_KEY` | No | Newbook API key (can be set in UI) |
| `NEWBOOK_USERNAME` | No | Newbook username |
| `NEWBOOK_PASSWORD` | No | Newbook password |
| `NEWBOOK_REGION` | No | Newbook region code |
| `RESOS_API_KEY` | No | Resos API key |

## API Documentation

FastAPI auto-generates OpenAPI documentation:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **OpenAPI JSON:** http://localhost:8000/openapi.json

## Testing

```bash
# Run tests
pytest

# With coverage
pytest --cov=. --cov-report=html
```

## Performance Considerations

1. **Async everywhere** - All database operations are async
2. **Connection pooling** - SQLAlchemy manages connection pool
3. **Background tasks** - Long operations don't block requests
4. **Batch processing** - Large data syncs processed in chunks
5. **Caching** - React Query handles frontend caching

## Security Notes

1. **JWT expiry** - Tokens expire after 24 hours
2. **Password hashing** - bcrypt with 12 rounds
3. **CORS** - Configured for frontend origin only
4. **SQL injection** - SQLAlchemy parameterized queries
5. **Input validation** - Pydantic models validate all input
6. **READ-ONLY** - No write operations to external APIs
