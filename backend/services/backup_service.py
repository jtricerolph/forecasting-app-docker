"""
Backup and Restore Service

Handles creating full backups of the database and files, and restoring from backups.
"""
import os
import json
import logging
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Backup storage directory
BACKUP_DIR = Path("/app/data/backups")
DATA_DIR = Path("/app/data")


class BackupService:
    """Service for managing backups and restores"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ensure_backup_dir()

    def ensure_backup_dir(self):
        """Ensure backup directory exists"""
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    async def ensure_backup_table_exists(self):
        """Create backup_history table if it doesn't exist"""
        await self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS backup_history (
                id SERIAL PRIMARY KEY,
                backup_type VARCHAR(20) NOT NULL,
                status VARCHAR(20) NOT NULL,
                filename VARCHAR(255),
                file_path TEXT,
                file_size_bytes BIGINT,
                snapshot_count INTEGER,
                file_count INTEGER,
                started_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP,
                error_message TEXT,
                created_by VARCHAR(100)
            )
        """))
        await self.db.commit()

    async def get_backup_settings(self) -> Dict[str, Any]:
        """Get backup configuration from system_config"""
        settings = {
            'backup_frequency': 'manual',
            'backup_retention_count': 7,
            'backup_destination': 'local',
            'backup_time': None,
            'backup_last_run_at': None,
            'backup_last_status': None
        }

        result = await self.db.execute(text("""
            SELECT config_key, config_value
            FROM system_config
            WHERE config_key LIKE 'backup_%'
        """))
        rows = result.fetchall()

        for row in rows:
            settings[row.config_key] = row.config_value

        return settings

    async def update_backup_settings(self, updates: Dict[str, Any]) -> bool:
        """Update backup configuration"""
        try:
            for key, value in updates.items():
                if not key.startswith('backup_'):
                    key = f'backup_{key}'

                await self.db.execute(text("""
                    INSERT INTO system_config (config_key, config_value, updated_at)
                    VALUES (:key, :value, NOW())
                    ON CONFLICT (config_key) DO UPDATE
                    SET config_value = :value, updated_at = NOW()
                """), {'key': key, 'value': str(value)})

            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update backup settings: {e}")
            await self.db.rollback()
            return False

    async def create_backup(
        self,
        backup_type: str = 'manual',
        created_by: Optional[str] = None
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Create a full backup of database and files

        Returns: (success, message, backup_id)
        """
        backup_id = None
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"backup_{timestamp}.zip"
        filepath = BACKUP_DIR / filename

        try:
            # Create backup record
            result = await self.db.execute(text("""
                INSERT INTO backup_history (
                    backup_type, status, filename, started_at, created_by
                ) VALUES (
                    :backup_type, 'running', :filename, NOW(), :created_by
                ) RETURNING id
            """), {
                'backup_type': backup_type,
                'filename': filename,
                'created_by': created_by
            })
            await self.db.commit()
            row = result.fetchone()
            backup_id = row.id if row else None

            # Create temporary directory for backup contents
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # 1. Create PostgreSQL dump
                db_url = os.getenv('DATABASE_URL', 'postgresql://forecast:forecast_secret@localhost:5432/forecast')
                db_parts = db_url.replace('postgresql://', '').split('@')
                user_pass = db_parts[0].split(':')
                host_db = db_parts[1].split('/')

                db_dump_path = temp_path / 'database.sql'
                env = os.environ.copy()
                env['PGPASSWORD'] = user_pass[1] if len(user_pass) > 1 else ''

                pg_dump_cmd = [
                    'pg_dump',
                    '-h', host_db[0].split(':')[0],
                    '-U', user_pass[0],
                    '-d', host_db[1] if len(host_db) > 1 else 'forecast',
                    '-f', str(db_dump_path),
                    '--no-owner',
                    '--no-acl'
                ]

                subprocess.run(pg_dump_cmd, env=env, check=True, capture_output=True)

                # 2. Create JSON export
                db_json_path = temp_path / 'database.json'
                snapshot_count = await self._export_database_json(db_json_path)

                # 3. Copy files
                files_dir = temp_path / 'files'
                file_count = self._copy_data_files(files_dir)

                # 4. Create metadata
                metadata = {
                    'version': '1.0',
                    'timestamp': datetime.now().isoformat(),
                    'snapshot_count': snapshot_count,
                    'file_count': file_count,
                    'database_url': db_url.split('@')[1]  # Only host/db, not credentials
                }
                metadata_path = temp_path / 'metadata.json'
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=2)

                # 5. Create ZIP file
                with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for file in temp_path.rglob('*'):
                        if file.is_file():
                            arcname = file.relative_to(temp_path)
                            zf.write(file, arcname)

            # Update backup record with success
            file_size = filepath.stat().st_size
            await self.db.execute(text("""
                UPDATE backup_history
                SET status = 'success',
                    file_path = :file_path,
                    file_size_bytes = :file_size,
                    snapshot_count = :snapshot_count,
                    file_count = :file_count,
                    completed_at = NOW()
                WHERE id = :backup_id
            """), {
                'backup_id': backup_id,
                'file_path': str(filepath),
                'file_size': file_size,
                'snapshot_count': snapshot_count,
                'file_count': file_count
            })
            await self.db.commit()

            # Update last backup settings
            await self.update_backup_settings({
                'backup_last_run_at': datetime.now().isoformat(),
                'backup_last_status': 'success'
            })

            # Enforce retention policy
            await self._enforce_retention()

            return True, f"Backup created successfully: {filename}", backup_id

        except Exception as e:
            logger.error(f"Backup creation failed: {e}")

            # Update backup record with failure
            if backup_id:
                await self.db.execute(text("""
                    UPDATE backup_history
                    SET status = 'failed',
                        error_message = :error,
                        completed_at = NOW()
                    WHERE id = :backup_id
                """), {
                    'backup_id': backup_id,
                    'error': str(e)
                })
                await self.db.commit()

            # Update last backup status
            await self.update_backup_settings({
                'backup_last_run_at': datetime.now().isoformat(),
                'backup_last_status': 'failed'
            })

            return False, f"Backup failed: {str(e)}", backup_id

    async def _export_database_json(self, output_path: Path) -> int:
        """Export database tables to JSON format"""
        export_data = {
            'exported_at': datetime.now().isoformat(),
            'tables': {}
        }

        # Tables to export
        tables = [
            'forecast_snapshots',
            'special_dates',
            'newbook_bookings_data',
            'newbook_bookings_stats',
            'newbook_booking_pace',
            'newbook_occupancy_report_data',
            'newbook_room_categories',
            'monthly_budgets',
            'system_config',
            'users'
        ]

        snapshot_count = 0
        for table in tables:
            try:
                result = await self.db.execute(text(f"SELECT * FROM {table}"))
                rows = result.fetchall()
                columns = result.keys()

                export_data['tables'][table] = [
                    {col: self._serialize_value(getattr(row, col)) for col in columns}
                    for row in rows
                ]

                if table == 'forecast_snapshots':
                    snapshot_count = len(rows)

            except Exception as e:
                logger.warning(f"Could not export table {table}: {e}")
                export_data['tables'][table] = []

        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)

        return snapshot_count

    def _serialize_value(self, value):
        """Convert value to JSON-serializable format"""
        if isinstance(value, (datetime,)):
            return value.isoformat()
        return value

    def _copy_data_files(self, dest_dir: Path) -> int:
        """Copy all data files to backup directory"""
        dest_dir.mkdir(parents=True, exist_ok=True)
        file_count = 0

        # Skip backup directory itself
        for root, dirs, files in os.walk(DATA_DIR):
            # Remove backup directory from traversal
            dirs[:] = [d for d in dirs if d != 'backups']

            for file in files:
                src_file = Path(root) / file
                rel_path = src_file.relative_to(DATA_DIR)
                dest_file = dest_dir / rel_path

                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dest_file)
                file_count += 1

        return file_count

    async def list_backups(self, limit: int = 50) -> list:
        """List all backups, newest first"""
        result = await self.db.execute(text("""
            SELECT
                id, backup_type, status, filename, file_path,
                file_size_bytes, snapshot_count, file_count,
                started_at, completed_at, error_message, created_by
            FROM backup_history
            ORDER BY started_at DESC
            LIMIT :limit
        """), {'limit': limit})

        rows = result.fetchall()
        return [
            {
                'id': row.id,
                'backup_type': row.backup_type,
                'status': row.status,
                'filename': row.filename,
                'file_path': row.file_path,
                'file_size_bytes': row.file_size_bytes,
                'snapshot_count': row.snapshot_count,
                'file_count': row.file_count,
                'started_at': row.started_at.isoformat() if row.started_at else None,
                'completed_at': row.completed_at.isoformat() if row.completed_at else None,
                'error_message': row.error_message,
                'created_by': row.created_by
            }
            for row in rows
        ]

    async def get_backup(self, backup_id: int) -> Optional[Dict]:
        """Get a specific backup by ID"""
        result = await self.db.execute(text("""
            SELECT
                id, backup_type, status, filename, file_path,
                file_size_bytes, snapshot_count, file_count,
                started_at, completed_at, error_message, created_by
            FROM backup_history
            WHERE id = :backup_id
        """), {'backup_id': backup_id})

        row = result.fetchone()
        if not row:
            return None

        return {
            'id': row.id,
            'backup_type': row.backup_type,
            'status': row.status,
            'filename': row.filename,
            'file_path': row.file_path,
            'file_size_bytes': row.file_size_bytes,
            'snapshot_count': row.snapshot_count,
            'file_count': row.file_count,
            'started_at': row.started_at.isoformat() if row.started_at else None,
            'completed_at': row.completed_at.isoformat() if row.completed_at else None,
            'error_message': row.error_message,
            'created_by': row.created_by
        }

    async def delete_backup(self, backup_id: int) -> Tuple[bool, str]:
        """Delete a backup file and record"""
        try:
            # Get backup info
            backup = await self.get_backup(backup_id)
            if not backup:
                return False, "Backup not found"

            # Delete file if it exists
            if backup['file_path']:
                file_path = Path(backup['file_path'])
                if file_path.exists():
                    file_path.unlink()

            # Delete database record
            await self.db.execute(text("""
                DELETE FROM backup_history WHERE id = :backup_id
            """), {'backup_id': backup_id})
            await self.db.commit()

            return True, "Backup deleted successfully"

        except Exception as e:
            logger.error(f"Failed to delete backup: {e}")
            await self.db.rollback()
            return False, f"Failed to delete backup: {str(e)}"

    async def restore_from_backup(self, backup_id: int) -> Tuple[bool, str]:
        """Restore database and files from a backup"""
        try:
            # Get backup info
            backup = await self.get_backup(backup_id)
            if not backup:
                return False, "Backup not found"

            if backup['status'] != 'success':
                return False, "Cannot restore from failed backup"

            backup_path = Path(backup['file_path'])
            if not backup_path.exists():
                return False, "Backup file not found"

            return await self._restore_from_file(backup_path)

        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return False, f"Restore failed: {str(e)}"

    async def restore_from_upload(self, file_content: bytes, filename: str) -> Tuple[bool, str]:
        """Restore from an uploaded backup file"""
        try:
            # Save uploaded file temporarily
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
                temp_file.write(file_content)
                temp_path = Path(temp_file.name)

            try:
                # Validate ZIP file
                if not zipfile.is_zipfile(temp_path):
                    return False, "Invalid backup file (not a ZIP file)"

                return await self._restore_from_file(temp_path)
            finally:
                # Clean up temp file
                if temp_path.exists():
                    temp_path.unlink()

        except Exception as e:
            logger.error(f"Upload restore failed: {e}")
            return False, f"Restore failed: {str(e)}"

    async def _restore_from_file(self, backup_path: Path) -> Tuple[bool, str]:
        """Internal method to restore from a backup ZIP file"""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Extract ZIP
                with zipfile.ZipFile(backup_path, 'r') as zf:
                    zf.extractall(temp_path)

                # Validate required files
                db_sql_path = temp_path / 'database.sql'
                if not db_sql_path.exists():
                    return False, "Invalid backup: missing database.sql"

                # Restore database
                db_url = os.getenv('DATABASE_URL', 'postgresql://forecast:forecast_secret@localhost:5432/forecast')
                db_parts = db_url.replace('postgresql://', '').split('@')
                user_pass = db_parts[0].split(':')
                host_db = db_parts[1].split('/')

                env = os.environ.copy()
                env['PGPASSWORD'] = user_pass[1] if len(user_pass) > 1 else ''

                psql_cmd = [
                    'psql',
                    '-h', host_db[0].split(':')[0],
                    '-U', user_pass[0],
                    '-d', host_db[1] if len(host_db) > 1 else 'forecast',
                    '-f', str(db_sql_path)
                ]

                result = subprocess.run(psql_cmd, env=env, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error(f"Database restore failed: {result.stderr}")
                    return False, f"Database restore failed: {result.stderr}"

                # Restore files
                files_dir = temp_path / 'files'
                if files_dir.exists():
                    file_count = 0
                    for root, dirs, files in os.walk(files_dir):
                        for file in files:
                            src_file = Path(root) / file
                            rel_path = src_file.relative_to(files_dir)
                            dest_file = DATA_DIR / rel_path

                            dest_file.parent.mkdir(parents=True, exist_ok=True)
                            # Don't overwrite existing files
                            if not dest_file.exists():
                                shutil.copy2(src_file, dest_file)
                                file_count += 1

                    logger.info(f"Restored {file_count} files")

                return True, "Backup restored successfully"

        except Exception as e:
            logger.error(f"Restore from file failed: {e}")
            return False, f"Restore failed: {str(e)}"

    async def _enforce_retention(self):
        """Delete old backups beyond retention count"""
        try:
            settings = await self.get_backup_settings()
            retention_count = int(settings.get('backup_retention_count', 7))

            # Get backups to delete (beyond retention count)
            result = await self.db.execute(text("""
                SELECT id, file_path
                FROM backup_history
                WHERE status = 'success'
                ORDER BY started_at DESC
                OFFSET :retention_count
            """), {'retention_count': retention_count})

            rows = result.fetchall()
            for row in rows:
                # Delete file
                if row.file_path:
                    file_path = Path(row.file_path)
                    if file_path.exists():
                        file_path.unlink()

                # Delete record
                await self.db.execute(text("""
                    DELETE FROM backup_history WHERE id = :backup_id
                """), {'backup_id': row.id})

            await self.db.commit()
            logger.info(f"Retention policy: deleted {len(rows)} old backups")

        except Exception as e:
            logger.error(f"Failed to enforce retention policy: {e}")
