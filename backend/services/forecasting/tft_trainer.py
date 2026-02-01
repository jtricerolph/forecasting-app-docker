"""
TFT Model Trainer
Background training with progress tracking and model persistence
"""
import logging
import time
from datetime import date, timedelta
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from sqlalchemy import text

from services.model_storage import save_model, update_training_job, get_tft_config

logger = logging.getLogger(__name__)


def train_tft_model_with_progress(
    db,
    metric_code: str,
    model_name: str,
    config: Dict[str, Any],
    job_id: str,
    created_by: str = "system"
) -> Dict[str, Any]:
    """
    Train a TFT model with progress tracking.

    This function is designed to be called from a background task.
    It updates the training job status as it progresses.

    Args:
        db: Synchronous database session
        metric_code: Metric to train model for
        model_name: Name for the saved model
        config: Training configuration (hyperparameters)
        job_id: Training job ID for progress updates
        created_by: User who initiated training

    Returns:
        Dict with training results
    """
    import torch
    from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet
    from pytorch_forecasting.metrics import QuantileLoss
    from lightning.pytorch import Trainer
    from lightning.pytorch.callbacks import EarlyStopping, Callback

    import warnings
    warnings.filterwarnings("ignore", category=UserWarning)

    start_time = time.time()

    # Extract config values with defaults
    encoder_length = config.get('encoder_length', 90)
    prediction_length = config.get('prediction_length', 28)
    hidden_size = config.get('hidden_size', 64)
    attention_heads = config.get('attention_heads', 4)
    learning_rate = config.get('learning_rate', 0.001)
    batch_size = config.get('batch_size', 128)
    max_epochs = config.get('max_epochs', 100)
    training_days = config.get('training_days', 2555)
    dropout = config.get('dropout', 0.1)
    use_gpu = config.get('use_gpu', False)

    logger.info(f"Starting TFT training for {metric_code} with config: "
                f"epochs={max_epochs}, hidden={hidden_size}, lr={learning_rate}")

    # Update job status to running
    update_training_job(db, job_id, status="running", progress_pct=5)

    try:
        # Determine device
        device = "gpu" if use_gpu and torch.cuda.is_available() else "cpu"
        accelerator = "cuda" if device == "gpu" else "cpu"
        logger.info(f"Training on {device}")

        # Load training data
        update_training_job(db, job_id, progress_pct=10)

        forecast_from = date.today()
        training_from = forecast_from - timedelta(days=training_days + encoder_length)

        # Map metric to column
        metric_column_map = {
            'hotel_occupancy_pct': 'total_occupancy_pct',
            'hotel_room_nights': 'booking_count',
            'hotel_guests': 'guests_count',
        }

        column_name = metric_column_map.get(metric_code)
        if not column_name:
            raise ValueError(f"Unknown metric_code: {metric_code}")

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

        min_required = encoder_length + 90
        if len(rows) < min_required:
            raise ValueError(
                f"Insufficient data: {len(rows)} records, need at least {min_required}"
            )

        logger.info(f"Loaded {len(rows)} training records")
        update_training_job(db, job_id, progress_pct=15)

        # Prepare DataFrame
        df = pd.DataFrame([{
            "ds": pd.Timestamp(row.date),
            "y": float(row.actual_value)
        } for row in rows])
        df = df.sort_values('ds').reset_index(drop=True)

        # Create features
        df = _create_tft_features(df)

        # Add time index for TFT
        df['time_idx'] = range(len(df))
        df['group'] = metric_code

        # Drop NaN from lag features
        df = df.dropna(subset=['lag_7', 'lag_14', 'lag_21', 'lag_28'])

        if len(df) < min_required:
            raise ValueError("Insufficient data after feature creation")

        update_training_job(db, job_id, progress_pct=20)

        # Define training cutoff
        training_cutoff = len(df) - prediction_length

        # Define feature columns
        time_varying_known = [
            'day_of_week', 'month', 'week_of_year', 'is_weekend',
            'dow_sin', 'dow_cos', 'month_sin', 'month_cos'
        ]

        time_varying_unknown = [
            'y', 'lag_7', 'lag_14', 'lag_21', 'lag_28',
            'rolling_mean_7', 'rolling_mean_14', 'rolling_mean_28',
            'rolling_std_7', 'rolling_std_14', 'rolling_std_28'
        ]

        if 'lag_364' in df.columns and df['lag_364'].notna().sum() > 30:
            time_varying_unknown.append('lag_364')

        # Create TimeSeriesDataSet
        training_data = df.iloc[:training_cutoff].copy()

        training_dataset = TimeSeriesDataSet(
            training_data,
            time_idx="time_idx",
            target="y",
            group_ids=["group"],
            min_encoder_length=encoder_length // 2,
            max_encoder_length=encoder_length,
            min_prediction_length=1,
            max_prediction_length=prediction_length,
            static_categoricals=["group"],
            time_varying_known_reals=time_varying_known,
            time_varying_unknown_reals=time_varying_unknown,
            add_relative_time_idx=True,
            add_target_scales=True,
            add_encoder_length=True,
        )

        # Create dataloaders
        train_dataloader = training_dataset.to_dataloader(
            train=True, batch_size=batch_size, num_workers=0
        )

        # Validation dataloader
        validation = TimeSeriesDataSet.from_dataset(
            training_dataset, df.iloc[training_cutoff - encoder_length:], predict=False
        )
        val_dataloader = validation.to_dataloader(
            train=False, batch_size=batch_size, num_workers=0
        )

        update_training_job(db, job_id, progress_pct=25)

        # Create TFT model
        tft = TemporalFusionTransformer.from_dataset(
            training_dataset,
            learning_rate=learning_rate,
            hidden_size=hidden_size,
            attention_head_size=attention_heads,
            dropout=dropout,
            hidden_continuous_size=hidden_size // 4,
            output_size=7,  # 7 quantiles
            loss=QuantileLoss(),
            reduce_on_plateau_patience=4,
        )

        logger.info(f"Created TFT model with {sum(p.numel() for p in tft.parameters()):,} parameters")

        # Progress callback
        class ProgressCallback(Callback):
            def __init__(self, db, job_id, max_epochs):
                self.db = db
                self.job_id = job_id
                self.max_epochs = max_epochs

            def on_train_epoch_end(self, trainer, pl_module):
                epoch = trainer.current_epoch + 1
                progress = 25 + int((epoch / self.max_epochs) * 65)  # 25-90%
                update_training_job(
                    self.db, self.job_id,
                    progress_pct=progress,
                    current_epoch=epoch
                )
                logger.info(f"Epoch {epoch}/{self.max_epochs} completed")

        # Training callbacks
        early_stop_callback = EarlyStopping(
            monitor="val_loss",
            min_delta=1e-4,
            patience=10,
            verbose=False,
            mode="min"
        )

        progress_callback = ProgressCallback(db, job_id, max_epochs)

        # Train model
        trainer = Trainer(
            max_epochs=max_epochs,
            accelerator=accelerator,
            devices=1,
            enable_model_summary=False,
            callbacks=[early_stop_callback, progress_callback],
            enable_progress_bar=False,
            logger=False,
        )

        logger.info("Starting training...")
        trainer.fit(tft, train_dataloaders=train_dataloader, val_dataloaders=val_dataloader)

        training_time = int(time.time() - start_time)
        epochs_completed = trainer.current_epoch + 1

        # Get validation loss
        val_loss = trainer.callback_metrics.get("val_loss")
        val_loss_float = float(val_loss) if val_loss is not None else None

        logger.info(f"Training completed in {training_time}s, "
                    f"epochs={epochs_completed}, val_loss={val_loss_float}")

        update_training_job(db, job_id, progress_pct=92)

        # Save model
        training_config = {
            "encoder_length": encoder_length,
            "prediction_length": prediction_length,
            "hidden_size": hidden_size,
            "attention_heads": attention_heads,
            "learning_rate": learning_rate,
            "batch_size": batch_size,
            "max_epochs": max_epochs,
            "training_days": training_days,
            "dropout": dropout,
            "use_gpu": use_gpu,
        }

        file_path = save_model(
            db=db,
            model=tft,
            dataset=training_dataset,
            metric_code=metric_code,
            model_name=model_name,
            training_config=training_config,
            training_time_seconds=training_time,
            validation_loss=val_loss_float,
            epochs_completed=epochs_completed,
            created_by=created_by
        )

        update_training_job(db, job_id, progress_pct=100, status="completed")

        return {
            "status": "success",
            "metric_code": metric_code,
            "model_name": model_name,
            "file_path": file_path,
            "training_time_seconds": training_time,
            "epochs_completed": epochs_completed,
            "validation_loss": val_loss_float
        }

    except Exception as e:
        logger.error(f"Training failed: {e}")
        import traceback
        logger.error(traceback.format_exc())

        update_training_job(db, job_id, status="failed", error_message=str(e))
        raise


def _create_tft_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create features for TFT model"""
    df = df.copy()

    # Ensure datetime
    df['ds'] = pd.to_datetime(df['ds'])

    # Time-varying known features
    df['day_of_week'] = df['ds'].dt.dayofweek
    df['month'] = df['ds'].dt.month
    df['day_of_month'] = df['ds'].dt.day
    df['week_of_year'] = df['ds'].dt.isocalendar().week.astype(int)
    df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)

    # Cyclical encoding
    df['dow_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
    df['dow_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)

    # Lag features
    for lag in [7, 14, 21, 28]:
        df[f'lag_{lag}'] = df['y'].shift(lag)

    # Year-over-year
    if len(df) > 364:
        df['lag_364'] = df['y'].shift(364)

    # Rolling statistics
    for window in [7, 14, 28]:
        df[f'rolling_mean_{window}'] = df['y'].rolling(window=window, min_periods=1).mean()
        df[f'rolling_std_{window}'] = df['y'].rolling(window=window, min_periods=1).std().fillna(0)

    return df
