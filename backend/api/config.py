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
    """Test Newbook API connection"""
    import httpx

    api_key = await _get_config_value(db, "newbook_api_key")
    username = await _get_config_value(db, "newbook_username")
    password = await _get_config_value(db, "newbook_password")
    region = await _get_config_value(db, "newbook_region")

    if not all([api_key, username, password, region]):
        raise HTTPException(status_code=400, detail="Newbook credentials not fully configured")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.newbook.cloud/rest/",
                json={
                    "api_key": api_key,
                    "username": username,
                    "password": password,
                    "region": region,
                    "action": "site_list"
                },
                auth=(username, password)
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return {"status": "connected", "message": "Newbook connection successful"}
                else:
                    raise HTTPException(status_code=400, detail=f"Newbook error: {data.get('message', 'Unknown error')}")
            else:
                raise HTTPException(status_code=400, detail=f"Newbook returned status {response.status_code}")

    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail="Connection timed out")
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
