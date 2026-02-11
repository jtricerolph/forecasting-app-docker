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


def get_metric_query_info(metric: str) -> dict:
    """
    Get SQL query information for each metric.
    Returns dict with:
        - column_expr: SQL expression for the metric value
        - needs_revenue_join: whether to join with newbook_net_revenue_data
        - is_pct_metric: whether it's a percentage metric (0-100)
        - is_revenue_metric: whether it's a revenue/rate metric
    """
    metric_info = {
        'occupancy': {
            'column_expr': 's.booking_count',
            'needs_revenue_join': False,
            'is_pct_metric': True,  # Will be converted to percentage
            'is_revenue_metric': False,
        },
        'rooms': {
            'column_expr': 's.booking_count',
            'needs_revenue_join': False,
            'is_pct_metric': False,
            'is_revenue_metric': False,
        },
        'guests': {
            'column_expr': 's.guests_count',
            'needs_revenue_join': False,
            'is_pct_metric': False,
            'is_revenue_metric': False,
        },
        'ave_guest_rate': {
            'column_expr': 'CASE WHEN s.booking_count > 0 THEN s.guest_rate_total / s.booking_count ELSE NULL END',
            'needs_revenue_join': False,
            'is_pct_metric': False,
            'is_revenue_metric': True,
        },
        'arr': {
            'column_expr': 'CASE WHEN s.booking_count > 0 THEN r.accommodation / s.booking_count ELSE NULL END',
            'needs_revenue_join': True,
            'is_pct_metric': False,
            'is_revenue_metric': True,
        },
        'net_accom': {
            'column_expr': 'r.accommodation',
            'needs_revenue_join': True,
            'is_pct_metric': False,
            'is_revenue_metric': True,
        },
        'net_dry': {
            'column_expr': 'r.dry',
            'needs_revenue_join': True,
            'is_pct_metric': False,
            'is_revenue_metric': True,
        },
        'net_wet': {
            'column_expr': 'r.wet',
            'needs_revenue_join': True,
            'is_pct_metric': False,
            'is_revenue_metric': True,
        },
    }
    return metric_info.get(metric, metric_info['rooms'])


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
    models: Optional[List[str]] = None,
    training_start: Optional[date] = None
) -> dict:
    """
    Run backtests from multiple perception dates (every Monday in range).

    Args:
        start_perception: First Monday to use as perception date
        end_perception: Last Monday to use as perception date
        forecast_days: How many days ahead to forecast from each perception date
        metric: 'occupancy' or 'rooms'
        models: List of models to run (default: ['xgboost'])
        training_start: Optional cutoff date for training data (e.g., 2021-05-01 to exclude COVID)
                        Results stored with '_postcovid' suffix when set.

    Returns:
        Summary of results
    """
    if models is None:
        models = ['xgboost']

    perception_dates = get_mondays_in_range(start_perception, end_perception)
    suffix = "_postcovid" if training_start else ""
    logger.info(f"Running batch backtest for {len(perception_dates)} perception dates{f' (training from {training_start})' if training_start else ''}")

    db = SyncSessionLocal()
    total_snapshots = 0
    errors = []

    try:
        for perception_date in perception_dates:
            logger.info(f"Processing perception_date: {perception_date}")

            for model in models:
                try:
                    # Model name with suffix for post-COVID training
                    model_name = f"{model}{suffix}"

                    if model == 'xgboost':
                        count = await run_xgboost_backtest(
                            db, perception_date, forecast_days, metric,
                            training_start=training_start, model_name=model_name
                        )
                        total_snapshots += count
                    elif model == 'prophet':
                        count = await run_prophet_backtest(
                            db, perception_date, forecast_days, metric,
                            training_start=training_start, model_name=model_name
                        )
                        total_snapshots += count
                    elif model == 'pickup':
                        count = await run_pickup_backtest(
                            db, perception_date, forecast_days, metric,
                            training_start=training_start, model_name=model_name
                        )
                        total_snapshots += count
                    elif model == 'pickup_avg':
                        count = await run_pickup_avg_backtest(
                            db, perception_date, forecast_days, metric,
                            training_start=training_start, model_name=model_name
                        )
                        total_snapshots += count
                    elif model == 'catboost':
                        count = await run_catboost_backtest(
                            db, perception_date, forecast_days, metric,
                            training_start=training_start, model_name=model_name
                        )
                        total_snapshots += count
                    elif model == 'blended':
                        count = await run_blended_backtest(
                            db, perception_date, forecast_days, metric,
                            training_start=training_start, model_name=model_name
                        )
                        total_snapshots += count
                    else:
                        logger.warning(f"Unknown model: {model}")
                except Exception as e:
                    error_msg = f"Error for {perception_date}/{model}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            db.commit()

        # Backfill actuals after all backtests complete
        logger.info("Backfilling actual values...")
        backfill_count = await backfill_actuals()
        logger.info(f"Backfilled {backfill_count} actual values")

        return {
            "perception_dates_processed": len(perception_dates),
            "total_snapshots": total_snapshots,
            "actuals_backfilled": backfill_count,
            "errors": errors
        }

    finally:
        db.close()


async def run_xgboost_backtest(
    db,
    perception_date: date,
    forecast_days: int,
    metric: str,
    training_start: Optional[date] = None,
    model_name: str = "xgboost"
) -> int:
    """
    Run XGBoost forecast from a specific perception date and store snapshots.
    Returns count of snapshots stored.

    For occupancy/rooms: Uses pace data (OTB at different lead times) as features.
    For other metrics: Uses time-series features only (like Prophet but with XGBoost).

    Args:
        training_start: Optional cutoff date - only use training data from this date forward
        model_name: Name to store in snapshots (e.g., 'xgboost' or 'xgboost_postcovid')
    """
    today = perception_date

    # Check if this metric has pace data
    pace_metrics = ['occupancy', 'rooms']
    use_pace = metric in pace_metrics

    # Get metric query info
    metric_info = get_metric_query_info(metric)
    column_expr = metric_info['column_expr']
    needs_revenue_join = metric_info['needs_revenue_join']
    is_pct_metric = metric_info['is_pct_metric']
    is_revenue_metric = metric_info['is_revenue_metric']

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

    # Get historical data for training (2 years before perception date, or from training_start)
    history_start = today - timedelta(days=730)
    if training_start and training_start > history_start:
        history_start = training_start

    # Build query based on metric type
    if use_pace:
        # Pace-based query for occupancy/rooms
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
    elif needs_revenue_join:
        # Revenue metrics
        history_result = db.execute(text(f"""
            SELECT s.date as ds, {column_expr} as final
            FROM newbook_bookings_stats s
            LEFT JOIN newbook_net_revenue_data r ON s.date = r.date
            WHERE s.date >= :history_start
            AND s.date < :today
            AND s.booking_count IS NOT NULL
            ORDER BY s.date
        """), {"history_start": history_start, "today": today})
    else:
        # Stats-based metrics (guests, ave_guest_rate)
        history_result = db.execute(text(f"""
            SELECT s.date as ds, {column_expr} as final
            FROM newbook_bookings_stats s
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
    final_by_date = {}
    for row in history_rows:
        if row.final is not None:
            final_by_date[row.ds] = row.final

    if use_pace:
        # Pace-based training for occupancy/rooms
        train_lead_times = [0, 1, 3, 7, 14, 21, 28, 30]
        pace_by_date = {}
        for row in history_rows:
            pace_by_date[row.ds] = {
                0: row.d0, 1: row.d1, 3: row.d3, 7: row.d7,
                14: row.d14, 21: row.d21, 28: row.d28, 30: row.d30
            }

        # Build training examples with pace features
        training_rows = []
        for row in history_rows:
            ds = row.ds
            if row.final is None:
                continue
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

        feature_cols = ['day_of_week', 'month', 'week_of_year', 'is_weekend', 'is_special_date',
                       'days_out', 'current_otb', 'prior_otb_same_lead', 'lag_364', 'otb_pct_of_prior_final']
    else:
        # Non-pace training for other metrics (time features + lag only)
        training_rows = []
        for row in history_rows:
            ds = row.ds
            if row.final is None:
                continue
            final = float(row.final)
            prior_ds = ds - timedelta(days=364)

            prior_final = final_by_date.get(prior_ds)
            if prior_final is None:
                prior_final = final  # Use same value as fallback

            training_rows.append({
                'ds': ds,
                'y': final,
                'lag_364': float(prior_final),
            })

        if len(training_rows) < 30:
            logger.warning(f"Insufficient training data for perception_date {perception_date}")
            return 0

        df = pd.DataFrame(training_rows)
        df['ds'] = pd.to_datetime(df['ds'])

        feature_cols = ['day_of_week', 'month', 'week_of_year', 'is_weekend', 'is_special_date', 'lag_364']

    # Create time features (common to both)
    df['day_of_week'] = df['ds'].dt.dayofweek
    df['month'] = df['ds'].dt.month
    df['week_of_year'] = df['ds'].dt.isocalendar().week.astype(int)
    df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
    df['is_special_date'] = df['ds'].dt.date.apply(lambda x: 1 if x in special_date_set else 0)

    df_train = df.dropna()

    if len(df_train) < 30:
        return 0

    X_train = df_train[feature_cols]
    y_train = df_train['y']

    # Determine training cap for capping predictions
    if is_pct_metric:
        training_cap = 100
    elif metric == 'rooms':
        training_cap = total_rooms
    elif metric == 'guests':
        training_cap = df_train["y"].max() * 1.5 if len(df_train) > 0 and df_train["y"].max() > 0 else total_rooms * 3
    else:
        # Revenue/rate metrics - use 99th percentile * 1.5
        training_cap = df_train["y"].quantile(0.99) * 1.5 if len(df_train) > 0 and df_train["y"].quantile(0.99) > 0 else 10000

    # Train model
    xgb_model = XGBRegressor(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        objective='reg:squarederror',
        random_state=42,
        n_jobs=-1
    )
    xgb_model.fit(X_train, y_train)

    # Generate forecasts
    snapshots_stored = 0
    end_date = today + timedelta(days=forecast_days)

    current_date = today
    while current_date <= end_date:
        lead_days = (current_date - today).days
        prior_year_date = current_date - timedelta(days=364)

        if use_pace:
            # Pace-based prediction for occupancy/rooms
            lead_col = get_lead_time_column(lead_days)

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
        else:
            # Non-pace prediction for other metrics
            # Get prior year value for lag feature
            lag_364_val = final_by_date.get(prior_year_date)
            if lag_364_val is None:
                lag_364_val = float(df_train["y"].mean())
            else:
                lag_364_val = float(lag_364_val)

            forecast_dt = pd.Timestamp(current_date)
            features = pd.DataFrame([{
                'day_of_week': int(forecast_dt.dayofweek),
                'month': int(forecast_dt.month),
                'week_of_year': int(forecast_dt.isocalendar().week),
                'is_weekend': 1 if forecast_dt.dayofweek >= 5 else 0,
                'is_special_date': 1 if current_date in special_date_set else 0,
                'lag_364': lag_364_val,
            }])

        # Predict
        yhat = float(xgb_model.predict(features)[0])

        # Cap based on metric type
        if is_pct_metric:
            yhat = min(max(yhat, 0), 100.0)
        elif metric == 'rooms':
            yhat = round(min(max(yhat, 0), float(total_rooms)))
        elif metric == 'guests':
            yhat = round(max(yhat, 0))
        else:
            # Revenue/rate metrics
            yhat = round(max(yhat, 0), 2)

        # Store snapshot
        db.execute(text("""
            INSERT INTO forecast_snapshots
                (perception_date, target_date, model, metric_code, days_out, forecast_value)
            VALUES
                (:perception_date, :target_date, :model_name, :metric, :days_out, :forecast_value)
            ON CONFLICT (perception_date, target_date, model, metric_code)
            DO UPDATE SET forecast_value = :forecast_value, created_at = NOW()
        """), {
            "perception_date": perception_date,
            "target_date": current_date,
            "model_name": model_name,
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
    metric: str,
    training_start: Optional[date] = None,
    model_name: str = "pickup"
) -> int:
    """
    Run Pickup (additive) forecast from a specific perception date.
    Uses: current_otb + (prior_final - prior_otb) = forecast

    Args:
        training_start: Not used by pickup model (no training), but accepted for API consistency
        model_name: Name to store in snapshots (e.g., 'pickup' or 'pickup_postcovid')

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
                (:perception_date, :target_date, :model_name, :metric, :days_out, :forecast_value)
            ON CONFLICT (perception_date, target_date, model, metric_code)
            DO UPDATE SET forecast_value = :forecast_value, created_at = NOW()
        """), {
            "perception_date": perception_date,
            "target_date": current_date,
            "model_name": model_name,
            "metric": metric,
            "days_out": lead_days,
            "forecast_value": round(yhat, 2)
        })

        snapshots_stored += 1
        current_date += timedelta(days=1)

    return snapshots_stored


def get_same_dow_prior_year(target_date: date, years_back: int) -> date:
    """
    Get the date from N years ago that matches the same day of week.
    Uses ISO week number and weekday to properly align across leap years.

    Example: Monday Jan 6, 2025 -> Monday Jan 8, 2024 (same ISO week, same DOW)
    """
    iso_cal = target_date.isocalendar()
    target_week = iso_cal.week
    target_dow = iso_cal.weekday  # 1=Monday, 7=Sunday

    prior_year = target_date.year - years_back

    # Find the first day of the target ISO week in the prior year
    # ISO week 1 is the week containing Jan 4th
    jan4 = date(prior_year, 1, 4)
    jan4_iso = jan4.isocalendar()

    # Calculate days from Jan 4 to the start of week 1
    days_to_week1_start = (jan4_iso.weekday - 1)  # Days from Monday of week 1 to Jan 4
    week1_monday = jan4 - timedelta(days=days_to_week1_start)

    # Now find the Monday of the target week
    target_week_monday = week1_monday + timedelta(weeks=target_week - 1)

    # Add days to get to the correct day of week
    prior_date = target_week_monday + timedelta(days=target_dow - 1)

    return prior_date


async def run_pickup_avg_backtest(
    db,
    perception_date: date,
    forecast_days: int,
    metric: str,
    training_start: Optional[date] = None,
    model_name: str = "pickup_avg"
) -> int:
    """
    Run Pickup (weighted 2-year average) forecast from a specific perception date.
    Uses weighted average pickup from last 2 years:
        current_otb + (0.7 * year1_pickup + 0.3 * year2_pickup)

    Weights: 70% year 1, 30% year 2
    This focuses on recent years and excludes COVID-affected periods.

    Also calculates confidence bounds using min/max pickup across the 2 years.

    Uses ISO week matching to ensure same day-of-week alignment across years,
    properly handling leap years.

    Args:
        training_start: Not used by pickup model (no training), but accepted for API consistency
        model_name: Name to store in snapshots (e.g., 'pickup_avg')

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

        # Get current OTB from booking_pace
        otb_result = db.execute(text(f"""
            SELECT {lead_col} as current_otb
            FROM newbook_booking_pace
            WHERE arrival_date = :arrival_date
        """), {"arrival_date": current_date})
        otb_row = otb_result.fetchone()
        current_otb = otb_row.current_otb if otb_row and otb_row.current_otb else 0

        # Convert current OTB to occupancy if needed
        if metric == "occupancy" and total_rooms > 0:
            current_otb = (current_otb / total_rooms) * 100

        # Collect pickup values from 2 years with weights (using proper DOW alignment)
        # Weights: 70% year 1, 30% year 2
        year_weights = {1: 0.7, 2: 0.3}
        pickups = []  # List of (pickup_value, weight) tuples
        pickup_values = []  # Just values for min/max

        for years_back in [1, 2]:
            prior_date = get_same_dow_prior_year(current_date, years_back)

            # Get prior year OTB at same lead
            prior_otb_result = db.execute(text(f"""
                SELECT {lead_col} as prior_otb
                FROM newbook_booking_pace
                WHERE arrival_date = :prior_date
            """), {"prior_date": prior_date})
            prior_otb_row = prior_otb_result.fetchone()

            # Get prior year final
            prior_final_result = db.execute(text("""
                SELECT booking_count as prior_final
                FROM newbook_bookings_stats
                WHERE date = :prior_date
            """), {"prior_date": prior_date})
            prior_final_row = prior_final_result.fetchone()

            prior_otb = prior_otb_row.prior_otb if prior_otb_row and prior_otb_row.prior_otb else None
            prior_final = prior_final_row.prior_final if prior_final_row and prior_final_row.prior_final else None

            if prior_final is not None and prior_otb is not None:
                # Convert to occupancy if needed
                if metric == "occupancy" and total_rooms > 0:
                    prior_otb = (prior_otb / total_rooms) * 100
                    prior_final = (prior_final / total_rooms) * 100

                pickup = prior_final - prior_otb
                pickups.append((pickup, year_weights[years_back]))
                pickup_values.append(pickup)

        # Calculate weighted average, min, max pickup
        if pickups:
            # Normalize weights if not all years have data
            total_weight = sum(w for _, w in pickups)
            avg_pickup = sum(p * w for p, w in pickups) / total_weight
            min_pickup = min(pickup_values)
            max_pickup = max(pickup_values)
        else:
            avg_pickup = 0
            min_pickup = 0
            max_pickup = 0

        # Forecast using average pickup
        yhat = current_otb + avg_pickup
        yhat_lower = current_otb + min_pickup
        yhat_upper = current_otb + max_pickup

        # Floor to current OTB
        yhat = max(yhat, current_otb)
        yhat_lower = max(yhat_lower, current_otb)
        yhat_upper = max(yhat_upper, current_otb)

        # Cap at max
        if metric == "occupancy":
            yhat = min(max(yhat, 0), 100.0)
            yhat_lower = min(max(yhat_lower, 0), 100.0)
            yhat_upper = min(max(yhat_upper, 0), 100.0)
        else:
            yhat = round(min(max(yhat, 0), float(total_rooms)))
            yhat_lower = round(min(max(yhat_lower, 0), float(total_rooms)))
            yhat_upper = round(min(max(yhat_upper, 0), float(total_rooms)))

        # Store snapshot (main forecast)
        db.execute(text("""
            INSERT INTO forecast_snapshots
                (perception_date, target_date, model, metric_code, days_out, forecast_value)
            VALUES
                (:perception_date, :target_date, :model_name, :metric, :days_out, :forecast_value)
            ON CONFLICT (perception_date, target_date, model, metric_code)
            DO UPDATE SET forecast_value = :forecast_value, created_at = NOW()
        """), {
            "perception_date": perception_date,
            "target_date": current_date,
            "model_name": model_name,
            "metric": metric,
            "days_out": lead_days,
            "forecast_value": round(yhat, 2)
        })

        # Store lower bound
        db.execute(text("""
            INSERT INTO forecast_snapshots
                (perception_date, target_date, model, metric_code, days_out, forecast_value)
            VALUES
                (:perception_date, :target_date, :model_name, :metric, :days_out, :forecast_value)
            ON CONFLICT (perception_date, target_date, model, metric_code)
            DO UPDATE SET forecast_value = :forecast_value, created_at = NOW()
        """), {
            "perception_date": perception_date,
            "target_date": current_date,
            "model_name": f"{model_name}_lower",
            "metric": metric,
            "days_out": lead_days,
            "forecast_value": round(yhat_lower, 2)
        })

        # Store upper bound
        db.execute(text("""
            INSERT INTO forecast_snapshots
                (perception_date, target_date, model, metric_code, days_out, forecast_value)
            VALUES
                (:perception_date, :target_date, :model_name, :metric, :days_out, :forecast_value)
            ON CONFLICT (perception_date, target_date, model, metric_code)
            DO UPDATE SET forecast_value = :forecast_value, created_at = NOW()
        """), {
            "perception_date": perception_date,
            "target_date": current_date,
            "model_name": f"{model_name}_upper",
            "metric": metric,
            "days_out": lead_days,
            "forecast_value": round(yhat_upper, 2)
        })

        snapshots_stored += 1
        current_date += timedelta(days=1)

    return snapshots_stored


async def run_prophet_backtest(
    db,
    perception_date: date,
    forecast_days: int,
    metric: str,
    training_start: Optional[date] = None,
    model_name: str = "prophet"
) -> int:
    """
    Run Prophet forecast from a specific perception date.
    Uses Facebook Prophet for time series forecasting.

    Args:
        training_start: Optional cutoff date - only use training data from this date forward
        model_name: Name to store in snapshots (e.g., 'prophet' or 'prophet_postcovid')

    Returns count of snapshots stored.
    """
    from prophet import Prophet

    today = perception_date

    # Get metric query info
    metric_info = get_metric_query_info(metric)
    column_expr = metric_info['column_expr']
    needs_revenue_join = metric_info['needs_revenue_join']
    is_pct_metric = metric_info['is_pct_metric']
    is_revenue_metric = metric_info['is_revenue_metric']

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

    # Get historical data (2 years before perception date, or from training_start)
    history_start = today - timedelta(days=730)
    if training_start and training_start > history_start:
        history_start = training_start

    # Build query based on metric type
    if needs_revenue_join:
        query = f"""
            SELECT s.date as ds, {column_expr} as y
            FROM newbook_bookings_stats s
            LEFT JOIN newbook_net_revenue_data r ON s.date = r.date
            WHERE s.date >= :history_start
            AND s.date < :today
            AND s.booking_count IS NOT NULL
            ORDER BY s.date
        """
    else:
        query = f"""
            SELECT s.date as ds, {column_expr} as y
            FROM newbook_bookings_stats s
            WHERE s.date >= :history_start
            AND s.date < :today
            AND s.booking_count IS NOT NULL
            ORDER BY s.date
        """

    history_result = db.execute(text(query), {"history_start": history_start, "today": today})
    history_rows = history_result.fetchall()

    if len(history_rows) < 30:
        logger.warning(f"Insufficient data for Prophet at perception_date {perception_date}")
        return 0

    # Build training dataframe, filtering out NULL values
    df = pd.DataFrame([{"ds": row.ds, "y": float(row.y)} for row in history_rows if row.y is not None])
    df['ds'] = pd.to_datetime(df['ds'])

    if len(df) < 30:
        logger.warning(f"Insufficient non-null data for Prophet at perception_date {perception_date}")
        return 0

    # Convert to occupancy percentage if needed
    if metric == "occupancy" and total_rooms > 0:
        df["y"] = (df["y"] / total_rooms) * 100

    # Determine cap for logistic growth based on metric type
    if is_pct_metric:
        training_cap = 100
    elif metric == 'rooms':
        training_cap = total_rooms
    elif metric == 'guests':
        training_cap = df["y"].max() * 1.5 if len(df) > 0 and df["y"].max() > 0 else total_rooms * 3
    else:
        # Revenue/rate metrics - use 99th percentile * 1.5
        training_cap = df["y"].quantile(0.99) * 1.5 if len(df) > 0 and df["y"].quantile(0.99) > 0 else 10000

    df["floor"] = 0
    df["cap"] = training_cap

    # Train Prophet model with logistic growth
    model = Prophet(
        growth='logistic',
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        seasonality_mode='multiplicative'
    )
    model.fit(df)

    # Create future dataframe
    future = model.make_future_dataframe(periods=forecast_days)
    future = future[future['ds'] >= pd.Timestamp(today)]
    future["floor"] = 0
    future["cap"] = training_cap

    # Predict
    forecast = model.predict(future)

    # Store snapshots
    snapshots_stored = 0
    for _, row in forecast.iterrows():
        target_date = row['ds'].date()
        lead_days = (target_date - today).days
        yhat = float(row['yhat'])

        # Cap based on metric type
        if is_pct_metric:
            yhat = min(max(yhat, 0), 100.0)
        elif metric == 'rooms':
            yhat = round(min(max(yhat, 0), float(total_rooms)))
        elif metric == 'guests':
            yhat = round(max(yhat, 0))  # No upper cap for guests, just floor at 0
        else:
            # Revenue/rate metrics - round to 2 decimal places
            yhat = round(max(yhat, 0), 2)

        db.execute(text("""
            INSERT INTO forecast_snapshots
                (perception_date, target_date, model, metric_code, days_out, forecast_value)
            VALUES
                (:perception_date, :target_date, :model_name, :metric, :days_out, :forecast_value)
            ON CONFLICT (perception_date, target_date, model, metric_code)
            DO UPDATE SET forecast_value = :forecast_value, created_at = NOW()
        """), {
            "perception_date": perception_date,
            "target_date": target_date,
            "model_name": model_name,
            "metric": metric,
            "days_out": lead_days,
            "forecast_value": round(yhat, 2)
        })

        snapshots_stored += 1

    return snapshots_stored


async def run_catboost_backtest(
    db,
    perception_date: date,
    forecast_days: int,
    metric: str,
    training_start: Optional[date] = None,
    model_name: str = "catboost"
) -> int:
    """
    Run CatBoost forecast from a specific perception date and store snapshots.

    For occupancy/rooms: Uses pace data (OTB at different lead times) as features.
    For other metrics: Uses time-series features only.

    Args:
        training_start: Optional cutoff date - only use training data from this date forward
        model_name: Name to store in snapshots (e.g., 'catboost' or 'catboost_postcovid')

    Returns count of snapshots stored.
    """
    from catboost import CatBoostRegressor

    today = perception_date

    # Check if this metric has pace data
    pace_metrics = ['occupancy', 'rooms']
    use_pace = metric in pace_metrics

    # Get metric query info
    metric_info = get_metric_query_info(metric)
    column_expr = metric_info['column_expr']
    needs_revenue_join = metric_info['needs_revenue_join']
    is_pct_metric = metric_info['is_pct_metric']
    is_revenue_metric = metric_info['is_revenue_metric']

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

    # Get historical data for training (2 years before perception date, or from training_start)
    history_start = today - timedelta(days=730)
    if training_start and training_start > history_start:
        history_start = training_start

    # Build query based on metric type
    if use_pace:
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
    elif needs_revenue_join:
        history_result = db.execute(text(f"""
            SELECT s.date as ds, {column_expr} as final
            FROM newbook_bookings_stats s
            LEFT JOIN newbook_net_revenue_data r ON s.date = r.date
            WHERE s.date >= :history_start
            AND s.date < :today
            AND s.booking_count IS NOT NULL
            ORDER BY s.date
        """), {"history_start": history_start, "today": today})
    else:
        history_result = db.execute(text(f"""
            SELECT s.date as ds, {column_expr} as final
            FROM newbook_bookings_stats s
            WHERE s.date >= :history_start
            AND s.date < :today
            AND s.booking_count IS NOT NULL
            ORDER BY s.date
        """), {"history_start": history_start, "today": today})

    history_rows = history_result.fetchall()

    if len(history_rows) < 30:
        logger.warning(f"Insufficient data for CatBoost at perception_date {perception_date}")
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
    final_by_date = {}
    for row in history_rows:
        if row.final is not None:
            final_by_date[row.ds] = row.final

    if use_pace:
        # Pace-based training
        train_lead_times = [0, 1, 3, 7, 14, 21, 28, 30]
        pace_by_date = {}
        for row in history_rows:
            pace_by_date[row.ds] = {
                0: row.d0, 1: row.d1, 3: row.d3, 7: row.d7,
                14: row.d14, 21: row.d21, 28: row.d28, 30: row.d30
            }

        training_rows = []
        for row in history_rows:
            ds = row.ds
            if row.final is None:
                continue
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
            logger.warning(f"Insufficient training data for CatBoost at perception_date {perception_date}")
            return 0

        df = pd.DataFrame(training_rows)
        df['ds'] = pd.to_datetime(df['ds'])

        # Convert to occupancy if needed
        if metric == "occupancy" and total_rooms > 0:
            df["y"] = (df["y"] / total_rooms) * 100
            df["current_otb"] = (df["current_otb"] / total_rooms) * 100
            df["prior_otb_same_lead"] = (df["prior_otb_same_lead"] / total_rooms) * 100
            df["lag_364"] = (df["lag_364"] / total_rooms) * 100

        categorical_features = ['day_of_week', 'month']
        numerical_features = ['week_of_year', 'is_weekend', 'is_special_date',
                             'days_out', 'current_otb', 'prior_otb_same_lead',
                             'lag_364', 'otb_pct_of_prior_final']
        feature_cols = categorical_features + numerical_features
    else:
        # Non-pace training for other metrics
        training_rows = []
        for row in history_rows:
            ds = row.ds
            if row.final is None:
                continue
            final = float(row.final)
            prior_ds = ds - timedelta(days=364)

            prior_final = final_by_date.get(prior_ds)
            if prior_final is None:
                prior_final = final

            training_rows.append({
                'ds': ds,
                'y': final,
                'lag_364': float(prior_final),
            })

        if len(training_rows) < 30:
            logger.warning(f"Insufficient training data for CatBoost at perception_date {perception_date}")
            return 0

        df = pd.DataFrame(training_rows)
        df['ds'] = pd.to_datetime(df['ds'])

        categorical_features = ['day_of_week', 'month']
        numerical_features = ['week_of_year', 'is_weekend', 'is_special_date', 'lag_364']
        feature_cols = categorical_features + numerical_features

    # Create time features - CatBoost uses categorical features natively
    df['day_of_week'] = df['ds'].dt.dayofweek.astype(str)  # Categorical for CatBoost
    df['month'] = df['ds'].dt.month.astype(str)  # Categorical for CatBoost
    df['week_of_year'] = df['ds'].dt.isocalendar().week.astype(int)
    df['is_weekend'] = (df['ds'].dt.dayofweek >= 5).astype(int)
    df['is_special_date'] = df['ds'].dt.date.apply(lambda x: 1 if x in special_date_set else 0)

    df_train = df.dropna()

    if len(df_train) < 30:
        return 0

    # Determine training cap for predictions
    if is_pct_metric:
        training_cap = 100
    elif metric == 'rooms':
        training_cap = total_rooms
    elif metric == 'guests':
        training_cap = df_train["y"].max() * 1.5 if len(df_train) > 0 and df_train["y"].max() > 0 else total_rooms * 3
    else:
        training_cap = df_train["y"].quantile(0.99) * 1.5 if len(df_train) > 0 and df_train["y"].quantile(0.99) > 0 else 10000

    X_train = df_train[feature_cols]
    y_train = df_train['y']

    # Train CatBoost model
    cat_model = CatBoostRegressor(
        iterations=200,
        depth=6,
        learning_rate=0.1,
        loss_function='RMSE',
        cat_features=categorical_features,
        verbose=False,
        random_seed=42
    )
    cat_model.fit(X_train, y_train)

    # Generate forecasts
    snapshots_stored = 0
    end_date = today + timedelta(days=forecast_days)

    current_date = today
    while current_date <= end_date:
        lead_days = (current_date - today).days
        prior_year_date = current_date - timedelta(days=364)

        if use_pace:
            lead_col = get_lead_time_column(lead_days)

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
                'day_of_week': str(forecast_dt.dayofweek),
                'month': str(forecast_dt.month),
                'week_of_year': forecast_dt.isocalendar().week,
                'is_weekend': 1 if forecast_dt.dayofweek >= 5 else 0,
                'is_special_date': 1 if current_date in special_date_set else 0,
                'days_out': lead_days,
                'current_otb': current_otb,
                'prior_otb_same_lead': prior_otb,
                'lag_364': lag_364_val,
                'otb_pct_of_prior_final': otb_pct_of_prior_final,
            }])
        else:
            # Non-pace prediction
            lag_364_val = final_by_date.get(prior_year_date)
            if lag_364_val is None:
                lag_364_val = float(df_train["y"].mean())
            else:
                lag_364_val = float(lag_364_val)

            forecast_dt = pd.Timestamp(current_date)
            features = pd.DataFrame([{
                'day_of_week': str(forecast_dt.dayofweek),
                'month': str(forecast_dt.month),
                'week_of_year': int(forecast_dt.isocalendar().week),
                'is_weekend': 1 if forecast_dt.dayofweek >= 5 else 0,
                'is_special_date': 1 if current_date in special_date_set else 0,
                'lag_364': lag_364_val,
            }])

        # Predict
        yhat = float(cat_model.predict(features)[0])

        # Cap based on metric type
        if is_pct_metric:
            yhat = min(max(yhat, 0), 100.0)
        elif metric == 'rooms':
            yhat = round(min(max(yhat, 0), float(total_rooms)))
        elif metric == 'guests':
            yhat = round(max(yhat, 0))
        else:
            yhat = round(max(yhat, 0), 2)

        # Store snapshot
        db.execute(text("""
            INSERT INTO forecast_snapshots
                (perception_date, target_date, model, metric_code, days_out, forecast_value)
            VALUES
                (:perception_date, :target_date, :model_name, :metric, :days_out, :forecast_value)
            ON CONFLICT (perception_date, target_date, model, metric_code)
            DO UPDATE SET forecast_value = :forecast_value, created_at = NOW()
        """), {
            "perception_date": perception_date,
            "target_date": current_date,
            "model_name": model_name,
            "metric": metric,
            "days_out": lead_days,
            "forecast_value": round(yhat, 2)
        })

        snapshots_stored += 1
        current_date += timedelta(days=1)

    return snapshots_stored


async def run_blended_backtest(
    db,
    perception_date: date,
    forecast_days: int,
    metric: str,
    training_start: Optional[date] = None,
    model_name: str = "blended"
) -> int:
    """
    Create blended forecast by averaging Prophet, XGBoost, and CatBoost predictions.

    This function reads existing forecasts from forecast_snapshots and creates
    a blended average. Run this AFTER running the individual models.

    Args:
        training_start: Used to determine if we should look for _postcovid model variants
        model_name: Name to store in snapshots (e.g., 'blended' or 'blended_postcovid')

    Returns count of snapshots stored.
    """
    suffix = "_postcovid" if training_start else ""
    models_to_blend = [f"prophet{suffix}", f"xgboost{suffix}", f"catboost{suffix}"]

    # Get all forecasts from the three models for this perception date and metric
    result = db.execute(text("""
        SELECT target_date, model, forecast_value
        FROM forecast_snapshots
        WHERE perception_date = :perception_date
        AND metric_code = :metric
        AND model IN :models
        ORDER BY target_date
    """), {
        "perception_date": perception_date,
        "metric": metric,
        "models": tuple(models_to_blend)
    })
    rows = result.fetchall()

    if not rows:
        logger.warning(f"No model forecasts found for blending at {perception_date}/{metric}")
        return 0

    # Group by target_date
    forecasts_by_date = {}
    for row in rows:
        if row.target_date not in forecasts_by_date:
            forecasts_by_date[row.target_date] = {}
        forecasts_by_date[row.target_date][row.model] = float(row.forecast_value)

    # Calculate blended average for each target date
    snapshots_stored = 0
    for target_date, model_forecasts in forecasts_by_date.items():
        # Only blend if we have at least 2 models
        if len(model_forecasts) < 2:
            continue

        # Calculate average
        values = list(model_forecasts.values())
        blended_value = sum(values) / len(values)

        days_out = (target_date - perception_date).days

        # Store blended snapshot
        db.execute(text("""
            INSERT INTO forecast_snapshots
                (perception_date, target_date, model, metric_code, days_out, forecast_value)
            VALUES
                (:perception_date, :target_date, :model_name, :metric, :days_out, :forecast_value)
            ON CONFLICT (perception_date, target_date, model, metric_code)
            DO UPDATE SET forecast_value = :forecast_value, created_at = NOW()
        """), {
            "perception_date": perception_date,
            "target_date": target_date,
            "model_name": model_name,
            "metric": metric,
            "days_out": days_out,
            "forecast_value": round(blended_value, 2)
        })

        snapshots_stored += 1

    return snapshots_stored


async def backfill_actuals():
    """
    Backfill actual_value in forecast_snapshots from newbook_bookings_stats and newbook_net_revenue_data.
    Run this after target_date has passed.

    Handles all metrics:
    - occupancy: booking_count / bookable_count * 100
    - rooms: booking_count
    - guests: guests_count
    - ave_guest_rate: guest_rate_total / booking_count
    - arr: accommodation / booking_count (from revenue data)
    - net_accom, net_dry, net_wet: from revenue data
    """
    db = SyncSessionLocal()

    try:
        # First, update stats-based metrics (occupancy, rooms, guests, ave_guest_rate)
        result1 = db.execute(text("""
            UPDATE forecast_snapshots fs
            SET actual_value = CASE
                WHEN fs.metric_code = 'occupancy' THEN
                    (s.booking_count::decimal / NULLIF(s.bookable_count, 0)) * 100
                WHEN fs.metric_code = 'rooms' THEN
                    s.booking_count
                WHEN fs.metric_code = 'guests' THEN
                    s.guests_count
                WHEN fs.metric_code = 'ave_guest_rate' THEN
                    s.guest_rate_total / NULLIF(s.booking_count, 0)
                ELSE NULL
            END
            FROM newbook_bookings_stats s
            WHERE fs.target_date = s.date
            AND fs.actual_value IS NULL
            AND fs.target_date < CURRENT_DATE
            AND fs.metric_code IN ('occupancy', 'rooms', 'guests', 'ave_guest_rate')
            AND s.booking_count IS NOT NULL
        """))

        # Then, update revenue-based metrics (arr, net_accom, net_dry, net_wet)
        result2 = db.execute(text("""
            UPDATE forecast_snapshots fs
            SET actual_value = CASE
                WHEN fs.metric_code = 'arr' THEN
                    r.accommodation / NULLIF(s.booking_count, 0)
                WHEN fs.metric_code = 'net_accom' THEN
                    r.accommodation
                WHEN fs.metric_code = 'net_dry' THEN
                    r.dry
                WHEN fs.metric_code = 'net_wet' THEN
                    r.wet
                ELSE NULL
            END
            FROM newbook_net_revenue_data r
            JOIN newbook_bookings_stats s ON r.date = s.date
            WHERE fs.target_date = r.date
            AND fs.actual_value IS NULL
            AND fs.target_date < CURRENT_DATE
            AND fs.metric_code IN ('arr', 'net_accom', 'net_dry', 'net_wet')
        """))

        db.commit()
        count = result1.rowcount + result2.rowcount
        logger.info(f"Backfilled {count} actual values")
        return count

    finally:
        db.close()
