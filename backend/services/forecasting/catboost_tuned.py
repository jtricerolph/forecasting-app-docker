"""
CatBoost Tuned Model Service

This is the production-tuned CatBoost model extracted from the catboost-preview endpoint.
Uses the exact same logic as the frontend preview to ensure value consistency.

Features:
- 2 years of training data
- Native categorical feature support (day_of_week, month)
- Pace features (OTB at different lead times) for room-based metrics
- Time-based features
- Lag features from prior year
- OTB floor capping
- Per-date bookable cap adjustments
"""
import logging
from datetime import date, timedelta
from typing import List, Dict, Optional
import pandas as pd
import numpy as np
from catboost import CatBoostRegressor
import warnings
from sqlalchemy import text

from utils.capacity import get_bookable_cap
from api.special_dates import resolve_special_date

logger = logging.getLogger(__name__)
warnings.filterwarnings('ignore')


# Metric configuration mapping
METRIC_COLUMN_MAP = {
    'occupancy': ('s.occupancy_pct', False, True),
    'rooms': ('s.booking_count', False, False),
    'guests': ('s.guest_count', False, False),
    'ave_guest_rate': ('s.arr_net', False, False),
    'arr': ('s.arr_net', False, False),
    'net_accom': ('r.accommodation', True, False),
    'net_dry': ('r.dry', True, False),
    'net_wet': ('r.wet', True, False),
    'total_rev': ('(COALESCE(r.accommodation, 0) + COALESCE(r.dry, 0) + COALESCE(r.wet, 0))', True, False),
}


def get_metric_query_parts(metric: str) -> tuple:
    """Get SQL query parts for a metric. Returns: (column_expr, from_clause, is_percentage)"""
    if metric not in METRIC_COLUMN_MAP:
        metric = 'rooms'
    col_expr, needs_revenue, is_pct = METRIC_COLUMN_MAP[metric]
    if needs_revenue:
        from_clause = """
            FROM newbook_bookings_stats s
            LEFT JOIN newbook_net_revenue_data r ON s.date = r.date
        """
    else:
        from_clause = "FROM newbook_bookings_stats s"
    return col_expr, from_clause, is_pct


def get_lead_time_column(lead_days: int) -> str:
    """Map lead days to the appropriate column in newbook_booking_pace."""
    if lead_days <= 0:
        return "d0"
    elif lead_days <= 30:
        return f"d{lead_days}"
    elif lead_days <= 177:
        weekly_cols = [37, 44, 51, 58, 65, 72, 79, 86, 93, 100, 107, 114, 121, 128, 135, 142, 149, 156, 163, 170, 177]
        for col in weekly_cols:
            if lead_days <= col:
                return f"d{col}"
        return "d177"
    else:
        monthly_cols = [210, 240, 270, 300, 330, 365]
        for col in monthly_cols:
            if lead_days <= col:
                return f"d{col}"
        return "d365"


def round_towards_reference(value: float, reference: Optional[float]) -> int:
    """Round a forecast value towards a reference value (prior year actual)."""
    if reference is None:
        return round(value)
    if value < reference:
        return int(np.ceil(value))
    else:
        return int(np.floor(value))


async def run_catboost_tuned_forecast(
    db,
    metric_code: str,
    start_date: date,
    end_date: date,
    perception_date: Optional[date] = None
) -> List[Dict]:
    """
    Generate CatBoost forecast using production-tuned model.

    This uses the exact same logic as the catboost-preview endpoint to ensure
    backend snapshots match frontend preview values.

    Args:
        db: Database session
        metric_code: Metric to forecast
        start_date: Start date for forecast
        end_date: End date for forecast
        perception_date: Optional date to generate forecast as-of (for backtesting)

    Returns:
        List of forecast dicts with forecast_date and predicted_value
    """
    logger.info(f"Running CatBoost tuned forecast for {metric_code}: {start_date} to {end_date}")

    # Map metric codes to preview endpoint metric names
    metric_map = {
        'hotel_occupancy_pct': 'occupancy',
        'hotel_room_nights': 'rooms',
        'hotel_guests': 'guests',
        'hotel_arr': 'arr',
        'ave_guest_rate': 'ave_guest_rate',
        'net_accom': 'net_accom',
        'net_dry': 'net_dry',
        'net_wet': 'net_wet',
        'total_rev': 'total_rev',
    }

    metric = metric_map.get(metric_code, 'rooms')

    # Use perception_date if provided, otherwise use actual today
    today = perception_date if perception_date else date.today()

    # Get default bookable cap
    default_bookable_cap = await get_bookable_cap(db)

    # Get metric column and query parts
    col_expr, from_clause, is_pct_metric = get_metric_query_parts(metric)
    is_room_based = metric in ('occupancy', 'rooms')

    # Get historical data (2+ years for YoY features)
    history_start = today - timedelta(days=730)

    # Lead times to train on (only used for room-based metrics)
    train_lead_times = [0, 1, 3, 7, 14, 21, 28, 30]

    # Get final values (and pace data for room-based metrics)
    if is_room_based:
        history_result = await db.execute(text("""
            SELECT s.date as ds, s.booking_count as final,
                   p.d0, p.d1, p.d3, p.d7, p.d14, p.d21, p.d28, p.d30
            FROM newbook_bookings_stats s
            LEFT JOIN newbook_booking_pace p ON s.date = p.arrival_date
            WHERE s.date >= :history_start
            AND s.date < :today
            AND s.booking_count IS NOT NULL
            ORDER BY s.date
        """), {"history_start": history_start, "today": today})
    else:
        # Non-room metrics: get values without pace join
        history_query = f"""
            SELECT s.date as ds, {col_expr} as final
            {from_clause}
            WHERE s.date >= :history_start
            AND s.date < :today
            AND {col_expr} IS NOT NULL
            ORDER BY s.date
        """
        history_result = await db.execute(text(history_query), {"history_start": history_start, "today": today})

    history_rows = history_result.fetchall()

    if len(history_rows) < 30:
        logger.warning(f"Insufficient historical data for CatBoost model: {len(history_rows)} rows")
        return []

    # Load special dates for feature
    special_date_set = set()
    try:
        special_dates_result = await db.execute(text(
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
    except Exception as e:
        logger.warning(f"Could not load special dates: {e}")

    # Build lookup dicts
    final_by_date = {}
    pace_by_date = {}
    for row in history_rows:
        final_by_date[row.ds] = row.final
        if is_room_based and hasattr(row, 'd0'):
            pace_by_date[row.ds] = {
                0: row.d0, 1: row.d1, 3: row.d3, 7: row.d7,
                14: row.d14, 21: row.d21, 28: row.d28, 30: row.d30
            }

    # Build training examples
    training_rows = []

    if is_room_based:
        # Room-based metrics: use pace features (one per date,lead_time combo)
        for row in history_rows:
            ds = row.ds
            final = float(row.final) if row.final else 0
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
    else:
        # Non-room metrics: use time features only (one per date)
        for row in history_rows:
            ds = row.ds
            final = float(row.final) if row.final else 0
            prior_ds = ds - timedelta(days=364)

            prior_final = final_by_date.get(prior_ds)
            if prior_final is None:
                prior_final = 0  # Allow training even without prior year for revenue metrics

            training_rows.append({
                'ds': ds,
                'y': final,
                'lag_364': float(prior_final) if prior_final else 0
            })

    if len(training_rows) < 30:
        logger.warning(f"Insufficient data for CatBoost training: {len(training_rows)} rows")
        return []

    df = pd.DataFrame(training_rows)
    df['ds'] = pd.to_datetime(df['ds'])

    # Convert to occupancy if needed
    if metric == "occupancy" and default_bookable_cap > 0:
        df["y"] = (df["y"] / default_bookable_cap) * 100
        if "current_otb" in df.columns:
            df["current_otb"] = (df["current_otb"] / default_bookable_cap) * 100
        if "prior_otb_same_lead" in df.columns:
            df["prior_otb_same_lead"] = (df["prior_otb_same_lead"] / default_bookable_cap) * 100
        df["lag_364"] = (df["lag_364"] / default_bookable_cap) * 100

    # Create features - CatBoost handles categoricals natively
    df['day_of_week'] = df['ds'].dt.dayofweek.astype(str)  # Categorical
    df['month'] = df['ds'].dt.month.astype(str)  # Categorical
    df['week_of_year'] = df['ds'].dt.isocalendar().week.astype(int)
    df['is_weekend'] = (df['ds'].dt.dayofweek >= 5).astype(int)
    df['is_special_date'] = df['ds'].dt.date.apply(lambda x: 1 if x in special_date_set else 0)

    df_train = df.dropna()

    if len(df_train) < 30:
        logger.warning(f"Insufficient data after creating features: {len(df_train)} rows")
        return []

    # Define features based on metric type - categoricals handled natively by CatBoost
    categorical_features = ['day_of_week', 'month']
    if is_room_based:
        numerical_features = ['week_of_year', 'is_weekend', 'is_special_date',
                             'days_out', 'current_otb', 'prior_otb_same_lead', 'lag_364', 'otb_pct_of_prior_final']
    else:
        numerical_features = ['week_of_year', 'is_weekend', 'is_special_date', 'lag_364']
    feature_cols = categorical_features + numerical_features

    X_train = df_train[feature_cols]
    y_train = df_train['y']

    # Train CatBoost model
    model = CatBoostRegressor(
        iterations=150,
        depth=6,
        learning_rate=0.1,
        loss_function='RMSE',
        cat_features=categorical_features,
        verbose=False,
        random_seed=42
    )
    model.fit(X_train, y_train)

    # Create future dataframe for forecast period
    future_dates = []
    current_date = start_date
    while current_date <= end_date:
        if (current_date - today).days >= 0:
            future_dates.append(current_date)
        current_date += timedelta(days=1)

    if not future_dates:
        logger.warning("No future dates to forecast")
        return []

    # Generate forecasts for each date
    forecasts = []

    for forecast_date in future_dates:
        lead_days = (forecast_date - today).days
        lead_col = get_lead_time_column(lead_days)
        prior_year_date = forecast_date - timedelta(days=364)

        # Get OTB data only for room-based metrics
        current_otb = None

        if is_room_based:
            current_query = text("""
                SELECT booking_count as current_otb
                FROM newbook_bookings_stats
                WHERE date = :arrival_date
            """)
            current_result = await db.execute(current_query, {"arrival_date": forecast_date})
            current_row = current_result.fetchone()
            current_otb = current_row.current_otb if current_row and current_row.current_otb is not None else 0

        # Get prior year final using metric mapping
        prior_query = f"""
            SELECT {col_expr} as prior_final
            {from_clause}
            WHERE s.date = :prior_date
        """
        prior_result = await db.execute(text(prior_query), {"prior_date": prior_year_date})
        prior_row = prior_result.fetchone()
        prior_final = float(prior_row.prior_final) if prior_row and prior_row.prior_final is not None else 0

        # Get per-date bookable cap
        date_bookable_cap = await get_bookable_cap(db, forecast_date, default_bookable_cap)

        forecast_dt = pd.Timestamp(forecast_date)
        lag_364_val = prior_final if prior_final else 0

        # Convert to occupancy if needed
        if metric == "occupancy" and date_bookable_cap > 0:
            if current_otb is not None:
                current_otb = (current_otb / date_bookable_cap) * 100
            lag_364_val = (prior_final / date_bookable_cap) * 100 if prior_final else 0

        # Build features based on metric type
        if is_room_based:
            # Get prior OTB at same lead time
            prior_year_for_otb = forecast_date - timedelta(days=364)
            prior_otb_query = text(f"""
                SELECT {lead_col} as prior_otb
                FROM newbook_booking_pace
                WHERE arrival_date = :prior_date
            """)
            prior_otb_result = await db.execute(prior_otb_query, {"prior_date": prior_year_for_otb})
            prior_otb_row = prior_otb_result.fetchone()
            prior_otb_same_lead = prior_otb_row.prior_otb if prior_otb_row and prior_otb_row.prior_otb is not None else 0

            if metric == "occupancy" and date_bookable_cap > 0:
                prior_otb_same_lead = (prior_otb_same_lead / date_bookable_cap) * 100 if prior_otb_same_lead else 0

            current_otb_val = current_otb if current_otb is not None else 0
            otb_pct_of_prior_final = (current_otb_val / lag_364_val * 100) if lag_364_val > 0 else 0

            features = pd.DataFrame([{
                'day_of_week': str(forecast_dt.dayofweek),  # Categorical
                'month': str(forecast_dt.month),  # Categorical
                'week_of_year': forecast_dt.isocalendar().week,
                'is_weekend': 1 if forecast_dt.dayofweek >= 5 else 0,
                'is_special_date': 1 if forecast_date in special_date_set else 0,
                'days_out': lead_days,
                'current_otb': current_otb_val,
                'prior_otb_same_lead': prior_otb_same_lead,
                'lag_364': lag_364_val,
                'otb_pct_of_prior_final': otb_pct_of_prior_final,
            }])
        else:
            features = pd.DataFrame([{
                'day_of_week': str(forecast_dt.dayofweek),  # Categorical
                'month': str(forecast_dt.month),  # Categorical
                'week_of_year': forecast_dt.isocalendar().week,
                'is_weekend': 1 if forecast_dt.dayofweek >= 5 else 0,
                'is_special_date': 1 if forecast_date in special_date_set else 0,
                'lag_364': lag_364_val,
            }])

        # Predict
        yhat = float(model.predict(features)[0])

        # Cap at max capacity based on metric type (uses per-date bookable cap)
        if is_pct_metric:
            yhat = min(max(yhat, 0), 100.0)
        elif metric == 'rooms':
            yhat = round(min(max(yhat, 0), float(date_bookable_cap)))
        elif metric == 'guests':
            yhat = round(max(yhat, 0))
        else:
            # Revenue/rate metrics: just ensure non-negative
            yhat = max(yhat, 0)

        # Floor forecast to current OTB (room-based only)
        if is_room_based and current_otb is not None and yhat < current_otb:
            yhat = current_otb

        # Round based on metric type
        if metric == "occupancy":
            yhat = round(yhat, 1)
        else:
            yhat = round_towards_reference(yhat, prior_final)

        forecasts.append({
            'forecast_date': forecast_date,
            'predicted_value': yhat
        })

    logger.info(f"CatBoost tuned generated {len(forecasts)} forecasts for {metric_code}")
    return forecasts
