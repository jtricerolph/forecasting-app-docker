"""
Configuration API endpoints
Manage system configuration including API credentials
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
import base64

from database import get_db
from auth import get_current_user

router = APIRouter()


# ============================================
# NEWBOOK SETTINGS ENDPOINTS
# ============================================

class NewbookSettingsResponse(BaseModel):
    newbook_api_key: Optional[str] = None
    newbook_api_key_set: bool = False
    newbook_username: Optional[str] = None
    newbook_password_set: bool = False
    newbook_region: Optional[str] = None


class NewbookSettingsUpdate(BaseModel):
    newbook_api_key: Optional[str] = None
    newbook_username: Optional[str] = None
    newbook_password: Optional[str] = None
    newbook_region: Optional[str] = None


@router.get("/settings/newbook", response_model=NewbookSettingsResponse)
async def get_newbook_settings(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all Newbook settings in one response"""
    result = await db.execute(
        text("""
            SELECT config_key, config_value, is_encrypted
            FROM system_config
            WHERE config_key IN ('newbook_api_key', 'newbook_username', 'newbook_password', 'newbook_region')
        """)
    )
    rows = result.fetchall()

    settings = {}
    for row in rows:
        key = row.config_key
        value = row.config_value
        is_encrypted = row.is_encrypted

        if key == 'newbook_api_key':
            settings['newbook_api_key'] = None
            settings['newbook_api_key_set'] = bool(value)
        elif key == 'newbook_username':
            settings['newbook_username'] = value
        elif key == 'newbook_password':
            settings['newbook_password_set'] = bool(value)
        elif key == 'newbook_region':
            settings['newbook_region'] = value

    return NewbookSettingsResponse(**settings)


@router.post("/settings/newbook")
async def update_newbook_settings(
    settings: NewbookSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update Newbook settings"""
    username = current_user.get("username")

    # Only update fields that are provided (not None)
    if settings.newbook_api_key is not None:
        encrypted_value = simple_encrypt(settings.newbook_api_key)
        await db.execute(
            text("""
                UPDATE system_config
                SET config_value = :value, is_encrypted = true, updated_at = NOW(), updated_by = :username
                WHERE config_key = 'newbook_api_key'
            """),
            {"value": encrypted_value, "username": username}
        )

    if settings.newbook_username is not None:
        await db.execute(
            text("""
                UPDATE system_config
                SET config_value = :value, updated_at = NOW(), updated_by = :username
                WHERE config_key = 'newbook_username'
            """),
            {"value": settings.newbook_username, "username": username}
        )

    if settings.newbook_password is not None:
        encrypted_value = simple_encrypt(settings.newbook_password)
        await db.execute(
            text("""
                UPDATE system_config
                SET config_value = :value, is_encrypted = true, updated_at = NOW(), updated_by = :username
                WHERE config_key = 'newbook_password'
            """),
            {"value": encrypted_value, "username": username}
        )

    if settings.newbook_region is not None:
        await db.execute(
            text("""
                UPDATE system_config
                SET config_value = :value, updated_at = NOW(), updated_by = :username
                WHERE config_key = 'newbook_region'
            """),
            {"value": settings.newbook_region, "username": username}
        )

    await db.commit()
    return {"status": "saved", "message": "Newbook settings updated"}


@router.post("/settings/newbook/test")
async def test_newbook_settings(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Test Newbook connection with current settings"""
    return await _test_newbook(db)


# ============================================
# ROOM CATEGORIES ENDPOINTS
# ============================================

from typing import List

class RoomCategoryResponse(BaseModel):
    id: int
    site_id: str
    site_name: str
    site_type: Optional[str] = None
    room_count: int = 0
    is_included: bool = True
    display_order: int = 0

    class Config:
        from_attributes = True


class RoomCategoryUpdate(BaseModel):
    id: int
    is_included: bool


class RoomCategoryBulkUpdate(BaseModel):
    updates: List[RoomCategoryUpdate]


@router.get("/room-categories", response_model=List[RoomCategoryResponse])
async def get_room_categories(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all room categories"""
    result = await db.execute(
        text("""
            SELECT id, site_id, site_name, site_type, room_count, is_included, display_order
            FROM newbook_room_categories
            ORDER BY display_order, site_name
        """)
    )
    rows = result.fetchall()

    return [
        {
            "id": row.id,
            "site_id": row.site_id,
            "site_name": row.site_name,
            "site_type": row.site_type,
            "room_count": row.room_count,
            "is_included": row.is_included,
            "display_order": row.display_order
        }
        for row in rows
    ]


@router.post("/room-categories/fetch")
async def fetch_room_categories(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Fetch room categories from Newbook API site_list endpoint"""
    import httpx

    api_key = await _get_config_value(db, "newbook_api_key")
    username = await _get_config_value(db, "newbook_username")
    password = await _get_config_value(db, "newbook_password")
    region = await _get_config_value(db, "newbook_region")

    if not all([api_key, username, password, region]):
        raise HTTPException(status_code=400, detail="Newbook credentials not configured")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.newbook.cloud/rest/site_list",
                json={
                    "region": region,
                    "api_key": api_key
                },
                auth=(username, password),
                headers={"Content-Type": "application/json"}
            )

            if response.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Newbook API error: {response.status_code}")

            data = response.json()
            if not data.get("success"):
                raise HTTPException(status_code=400, detail=data.get("message", "API request failed"))

            sites = data.get("data", [])

            # Aggregate by category_id - Newbook returns:
            # - category_id: numeric category ID (e.g., "56")
            # - category_name: category name (e.g., "Holiday Rentals")
            # - site_id: individual room ID (not what we want)
            # - site_name: individual room name (not what we want)
            room_categories = {}
            for site in sites:
                cat_id = site.get("category_id")
                cat_name = site.get("category_name") or "Unknown"

                if not cat_id:
                    continue

                cat_id_str = str(cat_id)
                if cat_id_str not in room_categories:
                    room_categories[cat_id_str] = {
                        "site_id": cat_id_str,
                        "site_name": cat_name,
                        "room_count": 0
                    }
                room_categories[cat_id_str]["room_count"] += 1

            # Upsert room categories - create new ones if they don't exist
            updated = 0
            created = 0
            for cat_id, cat in room_categories.items():
                result = await db.execute(
                    text("""
                        INSERT INTO newbook_room_categories (site_id, site_name, site_type, room_count, fetched_at)
                        VALUES (:site_id, :site_name, :site_name, :room_count, NOW())
                        ON CONFLICT (site_id) DO UPDATE SET
                            site_name = EXCLUDED.site_name,
                            room_count = EXCLUDED.room_count,
                            fetched_at = NOW()
                    """),
                    cat
                )
                if result.rowcount > 0:
                    updated += 1

            await db.commit()

            return {
                "status": "success",
                "count": updated,
                "message": f"Updated {updated} room categories ({len(sites)} total rooms from API)"
            }

    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail="Connection timed out")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/room-categories/bulk-update")
async def bulk_update_room_categories(
    request: RoomCategoryBulkUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Bulk update room category is_included flag"""
    updated = 0
    for upd in request.updates:
        result = await db.execute(
            text("""
                UPDATE newbook_room_categories
                SET is_included = :is_included
                WHERE id = :id
            """),
            {"id": upd.id, "is_included": upd.is_included}
        )
        if result.rowcount > 0:
            updated += 1

    await db.commit()
    return {"status": "success", "updated": updated}


# ============================================
# GL ACCOUNT ENDPOINTS
# ============================================

class GLAccountResponse(BaseModel):
    id: int
    gl_account_id: str
    gl_code: Optional[str] = None
    gl_name: Optional[str] = None
    gl_group_id: Optional[str] = None
    gl_group_name: Optional[str] = None
    department: Optional[str] = None
    is_active: bool = True

    class Config:
        from_attributes = True


class GLAccountDepartmentUpdate(BaseModel):
    id: int
    department: Optional[str] = None  # 'accommodation', 'dry', 'wet', or null


class GLAccountBulkDepartmentUpdate(BaseModel):
    updates: List[GLAccountDepartmentUpdate]


@router.get("/gl-accounts", response_model=List[GLAccountResponse])
async def get_gl_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all GL accounts sorted by group then name"""
    result = await db.execute(
        text("""
            SELECT id, gl_account_id, gl_code, gl_name, gl_group_id, gl_group_name, department, is_active
            FROM newbook_gl_accounts
            WHERE is_active = TRUE
            ORDER BY gl_group_name NULLS LAST, gl_name
        """)
    )
    rows = result.fetchall()

    return [
        {
            "id": row.id,
            "gl_account_id": row.gl_account_id,
            "gl_code": row.gl_code,
            "gl_name": row.gl_name,
            "gl_group_id": row.gl_group_id,
            "gl_group_name": row.gl_group_name,
            "department": row.department,
            "is_active": row.is_active
        }
        for row in rows
    ]


@router.post("/gl-accounts/fetch")
async def fetch_gl_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Fetch GL accounts from Newbook API gl_account_list endpoint"""
    import httpx

    api_key = await _get_config_value(db, "newbook_api_key")
    username = await _get_config_value(db, "newbook_username")
    password = await _get_config_value(db, "newbook_password")
    region = await _get_config_value(db, "newbook_region")

    if not all([api_key, username, password, region]):
        raise HTTPException(status_code=400, detail="Newbook credentials not configured")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.newbook.cloud/rest/gl_account_list",
                json={
                    "region": region,
                    "api_key": api_key
                },
                auth=(username, password),
                headers={"Content-Type": "application/json"}
            )

            if response.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Newbook API error: {response.status_code}")

            data = response.json()
            if not data.get("success"):
                raise HTTPException(status_code=400, detail=data.get("message", "API request failed"))

            accounts = data.get("data", [])

            # Debug: Log first account to see actual field names
            import logging
            logger = logging.getLogger(__name__)
            if accounts and len(accounts) > 0:
                logger.info(f"GL Account first item keys: {list(accounts[0].keys())}")
                logger.info(f"GL Account first item: {accounts[0]}")

            # Upsert GL accounts - preserve existing department mappings
            # Newbook API field names: gl_account_id, gl_account_name, gl_account_code, gl_group_id, gl_group_name
            for acc in accounts:
                # Get account ID - prefer gl_account_id, fall back to id
                gl_account_id = str(acc.get("gl_account_id") or acc.get("id") or "")
                if not gl_account_id:
                    continue

                # Get account name - Newbook uses gl_account_name
                gl_name = acc.get("gl_account_name") or acc.get("name") or ""

                # Get account code - Newbook uses gl_account_code
                gl_code = acc.get("gl_account_code") or acc.get("code") or ""
                # Extract code from name if not available (format: "4100 - Room Revenue")
                if not gl_code and " - " in gl_name:
                    gl_code = gl_name.split(" - ")[0].strip()

                # Get group info - Newbook uses gl_group_id and gl_group_name directly
                gl_group_id = str(acc.get("gl_group_id") or "")
                gl_group_name = acc.get("gl_group_name") or ""

                await db.execute(
                    text("""
                        INSERT INTO newbook_gl_accounts (gl_account_id, gl_code, gl_name, gl_group_id, gl_group_name, fetched_at)
                        VALUES (:gl_account_id, :gl_code, :gl_name, :gl_group_id, :gl_group_name, NOW())
                        ON CONFLICT (gl_account_id) DO UPDATE SET
                            gl_code = EXCLUDED.gl_code,
                            gl_name = EXCLUDED.gl_name,
                            gl_group_id = EXCLUDED.gl_group_id,
                            gl_group_name = EXCLUDED.gl_group_name,
                            fetched_at = NOW()
                    """),
                    {
                        "gl_account_id": gl_account_id,
                        "gl_code": gl_code,
                        "gl_name": gl_name,
                        "gl_group_id": gl_group_id,
                        "gl_group_name": gl_group_name
                    }
                )

            await db.commit()

            return {
                "status": "success",
                "count": len(accounts),
                "message": f"Fetched {len(accounts)} GL accounts"
            }

    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail="Connection timed out")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/gl-accounts/department")
async def update_gl_account_departments(
    request: GLAccountBulkDepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Bulk update GL account department mappings"""
    updated = 0
    for upd in request.updates:
        # Validate department value
        if upd.department and upd.department not in ('accommodation', 'dry', 'wet'):
            raise HTTPException(status_code=400, detail=f"Invalid department: {upd.department}")

        result = await db.execute(
            text("""
                UPDATE newbook_gl_accounts
                SET department = :department
                WHERE id = :id
            """),
            {"id": upd.id, "department": upd.department}
        )
        if result.rowcount > 0:
            updated += 1

    await db.commit()
    return {"status": "success", "updated": updated}


# ============================================
# GENERIC CONFIG ENDPOINTS
# ============================================

class ConfigValue(BaseModel):
    key: str
    value: str
    is_encrypted: bool = False


class ConfigResponse(BaseModel):
    key: str
    value: Optional[str]
    description: Optional[str]


def simple_encrypt(value: str) -> str:
    """Simple obfuscation for sensitive values (use proper encryption in production)"""
    return base64.b64encode(value.encode()).decode()


def simple_decrypt(value: str) -> str:
    """Decrypt obfuscated values"""
    try:
        return base64.b64decode(value.encode()).decode()
    except:
        return value


@router.get("/gl-accounts")
async def get_gl_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get cached GL accounts from Newbook (for reference when configuring GL code mapping).
    """
    result = await db.execute(
        text("SELECT gl_account_id, gl_code, gl_name, is_active FROM newbook_gl_accounts ORDER BY gl_code")
    )
    rows = result.fetchall()

    return [
        {
            "gl_account_id": row.gl_account_id,
            "gl_code": row.gl_code,
            "gl_name": row.gl_name,
            "is_active": row.is_active
        }
        for row in rows
    ]


@router.get("/{key}")
async def get_config(
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a configuration value by key.
    Encrypted values are masked in the response.
    """
    result = await db.execute(
        text("SELECT config_value, is_encrypted, description FROM system_config WHERE config_key = :key"),
        {"key": key}
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Config key not found: {key}")

    # Mask encrypted values
    value = row.config_value
    if row.is_encrypted and value:
        value = "********"  # Don't expose encrypted values

    return {
        "key": key,
        "value": value,
        "description": row.description,
        "is_encrypted": row.is_encrypted
    }


@router.get("/")
async def list_config(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all configuration keys with masked values for encrypted fields.
    """
    result = await db.execute(
        text("SELECT config_key, config_value, is_encrypted, description, updated_at FROM system_config ORDER BY config_key")
    )
    rows = result.fetchall()

    return [
        {
            "key": row.config_key,
            "value": "********" if row.is_encrypted and row.config_value else row.config_value,
            "is_encrypted": row.is_encrypted,
            "description": row.description,
            "updated_at": row.updated_at,
            "is_set": row.config_value is not None and row.config_value != ""
        }
        for row in rows
    ]


@router.post("/")
async def set_config(
    config: ConfigValue,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Set a configuration value.
    Sensitive values (API keys, passwords) are encrypted before storage.
    """
    value = config.value
    if config.is_encrypted and value:
        value = simple_encrypt(value)

    result = await db.execute(
        text("""
            UPDATE system_config
            SET config_value = :value,
                is_encrypted = :is_encrypted,
                updated_at = NOW(),
                updated_by = :username
            WHERE config_key = :key
            RETURNING config_key
        """),
        {
            "key": config.key,
            "value": value,
            "is_encrypted": config.is_encrypted,
            "username": current_user.get("username")
        }
    )
    await db.commit()

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Config key not found: {config.key}")

    return {"status": "saved", "key": config.key}


@router.post("/test/{api}")
async def test_api_connection(
    api: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Test connection to an external API using stored credentials.
    """
    if api == "newbook":
        return await _test_newbook(db)
    elif api == "resos":
        return await _test_resos(db)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown API: {api}")


async def _get_config_value(db: AsyncSession, key: str) -> Optional[str]:
    """Get a config value, decrypting if necessary"""
    result = await db.execute(
        text("SELECT config_value, is_encrypted FROM system_config WHERE config_key = :key"),
        {"key": key}
    )
    row = result.fetchone()
    if not row or not row.config_value:
        return None

    if row.is_encrypted:
        return simple_decrypt(row.config_value)
    return row.config_value


async def _test_newbook(db: AsyncSession):
    """Test Newbook API connection with full credentials"""
    import httpx
    import logging

    logger = logging.getLogger(__name__)

    api_key = await _get_config_value(db, "newbook_api_key")
    username = await _get_config_value(db, "newbook_username")
    password = await _get_config_value(db, "newbook_password")
    region = await _get_config_value(db, "newbook_region")

    # Log what we have (masked)
    logger.info(f"Testing Newbook: api_key={'set' if api_key else 'empty'}, username={username}, region={region}")

    # Check we have all required credentials
    missing = []
    if not api_key:
        missing.append("API Key")
    if not username:
        missing.append("Username")
    if not password:
        missing.append("Password")
    if not region:
        missing.append("Region")

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required credentials: {', '.join(missing)}"
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Test with api_keys endpoint - uses Basic Auth + JSON body
            response = await client.post(
                "https://api.newbook.cloud/rest/api_keys",
                json={
                    "region": region,
                    "api_key": api_key,
                    "list_type": "inhouse"
                },
                auth=(username, password),
                headers={"Content-Type": "application/json"}
            )

            logger.info(f"Newbook test response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return {
                        "status": "connected",
                        "message": "Newbook connection successful!"
                    }
                else:
                    error_msg = data.get("message", "Authentication failed")
                    raise HTTPException(status_code=400, detail=f"Newbook API error: {error_msg}")
            else:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("message", str(error_data))
                except:
                    error_msg = response.text[:200] if response.text else "No details"

                raise HTTPException(
                    status_code=400,
                    detail=f"Newbook authentication failed ({response.status_code}): {error_msg}"
                )

    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail="Connection timed out")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


async def _test_resos(db: AsyncSession):
    """Test Resos API connection"""
    import httpx

    api_key = await _get_config_value(db, "resos_api_key")

    if not api_key:
        raise HTTPException(status_code=400, detail="Resos API key not configured")

    try:
        auth_header = f"Basic {base64.b64encode(f'{api_key}:'.encode()).decode()}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://api.resos.com/v1/openingHours",
                headers={"Authorization": auth_header}
            )

            if response.status_code == 200:
                return {"status": "connected", "message": "Resos connection successful"}
            elif response.status_code == 401:
                raise HTTPException(status_code=400, detail="Invalid API key")
            else:
                raise HTTPException(status_code=400, detail=f"Resos returned status {response.status_code}")

    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail="Connection timed out")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
