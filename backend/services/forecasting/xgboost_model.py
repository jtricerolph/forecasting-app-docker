"""
XGBoost forecasting model
Gradient boosting with feature engineering and SHAP explainability
"""
import logging
from datetime import date, timedelta
from typing import List, Optional
import pandas as pd
import numpy as np
import json
from sqlalchemy import text

logger = logging.getLogger(__name__)


def create_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create features for XGBoost model

    Features include:
    - Day of week (0-6)
    - Month (1-12)
    - Day of month
    - Week of year
    - Is weekend
    - Is holiday (would need holiday calendar)
    - Lag features (7, 14, 28 days)
    - Rolling averages (7, 14, 28 days)
    """
    df = df.copy()

    # Date features
    df['day_of_week'] = df['ds'].dt.dayofweek
    df['month'] = df['ds'].dt.month
    df['day_of_month'] = df['ds'].dt.day
    df['week_of_year'] = df['ds'].dt.isocalendar().week.astype(int)
    df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)

    # Cyclical encoding for day of week
    df['dow_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
    df['dow_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)

    # Cyclical encoding for month
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)

    # Lag features
    for lag in [7, 14, 21, 28]:
        df[f'lag_{lag}'] = df['y'].shift(lag)

    # Rolling averages
    for window in [7, 14, 28]:
        df[f'rolling_mean_{window}'] = df['y'].rolling(window=window, min_periods=1).mean()
        df[f'rolling_std_{window}'] = df['y'].rolling(window=window, min_periods=1).std()

    # Year-over-year feature: uses 365 days (same calendar date, not DOW-aligned)
    # This is intentional for ML: captures date-specific patterns like holidays
    # Combined with day_of_week features, the model learns both patterns
    # Note: For direct comparisons (pickup model), use 364 days for DOW alignment
    if len(df) > 365:
        df['lag_365'] = df['y'].shift(365)

    return df


async def run_xgboost_forecast(
    db,
    metric_code: str,
    forecast_from: date,
    forecast_to: date,
    training_days: int = 2555  # ~7 years - use all available history
) -> List[dict]:
    """
    Run XGBoost forecast for a metric

    Args:
        db: Database session
        metric_code: Metric to forecast
        forecast_from: Start date for forecasts
        forecast_to: End date for forecasts
        training_days: Days of historical data to use

    Returns:
        List of forecast records
    """
    try:
        import xgboost as xgb
        from sklearn.model_selection import train_test_split

        # Get historical data from newbook_bookings_stats (forecast_data database)
        training_from = forecast_from - timedelta(days=training_days + 60)  # Extra for lag features

        # Map metric_code to the correct column in newbook_bookings_stats
        metric_column_map = {
            'hotel_occupancy_pct': 'total_occupancy_pct',
            'hotel_room_nights': 'booking_count',
            'hotel_guests': 'guests_count',
        }

        column_name = metric_column_map.get(metric_code)
        if not column_name:
            logger.warning(f"Unknown metric_code for XGBoost: {metric_code}")
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
            logger.warning(f"Insufficient data for XGBoost forecast: {metric_code} has {len(rows)} records")
            return []

        # Prepare data
        df = pd.DataFrame([{"ds": pd.Timestamp(row.date), "y": float(row.actual_value)} for row in rows])
        df = df.sort_values('ds').reset_index(drop=True)

        # Create features
        df = create_features(df)

        # Remove rows with NaN from lag features
        df = df.dropna()

        # Define feature columns
        feature_cols = [
            'day_of_week', 'month', 'day_of_month', 'week_of_year', 'is_weekend',
            'dow_sin', 'dow_cos', 'month_sin', 'month_cos',
            'lag_7', 'lag_14', 'lag_21', 'lag_28',
            'rolling_mean_7', 'rolling_mean_14', 'rolling_mean_28',
            'rolling_std_7', 'rolling_std_14', 'rolling_std_28'
        ]

        # Add lag_365 if available
        if 'lag_365' in df.columns and df['lag_365'].notna().sum() > 30:
            feature_cols.append('lag_365')

        X = df[feature_cols]
        y = df['y']

        # Train model
        model = xgb.XGBRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            objective='reg:squarederror',
            random_state=42
        )
        model.fit(X, y)

        # Generate forecasts
        forecasts = []
        current_df = df.copy()

        for forecast_date in pd.date_range(start=forecast_from, end=forecast_to, freq='D'):
            # Create row for forecast date
            new_row = pd.DataFrame([{"ds": forecast_date, "y": np.nan}])
            current_df = pd.concat([current_df, new_row], ignore_index=True)
            current_df = create_features(current_df)

            # Get features for prediction
            X_pred = current_df[feature_cols].iloc[-1:].ffill()

            # Make prediction
            prediction = float(model.predict(X_pred)[0])

            # Update y value for lag features
            current_df.iloc[-1, current_df.columns.get_loc('y')] = prediction

            forecast_record = {
                "forecast_date": forecast_date.date(),
                "forecast_type": metric_code,
                "model_type": "xgboost",
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

        # Commit forecasts before SHAP calculations
        db.commit()

        # Calculate SHAP values for explainability
        try:
            import shap
            explainer = shap.TreeExplainer(model)

            # Get SHAP values for last few predictions
            for i, forecast_date in enumerate(pd.date_range(start=forecast_from, end=min(forecast_from + timedelta(days=7), forecast_to), freq='D')):
                idx = len(df) + i
                X_explain = current_df[feature_cols].iloc[idx:idx+1].ffill()
                shap_values = explainer.shap_values(X_explain)

                # Store SHAP explanation
                feature_contributions = dict(zip(feature_cols, shap_values[0].tolist()))
                top_positive = sorted(
                    [{"feature": k, "contribution": v} for k, v in feature_contributions.items() if v > 0],
                    key=lambda x: x["contribution"], reverse=True
                )[:5]
                top_negative = sorted(
                    [{"feature": k, "contribution": v} for k, v in feature_contributions.items() if v < 0],
                    key=lambda x: x["contribution"]
                )[:3]

                try:
                    db.execute(
                        text("""
                        INSERT INTO xgboost_explanations (
                            forecast_date, forecast_type, base_value,
                            feature_values, shap_values, top_positive, top_negative, generated_at
                        ) VALUES (
                            :date, :metric, :base_value, :feature_values,
                            :shap_values, :top_positive, :top_negative, NOW()
                        )
                        """),
                        {
                            "date": forecast_date.date(),
                            "metric": metric_code,
                            "base_value": float(explainer.expected_value),
                            "feature_values": json.dumps(X_explain.iloc[0].to_dict()),
                            "shap_values": json.dumps(feature_contributions),
                            "top_positive": json.dumps(top_positive),
                            "top_negative": json.dumps(top_negative)
                        }
                    )
                except Exception:
                    pass  # Skip if conflict, explanations are supplementary
        except Exception as e:
            logger.warning(f"SHAP calculation failed: {e}")

        db.commit()
        logger.info(f"XGBoost forecast generated for {metric_code}: {len(forecasts)} records")
        return forecasts

    except ImportError as e:
        logger.error(f"Required package not installed: {e}")
        return []
    except Exception as e:
        logger.error(f"XGBoost forecast failed for {metric_code}: {e}")
        return []
