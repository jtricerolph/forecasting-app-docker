"""
Historical Forecast Runner
Runs all models as if it were a specific historical date.

This allows backtesting of Prophet, XGBoost, and Pickup models
by only using data that would have been available at that time.
"""
import logging
from datetime import date, timedelta
from typing import List, Optional
import pandas as pd
import numpy as np
import json
from sqlalchemy import text

from utils.time_alignment import get_prior_year_daily

logger = logging.getLogger(__name__)


async def run_historical_forecast(
    db,
    simulated_today: date,
    metric_codes: List[str] = None,
    models: List[str] = None,
    forecast_days: int = 60
) -> dict:
    """
    Run forecasts as if today were a specific historical date.

    Only uses data that would have been available on simulated_today.

    Args:
        db: Database session
        simulated_today: The date to pretend "today" is
        metric_codes: List of metrics to forecast (default: all main metrics)
        models: List of models to run (default: all)
        forecast_days: Number of days to forecast (default: 60)

    Returns:
        Dict with results summary
    """
    if metric_codes is None:
        metric_codes = ['hotel_room_nights', 'hotel_occupancy_pct', 'resos_dinner_covers', 'resos_lunch_covers']

    if models is None:
        models = ['prophet', 'xgboost', 'pickup', 'catboost']

    forecast_from = simulated_today + timedelta(days=1)
    forecast_to = simulated_today + timedelta(days=forecast_days)

    results = {
        "simulated_today": str(simulated_today),
        "forecast_from": str(forecast_from),
        "forecast_to": str(forecast_to),
        "metrics": {},
        "total_forecasts": 0
    }

    for metric_code in metric_codes:
        results["metrics"][metric_code] = {}

        for model in models:
            try:
                if model == 'prophet':
                    forecasts = await _run_prophet_historical(
                        db, metric_code, simulated_today, forecast_from, forecast_to
                    )
                elif model == 'xgboost':
                    forecasts = await _run_xgboost_historical(
                        db, metric_code, simulated_today, forecast_from, forecast_to
                    )
                elif model == 'pickup':
                    forecasts = await _run_pickup_historical(
                        db, metric_code, simulated_today, forecast_from, forecast_to
                    )
                elif model == 'catboost':
                    forecasts = await _run_catboost_historical(
                        db, metric_code, simulated_today, forecast_from, forecast_to
                    )
                else:
                    continue

                results["metrics"][metric_code][model] = len(forecasts)
                results["total_forecasts"] += len(forecasts)
                await db.commit()  # Commit after each successful model run

            except Exception as e:
                logger.error(f"Historical {model} forecast failed for {metric_code}: {e}")
                await db.rollback()  # Rollback on error to clear failed transaction
                results["metrics"][metric_code][model] = f"error: {str(e)[:100]}"
    logger.info(f"Historical forecasts complete for {simulated_today}: {results['total_forecasts']} total forecasts")

    return results


async def _run_prophet_historical(
    db,
    metric_code: str,
    simulated_today: date,
    forecast_from: date,
    forecast_to: date,
    training_days: int = 2555
) -> List[dict]:
    """Run Prophet using only data available before simulated_today."""
    try:
        from prophet import Prophet

        # Get room capacity for capping (sum across all room categories for a single date)
        total_rooms = 25
        if metric_code in ('hotel_room_nights', 'hotel_occupancy_pct'):
            rooms_result = await db.execute(
                text("""
                SELECT COALESCE(SUM(available), 25) as total_rooms
                FROM newbook_occupancy_report
                WHERE date = (
                    SELECT MAX(date) FROM newbook_occupancy_report
                    WHERE date <= :simulated_today
                )
                """),
                {"simulated_today": simulated_today}
            )
            rooms_row = rooms_result.fetchone()
            if rooms_row and rooms_row.total_rooms:
                total_rooms = int(rooms_row.total_rooms)

        # Training data ends at simulated_today - 1 (yesterday from simulated perspective)
        training_to = simulated_today - timedelta(days=1)
        training_from = training_to - timedelta(days=training_days)

        result = await db.execute(
            text("""
            SELECT date, actual_value
            FROM daily_metrics
            WHERE metric_code = :metric_code
                AND date BETWEEN :from_date AND :to_date
                AND actual_value IS NOT NULL
            ORDER BY date
            """),
            {"metric_code": metric_code, "from_date": training_from, "to_date": training_to}
        )
        rows = result.fetchall()

        if len(rows) < 30:
            logger.warning(f"Insufficient data for historical Prophet: {metric_code} has {len(rows)} records as of {simulated_today}")
            return []

        df = pd.DataFrame([{"ds": row.date, "y": float(row.actual_value)} for row in rows])

        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            interval_width=0.80
        )
        model.add_country_holidays(country_name='GB')
        model.fit(df)

        future_dates = pd.date_range(start=forecast_from, end=forecast_to, freq='D')
        future_df = pd.DataFrame({"ds": future_dates})
        forecast = model.predict(future_df)

        forecasts = []
        for _, row in forecast.iterrows():
            predicted_value = float(row["yhat"])
            lower_bound = float(row["yhat_lower"])
            upper_bound = float(row["yhat_upper"])

            # Apply physical caps
            if metric_code == 'hotel_occupancy_pct':
                predicted_value = min(predicted_value, 100)
                lower_bound = min(lower_bound, 100)
                upper_bound = min(upper_bound, 100)
            if metric_code == 'hotel_room_nights':
                predicted_value = min(predicted_value, total_rooms)
                lower_bound = min(lower_bound, total_rooms)
                upper_bound = min(upper_bound, total_rooms)

            forecast_record = {
                "forecast_date": row["ds"].date(),
                "forecast_type": metric_code,
                "model_type": "prophet",
                "predicted_value": round(predicted_value, 2),
                "lower_bound": round(lower_bound, 2),
                "upper_bound": round(upper_bound, 2)
            }
            forecasts.append(forecast_record)

            # Store with generated_at = simulated_today to track when this "would have been" generated
            await db.execute(
                text("""
                INSERT INTO forecasts (
                    forecast_date, forecast_type, model_type,
                    predicted_value, lower_bound, upper_bound, generated_at
                ) VALUES (
                    :forecast_date, :forecast_type, :model_type,
                    :predicted_value, :lower_bound, :upper_bound, :generated_at
                )
                """),
                {**forecast_record, "generated_at": simulated_today}
            )

        logger.info(f"Historical Prophet forecast for {metric_code} as of {simulated_today}: {len(forecasts)} records")
        return forecasts

    except ImportError:
        logger.error("Prophet not installed")
        return []
    except Exception as e:
        logger.error(f"Historical Prophet failed: {e}")
        raise


async def _run_xgboost_historical(
    db,
    metric_code: str,
    simulated_today: date,
    forecast_from: date,
    forecast_to: date,
    training_days: int = 2555
) -> List[dict]:
    """Run XGBoost using only data available before simulated_today."""
    try:
        import xgboost as xgb

        training_to = simulated_today - timedelta(days=1)
        training_from = training_to - timedelta(days=training_days + 60)

        result = await db.execute(
            text("""
            SELECT date, actual_value
            FROM daily_metrics
            WHERE metric_code = :metric_code
                AND date BETWEEN :from_date AND :to_date
                AND actual_value IS NOT NULL
            ORDER BY date
            """),
            {"metric_code": metric_code, "from_date": training_from, "to_date": training_to}
        )
        rows = result.fetchall()

        if len(rows) < 60:
            logger.warning(f"Insufficient data for historical XGBoost: {metric_code} has {len(rows)} records")
            return []

        df = pd.DataFrame([{"ds": pd.Timestamp(row.date), "y": float(row.actual_value)} for row in rows])
        df = df.sort_values('ds').reset_index(drop=True)
        df = _create_features(df)
        df = df.dropna()

        feature_cols = [
            'day_of_week', 'month', 'day_of_month', 'week_of_year', 'is_weekend',
            'dow_sin', 'dow_cos', 'month_sin', 'month_cos',
            'lag_7', 'lag_14', 'lag_21', 'lag_28',
            'rolling_mean_7', 'rolling_mean_14', 'rolling_mean_28',
            'rolling_std_7', 'rolling_std_14', 'rolling_std_28'
        ]

        if 'lag_365' in df.columns and df['lag_365'].notna().sum() > 30:
            feature_cols.append('lag_365')

        X = df[feature_cols]
        y = df['y']

        model = xgb.XGBRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            objective='reg:squarederror',
            random_state=42
        )
        model.fit(X, y)

        forecasts = []
        current_df = df.copy()

        for forecast_date in pd.date_range(start=forecast_from, end=forecast_to, freq='D'):
            new_row = pd.DataFrame([{"ds": forecast_date, "y": np.nan}])
            current_df = pd.concat([current_df, new_row], ignore_index=True)
            current_df = _create_features(current_df)

            X_pred = current_df[feature_cols].iloc[-1:].ffill()
            prediction = float(model.predict(X_pred)[0])
            current_df.iloc[-1, current_df.columns.get_loc('y')] = prediction

            forecast_record = {
                "forecast_date": forecast_date.date(),
                "forecast_type": metric_code,
                "model_type": "xgboost",
                "predicted_value": round(float(prediction), 2)
            }
            forecasts.append(forecast_record)

            await db.execute(
                text("""
                INSERT INTO forecasts (
                    forecast_date, forecast_type, model_type, predicted_value, generated_at
                ) VALUES (
                    :forecast_date, :forecast_type, :model_type, :predicted_value, :generated_at
                )
                """),
                {**forecast_record, "generated_at": simulated_today}
            )

        logger.info(f"Historical XGBoost forecast for {metric_code} as of {simulated_today}: {len(forecasts)} records")
        return forecasts

    except ImportError as e:
        logger.error(f"Required package not installed: {e}")
        return []
    except Exception as e:
        logger.error(f"Historical XGBoost failed: {e}")
        raise


async def _run_pickup_historical(
    db,
    metric_code: str,
    simulated_today: date,
    forecast_from: date,
    forecast_to: date
) -> List[dict]:
    """Run Pickup model using only data available before simulated_today."""

    forecasts = []

    # Get room capacity (sum of available rooms across all categories for a single date)
    total_rooms = 25
    if metric_code in ('hotel_room_nights', 'hotel_occupancy_pct'):
        rooms_result = await db.execute(
            text("""
            SELECT COALESCE(SUM(available), 25) as total_rooms
            FROM newbook_occupancy_report
            WHERE date = (
                SELECT MAX(date) FROM newbook_occupancy_report
                WHERE date <= :simulated_today
            )
            """),
            {"simulated_today": simulated_today}
        )
        rooms_row = rooms_result.fetchone()
        if rooms_row and rooms_row.total_rooms:
            total_rooms = int(rooms_row.total_rooms)

    for days_out in range((forecast_to - forecast_from).days + 1):
        forecast_date = forecast_from + timedelta(days=days_out)
        lead_time = (forecast_date - simulated_today).days

        if lead_time < 1:
            continue

        # Calculate prior year comparison date
        prior_year_date = get_prior_year_daily(forecast_date)

        # Get/reconstruct current OTB as of simulated_today
        current_otb = await _get_reconstructed_otb(
            db, metric_code, forecast_date, simulated_today, total_rooms
        )

        if current_otb is None:
            continue

        # Get prior year OTB at same lead time
        prior_simulated_today = get_prior_year_daily(simulated_today)
        prior_otb = await _get_reconstructed_otb(
            db, metric_code, prior_year_date, prior_simulated_today, total_rooms
        )

        # Get prior year final actual
        prior_final_result = await db.execute(
            text("""
            SELECT actual_value
            FROM daily_metrics
            WHERE date = :prior_date AND metric_code = :metric
            """),
            {"prior_date": prior_year_date, "metric": metric_code}
        )
        prior_final_row = prior_final_result.fetchone()
        prior_final = float(prior_final_row.actual_value) if prior_final_row and prior_final_row.actual_value else None

        # Calculate projection using additive method
        projected_value = current_otb

        if prior_otb is not None and prior_final is not None:
            prior_pickup = prior_final - prior_otb
            projected_value = current_otb + prior_pickup

            if projected_value < current_otb:
                projected_value = current_otb

            # Apply caps
            if metric_code == 'hotel_occupancy_pct' and projected_value > 100:
                projected_value = 100
            if metric_code == 'hotel_room_nights' and projected_value > total_rooms:
                projected_value = total_rooms

        elif prior_final is not None and prior_final > 0:
            # Implied additive
            if lead_time >= 28:
                estimated_pct = 0.35
            elif lead_time >= 14:
                estimated_pct = 0.55
            elif lead_time >= 7:
                estimated_pct = 0.75
            else:
                estimated_pct = 0.90

            implied_pickup = prior_final * (1 - estimated_pct)
            projected_value = current_otb + implied_pickup
            projected_value = max(projected_value, current_otb)

            if metric_code == 'hotel_occupancy_pct' and projected_value > 100:
                projected_value = 100
            if metric_code == 'hotel_room_nights' and projected_value > total_rooms:
                projected_value = total_rooms

        forecast_record = {
            "forecast_date": forecast_date,
            "forecast_type": metric_code,
            "model_type": "pickup",
            "predicted_value": round(projected_value, 2)
        }
        forecasts.append(forecast_record)

        await db.execute(
            text("""
            INSERT INTO forecasts (
                forecast_date, forecast_type, model_type, predicted_value, generated_at
            ) VALUES (
                :forecast_date, :forecast_type, :model_type, :predicted_value, :generated_at
            )
            """),
            {**forecast_record, "generated_at": simulated_today}
        )

    logger.info(f"Historical Pickup forecast for {metric_code} as of {simulated_today}: {len(forecasts)} records")
    return forecasts


async def _run_catboost_historical(
    db,
    metric_code: str,
    simulated_today: date,
    forecast_from: date,
    forecast_to: date,
    training_days: int = 2555
) -> List[dict]:
    """Run CatBoost using only data available before simulated_today."""
    try:
        from catboost import CatBoostRegressor

        training_to = simulated_today - timedelta(days=1)
        training_from = training_to - timedelta(days=training_days + 60)

        result = await db.execute(
            text("""
            SELECT date, actual_value
            FROM daily_metrics
            WHERE metric_code = :metric_code
                AND date BETWEEN :from_date AND :to_date
                AND actual_value IS NOT NULL
            ORDER BY date
            """),
            {"metric_code": metric_code, "from_date": training_from, "to_date": training_to}
        )
        rows = result.fetchall()

        if len(rows) < 60:
            logger.warning(f"Insufficient data for historical CatBoost: {metric_code} has {len(rows)} records")
            return []

        df = pd.DataFrame([{"ds": pd.Timestamp(row.date), "y": float(row.actual_value)} for row in rows])
        df = df.sort_values('ds').reset_index(drop=True)
        df = _create_catboost_features(df)
        df = df.dropna()

        categorical_features = ['day_of_week', 'month']
        numerical_features = [
            'day_of_month', 'week_of_year', 'is_weekend',
            'lag_7', 'lag_14', 'lag_21', 'lag_28',
            'rolling_mean_7', 'rolling_mean_14', 'rolling_mean_28',
            'rolling_std_7', 'rolling_std_14', 'rolling_std_28'
        ]

        if 'lag_365' in df.columns and df['lag_365'].notna().sum() > 30:
            numerical_features.append('lag_365')

        feature_cols = categorical_features + numerical_features

        X = df[feature_cols]
        y = df['y']

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

        forecasts = []
        current_df = df.copy()

        for forecast_date in pd.date_range(start=forecast_from, end=forecast_to, freq='D'):
            new_row = pd.DataFrame([{"ds": forecast_date, "y": np.nan}])
            current_df = pd.concat([current_df, new_row], ignore_index=True)
            current_df = _create_catboost_features(current_df)

            X_pred = current_df[feature_cols].iloc[-1:].copy()
            for col in numerical_features:
                if col in X_pred.columns:
                    X_pred[col] = X_pred[col].ffill()
                    if X_pred[col].isna().any():
                        X_pred[col] = X_pred[col].fillna(0)

            prediction = float(model.predict(X_pred)[0])
            prediction = max(0, prediction)
            current_df.iloc[-1, current_df.columns.get_loc('y')] = prediction

            forecast_record = {
                "forecast_date": forecast_date.date(),
                "forecast_type": metric_code,
                "model_type": "catboost",
                "predicted_value": round(float(prediction), 2)
            }
            forecasts.append(forecast_record)

            await db.execute(
                text("""
                INSERT INTO forecasts (
                    forecast_date, forecast_type, model_type, predicted_value, generated_at
                ) VALUES (
                    :forecast_date, :forecast_type, :model_type, :predicted_value, :generated_at
                )
                """),
                {**forecast_record, "generated_at": simulated_today}
            )

        logger.info(f"Historical CatBoost forecast for {metric_code} as of {simulated_today}: {len(forecasts)} records")
        return forecasts

    except ImportError as e:
        logger.error(f"CatBoost not installed: {e}")
        return []
    except Exception as e:
        logger.error(f"Historical CatBoost failed: {e}")
        raise


def _create_catboost_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create features for CatBoost model with native categorical support."""
    df = df.copy()

    df['day_of_week'] = df['ds'].dt.dayofweek.astype(str)  # Categorical for CatBoost
    df['month'] = df['ds'].dt.month.astype(str)  # Categorical for CatBoost
    df['day_of_month'] = df['ds'].dt.day
    df['week_of_year'] = df['ds'].dt.isocalendar().week.astype(int)
    df['is_weekend'] = (df['ds'].dt.dayofweek >= 5).astype(int)

    for lag in [7, 14, 21, 28]:
        df[f'lag_{lag}'] = df['y'].shift(lag)

    for window in [7, 14, 28]:
        df[f'rolling_mean_{window}'] = df['y'].rolling(window=window, min_periods=1).mean()
        df[f'rolling_std_{window}'] = df['y'].rolling(window=window, min_periods=1).std().fillna(0)

    if len(df) > 365:
        df['lag_365'] = df['y'].shift(365)

    return df


async def _get_reconstructed_otb(
    db,
    metric_code: str,
    target_date: date,
    as_of_date: date,
    total_rooms: int = 25
) -> Optional[float]:
    """
    Get or reconstruct OTB value for a target date as of a specific date.

    First tries pickup_snapshots, then reconstructs from booking data.
    """
    # Try snapshots first
    snap_result = await db.execute(
        text("""
        SELECT otb_value
        FROM pickup_snapshots
        WHERE stay_date = :target_date
            AND metric_type = :metric
            AND snapshot_date <= :as_of_date
        ORDER BY snapshot_date DESC
        LIMIT 1
        """),
        {"target_date": target_date, "metric": metric_code, "as_of_date": as_of_date}
    )
    snap_row = snap_result.fetchone()

    if snap_row and snap_row.otb_value is not None:
        return float(snap_row.otb_value)

    # Reconstruct from booking data
    # EXCLUDES overflow category (category_id=5) used for chargeable no-shows
    if metric_code in ('hotel_room_nights', 'hotel_occupancy_pct'):
        # Use CAST instead of :: to avoid asyncpg parameter parsing issues
        recon_result = await db.execute(
            text("""
            SELECT COUNT(DISTINCT newbook_id) as otb_count
            FROM newbook_bookings
            WHERE arrival_date <= :target_date
                AND departure_date > :target_date
                AND LOWER(status) NOT IN ('cancelled', 'no show', 'no_show', 'quote', 'waitlist')
                AND CAST(raw_json->>'booking_placed' AS timestamp) <= CAST(:as_of_date AS date) + INTERVAL '1 day'
                AND (category_id IS NULL OR category_id != '5')
            """),
            {"target_date": target_date, "as_of_date": as_of_date}
        )
        recon_row = recon_result.fetchone()

        if recon_row:
            otb_count = recon_row.otb_count or 0
            if metric_code == 'hotel_occupancy_pct':
                return (otb_count / total_rooms) * 100 if total_rooms > 0 else 0
            else:
                return otb_count

    return None


def _create_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create features for XGBoost model."""
    df = df.copy()

    df['day_of_week'] = df['ds'].dt.dayofweek
    df['month'] = df['ds'].dt.month
    df['day_of_month'] = df['ds'].dt.day
    df['week_of_year'] = df['ds'].dt.isocalendar().week.astype(int)
    df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)

    df['dow_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
    df['dow_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)

    for lag in [7, 14, 21, 28]:
        df[f'lag_{lag}'] = df['y'].shift(lag)

    for window in [7, 14, 28]:
        df[f'rolling_mean_{window}'] = df['y'].rolling(window=window, min_periods=1).mean()
        df[f'rolling_std_{window}'] = df['y'].rolling(window=window, min_periods=1).std()

    if len(df) > 365:
        df['lag_365'] = df['y'].shift(365)

    return df
