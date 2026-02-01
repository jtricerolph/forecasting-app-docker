"""
Batch Backtest Job
Runs forecasts from multiple perception dates and stores results for accuracy analysis.
"""
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional
import pandas as pd
import numpy as np
from xgboost import XGBRegressor
import warnings

from sqlalchemy import text
from database import SyncSessionLocal

from api.special_dates import resolve_special_date

logger = logging.getLogger(__name__)

warnings.filterwarnings('ignore')


def get_mondays_in_range(start_date: date, end_date: date) -> List[date]:
    """Get all Mondays between start and end date."""
    mondays = []
    current = start_date
    # Move to first Monday
    while current.weekday() != 0:
        current += timedelta(days=1)
    # Collect all Mondays
    while current <= end_date:
        mondays.append(current)
        current += timedelta(days=7)
    return mondays


def get_lead_time_column(days_out: int) -> str:
    """Map days out to the appropriate booking_pace column."""
    if days_out <= 30:
        return f"d{days_out}"
    elif days_out <= 37:
        return "d37"
    elif days_out <= 44:
        return "d44"
    elif days_out <= 51:
        return "d51"
    elif days_out <= 58:
        return "d58"
    elif days_out <= 65:
        return "d65"
    elif days_out <= 72:
        return "d72"
    elif days_out <= 79:
        return "d79"
    elif days_out <= 86:
        return "d86"
    elif days_out <= 93:
        return "d93"
    elif days_out <= 100:
        return "d100"
    elif days_out <= 107:
        return "d107"
    elif days_out <= 114:
        return "d114"
    elif days_out <= 121:
        return "d121"
    elif days_out <= 128:
        return "d128"
    elif days_out <= 135:
        return "d135"
    elif days_out <= 142:
        return "d142"
    elif days_out <= 149:
        return "d149"
    elif days_out <= 156:
        return "d156"
    elif days_out <= 163:
        return "d163"
    elif days_out <= 170:
        return "d170"
    elif days_out <= 177:
        return "d177"
    elif days_out <= 210:
        return "d210"
    elif days_out <= 240:
        return "d240"
    elif days_out <= 270:
        return "d270"
    elif days_out <= 300:
        return "d300"
    elif days_out <= 330:
        return "d330"
    else:
        return "d365"


async def run_batch_backtest(
    start_perception: date,
    end_perception: date,
    forecast_days: int = 365,
    metric: str = "occupancy",
    models: Optional[List[str]] = None
) -> dict:
    """
    Run backtests from multiple perception dates (every Monday in range).

    Args:
        start_perception: First Monday to use as perception date
        end_perception: Last Monday to use as perception date
        forecast_days: How many days ahead to forecast from each perception date
        metric: 'occupancy' or 'rooms'
        models: List of models to run (default: ['xgboost'])

    Returns:
        Summary of results
    """
    if models is None:
        models = ['xgboost']

    perception_dates = get_mondays_in_range(start_perception, end_perception)
    logger.info(f"Running batch backtest for {len(perception_dates)} perception dates")

    db = SyncSessionLocal()
    total_snapshots = 0
    errors = []

    try:
        for perception_date in perception_dates:
            logger.info(f"Processing perception_date: {perception_date}")

            for model in models:
                try:
                    if model == 'xgboost':
                        count = await run_xgboost_backtest(
                            db, perception_date, forecast_days, metric
                        )
                        total_snapshots += count
                    elif model == 'prophet':
                        count = await run_prophet_backtest(
                            db, perception_date, forecast_days, metric
                        )
                        total_snapshots += count
                    elif model == 'pickup':
                        count = await run_pickup_backtest(
                            db, perception_date, forecast_days, metric
                        )
                        total_snapshots += count
                    else:
                        logger.warning(f"Unknown model: {model}")
                except Exception as e:
                    error_msg = f"Error for {perception_date}/{model}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            db.commit()

        return {
            "perception_dates_processed": len(perception_dates),
            "total_snapshots": total_snapshots,
            "errors": errors
        }

    finally:
        db.close()


async def run_xgboost_backtest(
    db,
    perception_date: date,
    forecast_days: int,
    metric: str
) -> int:
    """
    Run XGBoost forecast from a specific perception date and store snapshots.
    Returns count of snapshots stored.
    """
    today = perception_date

    # Get bookable rooms
    bookable_result = db.execute(text("""
        SELECT bookable_count
        FROM newbook_bookings_stats
        WHERE bookable_count IS NOT NULL AND date < :today
        ORDER BY date DESC
        LIMIT 1
    """), {"today": today})
    bookable_row = bookable_result.fetchone()
    total_rooms = int(bookable_row.bookable_count) if bookable_row else 25

    # Get historical data for training (2 years before perception date)
    history_start = today - timedelta(days=730)

    train_lead_times = [0, 1, 3, 7, 14, 21, 28, 30]

    history_result = db.execute(text("""
        SELECT s.date as ds, s.booking_count as final,
               p.d0, p.d1, p.d3, p.d7, p.d14, p.d21, p.d28, p.d30
        FROM newbook_bookings_stats s
        LEFT JOIN newbook_booking_pace p ON s.date = p.arrival_date
        WHERE s.date >= :history_start
        AND s.date < :today
        AND s.booking_count IS NOT NULL
        ORDER BY s.date
    """), {"history_start": history_start, "today": today})
    history_rows = history_result.fetchall()

    if len(history_rows) < 30:
        logger.warning(f"Insufficient data for perception_date {perception_date}")
        return 0

    # Load special dates
    special_date_set = set()
    try:
        special_dates_result = db.execute(text(
            "SELECT * FROM special_dates WHERE is_active = TRUE"
        ))
        special_dates_rows = special_dates_result.fetchall()
        years_needed = set(r.ds.year for r in history_rows) | {today.year, today.year + 1}
        for row in special_dates_rows:
            sd = {
                'pattern_type': row.pattern_type,
                'fixed_month': row.fixed_month,
                'fixed_day': row.fixed_day,
                'nth_week': row.nth_week,
                'weekday': row.weekday,
                'month': row.month,
                'relative_to_month': row.relative_to_month,
                'relative_to_day': row.relative_to_day,
                'relative_weekday': row.relative_weekday,
                'relative_direction': row.relative_direction,
                'duration_days': row.duration_days,
                'is_recurring': row.is_recurring,
                'one_off_year': row.one_off_year
            }
            for year in years_needed:
                resolved_dates = resolve_special_date(sd, year)
                for d in resolved_dates:
                    special_date_set.add(d)
    except Exception:
        pass

    # Build lookup dicts
    pace_by_date = {}
    final_by_date = {}
    for row in history_rows:
        pace_by_date[row.ds] = {
            0: row.d0, 1: row.d1, 3: row.d3, 7: row.d7,
            14: row.d14, 21: row.d21, 28: row.d28, 30: row.d30
        }
        final_by_date[row.ds] = row.final

    # Build training examples
    training_rows = []
    for row in history_rows:
        ds = row.ds
        final = float(row.final)
        prior_ds = ds - timedelta(days=364)

        prior_final = final_by_date.get(prior_ds)
        if prior_final is None:
            continue

        for lead_time in train_lead_times:
            current_otb = pace_by_date.get(ds, {}).get(lead_time)
            if current_otb is None:
                continue

            prior_otb = pace_by_date.get(prior_ds, {}).get(lead_time)
            if prior_otb is None:
                prior_otb = 0

            otb_pct_of_prior_final = (float(current_otb) / float(prior_final) * 100) if prior_final > 0 else 0

            training_rows.append({
                'ds': ds,
                'y': final,
                'days_out': lead_time,
                'current_otb': float(current_otb),
                'prior_otb_same_lead': float(prior_otb),
                'lag_364': float(prior_final),
                'otb_pct_of_prior_final': otb_pct_of_prior_final
            })

    if len(training_rows) < 30:
        logger.warning(f"Insufficient training data for perception_date {perception_date}")
        return 0

    df = pd.DataFrame(training_rows)
    df['ds'] = pd.to_datetime(df['ds'])

    # Convert to occupancy if needed
    if metric == "occupancy" and total_rooms > 0:
        df["y"] = (df["y"] / total_rooms) * 100
        df["current_otb"] = (df["current_otb"] / total_rooms) * 100
        df["prior_otb_same_lead"] = (df["prior_otb_same_lead"] / total_rooms) * 100
        df["lag_364"] = (df["lag_364"] / total_rooms) * 100

    # Create time features
    df['day_of_week'] = df['ds'].dt.dayofweek
    df['month'] = df['ds'].dt.month
    df['week_of_year'] = df['ds'].dt.isocalendar().week.astype(int)
    df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
    df['is_special_date'] = df['ds'].dt.date.apply(lambda x: 1 if x in special_date_set else 0)

    df_train = df.dropna()

    if len(df_train) < 30:
        return 0

    feature_cols = ['day_of_week', 'month', 'week_of_year', 'is_weekend', 'is_special_date',
                   'days_out', 'current_otb', 'prior_otb_same_lead', 'lag_364', 'otb_pct_of_prior_final']

    X_train = df_train[feature_cols]
    y_train = df_train['y']

    # Train model
    model = XGBRegressor(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        objective='reg:squarederror',
        random_state=42,
        n_jobs=-1
    )
    model.fit(X_train, y_train)

    # Generate forecasts
    snapshots_stored = 0
    end_date = today + timedelta(days=forecast_days)

    current_date = today
    while current_date <= end_date:
        lead_days = (current_date - today).days
        lead_col = get_lead_time_column(lead_days)
        prior_year_date = current_date - timedelta(days=364)

        # Get current OTB from booking_pace at that lead time
        otb_result = db.execute(text(f"""
            SELECT {lead_col} as current_otb
            FROM newbook_booking_pace
            WHERE arrival_date = :arrival_date
        """), {"arrival_date": current_date})
        otb_row = otb_result.fetchone()

        # Get prior year OTB at same lead
        prior_otb_result = db.execute(text(f"""
            SELECT {lead_col} as prior_otb
            FROM newbook_booking_pace
            WHERE arrival_date = :prior_date
        """), {"prior_date": prior_year_date})
        prior_otb_row = prior_otb_result.fetchone()

        # Get prior year final
        prior_final_result = db.execute(text("""
            SELECT booking_count as prior_final
            FROM newbook_bookings_stats
            WHERE date = :prior_date
        """), {"prior_date": prior_year_date})
        prior_final_row = prior_final_result.fetchone()

        current_otb = otb_row.current_otb if otb_row and otb_row.current_otb else 0
        prior_otb = prior_otb_row.prior_otb if prior_otb_row and prior_otb_row.prior_otb else 0
        prior_final = prior_final_row.prior_final if prior_final_row and prior_final_row.prior_final else 0

        # Convert to occupancy
        if metric == "occupancy" and total_rooms > 0:
            current_otb = (current_otb / total_rooms) * 100
            prior_otb = (prior_otb / total_rooms) * 100
            prior_final = (prior_final / total_rooms) * 100

        lag_364_val = prior_final if prior_final else 0
        otb_pct_of_prior_final = (current_otb / lag_364_val * 100) if lag_364_val > 0 else 0

        # Build features
        forecast_dt = pd.Timestamp(current_date)
        features = pd.DataFrame([{
            'day_of_week': forecast_dt.dayofweek,
            'month': forecast_dt.month,
            'week_of_year': forecast_dt.isocalendar().week,
            'is_weekend': 1 if forecast_dt.dayofweek >= 5 else 0,
            'is_special_date': 1 if current_date in special_date_set else 0,
            'days_out': lead_days,
            'current_otb': current_otb,
            'prior_otb_same_lead': prior_otb,
            'lag_364': lag_364_val,
            'otb_pct_of_prior_final': otb_pct_of_prior_final,
        }])

        # Predict
        yhat = float(model.predict(features)[0])

        # Cap at max
        if metric == "occupancy":
            yhat = min(max(yhat, 0), 100.0)
        else:
            yhat = round(min(max(yhat, 0), float(total_rooms)))

        # Store snapshot
        db.execute(text("""
            INSERT INTO forecast_snapshots
                (perception_date, target_date, model, metric_code, days_out, forecast_value)
            VALUES
                (:perception_date, :target_date, 'xgboost', :metric, :days_out, :forecast_value)
            ON CONFLICT (perception_date, target_date, model, metric_code)
            DO UPDATE SET forecast_value = :forecast_value, created_at = NOW()
        """), {
            "perception_date": perception_date,
            "target_date": current_date,
            "metric": metric,
            "days_out": lead_days,
            "forecast_value": round(yhat, 2)
        })

        snapshots_stored += 1
        current_date += timedelta(days=1)

    return snapshots_stored


async def run_pickup_backtest(
    db,
    perception_date: date,
    forecast_days: int,
    metric: str
) -> int:
    """
    Run Pickup (additive) forecast from a specific perception date.
    Uses: current_otb + (prior_final - prior_otb) = forecast

    Returns count of snapshots stored.
    """
    today = perception_date

    # Get bookable rooms
    bookable_result = db.execute(text("""
        SELECT bookable_count
        FROM newbook_bookings_stats
        WHERE bookable_count IS NOT NULL AND date < :today
        ORDER BY date DESC
        LIMIT 1
    """), {"today": today})
    bookable_row = bookable_result.fetchone()
    total_rooms = int(bookable_row.bookable_count) if bookable_row else 25

    snapshots_stored = 0
    end_date = today + timedelta(days=forecast_days)

    current_date = today
    while current_date <= end_date:
        lead_days = (current_date - today).days
        lead_col = get_lead_time_column(lead_days)
        prior_year_date = current_date - timedelta(days=364)

        # Get current OTB from booking_pace
        otb_result = db.execute(text(f"""
            SELECT {lead_col} as current_otb
            FROM newbook_booking_pace
            WHERE arrival_date = :arrival_date
        """), {"arrival_date": current_date})
        otb_row = otb_result.fetchone()

        # Get prior year OTB at same lead
        prior_otb_result = db.execute(text(f"""
            SELECT {lead_col} as prior_otb
            FROM newbook_booking_pace
            WHERE arrival_date = :prior_date
        """), {"prior_date": prior_year_date})
        prior_otb_row = prior_otb_result.fetchone()

        # Get prior year final
        prior_final_result = db.execute(text("""
            SELECT booking_count as prior_final
            FROM newbook_bookings_stats
            WHERE date = :prior_date
        """), {"prior_date": prior_year_date})
        prior_final_row = prior_final_result.fetchone()

        current_otb = otb_row.current_otb if otb_row and otb_row.current_otb else 0
        prior_otb = prior_otb_row.prior_otb if prior_otb_row and prior_otb_row.prior_otb else 0
        prior_final = prior_final_row.prior_final if prior_final_row and prior_final_row.prior_final else 0

        # Convert to occupancy if needed
        if metric == "occupancy" and total_rooms > 0:
            current_otb = (current_otb / total_rooms) * 100
            prior_otb = (prior_otb / total_rooms) * 100
            prior_final = (prior_final / total_rooms) * 100

        # Additive pickup: forecast = current_otb + (prior_final - prior_otb)
        if prior_final > 0 and prior_otb is not None:
            prior_pickup = prior_final - prior_otb
            yhat = current_otb + prior_pickup
        else:
            yhat = current_otb

        # Floor to current OTB
        yhat = max(yhat, current_otb)

        # Cap at max
        if metric == "occupancy":
            yhat = min(max(yhat, 0), 100.0)
        else:
            yhat = round(min(max(yhat, 0), float(total_rooms)))

        # Store snapshot
        db.execute(text("""
            INSERT INTO forecast_snapshots
                (perception_date, target_date, model, metric_code, days_out, forecast_value)
            VALUES
                (:perception_date, :target_date, 'pickup', :metric, :days_out, :forecast_value)
            ON CONFLICT (perception_date, target_date, model, metric_code)
            DO UPDATE SET forecast_value = :forecast_value, created_at = NOW()
        """), {
            "perception_date": perception_date,
            "target_date": current_date,
            "metric": metric,
            "days_out": lead_days,
            "forecast_value": round(yhat, 2)
        })

        snapshots_stored += 1
        current_date += timedelta(days=1)

    return snapshots_stored


async def run_prophet_backtest(
    db,
    perception_date: date,
    forecast_days: int,
    metric: str
) -> int:
    """
    Run Prophet forecast from a specific perception date.
    Uses Facebook Prophet for time series forecasting.

    Returns count of snapshots stored.
    """
    from prophet import Prophet

    today = perception_date

    # Get bookable rooms
    bookable_result = db.execute(text("""
        SELECT bookable_count
        FROM newbook_bookings_stats
        WHERE bookable_count IS NOT NULL AND date < :today
        ORDER BY date DESC
        LIMIT 1
    """), {"today": today})
    bookable_row = bookable_result.fetchone()
    total_rooms = int(bookable_row.bookable_count) if bookable_row else 25

    # Get historical data (2 years before perception date)
    history_start = today - timedelta(days=730)
    history_result = db.execute(text("""
        SELECT date as ds, booking_count as y
        FROM newbook_bookings_stats
        WHERE date >= :history_start
        AND date < :today
        AND booking_count IS NOT NULL
        ORDER BY date
    """), {"history_start": history_start, "today": today})
    history_rows = history_result.fetchall()

    if len(history_rows) < 30:
        logger.warning(f"Insufficient data for Prophet at perception_date {perception_date}")
        return 0

    # Build training dataframe
    df = pd.DataFrame([{"ds": row.ds, "y": float(row.y)} for row in history_rows])
    df['ds'] = pd.to_datetime(df['ds'])

    # Convert to occupancy if needed
    if metric == "occupancy" and total_rooms > 0:
        df["y"] = (df["y"] / total_rooms) * 100

    # Train Prophet model
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        seasonality_mode='multiplicative'
    )
    model.fit(df)

    # Create future dataframe
    future = model.make_future_dataframe(periods=forecast_days)
    future = future[future['ds'] >= pd.Timestamp(today)]

    # Predict
    forecast = model.predict(future)

    # Store snapshots
    snapshots_stored = 0
    for _, row in forecast.iterrows():
        target_date = row['ds'].date()
        lead_days = (target_date - today).days
        yhat = float(row['yhat'])

        # Cap at max
        if metric == "occupancy":
            yhat = min(max(yhat, 0), 100.0)
        else:
            yhat = round(min(max(yhat, 0), float(total_rooms)))

        db.execute(text("""
            INSERT INTO forecast_snapshots
                (perception_date, target_date, model, metric_code, days_out, forecast_value)
            VALUES
                (:perception_date, :target_date, 'prophet', :metric, :days_out, :forecast_value)
            ON CONFLICT (perception_date, target_date, model, metric_code)
            DO UPDATE SET forecast_value = :forecast_value, created_at = NOW()
        """), {
            "perception_date": perception_date,
            "target_date": target_date,
            "metric": metric,
            "days_out": lead_days,
            "forecast_value": round(yhat, 2)
        })

        snapshots_stored += 1

    return snapshots_stored


async def backfill_actuals():
    """
    Backfill actual_value in forecast_snapshots from newbook_bookings_stats.
    Run this after target_date has passed.
    """
    db = SyncSessionLocal()

    try:
        # Get all snapshots missing actual values where target_date has passed
        result = db.execute(text("""
            UPDATE forecast_snapshots fs
            SET actual_value = CASE
                WHEN fs.metric_code = 'occupancy' THEN
                    (s.booking_count::decimal / NULLIF(s.bookable_count, 0)) * 100
                ELSE
                    s.booking_count
            END
            FROM newbook_bookings_stats s
            WHERE fs.target_date = s.date
            AND fs.actual_value IS NULL
            AND fs.target_date < CURRENT_DATE
            AND s.booking_count IS NOT NULL
        """))

        db.commit()
        count = result.rowcount
        logger.info(f"Backfilled {count} actual values")
        return count

    finally:
        db.close()
