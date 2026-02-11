# Future Enhancements

## Ensemble/Weighted Average Model

Combine predictions from all 3 models into a single "best estimate" forecast.

### Implementation Ideas

1. **Simple Average**: Average all 3 model predictions
   - Easy to implement
   - Works well when models are equally reliable

2. **Weighted by Historical Accuracy**: Weight each model based on recent MAPE
   - Calculate rolling 90-day accuracy for each model
   - Higher accuracy = higher weight
   - Example: Pickup 50%, XGBoost 30%, Prophet 20%

3. **Dynamic Weighting by Horizon**:
   - Short-term (0-7 days): Pickup weighted higher (tracks booking pace)
   - Medium-term (8-28 days): Equal weights
   - Long-term (29+ days): Prophet weighted higher (best for seasonality)

4. **Per-Metric Weighting**: Different models may be better for different metrics
   - Track accuracy by metric_code
   - Occupancy might favor Pickup, Revenue might favor XGBoost

### Dashboard Display
- Show "Ensemble Forecast" as primary number
- Show individual model predictions below for transparency
- Highlight when models diverge significantly (low confidence)

---

## Revenue Data Sources & Forecasting Strategy

Two separate sources of revenue data exist - important to understand which to use when.

### 1. Earned Revenue (GL-Based Actuals)

**Source:** Newbook `reports_earned_revenue` API
**Stored in:** `daily_revenue` (raw GL records), `daily_occupancy.room_revenue` (summed)

- Actual recognized revenue by GL account
- What was actually earned on that date (accounting perspective)
- Used for: Historical analysis, accuracy tracking, model training

**Characteristics:**
- Reflects adjustments, refunds, discounts applied
- Revenue recognition timing (may differ from stay date)
- Aggregated total - no room type breakdown

### 2. Booking Tariffs (Rate-Based)

**Source:** Newbook booking data → `tariffs_quoted[]` array
**Stored in:** `newbook_booking_nights.charge_amount`, `calculated_amount`

- Nightly rate charged per booking
- What was quoted/charged per room per night
- Segmentable by room type (`category_id`)

**Characteristics:**
- Available before stay date (for forecasting)
- Broken down by room category
- May not match final earned revenue (adjustments, etc.)

### When to Use Each

| Use Case | Data Source | Reason |
|----------|-------------|--------|
| **Historical accuracy** | Earned Revenue (GL) | True actuals for comparison |
| **Model training** | Earned Revenue (GL) | Train on what actually happened |
| **Future revenue forecast** | Booking Tariffs | Only data available for future |
| **Category-aware ADR** | Booking Tariffs | Can segment by room type |

### Why Booking Tariffs for Future Forecasts

**Problem with overall ADR:**
- Suite at £400/night, Standard at £150/night
- Historical average ADR = £200
- But if future bookings are ALL standards, using £200 overstates revenue

**Solution - Category-specific rates:**
```sql
-- Calculate ADR by room category for future dates
SELECT
    category_id,
    AVG(charge_amount) as category_adr,
    COUNT(*) as bookings
FROM newbook_booking_nights bn
JOIN newbook_bookings b ON bn.booking_id = b.id
WHERE bn.stay_date >= CURRENT_DATE
GROUP BY category_id
```

**Revenue forecast logic:**
1. Get OTB rooms by category for future date
2. Apply category-specific historical ADR (not overall)
3. Account for available inventory by category
4. Pickup model projects remaining rooms by category

**Example:**
```
Future date: Feb 14
OTB: 15 Standard rooms @ £155 avg = £2,325
OTB: 2 Suites @ £380 avg = £760
Available: 5 Standard, 0 Suite (sold out)
Pickup projects: +3 Standard @ £155 = £465
Forecast revenue: £2,325 + £760 + £465 = £3,550

(vs naive: 20 rooms × £200 overall ADR = £4,000 - WRONG)
```

### Implementation Notes

- `daily_occupancy.room_revenue` = GL actuals (historical)
- Future revenue = sum of `newbook_booking_nights.charge_amount` by category
- Need to track category availability for accurate pickup
- Consider adding `daily_occupancy.room_revenue_booked` for comparison

---

## XGBoost Confidence Intervals (Bootstrapping)

Currently XGBoost only outputs a point prediction. Add uncertainty bounds via bootstrapping.

### How It Works
1. Train multiple XGBoost models (e.g., 100) on random subsamples of data
2. Each model makes a prediction for the forecast date
3. Use the distribution of predictions to get confidence intervals:
   - Lower bound: 10th percentile
   - Upper bound: 90th percentile
   - Central: median or mean

### Benefits
- Shows uncertainty in XGBoost predictions
- Comparable to Prophet's built-in intervals
- Users can see when XGBoost is "confident" vs "uncertain"

---

## XGBoost with OTB Features (Booking-Aware Forecasting)

Currently Prophet/XGBoost only see historical actuals. Since we store `booked_at` timestamps, we can retroactively calculate historical OTB and add it as training features.

### Implementation

1. **Calculate historical OTB for training data**:
   ```sql
   -- For each historical date, calculate what OTB was at various lead times
   SELECT
     stay_date,
     -- OTB at 7 days out
     (SELECT COUNT(*) FROM newbook_bookings
      WHERE arrival_date <= stay_date AND departure_date > stay_date
      AND booked_at < stay_date - INTERVAL '7 days') as otb_7d,
     -- OTB at 14 days out
     (SELECT COUNT(*) FROM newbook_bookings
      WHERE arrival_date <= stay_date AND departure_date > stay_date
      AND booked_at < stay_date - INTERVAL '14 days') as otb_14d,
     actual_value
   FROM daily_metrics
   ```

2. **Add features to XGBoost**:
   - `otb_at_7_days` - rooms booked 7 days before stay
   - `otb_at_14_days` - rooms booked 14 days before stay
   - `otb_at_28_days` - rooms booked 28 days before stay
   - `days_out` - how far out is this forecast

3. **For predictions**: Include current OTB as input feature

### Benefits
- XGBoost learns booking patterns: "When 50 rooms booked at 14 days, usually end at 72"
- Blends historical seasonality WITH current booking momentum
- Could outperform both pure time-series (Prophet) and pure pace (Pickup)

### Complexity
- Training data prep more complex (need to calculate historical OTB)
- Need to handle cases where `booked_at` might be missing for old data
- Query performance - may need to pre-compute and cache

### Pre-computation Strategy (Recommended)

Since historical data doesn't change, pre-compute OTB values once and store them:

**1. New table: `historical_otb_cache`**
```sql
CREATE TABLE historical_otb_cache (
    id SERIAL PRIMARY KEY,
    stay_date DATE NOT NULL,
    metric_code VARCHAR(50) NOT NULL,  -- 'hotel_room_nights', 'resos_dinner_covers'
    days_out INTEGER NOT NULL,          -- 7, 14, 21, 28, etc.
    otb_value DECIMAL(12,2),
    actual_value DECIMAL(12,2),         -- Final actual for comparison
    calculated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(stay_date, metric_code, days_out)
);
```

**2. Nightly job to populate cache**
```python
# Run once nightly (e.g., 2am) to calculate historical OTB
# Only processes dates not already in cache

async def populate_historical_otb_cache():
    lead_times = [7, 14, 21, 28, 60, 90]  # Days out to calculate

    # Get historical dates not yet cached
    uncached_dates = db.execute("""
        SELECT DISTINCT dm.date
        FROM daily_metrics dm
        WHERE dm.date < CURRENT_DATE - INTERVAL '1 day'
          AND dm.metric_code = 'hotel_room_nights'
          AND NOT EXISTS (
              SELECT 1 FROM historical_otb_cache hoc
              WHERE hoc.stay_date = dm.date AND hoc.days_out = 14
          )
        ORDER BY dm.date
        LIMIT 100  -- Process in batches
    """)

    for stay_date in uncached_dates:
        for days_out in lead_times:
            snapshot_date = stay_date - timedelta(days=days_out)

            # Calculate what was booked by snapshot_date for stay_date
            otb = db.execute("""
                SELECT COUNT(*)
                FROM newbook_bookings
                WHERE arrival_date <= :stay_date
                  AND departure_date > :stay_date
                  AND booked_at < :snapshot_date
                  AND status NOT IN ('cancelled', 'no show', ...)
            """, {"stay_date": stay_date, "snapshot_date": snapshot_date})

            # Get actual final value
            actual = db.execute("""
                SELECT actual_value FROM daily_metrics
                WHERE date = :stay_date AND metric_code = 'hotel_room_nights'
            """, {"stay_date": stay_date})

            # Cache it
            db.execute("""
                INSERT INTO historical_otb_cache
                (stay_date, metric_code, days_out, otb_value, actual_value)
                VALUES (:stay_date, 'hotel_room_nights', :days_out, :otb, :actual)
                ON CONFLICT DO NOTHING
            """)
```

**3. XGBoost training uses cached data**
```python
# Fast query - joins cached OTB with daily_metrics
training_data = db.execute("""
    SELECT
        dm.date,
        dm.actual_value,
        EXTRACT(dow FROM dm.date) as day_of_week,
        EXTRACT(month FROM dm.date) as month,
        hoc7.otb_value as otb_7d,
        hoc14.otb_value as otb_14d,
        hoc28.otb_value as otb_28d
    FROM daily_metrics dm
    LEFT JOIN historical_otb_cache hoc7
        ON dm.date = hoc7.stay_date AND hoc7.days_out = 7
    LEFT JOIN historical_otb_cache hoc14
        ON dm.date = hoc14.stay_date AND hoc14.days_out = 14
    LEFT JOIN historical_otb_cache hoc28
        ON dm.date = hoc28.stay_date AND hoc28.days_out = 28
    WHERE dm.metric_code = 'hotel_room_nights'
      AND dm.date >= :training_start
    ORDER BY dm.date
""")
```

**4. Initial backfill**
- Run once to populate all 7 years of history
- Could take a few hours but only needs to run once
- After that, nightly job just adds new days as they become historical

### Benefits of Pre-computation
- Training queries are fast (simple joins vs subqueries)
- Historical OTB never changes, so calculate once
- Can run heavy computation during quiet hours (2-4am)
- XGBoost training stays fast even with 7 years of data

---

## Hotel Occupancy → Restaurant Cover Forecasting

Restaurant covers are heavily influenced by hotel occupancy. Hotel guests are a predictable portion of dinner covers.

### The Problem

Forecasting restaurant covers in isolation misses a key driver:
- 100 hotel guests tonight → ~40 will dine at restaurant (if 40% dining rate)
- 50 hotel guests tonight → ~20 will dine

Without accounting for occupancy, the model treats all Saturdays the same, missing the occupancy-driven variation.

### Solution: Two-Stage Forecasting

**Stage 1: Forecast Hotel Guest Covers**
1. Forecast hotel occupancy (total_guests) using hotel models
2. Apply historical dining rate for that day-of-week/season
3. Result: Expected hotel guest covers

**Stage 2: Forecast External Covers**
- Forecast external covers separately (not occupancy-dependent)
- Uses day-of-week, season, events, weather, etc.

**Final Forecast = Hotel Guest Covers + External Covers**

### Data Captured in `daily_covers`

```sql
-- New fields in daily_covers table:
total_hotel_residents INTEGER,        -- Hotel guests staying that night
hotel_guest_dining_rate DECIMAL(5,2)  -- % of residents who dined: (hotel_guest_covers / total_hotel_residents) * 100
```

### Example Calculation

```
Historical pattern (dinner service, Saturdays):
- Avg dining rate: 42% of hotel guests dine
- Avg external covers: 65 covers

Future Saturday forecast:
- Hotel occupancy forecast: 85 guests
- Expected hotel guest covers: 85 × 42% = 36 covers
- External covers forecast: 65 covers
- Total dinner forecast: 36 + 65 = 101 covers
```

### Model Training Approach

**For hotel_guest_covers forecasting:**
- Use occupancy forecast as primary feature
- Add day-of-week dining rate patterns
- Season adjustments (dining rate varies by season)
- Special events (Valentine's = higher dining rate)

**For external_covers forecasting:**
- Standard time series features (DOW, month, holidays)
- Weather features
- Local events
- Not dependent on hotel occupancy

### XGBoost Features for Restaurant Covers

```python
# Features for total covers model
features = {
    # Standard time features
    'day_of_week': ...,
    'month': ...,
    'is_holiday': ...,

    # Hotel correlation features (key addition)
    'forecast_hotel_guests': ...,           # Occupancy forecast for this date
    'historical_dining_rate': ...,          # Avg dining rate for this DOW/season
    'expected_hotel_guest_covers': ...,     # Calculated: guests × rate

    # External factors
    'weather_temp': ...,
    'local_event': ...,
    'lag_7_external_covers': ...,           # Last week's external covers
}
```

### Migration for Existing Database

```sql
-- Add new columns to existing daily_covers table
ALTER TABLE daily_covers
ADD COLUMN IF NOT EXISTS total_hotel_residents INTEGER,
ADD COLUMN IF NOT EXISTS hotel_guest_dining_rate DECIMAL(5,2);
```

---
