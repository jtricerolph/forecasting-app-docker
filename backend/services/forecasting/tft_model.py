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

# Default model configuration (can be overridden by database settings)
DEFAULT_ENCODER_LENGTH = 60      # 60 days of historical context
DEFAULT_PREDICTION_LENGTH = 28   # 28 days ahead forecast
DEFAULT_MAX_EPOCHS = 50
DEFAULT_BATCH_SIZE = 64
DEFAULT_LEARNING_RATE = 0.001
DEFAULT_HIDDEN_SIZE = 32
DEFAULT_ATTENTION_HEAD_SIZE = 4
DEFAULT_DROPOUT = 0.1
DEFAULT_TRAINING_DAYS = 2555


def get_tft_config_from_db(db) -> Dict[str, Any]:
    """Load TFT configuration from database system_config table."""
    try:
        result = db.execute(text("""
            SELECT config_key, config_value
            FROM system_config
            WHERE config_key LIKE 'tft_%'
        """))
        rows = result.fetchall()

        config = {}
        for row in rows:
            key = row.config_key.replace('tft_', '')
            value = row.config_value

            # Convert to appropriate types
            if key in ('encoder_length', 'prediction_length', 'hidden_size',
                       'attention_heads', 'batch_size', 'max_epochs', 'training_days'):
                config[key] = int(value) if value else 0
            elif key in ('learning_rate', 'dropout'):
                config[key] = float(value) if value else 0.0
            elif key in ('use_gpu', 'auto_retrain', 'use_cached_model', 'use_special_dates', 'use_otb_data'):
                config[key] = value.lower() == 'true' if value else False
            else:
                config[key] = value

        return config
    except Exception as e:
        logger.warning(f"Failed to load TFT config from database: {e}")
        return {}


def get_effective_config(db=None) -> Dict[str, Any]:
    """Get effective TFT config, merging DB values with defaults."""
    # Start with defaults
    config = {
        'encoder_length': DEFAULT_ENCODER_LENGTH,
        'prediction_length': DEFAULT_PREDICTION_LENGTH,
        'max_epochs': DEFAULT_MAX_EPOCHS,
        'batch_size': DEFAULT_BATCH_SIZE,
        'learning_rate': DEFAULT_LEARNING_RATE,
        'hidden_size': DEFAULT_HIDDEN_SIZE,
        'attention_heads': DEFAULT_ATTENTION_HEAD_SIZE,
        'dropout': DEFAULT_DROPOUT,
        'training_days': DEFAULT_TRAINING_DAYS,
        'use_gpu': False,
        'use_cached_model': True,
        'use_special_dates': True,
        'use_otb_data': True,
    }

    # Override with database values if available
    if db:
        db_config = get_tft_config_from_db(db)
        for key, value in db_config.items():
            if value is not None and key in config:
                config[key] = value

    return config


# Keep legacy constants for backward compatibility
ENCODER_LENGTH = DEFAULT_ENCODER_LENGTH
PREDICTION_LENGTH = DEFAULT_PREDICTION_LENGTH
MAX_EPOCHS = DEFAULT_MAX_EPOCHS
BATCH_SIZE = DEFAULT_BATCH_SIZE
LEARNING_RATE = DEFAULT_LEARNING_RATE
HIDDEN_SIZE = DEFAULT_HIDDEN_SIZE
ATTENTION_HEAD_SIZE = DEFAULT_ATTENTION_HEAD_SIZE
DROPOUT = DEFAULT_DROPOUT


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
    # Only create if we have enough data (>450 rows)
    if len(df) > 450:
        df['lag_364'] = df['y'].shift(364)
        # Fill NaN with forward fill for early rows
        df['lag_364'] = df['lag_364'].ffill().bfill()

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
    training_days: int = None,  # Load from DB config if None
    use_gpu: bool = None,  # Load from DB config if None
) -> List[dict]:
    """
    Run TFT forecast for a metric using a pre-trained model from Settings.

    This function ONLY uses models that have been trained or uploaded via the
    Settings page. If no active model exists for the metric, it returns an
    empty list. On-the-fly training is not supported - train models via Settings.

    Args:
        db: Database session
        metric_code: Metric to forecast
        forecast_from: Start date for forecasts
        forecast_to: End date for forecasts
        training_days: Days of historical data for encoder context (None = from DB)
        use_gpu: Whether to use GPU acceleration (None = from DB)

    Returns:
        List of forecast records, or empty list if no active model exists
    """
    try:
        import torch

        import warnings
        warnings.filterwarnings("ignore", category=UserWarning)

        # Load configuration from database
        config = get_effective_config(db)

        # Use provided values or fall back to config
        if training_days is None:
            training_days = config['training_days']

        logger.info(f"TFT forecast for {metric_code}: loading pre-trained model from Settings")

        # Try to load active model checkpoint from tft_models table
        checkpoint, model_info = await _load_active_model(db, metric_code)

        if checkpoint is None:
            logger.warning(
                f"No active TFT model found for {metric_code}. "
                f"Train or upload a model in Settings > TFT Model Training, then activate it."
            )
            return []

        logger.info(
            f"Using TFT model '{model_info['model_name']}' "
            f"(trained: {model_info['trained_at']}) for {metric_code}"
        )

        # Generate predictions using the pre-trained model checkpoint
        forecasts = await _generate_forecasts_from_pretrained_model(
            db, checkpoint, metric_code,
            forecast_from, forecast_to, training_days
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


async def _load_active_model(db, metric_code: str):
    """
    Load the active TFT model checkpoint for a metric from tft_models table.

    Returns:
        Tuple of (checkpoint, model_info) if found, (None, None) otherwise
    """
    try:
        from services.model_storage import load_model
        return load_model(db, metric_code)
    except Exception as e:
        logger.warning(f"Failed to load active model for {metric_code}: {e}")
        return None, None


async def _generate_forecasts_from_pretrained_model(
    db, checkpoint, metric_code: str,
    forecast_from: date, forecast_to: date,
    training_days: int
) -> List[dict]:
    """
    Generate forecasts using a pre-trained TFT model checkpoint.

    Loads historical data needed for encoder context, reconstructs the model
    from the checkpoint, and generates predictions.
    """
    try:
        import torch
        from pytorch_forecasting import TimeSeriesDataSet, TemporalFusionTransformer
        from pytorch_forecasting.metrics import QuantileLoss
        import pandas as pd
        import numpy as np

        # Get dataset parameters from checkpoint
        dataset_params = checkpoint.get("dataset_parameters", {})
        encoder_length = dataset_params.get("max_encoder_length", 90)
        prediction_length = dataset_params.get("max_prediction_length", 28)
        time_varying_known = dataset_params.get("time_varying_known_reals", [])
        time_varying_unknown = dataset_params.get("time_varying_unknown_reals", [])

        # Load historical data for encoder context
        context_from = forecast_from - timedelta(days=training_days + encoder_length)

        # Map metric to column
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
                "from_date": context_from,
                "to_date": forecast_from - timedelta(days=1)
            }
        )
        rows = result.fetchall()

        min_required = encoder_length + 30
        if len(rows) < min_required:
            logger.warning(f"Insufficient historical data for TFT prediction: {len(rows)} rows, need {min_required}")
            return []

        # Prepare DataFrame
        df = pd.DataFrame([{
            "ds": pd.Timestamp(row.date),
            "y": float(row.actual_value)
        } for row in rows])
        df = df.sort_values('ds').reset_index(drop=True)

        # Check if model was trained with special dates and/or OTB features
        training_config = checkpoint.get("training_config", {})
        use_special_dates = training_config.get("use_special_dates", True)
        use_otb_data = training_config.get("use_otb_data", False)

        # Load holidays if model was trained with special dates
        holidays_df = None
        if use_special_dates:
            holidays_df = await _load_holidays(forecast_from, forecast_to)

        # Create features
        df = create_tft_features(df, holidays_df)

        # Load and add OTB features if model was trained with them
        if use_otb_data:
            otb_df = _load_otb_data_for_inference(db, context_from, forecast_from)
            if otb_df is not None and len(otb_df) > 0:
                df = _add_otb_features_for_inference(df, otb_df)
                logger.info("Added OTB features for inference")
            else:
                # Add zero defaults if no OTB data available
                df = _add_otb_features_for_inference(df, None)
                logger.info("No OTB data found - using zero defaults for inference")

        # Add time index and group
        df['time_idx'] = range(len(df))
        df['group'] = metric_code

        # Drop NaN from lag features
        df = df.dropna(subset=['lag_7', 'lag_14', 'lag_21', 'lag_28'])

        if len(df) < min_required:
            logger.warning(f"Insufficient data after feature creation for {metric_code}")
            return []

        # Default feature lists if not stored in checkpoint
        default_known = [
            'day_of_week', 'month', 'week_of_year', 'is_weekend',
            'is_holiday', 'days_to_holiday',
            'dow_sin', 'dow_cos', 'month_sin', 'month_cos'
        ]
        default_unknown = [
            'y', 'lag_7', 'lag_14', 'lag_21', 'lag_28',
            'rolling_mean_7', 'rolling_mean_14', 'rolling_mean_28',
            'rolling_std_7', 'rolling_std_14', 'rolling_std_28'
        ]

        known_reals = time_varying_known if time_varying_known else default_known
        unknown_reals = time_varying_unknown if time_varying_unknown else default_unknown

        # Recreate the training dataset structure (needed for prediction)
        training = TimeSeriesDataSet(
            df.copy(),
            time_idx="time_idx",
            target="y",
            group_ids=["group"],
            min_encoder_length=encoder_length // 2,
            max_encoder_length=encoder_length,
            min_prediction_length=1,
            max_prediction_length=prediction_length,
            static_categoricals=["group"],
            time_varying_known_reals=known_reals,
            time_varying_unknown_reals=unknown_reals,
            add_relative_time_idx=True,
            add_target_scales=True,
            add_encoder_length=True,
        )

        # Reconstruct the model from the checkpoint using the dataset structure
        hparams = checkpoint.get("model_hparams", {})

        # Create a fresh model with the same architecture using the dataset
        model = TemporalFusionTransformer.from_dataset(
            training,
            learning_rate=hparams.get("learning_rate", 0.001),
            hidden_size=hparams.get("hidden_size", 64),
            attention_head_size=hparams.get("attention_head_size", 4),
            dropout=hparams.get("dropout", 0.1),
            hidden_continuous_size=hparams.get("hidden_continuous_size", 16),
            output_size=hparams.get("output_size", 7),
            loss=QuantileLoss(),
            reduce_on_plateau_patience=4,
        )

        # Load the trained weights
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()  # Set to evaluation mode

        logger.info(f"Reconstructed TFT model for {metric_code} with {sum(p.numel() for p in model.parameters()):,} parameters")

        # Generate forecasts
        forecasts = await _generate_forecasts(
            db, model, training, df, metric_code,
            forecast_from, forecast_to, holidays_df,
            known_reals, unknown_reals,
            use_otb_data=use_otb_data
        )

        return forecasts

    except Exception as e:
        logger.error(f"Failed to generate forecasts from pre-trained model: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


async def _generate_forecasts(
    db, model, training_dataset, historical_df, metric_code,
    forecast_from, forecast_to, holidays_df, time_varying_known, time_varying_unknown,
    use_otb_data: bool = False
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

    # Add OTB features for future dates if needed
    if use_otb_data:
        # If historical_df already has OTB columns, we just need to fill future rows
        if 'otb_at_30d' not in combined.columns:
            # No OTB columns exist, add defaults
            combined = _add_otb_features_for_inference(combined, None)
        else:
            # OTB columns exist from historical, load current OTB for future dates
            otb_future = _load_otb_data_for_inference(db, forecast_from, forecast_to)
            if otb_future is not None and len(otb_future) > 0:
                # Map future OTB data to the combined dataframe
                otb_future['date_only'] = pd.to_datetime(otb_future['arrival_date']).dt.date
                combined['date_only_temp'] = combined['ds'].dt.date
                otb_lookup = otb_future.set_index('date_only')

                # Fill in OTB for future dates
                for idx in combined[combined['ds'] >= pd.Timestamp(forecast_from)].index:
                    d = combined.loc[idx, 'date_only_temp']
                    if d in otb_lookup.index:
                        row = otb_lookup.loc[d]
                        combined.loc[idx, 'otb_at_30d'] = row.get('otb_at_30d', 0)
                        combined.loc[idx, 'otb_at_14d'] = row.get('otb_at_14d', 0)
                        combined.loc[idx, 'otb_at_7d'] = row.get('otb_at_7d', 0)

                combined = combined.drop(columns=['date_only_temp'], errors='ignore')

    # Forward fill lag and rolling features for future dates
    for col in combined.columns:
        if col.startswith('lag_') or col.startswith('rolling_') or col.startswith('otb_') or col.startswith('pickup_'):
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


async def _load_holidays(from_date: date, to_date: date, db=None) -> pd.DataFrame:
    """
    Load special dates from Settings database.

    Uses the special_dates table configured in Settings > Special Dates,
    which includes school holidays, local events, conferences, etc.
    Falls back to empty if no special dates configured.
    """
    try:
        from api.special_dates import resolve_special_date
        from database import SyncSessionLocal

        # Use provided db or create new session
        if db is None:
            db = SyncSessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            # Query active special dates from settings
            result = db.execute(text("""
                SELECT
                    id, name, pattern_type,
                    fixed_month, fixed_day,
                    nth_week, weekday, month,
                    relative_to_month, relative_to_day,
                    relative_weekday, relative_direction,
                    duration_days, is_recurring, one_off_year
                FROM special_dates
                WHERE is_active = TRUE
            """))
            rows = result.fetchall()

            if not rows:
                logger.info("No special dates configured in Settings")
                return pd.DataFrame()

            # Resolve all special dates for the years in our range
            all_dates = []
            years = set(range(from_date.year - 1, to_date.year + 2))  # Include buffer years

            for row in rows:
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
                    'duration_days': row.duration_days or 1,
                    'is_recurring': row.is_recurring,
                    'one_off_year': row.one_off_year
                }

                for year in years:
                    resolved = resolve_special_date(sd, year)
                    for d in resolved:
                        if from_date - timedelta(days=365) <= d <= to_date + timedelta(days=365):
                            all_dates.append({
                                'ds': pd.Timestamp(d),
                                'name': row.name
                            })

            if all_dates:
                holidays_df = pd.DataFrame(all_dates)
                logger.info(f"Loaded {len(holidays_df)} special date occurrences from Settings")
                return holidays_df

            return pd.DataFrame()

        finally:
            if close_db:
                db.close()

    except Exception as e:
        logger.warning(f"Failed to load special dates from Settings: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return pd.DataFrame()


def _load_otb_data_for_inference(db, from_date: date, to_date: date) -> Optional[pd.DataFrame]:
    """
    Load OTB (On-The-Books) data for inference.

    Returns DataFrame with columns:
    - arrival_date
    - otb_at_90d, otb_at_60d, otb_at_30d, otb_at_14d, otb_at_7d, final_bookings
    """
    try:
        result = db.execute(text("""
            SELECT
                arrival_date,
                d90 as otb_at_90d,
                d60 as otb_at_60d,
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
            logger.debug("No OTB data found in booking_pace table for inference")
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

        logger.debug(f"Loaded OTB data for {len(df)} dates for inference")
        return df

    except Exception as e:
        logger.warning(f"Failed to load OTB data for inference: {e}")
        return None


def _add_otb_features_for_inference(df: pd.DataFrame, otb_df: Optional[pd.DataFrame]) -> pd.DataFrame:
    """
    Add OTB features for inference (matching the training features).
    """
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

    df = df.merge(
        otb_df[['date_only', 'otb_at_90d', 'otb_at_60d', 'otb_at_30d',
                'otb_at_14d', 'otb_at_7d', 'final_bookings']],
        on='date_only',
        how='left'
    )

    # Fill NaN with 0
    for col in ['otb_at_90d', 'otb_at_60d', 'otb_at_30d', 'otb_at_14d', 'otb_at_7d', 'final_bookings']:
        df[col] = df[col].fillna(0)

    # Calculate pickup between windows
    df['pickup_30d_to_14d'] = df['otb_at_14d'] - df['otb_at_30d']
    df['pickup_14d_to_7d'] = df['otb_at_7d'] - df['otb_at_14d']

    # Calculate OTB as percentage of final (capped at 100%)
    df['otb_pct_at_30d'] = np.where(
        df['final_bookings'] > 0,
        np.minimum(df['otb_at_30d'] / df['final_bookings'] * 100, 100),
        0
    )
    df['otb_pct_at_14d'] = np.where(
        df['final_bookings'] > 0,
        np.minimum(df['otb_at_14d'] / df['final_bookings'] * 100, 100),
        0
    )
    df['otb_pct_at_7d'] = np.where(
        df['final_bookings'] > 0,
        np.minimum(df['otb_at_7d'] / df['final_bookings'] * 100, 100),
        0
    )

    # Drop temporary column
    df = df.drop(columns=['date_only'], errors='ignore')

    return df


# Import for TimeSeriesDataSet (used in _generate_forecasts)
try:
    from pytorch_forecasting import TimeSeriesDataSet
except ImportError:
    TimeSeriesDataSet = None
