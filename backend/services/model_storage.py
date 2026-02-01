"""
TFT Model Storage Service
Handles saving, loading, exporting, and importing trained TFT models
"""
import os
import io
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Model storage directory
MODEL_DIR = Path("/app/models/tft")


@dataclass
class ModelInfo:
    """Information about a stored model"""
    id: int
    metric_code: str
    model_name: str
    file_path: Optional[str]
    file_size_bytes: Optional[int]
    trained_at: datetime
    training_config: Dict[str, Any]
    training_time_seconds: Optional[int]
    validation_loss: Optional[float]
    epochs_completed: Optional[int]
    is_active: bool
    created_by: Optional[str]
    notes: Optional[str]


def ensure_model_dir(metric_code: str) -> Path:
    """Ensure model directory exists for a metric"""
    metric_dir = MODEL_DIR / metric_code
    metric_dir.mkdir(parents=True, exist_ok=True)
    return metric_dir


def get_tft_config(db) -> Dict[str, Any]:
    """Load TFT configuration from database"""
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
            config[key] = int(value)
        elif key in ('learning_rate', 'dropout'):
            config[key] = float(value)
        elif key in ('use_gpu', 'auto_retrain', 'use_cached_model'):
            config[key] = value.lower() == 'true'
        else:
            config[key] = value

    return config


def save_tft_config(db, config: Dict[str, Any]) -> bool:
    """Save TFT configuration to database"""
    try:
        for key, value in config.items():
            config_key = f"tft_{key}"
            config_value = str(value).lower() if isinstance(value, bool) else str(value)

            db.execute(text("""
                INSERT INTO system_config (config_key, config_value)
                VALUES (:key, :value)
                ON CONFLICT (config_key) DO UPDATE SET config_value = :value
            """), {"key": config_key, "value": config_value})

        db.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save TFT config: {e}")
        db.rollback()
        return False


def save_model(
    db,
    model,
    dataset,
    metric_code: str,
    model_name: str,
    training_config: Dict[str, Any],
    training_time_seconds: int,
    validation_loss: Optional[float],
    epochs_completed: int,
    created_by: str = "system"
) -> Optional[str]:
    """
    Save a trained TFT model to disk and register in database.

    Args:
        db: Database session
        model: Trained TFT model
        dataset: TimeSeriesDataSet used for training (needed for loading)
        metric_code: Metric this model forecasts
        model_name: Unique name for this model
        training_config: Hyperparameters used
        training_time_seconds: How long training took
        validation_loss: Final validation loss
        epochs_completed: Number of epochs completed
        created_by: Who initiated training

    Returns:
        File path if successful, None otherwise
    """
    try:
        import torch

        # Ensure directory exists
        metric_dir = ensure_model_dir(metric_code)

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = model_name.replace(" ", "_").lower()
        filename = f"{safe_name}_{timestamp}.pt"
        file_path = metric_dir / filename

        # Save model checkpoint with all necessary info for loading
        checkpoint = {
            "model_state_dict": model.state_dict(),
            "model_hparams": model.hparams,
            "training_config": training_config,
            "metric_code": metric_code,
            "trained_at": datetime.now().isoformat(),
            "dataset_parameters": {
                "time_idx": dataset.time_idx,
                "target": dataset.target,
                "group_ids": dataset.group_ids,
                "max_encoder_length": dataset.max_encoder_length,
                "max_prediction_length": dataset.max_prediction_length,
                "time_varying_known_reals": dataset.time_varying_known_reals,
                "time_varying_unknown_reals": dataset.time_varying_unknown_reals,
                "static_categoricals": dataset.static_categoricals,
            }
        }

        torch.save(checkpoint, file_path)

        # Get file size
        file_size = file_path.stat().st_size

        # Deactivate any existing active model for this metric
        db.execute(text("""
            UPDATE tft_models SET is_active = FALSE
            WHERE metric_code = :metric_code AND is_active = TRUE
        """), {"metric_code": metric_code})

        # Register in database
        db.execute(text("""
            INSERT INTO tft_models (
                metric_code, model_name, file_path, file_size_bytes,
                training_config, training_time_seconds, validation_loss,
                epochs_completed, is_active, created_by
            ) VALUES (
                :metric_code, :model_name, :file_path, :file_size,
                :config, :time, :loss, :epochs, TRUE, :created_by
            )
            ON CONFLICT (metric_code, model_name) DO UPDATE SET
                file_path = :file_path,
                file_size_bytes = :file_size,
                trained_at = NOW(),
                training_config = :config,
                training_time_seconds = :time,
                validation_loss = :loss,
                epochs_completed = :epochs,
                is_active = TRUE
        """), {
            "metric_code": metric_code,
            "model_name": model_name,
            "file_path": str(file_path),
            "file_size": file_size,
            "config": json.dumps(training_config),
            "time": training_time_seconds,
            "loss": validation_loss,
            "epochs": epochs_completed,
            "created_by": created_by
        })

        db.commit()
        logger.info(f"Saved TFT model for {metric_code}: {file_path}")
        return str(file_path)

    except Exception as e:
        logger.error(f"Failed to save TFT model: {e}")
        db.rollback()
        return None


def load_model(db, metric_code: str):
    """
    Load the active TFT model for a metric.

    Args:
        db: Database session
        metric_code: Metric to load model for

    Returns:
        Tuple of (model, checkpoint, model_info) if found, (None, None, None) otherwise
    """
    try:
        import torch
        from pytorch_forecasting import TemporalFusionTransformer

        # Get active model path
        result = db.execute(text("""
            SELECT id, file_path, training_config, model_name, trained_at
            FROM tft_models
            WHERE metric_code = :metric_code AND is_active = TRUE
            ORDER BY trained_at DESC
            LIMIT 1
        """), {"metric_code": metric_code})
        row = result.fetchone()

        if not row or not row.file_path:
            logger.info(f"No active TFT model found for {metric_code}")
            return None, None, None

        file_path = Path(row.file_path)
        if not file_path.exists():
            logger.warning(f"Model file not found: {file_path}")
            return None, None, None

        # Load checkpoint
        checkpoint = torch.load(file_path, map_location="cpu", weights_only=False)

        # Reconstruct model from checkpoint
        # We need to recreate the model architecture from saved hparams
        if "model_state_dict" not in checkpoint:
            logger.error(f"Invalid checkpoint format: missing model_state_dict")
            return None, None, None

        # Create model from hparams and load state dict
        hparams = checkpoint.get("model_hparams", {})

        # Build model with the same architecture
        from pytorch_forecasting.metrics import QuantileLoss
        model = TemporalFusionTransformer(
            hidden_size=hparams.get("hidden_size", 64),
            attention_head_size=hparams.get("attention_head_size", 4),
            dropout=hparams.get("dropout", 0.1),
            hidden_continuous_size=hparams.get("hidden_continuous_size", 16),
            output_size=hparams.get("output_size", 7),
            loss=QuantileLoss(),
            learning_rate=hparams.get("learning_rate", 0.001),
            **{k: v for k, v in hparams.items() if k not in [
                "hidden_size", "attention_head_size", "dropout",
                "hidden_continuous_size", "output_size", "learning_rate", "loss"
            ]}
        )

        # Load the trained weights
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()  # Set to evaluation mode

        model_info = {
            "id": row.id,
            "model_name": row.model_name,
            "trained_at": row.trained_at.isoformat() if row.trained_at else None,
            "file_path": str(file_path)
        }

        logger.info(f"Loaded TFT model '{row.model_name}' for {metric_code} from {file_path}")
        return model, checkpoint, model_info

    except Exception as e:
        logger.error(f"Failed to load TFT model for {metric_code}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None, None, None


def load_model_by_id(db, model_id: int):
    """Load a specific model by ID"""
    try:
        import torch
        from pytorch_forecasting import TemporalFusionTransformer

        result = db.execute(text("""
            SELECT file_path FROM tft_models WHERE id = :id
        """), {"id": model_id})
        row = result.fetchone()

        if not row or not row.file_path:
            return None, None

        file_path = Path(row.file_path)
        if not file_path.exists():
            return None, None

        checkpoint = torch.load(file_path, map_location="cpu")
        return checkpoint, file_path

    except Exception as e:
        logger.error(f"Failed to load model {model_id}: {e}")
        return None, None


def export_model(db, model_id: int) -> Optional[bytes]:
    """
    Export a model as bytes for download.

    Args:
        db: Database session
        model_id: Model ID to export

    Returns:
        Model file bytes if successful, None otherwise
    """
    try:
        result = db.execute(text("""
            SELECT file_path FROM tft_models WHERE id = :id
        """), {"id": model_id})
        row = result.fetchone()

        if not row or not row.file_path:
            return None

        file_path = Path(row.file_path)
        if not file_path.exists():
            return None

        with open(file_path, "rb") as f:
            return f.read()

    except Exception as e:
        logger.error(f"Failed to export model {model_id}: {e}")
        return None


def import_model(
    db,
    file_bytes: bytes,
    metric_code: str,
    model_name: str,
    created_by: str = "import"
) -> Optional[int]:
    """
    Import a model from uploaded bytes.

    Args:
        db: Database session
        file_bytes: Model file content
        metric_code: Metric this model is for
        model_name: Name for the imported model
        created_by: Who imported it

    Returns:
        Model ID if successful, None otherwise
    """
    try:
        import torch

        # Validate the file is a valid PyTorch checkpoint
        buffer = io.BytesIO(file_bytes)
        checkpoint = torch.load(buffer, map_location="cpu")

        # Verify it has required fields
        if "model_state_dict" not in checkpoint:
            logger.error("Invalid model file: missing model_state_dict")
            return None

        # Save to disk
        metric_dir = ensure_model_dir(metric_code)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = model_name.replace(" ", "_").lower()
        filename = f"{safe_name}_{timestamp}.pt"
        file_path = metric_dir / filename

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        file_size = len(file_bytes)

        # Get config from checkpoint
        training_config = checkpoint.get("training_config", {})

        # Register in database
        db.execute(text("""
            INSERT INTO tft_models (
                metric_code, model_name, file_path, file_size_bytes,
                training_config, is_active, created_by, notes
            ) VALUES (
                :metric_code, :model_name, :file_path, :file_size,
                :config, FALSE, :created_by, 'Imported model'
            )
        """), {
            "metric_code": metric_code,
            "model_name": model_name,
            "file_path": str(file_path),
            "file_size": file_size,
            "config": json.dumps(training_config),
            "created_by": created_by
        })

        db.commit()

        # Get the inserted ID
        result = db.execute(text("""
            SELECT id FROM tft_models
            WHERE metric_code = :metric_code AND model_name = :model_name
        """), {"metric_code": metric_code, "model_name": model_name})
        row = result.fetchone()

        logger.info(f"Imported TFT model for {metric_code}: {file_path}")
        return row.id if row else None

    except Exception as e:
        logger.error(f"Failed to import model: {e}")
        db.rollback()
        return None


def list_models(db, metric_code: Optional[str] = None) -> List[ModelInfo]:
    """
    List all stored models, optionally filtered by metric.

    Args:
        db: Database session
        metric_code: Optional filter by metric

    Returns:
        List of ModelInfo objects
    """
    try:
        if metric_code:
            result = db.execute(text("""
                SELECT * FROM tft_models
                WHERE metric_code = :metric_code
                ORDER BY trained_at DESC
            """), {"metric_code": metric_code})
        else:
            result = db.execute(text("""
                SELECT * FROM tft_models
                ORDER BY metric_code, trained_at DESC
            """))

        models = []
        for row in result.fetchall():
            models.append(ModelInfo(
                id=row.id,
                metric_code=row.metric_code,
                model_name=row.model_name,
                file_path=row.file_path,
                file_size_bytes=row.file_size_bytes,
                trained_at=row.trained_at,
                training_config=json.loads(row.training_config) if row.training_config else {},
                training_time_seconds=row.training_time_seconds,
                validation_loss=float(row.validation_loss) if row.validation_loss else None,
                epochs_completed=row.epochs_completed,
                is_active=row.is_active,
                created_by=row.created_by,
                notes=row.notes
            ))

        return models

    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        return []


def activate_model(db, model_id: int) -> bool:
    """
    Set a model as the active model for its metric.

    Args:
        db: Database session
        model_id: Model to activate

    Returns:
        True if successful
    """
    try:
        # Get the metric code
        result = db.execute(text("""
            SELECT metric_code FROM tft_models WHERE id = :id
        """), {"id": model_id})
        row = result.fetchone()

        if not row:
            return False

        metric_code = row.metric_code

        # Deactivate all models for this metric
        db.execute(text("""
            UPDATE tft_models SET is_active = FALSE
            WHERE metric_code = :metric_code
        """), {"metric_code": metric_code})

        # Activate the specified model
        db.execute(text("""
            UPDATE tft_models SET is_active = TRUE WHERE id = :id
        """), {"id": model_id})

        db.commit()
        logger.info(f"Activated model {model_id} for {metric_code}")
        return True

    except Exception as e:
        logger.error(f"Failed to activate model {model_id}: {e}")
        db.rollback()
        return False


def delete_model(db, model_id: int) -> bool:
    """
    Delete a model from database and disk.

    Args:
        db: Database session
        model_id: Model to delete

    Returns:
        True if successful
    """
    try:
        # Get file path
        result = db.execute(text("""
            SELECT file_path, is_active FROM tft_models WHERE id = :id
        """), {"id": model_id})
        row = result.fetchone()

        if not row:
            return False

        if row.is_active:
            logger.warning("Cannot delete active model")
            return False

        # Delete file if exists
        if row.file_path:
            file_path = Path(row.file_path)
            if file_path.exists():
                file_path.unlink()

        # Delete from database
        db.execute(text("DELETE FROM tft_models WHERE id = :id"), {"id": model_id})
        db.commit()

        logger.info(f"Deleted model {model_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to delete model {model_id}: {e}")
        db.rollback()
        return False


def get_training_job_status(db, job_id: str) -> Optional[Dict[str, Any]]:
    """Get status of a training job"""
    try:
        result = db.execute(text("""
            SELECT * FROM tft_training_jobs WHERE job_id = :job_id
        """), {"job_id": job_id})
        row = result.fetchone()

        if not row:
            return None

        return {
            "id": row.id,
            "job_id": str(row.job_id),
            "metric_code": row.metric_code,
            "status": row.status,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "progress_pct": row.progress_pct,
            "current_epoch": row.current_epoch,
            "total_epochs": row.total_epochs,
            "error_message": row.error_message,
            "created_by": row.created_by
        }

    except Exception as e:
        logger.error(f"Failed to get job status: {e}")
        return None


def create_training_job(db, metric_code: str, total_epochs: int, created_by: str) -> str:
    """Create a new training job and return job_id"""
    import uuid
    job_id = str(uuid.uuid4())

    try:
        db.execute(text("""
            INSERT INTO tft_training_jobs (job_id, metric_code, total_epochs, created_by)
            VALUES (:job_id, :metric_code, :total_epochs, :created_by)
        """), {
            "job_id": job_id,
            "metric_code": metric_code,
            "total_epochs": total_epochs,
            "created_by": created_by
        })
        db.commit()
        return job_id
    except Exception as e:
        logger.error(f"Failed to create training job: {e}")
        db.rollback()
        raise


def update_training_job(
    db,
    job_id: str,
    status: Optional[str] = None,
    progress_pct: Optional[int] = None,
    current_epoch: Optional[int] = None,
    error_message: Optional[str] = None
):
    """Update training job status"""
    try:
        updates = []
        params = {"job_id": job_id}

        if status:
            updates.append("status = :status")
            params["status"] = status
            if status == "running":
                updates.append("started_at = NOW()")
            elif status in ("completed", "failed"):
                updates.append("completed_at = NOW()")

        if progress_pct is not None:
            updates.append("progress_pct = :progress_pct")
            params["progress_pct"] = progress_pct

        if current_epoch is not None:
            updates.append("current_epoch = :current_epoch")
            params["current_epoch"] = current_epoch

        if error_message:
            updates.append("error_message = :error_message")
            params["error_message"] = error_message

        if updates:
            db.execute(text(f"""
                UPDATE tft_training_jobs
                SET {', '.join(updates)}
                WHERE job_id = :job_id
            """), params)
            db.commit()

    except Exception as e:
        logger.error(f"Failed to update training job: {e}")
        db.rollback()
