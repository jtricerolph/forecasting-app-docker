"""
Temporal Fusion Transformer (TFT) forecasting model
Deep learning model with attention-based explainability

Uses PyTorch Forecasting library for TFT implementation.
Provides multi-horizon forecasts with uncertainty quantification
and attention-based feature importance.
"""
import logging
import json
from datetime import date, timedelta
from typing import List, Optional, Dict, Any
import pandas as pd
import numpy as np
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Model configuration
ENCODER_LENGTH = 60      # 60 days of historical context
PREDICTION_LENGTH = 28   # 28 days ahead forecast
MAX_EPOCHS = 50
BATCH_SIZE = 64
LEARNING_RATE = 0.001
HIDDEN_SIZE = 32
ATTENTION_HEAD_SIZE = 4
DROPOUT = 0.1


def create_tft_features(df: pd.DataFrame, holidays_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Create features optimized for TFT architecture.

    TFT distinguishes between:
    - Time-varying known features (known in advance: holidays, day of week)
    - Time-varying unknown features (only known historically: actual values, lags)

    Uses same feature engineering approach as XGBoost for consistency.
    """
    df = df.copy()

    # Ensure datetime
    df['ds'] = pd.to_datetime(df['ds'])

    # Time-varying known features (known for future dates)
    df['day_of_week'] = df['ds'].dt.dayofweek
    df['month'] = df['ds'].dt.month
    df['day_of_month'] = df['ds'].dt.day
    df['week_of_year'] = df['ds'].dt.isocalendar().week.astype(int)
    df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)

    # Cyclical encoding (same as XGBoost)
    df['dow_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
    df['dow_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)

    # Holiday features
    if holidays_df is not None and len(holidays_df) > 0:
        holiday_dates = set(pd.to_datetime(holidays_df['ds']).dt.date)
        df['is_holiday'] = df['ds'].dt.date.apply(lambda x: 1 if x in holiday_dates else 0)

        # Days to nearest holiday (known future feature)
        def days_to_holiday(d):
            future_holidays = [h for h in holiday_dates if h >= d]
            if future_holidays:
                return min((h - d).days for h in future_holidays)
            return 30  # Default if no holidays in range

        df['days_to_holiday'] = df['ds'].dt.date.apply(days_to_holiday)
    else:
        df['is_holiday'] = 0
        df['days_to_holiday'] = 30

    # Time-varying unknown features (historical only, same as XGBoost)
    # Lag features
    for lag in [7, 14, 21, 28]:
        df[f'lag_{lag}'] = df['y'].shift(lag)

    # Year-over-year (364 days for DOW alignment, like pickup model)
    if len(df) > 364:
        df['lag_364'] = df['y'].shift(364)

    # Rolling statistics
    for window in [7, 14, 28]:
        df[f'rolling_mean_{window}'] = df['y'].rolling(window=window, min_periods=1).mean()
        df[f'rolling_std_{window}'] = df['y'].rolling(window=window, min_periods=1).std().fillna(0)

    return df


async def get_room_capacity(db, forecast_date: date) -> int:
    """
    Get total available rooms for a date (same logic as pickup_model.py).
    Used for capping room_nights forecasts.
    """
    result = db.execute(
        text("""
        SELECT COALESCE(SUM(available), 25) as total_rooms
        FROM newbook_occupancy_report_data
        WHERE date = :forecast_date
        """),
        {"forecast_date": forecast_date}
    )
    row = result.fetchone()
    return int(row.total_rooms) if row and row.total_rooms else 25


def apply_floor_cap(value: float, metric_code: str, total_rooms: int = 25) -> float:
    """
    Apply physical constraints to predictions (same as pickup_model.py).

    - hotel_occupancy_pct: 0-100%
    - hotel_room_nights: 0-total_rooms
    - All other metrics: floor at 0
    """
    if metric_code == 'hotel_occupancy_pct':
        return min(max(value, 0), 100)
    elif metric_code == 'hotel_room_nights':
        return min(max(value, 0), total_rooms)
    else:
        return max(value, 0)


async def run_tft_forecast(
    db,
    metric_code: str,
    forecast_from: date,
    forecast_to: date,
    training_days: int = 2555,  # ~7 years, same as Prophet/XGBoost
    use_gpu: bool = False,
    save_model: bool = True
) -> List[dict]:
    """
    Run TFT forecast for a metric.

    Uses same data source as Prophet/XGBoost (newbook_bookings_stats table).
    Applies same floor/cap logic as pickup model.

    Args:
        db: Database session
        metric_code: Metric to forecast
        forecast_from: Start date for forecasts
        forecast_to: End date for forecasts
        training_days: Days of historical data to use
        use_gpu: Whether to use GPU acceleration
        save_model: Whether to persist trained model

    Returns:
        List of forecast records
    """
    try:
        import torch
        from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet
        from pytorch_forecasting.metrics import QuantileLoss
        # Use lightning.pytorch (not pytorch_lightning) to match pytorch_forecasting's internal imports
        from lightning.pytorch import Trainer
        from lightning.pytorch.callbacks import EarlyStopping

        import warnings
        warnings.filterwarnings("ignore", category=UserWarning)

        # Check GPU availability
        device = "gpu" if use_gpu and torch.cuda.is_available() else "cpu"
        accelerator = "cuda" if device == "gpu" else "cpu"
        logger.info(f"TFT training for {metric_code} on {device}")

        # Get historical data from newbook_bookings_stats (forecast_data database)
        training_from = forecast_from - timedelta(days=training_days + ENCODER_LENGTH)

        # Map metric_code to the correct column in newbook_bookings_stats
        metric_column_map = {
            'hotel_occupancy_pct': 'total_occupancy_pct',
            'hotel_room_nights': 'booking_count',
            'hotel_guests': 'guests_count',
        }

        column_name = metric_column_map.get(metric_code)
        if not column_name:
            logger.warning(f"Unknown metric_code for TFT: {metric_code}")
            return []

        result = db.execute(
            text(f"""
            SELECT date, {column_name} as actual_value
            FROM newbook_bookings_stats
            WHERE date BETWEEN :from_date AND :to_date
                AND {column_name} IS NOT NULL
            ORDER BY date
            """),
            {
                "from_date": training_from,
                "to_date": forecast_from - timedelta(days=1)
            }
        )
        rows = result.fetchall()

        min_required = ENCODER_LENGTH + 90  # Need enough for training + validation
        if len(rows) < min_required:
            logger.warning(
                f"Insufficient data for TFT: {metric_code} has {len(rows)} records, "
                f"need at least {min_required}"
            )
            return []

        # Prepare DataFrame
        df = pd.DataFrame([{
            "ds": pd.Timestamp(row.date),
            "y": float(row.actual_value)
        } for row in rows])
        df = df.sort_values('ds').reset_index(drop=True)

        # Load holidays (using Prophet's holiday calendar)
        holidays_df = await _load_holidays(forecast_from, forecast_to)

        # Create features
        df = create_tft_features(df, holidays_df)

        # Add time index for TFT
        df['time_idx'] = range(len(df))
        df['group'] = metric_code  # Single series per metric

        # Drop NaN from lag features
        df = df.dropna(subset=['lag_7', 'lag_14', 'lag_21', 'lag_28'])

        if len(df) < min_required:
            logger.warning(f"Insufficient data after feature creation for {metric_code}")
            return []

        # Define training cutoff (leave some for validation)
        training_cutoff = len(df) - PREDICTION_LENGTH

        # Define feature columns
        time_varying_known = [
            'day_of_week', 'month', 'week_of_year', 'is_weekend',
            'is_holiday', 'days_to_holiday',
            'dow_sin', 'dow_cos', 'month_sin', 'month_cos'
        ]

        time_varying_unknown = [
            'y', 'lag_7', 'lag_14', 'lag_21', 'lag_28',
            'rolling_mean_7', 'rolling_mean_14', 'rolling_mean_28',
            'rolling_std_7', 'rolling_std_14', 'rolling_std_28'
        ]

        # Add lag_364 if available
        if 'lag_364' in df.columns and df['lag_364'].notna().sum() > 30:
            time_varying_unknown.append('lag_364')

        # Create TimeSeriesDataSet
        training_data = df.iloc[:training_cutoff].copy()

        training = TimeSeriesDataSet(
            training_data,
            time_idx="time_idx",
            target="y",
            group_ids=["group"],
            min_encoder_length=ENCODER_LENGTH // 2,
            max_encoder_length=ENCODER_LENGTH,
            min_prediction_length=1,
            max_prediction_length=PREDICTION_LENGTH,
            static_categoricals=["group"],
            time_varying_known_reals=time_varying_known,
            time_varying_unknown_reals=time_varying_unknown,
            add_relative_time_idx=True,
            add_target_scales=True,
            add_encoder_length=True,
        )

        # Create dataloaders
        train_dataloader = training.to_dataloader(
            train=True, batch_size=BATCH_SIZE, num_workers=0
        )

        # Validation dataloader
        validation = TimeSeriesDataSet.from_dataset(
            training, df.iloc[training_cutoff - ENCODER_LENGTH:], predict=False
        )
        val_dataloader = validation.to_dataloader(
            train=False, batch_size=BATCH_SIZE, num_workers=0
        )

        # Create TFT model
        tft = TemporalFusionTransformer.from_dataset(
            training,
            learning_rate=LEARNING_RATE,
            hidden_size=HIDDEN_SIZE,
            attention_head_size=ATTENTION_HEAD_SIZE,
            dropout=DROPOUT,
            hidden_continuous_size=16,
            output_size=7,  # 7 quantiles for uncertainty
            loss=QuantileLoss(),
            reduce_on_plateau_patience=4,
        )

        # Training callbacks
        early_stop_callback = EarlyStopping(
            monitor="val_loss",
            min_delta=1e-4,
            patience=10,
            verbose=False,
            mode="min"
        )

        # Train model
        import time
        start_time = time.time()

        trainer = Trainer(
            max_epochs=MAX_EPOCHS,
            accelerator=accelerator,
            devices=1,
            enable_model_summary=False,
            callbacks=[early_stop_callback],
            enable_progress_bar=False,
            logger=False,
        )

        trainer.fit(tft, train_dataloaders=train_dataloader, val_dataloaders=val_dataloader)

        training_time = int(time.time() - start_time)
        logger.info(f"TFT training completed in {training_time}s for {metric_code}")

        # Generate forecasts for future dates
        forecasts = await _generate_forecasts(
            db, tft, training, df, metric_code,
            forecast_from, forecast_to, holidays_df, time_varying_known, time_varying_unknown
        )

        # Log training run
        if save_model:
            await _log_training_run(
                db, metric_code, training_from, forecast_from,
                len(df), training_time, use_gpu,
                time_varying_known + time_varying_unknown
            )

        logger.info(f"TFT forecast generated for {metric_code}: {len(forecasts)} records")
        return forecasts

    except ImportError as e:
        logger.error(f"PyTorch Forecasting not installed: {e}")
        return []
    except Exception as e:
        logger.error(f"TFT forecast failed for {metric_code}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


async def _generate_forecasts(
    db, model, training_dataset, historical_df, metric_code,
    forecast_from, forecast_to, holidays_df, time_varying_known, time_varying_unknown
) -> List[dict]:
    """Generate forecasts and store in database with explanations."""
    import torch

    forecasts = []

    # Create future dates dataframe
    future_dates = pd.date_range(start=forecast_from, end=forecast_to, freq='D')

    # Build prediction dataframe (historical + future)
    future_df = pd.DataFrame({'ds': future_dates})
    future_df['y'] = np.nan  # Target unknown for future
    future_df = create_tft_features(future_df, holidays_df)

    # Combine with historical data
    combined = pd.concat([historical_df, future_df], ignore_index=True)
    combined['time_idx'] = range(len(combined))
    combined['group'] = metric_code

    # Forward fill lag and rolling features for future dates
    for col in combined.columns:
        if col.startswith('lag_') or col.startswith('rolling_'):
            combined[col] = combined[col].ffill()

    # Get room capacity for capping (if applicable)
    total_rooms = 25
    if metric_code in ('hotel_room_nights', 'hotel_occupancy_pct'):
        total_rooms = await get_room_capacity(db, forecast_from)

    # Create prediction dataset
    prediction_data = combined.iloc[-(len(future_dates) + ENCODER_LENGTH):].copy()

    try:
        predict_dataset = TimeSeriesDataSet.from_dataset(
            training_dataset, prediction_data, predict=True
        )
        predict_dataloader = predict_dataset.to_dataloader(
            train=False, batch_size=1, num_workers=0
        )

        # Get predictions
        predictions = model.predict(predict_dataloader, return_x=True)
        pred_values = predictions.output

        # TFT returns 7 quantiles: [0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98]
        # We use: q10 (index 1), q50 (index 3), q90 (index 5)

        for i, forecast_date in enumerate(future_dates):
            if i >= pred_values.shape[1]:
                break

            # Get date-specific room capacity
            if metric_code in ('hotel_room_nights', 'hotel_occupancy_pct'):
                date_rooms = await get_room_capacity(db, forecast_date.date())
            else:
                date_rooms = total_rooms

            # Extract quantile predictions
            pred_value = float(pred_values[0, i, 3])  # Median (q50)
            lower_bound = float(pred_values[0, i, 1])  # q10
            upper_bound = float(pred_values[0, i, 5])  # q90

            # Apply floor/cap constraints
            pred_value = apply_floor_cap(pred_value, metric_code, date_rooms)
            lower_bound = apply_floor_cap(lower_bound, metric_code, date_rooms)
            upper_bound = apply_floor_cap(upper_bound, metric_code, date_rooms)

            forecast_record = {
                "forecast_date": forecast_date.date(),
                "forecast_type": metric_code,
                "model_type": "tft",
                "predicted_value": round(pred_value, 2),
                "lower_bound": round(lower_bound, 2),
                "upper_bound": round(upper_bound, 2)
            }
            forecasts.append(forecast_record)

            # Store forecast in database
            db.execute(
                text("""
                INSERT INTO forecasts (
                    forecast_date, forecast_type, model_type,
                    predicted_value, lower_bound, upper_bound, generated_at
                ) VALUES (
                    :forecast_date, :forecast_type, :model_type,
                    :predicted_value, :lower_bound, :upper_bound, NOW()
                )
                """),
                forecast_record
            )

            # Store explanation for first 7 days
            if i < 7:
                await _store_explanation(
                    db, forecast_date.date(), metric_code,
                    pred_value, lower_bound, upper_bound
                )

        db.commit()

    except Exception as e:
        logger.error(f"Prediction generation failed: {e}")
        import traceback
        logger.error(traceback.format_exc())

    return forecasts


async def _store_explanation(
    db, forecast_date: date, metric_code: str,
    pred_value: float, lower_bound: float, upper_bound: float
):
    """Store TFT attention-based explanations."""
    try:
        # For now, store quantile predictions as main explanation
        # Full attention weights would require model.interpret_output()
        db.execute(
            text("""
            INSERT INTO tft_explanations (
                forecast_date, forecast_type,
                quantile_10, quantile_50, quantile_90,
                generated_at
            ) VALUES (
                :date, :metric,
                :q10, :q50, :q90,
                NOW()
            )
            """),
            {
                "date": forecast_date,
                "metric": metric_code,
                "q10": lower_bound,
                "q50": pred_value,
                "q90": upper_bound
            }
        )
    except Exception as e:
        logger.warning(f"Failed to store TFT explanation: {e}")


async def _log_training_run(
    db, metric_code: str, training_from: date, training_to: date,
    training_rows: int, training_time: int, gpu_used: bool,
    feature_list: List[str]
):
    """Log TFT training run for tracking."""
    try:
        db.execute(
            text("""
            INSERT INTO tft_training_log (
                forecast_type, training_from, training_to,
                training_rows, training_time_seconds, gpu_used,
                encoder_length, prediction_length, feature_list,
                hyperparameters, trained_at
            ) VALUES (
                :metric, :from_date, :to_date,
                :rows, :time_sec, :gpu,
                :encoder, :prediction, :features,
                :hyperparams, NOW()
            )
            """),
            {
                "metric": metric_code,
                "from_date": training_from,
                "to_date": training_to,
                "rows": training_rows,
                "time_sec": training_time,
                "gpu": gpu_used,
                "encoder": ENCODER_LENGTH,
                "prediction": PREDICTION_LENGTH,
                "features": json.dumps(feature_list),
                "hyperparams": json.dumps({
                    "hidden_size": HIDDEN_SIZE,
                    "attention_head_size": ATTENTION_HEAD_SIZE,
                    "dropout": DROPOUT,
                    "learning_rate": LEARNING_RATE,
                    "max_epochs": MAX_EPOCHS,
                    "batch_size": BATCH_SIZE
                })
            }
        )
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to log TFT training run: {e}")


async def _load_holidays(from_date: date, to_date: date) -> pd.DataFrame:
    """Load UK holidays using Prophet's holiday calendar."""
    try:
        from prophet import Prophet

        # Create minimal Prophet model to get holidays
        m = Prophet()
        m.add_country_holidays(country_name='GB')

        # Fit on dummy data
        dummy_df = pd.DataFrame({
            'ds': pd.date_range(start=from_date - timedelta(days=365), end=to_date, freq='D'),
            'y': 0
        })
        m.fit(dummy_df)

        # Generate future dataframe to get holidays
        future = m.make_future_dataframe(periods=0)

        # Return holiday dates
        if hasattr(m, 'train_holiday_names') and m.train_holiday_names:
            holidays = pd.DataFrame({
                'ds': pd.date_range(start=from_date, end=to_date, freq='D')
            })
            return holidays
        return pd.DataFrame()

    except Exception as e:
        logger.warning(f"Failed to load holidays: {e}")
        return pd.DataFrame()


# Import for TimeSeriesDataSet (used in _generate_forecasts)
try:
    from pytorch_forecasting import TimeSeriesDataSet
except ImportError:
    TimeSeriesDataSet = None
