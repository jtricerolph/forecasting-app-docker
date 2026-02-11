"""
CatBoost forecasting model
Gradient boosting with native categorical feature support and better out-of-box performance.
Similar to XGBoost but handles categorical features natively without encoding.
"""
import logging
from datetime import date, timedelta
from typing import List, Optional
import pandas as pd
import numpy as np
import json
from sqlalchemy import text

logger = logging.getLogger(__name__)


def create_features(df: pd.DataFrame, special_dates: set = None) -> pd.DataFrame:
    """
    Create features for CatBoost model.

    CatBoost handles categorical features natively, so we keep day_of_week as categorical
    instead of using cyclical encoding.
    """
    df = df.copy()

    # Date features - keep as categorical for CatBoost
    df['day_of_week'] = df['ds'].dt.dayofweek.astype(str)  # Categorical
    df['month'] = df['ds'].dt.month.astype(str)  # Categorical
    df['day_of_month'] = df['ds'].dt.day
    df['week_of_year'] = df['ds'].dt.isocalendar().week.astype(int)
    df['is_weekend'] = (df['ds'].dt.dayofweek >= 5).astype(int)

    # Special dates / holidays
    if special_dates and len(special_dates) > 0:
        df['is_holiday'] = df['ds'].dt.date.apply(lambda x: 1 if x in special_dates else 0)

        # Days to nearest special date
        def days_to_nearest(d):
            if not special_dates:
                return 30
            future = [s for s in special_dates if s >= d]
            if not future:
                return 30
            return min((s - d).days for s in future)

        df['days_to_holiday'] = df['ds'].dt.date.apply(days_to_nearest)
    else:
        df['is_holiday'] = 0
        df['days_to_holiday'] = 30

    # Lag features
    for lag in [7, 14, 21, 28]:
        df[f'lag_{lag}'] = df['y'].shift(lag)

    # Rolling averages
    for window in [7, 14, 28]:
        df[f'rolling_mean_{window}'] = df['y'].rolling(window=window, min_periods=1).mean()
        df[f'rolling_std_{window}'] = df['y'].rolling(window=window, min_periods=1).std().fillna(0)

    # Year-over-year feature (364 days for DOW alignment)
    if len(df) > 364:
        df['lag_364'] = df['y'].shift(364)

    return df


async def run_catboost_forecast(
    db,
    metric_code: str,
    forecast_from: date,
    forecast_to: date,
    training_days: int = 2555,  # ~7 years
    use_special_dates: bool = True,
    use_otb_data: bool = True
) -> List[dict]:
    """
    Run CatBoost forecast for a metric.

    Args:
        db: Database session
        metric_code: Metric to forecast
        forecast_from: Start date for forecasts
        forecast_to: End date for forecasts
        training_days: Days of historical data to use
        use_special_dates: Include holiday features
        use_otb_data: Include OTB pickup features

    Returns:
        List of forecast records
    """
    try:
        from catboost import CatBoostRegressor

        # Get historical data
        training_from = forecast_from - timedelta(days=training_days + 400)  # Extra for lag features

        # Revenue metrics use earned_revenue_data joined with gl_accounts
        revenue_metrics = ['net_accom', 'net_dry', 'net_wet', 'total_rev']
        if metric_code in revenue_metrics:
            revenue_departments = {
                'net_accom': 'accommodation',
                'net_dry': 'dry',
                'net_wet': 'wet',
                'total_rev': None,  # All departments
            }
            department = revenue_departments.get(metric_code)
            if department is None and metric_code != 'total_rev':
                logger.warning(f"Unknown revenue metric for CatBoost: {metric_code}")
                return []

            if metric_code == 'total_rev':
                # Total revenue across all departments
                result = db.execute(
                    text("""
                    SELECT date, SUM(amount_net) as actual_value
                    FROM newbook_earned_revenue_data
                    WHERE date BETWEEN :from_date AND :to_date
                    GROUP BY date
                    HAVING SUM(amount_net) IS NOT NULL
                    ORDER BY date
                    """),
                    {"from_date": training_from, "to_date": forecast_from - timedelta(days=1)}
                )
            else:
                # Revenue by department
                result = db.execute(
                    text("""
                    SELECT r.date, SUM(r.amount_net) as actual_value
                    FROM newbook_earned_revenue_data r
                    JOIN newbook_gl_accounts g ON r.gl_account_id = g.gl_account_id
                    WHERE r.date BETWEEN :from_date AND :to_date
                        AND g.department = :department
                    GROUP BY r.date
                    HAVING SUM(r.amount_net) IS NOT NULL
                    ORDER BY r.date
                    """),
                    {"from_date": training_from, "to_date": forecast_from - timedelta(days=1), "department": department}
                )
        else:
            # Hotel metrics use newbook_bookings_stats table
            metric_column_map = {
                'hotel_occupancy_pct': 'total_occupancy_pct',
                'hotel_room_nights': 'booking_count',
                'hotel_guests': 'guests_count',
            }

            column_name = metric_column_map.get(metric_code)
            if not column_name:
                logger.warning(f"Unknown metric_code for CatBoost: {metric_code}")
                return []

            result = db.execute(
                text(f"""
                SELECT date, {column_name} as actual_value
                FROM newbook_bookings_stats
                WHERE date BETWEEN :from_date AND :to_date
                    AND {column_name} IS NOT NULL
                ORDER BY date
                """),
                {"from_date": training_from, "to_date": forecast_from - timedelta(days=1)}
            )

        rows = result.fetchall()

        if len(rows) < 60:
            logger.warning(f"Insufficient data for CatBoost: {metric_code} has {len(rows)} records")
            return []

        # Prepare DataFrame
        df = pd.DataFrame([{"ds": pd.Timestamp(row.date), "y": float(row.actual_value)} for row in rows])
        df = df.sort_values('ds').reset_index(drop=True)

        # Load special dates if enabled
        special_dates = None
        if use_special_dates:
            special_dates = await _load_special_dates(db, forecast_from, forecast_to)

        # Create features
        df = create_features(df, special_dates)

        # Add OTB features if enabled
        if use_otb_data:
            otb_df = _load_otb_data(db, training_from, forecast_from)
            if otb_df is not None and len(otb_df) > 0:
                df = _add_otb_features(df, otb_df)
                logger.info("Added OTB features to CatBoost training data")

        # Remove rows with NaN from lag features
        df = df.dropna(subset=['lag_7', 'lag_14', 'lag_21', 'lag_28'])

        # Define feature columns
        categorical_features = ['day_of_week', 'month']

        numerical_features = [
            'day_of_month', 'week_of_year', 'is_weekend',
            'is_holiday', 'days_to_holiday',
            'lag_7', 'lag_14', 'lag_21', 'lag_28',
            'rolling_mean_7', 'rolling_mean_14', 'rolling_mean_28',
            'rolling_std_7', 'rolling_std_14', 'rolling_std_28'
        ]

        # Add lag_364 if available
        if 'lag_364' in df.columns and df['lag_364'].notna().sum() > 30:
            numerical_features.append('lag_364')

        # Add OTB features if present
        otb_cols = ['otb_at_30d', 'otb_at_14d', 'otb_at_7d',
                    'pickup_30d_to_14d', 'pickup_14d_to_7d',
                    'otb_pct_at_30d', 'otb_pct_at_14d', 'otb_pct_at_7d']
        for col in otb_cols:
            if col in df.columns:
                numerical_features.append(col)

        feature_cols = categorical_features + numerical_features

        X = df[feature_cols].copy()
        y = df['y']

        # Train CatBoost model
        model = CatBoostRegressor(
            iterations=200,
            depth=6,
            learning_rate=0.1,
            loss_function='RMSE',
            cat_features=categorical_features,
            verbose=False,
            random_seed=42
        )
        model.fit(X, y)

        # Generate forecasts
        forecasts = []
        current_df = df.copy()

        for forecast_date in pd.date_range(start=forecast_from, end=forecast_to, freq='D'):
            # Create row for forecast date
            new_row = pd.DataFrame([{"ds": forecast_date, "y": np.nan}])
            current_df = pd.concat([current_df, new_row], ignore_index=True)
            current_df = create_features(current_df, special_dates)

            # Add OTB features for future dates if available
            if use_otb_data:
                current_df = _add_otb_features(current_df, otb_df)

            # Get features for prediction
            X_pred = current_df[feature_cols].iloc[-1:].copy()

            # Forward fill any NaN values
            for col in numerical_features:
                if col in X_pred.columns:
                    X_pred[col] = X_pred[col].ffill()
                    if X_pred[col].isna().any():
                        X_pred[col] = X_pred[col].fillna(0)

            # Make prediction
            prediction = float(model.predict(X_pred)[0])

            # Ensure non-negative
            prediction = max(0, prediction)

            # Update y value for lag features
            current_df.iloc[-1, current_df.columns.get_loc('y')] = prediction

            forecast_record = {
                "forecast_date": forecast_date.date(),
                "forecast_type": metric_code,
                "model_type": "catboost",
                "predicted_value": round(float(prediction), 2)
            }
            forecasts.append(forecast_record)

            # Store in database
            db.execute(
                text("""
                INSERT INTO forecasts (
                    forecast_date, forecast_type, model_type, predicted_value, generated_at
                ) VALUES (
                    :forecast_date, :forecast_type, :model_type, :predicted_value, NOW()
                )
                """),
                forecast_record
            )

        db.commit()

        # Calculate feature importance for explainability
        try:
            feature_importance = dict(zip(feature_cols, model.feature_importances_.tolist()))
            top_features = sorted(
                [{"feature": k, "importance": v} for k, v in feature_importance.items()],
                key=lambda x: x["importance"], reverse=True
            )[:10]

            logger.info(f"CatBoost top features: {[f['feature'] for f in top_features[:5]]}")
        except Exception as e:
            logger.warning(f"Feature importance calculation failed: {e}")

        logger.info(f"CatBoost forecast generated for {metric_code}: {len(forecasts)} records")
        return forecasts

    except ImportError as e:
        logger.error(f"CatBoost not installed: {e}")
        return []
    except Exception as e:
        logger.error(f"CatBoost forecast failed for {metric_code}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


async def _load_special_dates(db, from_date: date, to_date: date) -> set:
    """Load special dates from system_config."""
    try:
        result = db.execute(text("""
            SELECT config_value FROM system_config
            WHERE config_key = 'special_dates'
        """))
        row = result.fetchone()

        if not row or not row.config_value:
            return set()

        dates_json = json.loads(row.config_value)
        special_dates = set()

        for item in dates_json:
            if isinstance(item, dict) and 'date' in item:
                try:
                    d = pd.to_datetime(item['date']).date()
                    special_dates.add(d)
                except:
                    pass

        logger.info(f"Loaded {len(special_dates)} special dates for CatBoost")
        return special_dates

    except Exception as e:
        logger.warning(f"Failed to load special dates: {e}")
        return set()


def _load_otb_data(db, from_date: date, to_date: date) -> Optional[pd.DataFrame]:
    """Load OTB (On-The-Books) data."""
    try:
        result = db.execute(text("""
            SELECT
                arrival_date,
                d93 as otb_at_90d,
                d65 as otb_at_60d,
                d30 as otb_at_30d,
                d14 as otb_at_14d,
                d7 as otb_at_7d,
                d0 as final_bookings
            FROM newbook_booking_pace
            WHERE arrival_date BETWEEN :from_date AND :to_date
            ORDER BY arrival_date
        """), {"from_date": from_date, "to_date": to_date})
        rows = result.fetchall()

        if not rows:
            return None

        df = pd.DataFrame([{
            "arrival_date": row.arrival_date,
            "otb_at_90d": float(row.otb_at_90d) if row.otb_at_90d else 0,
            "otb_at_60d": float(row.otb_at_60d) if row.otb_at_60d else 0,
            "otb_at_30d": float(row.otb_at_30d) if row.otb_at_30d else 0,
            "otb_at_14d": float(row.otb_at_14d) if row.otb_at_14d else 0,
            "otb_at_7d": float(row.otb_at_7d) if row.otb_at_7d else 0,
            "final_bookings": float(row.final_bookings) if row.final_bookings else 0
        } for row in rows])

        return df

    except Exception as e:
        logger.warning(f"Failed to load OTB data: {e}")
        return None


def _add_otb_features(df: pd.DataFrame, otb_df: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Add OTB features to DataFrame."""
    df = df.copy()

    if otb_df is None or len(otb_df) == 0:
        # No OTB data - set defaults
        df['otb_at_30d'] = 0
        df['otb_at_14d'] = 0
        df['otb_at_7d'] = 0
        df['pickup_30d_to_14d'] = 0
        df['pickup_14d_to_7d'] = 0
        df['otb_pct_at_30d'] = 0
        df['otb_pct_at_14d'] = 0
        df['otb_pct_at_7d'] = 0
        return df

    # Create date column for merging
    df['date_only'] = df['ds'].dt.date

    # Merge OTB data
    otb_df = otb_df.copy()
    otb_df['date_only'] = pd.to_datetime(otb_df['arrival_date']).dt.date

    # Check if columns already exist (avoid duplicates)
    merge_cols = ['date_only']
    for col in ['otb_at_90d', 'otb_at_60d', 'otb_at_30d', 'otb_at_14d', 'otb_at_7d', 'final_bookings']:
        if col not in df.columns:
            merge_cols.append(col)

    if len(merge_cols) > 1:
        df = df.merge(
            otb_df[merge_cols],
            on='date_only',
            how='left'
        )

    # Fill NaN with 0
    for col in ['otb_at_90d', 'otb_at_60d', 'otb_at_30d', 'otb_at_14d', 'otb_at_7d', 'final_bookings']:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    # Calculate pickup between windows
    if 'pickup_30d_to_14d' not in df.columns:
        df['pickup_30d_to_14d'] = df['otb_at_14d'] - df['otb_at_30d']
    if 'pickup_14d_to_7d' not in df.columns:
        df['pickup_14d_to_7d'] = df['otb_at_7d'] - df['otb_at_14d']

    # Calculate OTB as percentage of final (capped at 100%)
    if 'otb_pct_at_30d' not in df.columns:
        df['otb_pct_at_30d'] = np.where(
            df['final_bookings'] > 0,
            np.minimum(df['otb_at_30d'] / df['final_bookings'] * 100, 100),
            0
        )
    if 'otb_pct_at_14d' not in df.columns:
        df['otb_pct_at_14d'] = np.where(
            df['final_bookings'] > 0,
            np.minimum(df['otb_at_14d'] / df['final_bookings'] * 100, 100),
            0
        )
    if 'otb_pct_at_7d' not in df.columns:
        df['otb_pct_at_7d'] = np.where(
            df['final_bookings'] > 0,
            np.minimum(df['otb_at_7d'] / df['final_bookings'] * 100, 100),
            0
        )

    # Drop temporary column
    df = df.drop(columns=['date_only'], errors='ignore')

    return df
