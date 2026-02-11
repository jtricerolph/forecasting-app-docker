"""
Backup and Restore API Endpoints
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

from database import get_db
from auth import get_current_user
from services.backup_service import BackupService

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================
# HELPER FUNCTIONS
# ============================================
# Note: All backup endpoints require authentication but not admin role,
# consistent with other sensitive operations in the application


# ============================================
# API ENDPOINTS
# ============================================

@router.get("/settings")
async def get_backup_settings(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get backup configuration settings

    Returns backup frequency, retention count, destination, and last backup status
    """
    try:
        service = BackupService(db)
        await service.ensure_backup_table_exists()
        settings = await service.get_backup_settings()
        return settings
    except Exception as e:
        logger.error(f"Failed to get backup settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/settings")
async def update_backup_settings(
    updates: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update backup configuration settings

    Body: {
        frequency?: 'manual' | 'daily' | 'weekly' | 'monthly',
        retention_count?: number,
        destination?: 'local',
        time?: 'HH:MM'
    }
    """
    try:
        service = BackupService(db)
        success = await service.update_backup_settings(updates)

        if success:
            return {"message": "Settings updated successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update settings")

    except Exception as e:
        logger.error(f"Failed to update backup settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
async def create_backup(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger manual backup creation

    Creates a ZIP file containing database dump, JSON export, and all data files.
    Returns backup ID and status.
    """
    try:
        service = BackupService(db)
        await service.ensure_backup_table_exists()

        username = current_user.get('username', 'unknown')
        success, message, backup_id = await service.create_backup(
            backup_type='manual',
            created_by=username
        )

        if success:
            return {
                "success": True,
                "message": message,
                "backup_id": backup_id
            }
        else:
            raise HTTPException(status_code=500, detail=message)

    except Exception as e:
        logger.error(f"Backup creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_backup_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all backups, newest first

    Query params:
    - limit: Maximum number of backups to return (default 50)
    """
    try:
        service = BackupService(db)
        await service.ensure_backup_table_exists()
        backups = await service.list_backups(limit=limit)
        return backups
    except Exception as e:
        logger.error(f"Failed to get backup history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{backup_id}")
async def get_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get a specific backup by ID"""
    try:
        service = BackupService(db)
        backup = await service.get_backup(backup_id)

        if not backup:
            raise HTTPException(status_code=404, detail="Backup not found")

        return backup
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{backup_id}/download")
async def download_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Download a backup file

    Returns the backup ZIP file for download
    """
    try:
        service = BackupService(db)
        backup = await service.get_backup(backup_id)

        if not backup:
            raise HTTPException(status_code=404, detail="Backup not found")

        if backup['status'] != 'success':
            raise HTTPException(
                status_code=400,
                detail="Cannot download backup that did not complete successfully"
            )

        file_path = Path(backup['file_path'])
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Backup file not found on disk")

        return FileResponse(
            path=str(file_path),
            filename=backup['filename'],
            media_type='application/zip'
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{backup_id}/restore")
async def restore_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Restore from an existing backup

    WARNING: This will overwrite the current database with the backup data.
    All current data will be replaced.
    """
    try:
        service = BackupService(db)
        success, message = await service.restore_from_backup(backup_id)

        if success:
            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=500, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-restore")
async def upload_and_restore(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload and restore from a backup file

    Upload a backup ZIP file and restore database and files from it.

    WARNING: This will overwrite the current database with the backup data.
    """
    try:
        # Validate file type
        if not file.filename or not file.filename.endswith('.zip'):
            raise HTTPException(
                status_code=400,
                detail="Only ZIP files are accepted"
            )

        # Read file content
        file_content = await file.read()

        # Validate file size (max 5GB)
        max_size = 5 * 1024 * 1024 * 1024  # 5GB
        if len(file_content) > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"File too large (max {max_size / 1024 / 1024 / 1024}GB)"
            )

        # Restore from uploaded file
        service = BackupService(db)
        success, message = await service.restore_from_upload(
            file_content=file_content,
            filename=file.filename
        )

        if success:
            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=500, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload restore failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{backup_id}")
async def delete_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a backup file and record

    Removes the backup file from disk and deletes the database record.
    """
    try:
        service = BackupService(db)
        success, message = await service.delete_backup(backup_id)

        if success:
            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=500, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))
