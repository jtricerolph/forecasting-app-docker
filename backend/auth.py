"""
Authentication utilities - JWT based simple auth
"""
import os
import bcrypt
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db

# Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Security scheme
security = HTTPBearer()


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: Optional[str]
    is_active: bool


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash using bcrypt directly"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password: str) -> str:
    """Generate password hash using bcrypt directly"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Get current user from JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Query user from database
    result = await db.execute(
        select_user_by_username(username)
    )
    user = result.fetchone()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "is_active": user.is_active
    }


def select_user_by_username(username: str):
    """SQL query to select user by username"""
    from sqlalchemy import text
    return text("SELECT id, username, password_hash, display_name, is_active FROM users WHERE username = :username").bindparams(username=username)


async def authenticate_user(db: AsyncSession, username: str, password: str) -> Optional[dict]:
    """Authenticate user with username and password"""
    result = await db.execute(
        select_user_by_username(username)
    )
    user = result.fetchone()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "is_active": user.is_active
    }


async def get_all_users(db: AsyncSession) -> list:
    """Get all users from database"""
    from sqlalchemy import text
    result = await db.execute(
        text("SELECT id, username, display_name, is_active, created_at FROM users ORDER BY id")
    )
    users = result.fetchall()
    return [
        {
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None
        }
        for u in users
    ]


async def create_user(db: AsyncSession, username: str, password: str, display_name: Optional[str] = None) -> dict:
    """Create a new user"""
    from sqlalchemy import text

    # Check if username already exists
    existing = await db.execute(
        text("SELECT id FROM users WHERE username = :username").bindparams(username=username)
    )
    if existing.fetchone():
        raise HTTPException(status_code=400, detail="Username already exists")

    # Hash password and insert user
    password_hash = get_password_hash(password)
    result = await db.execute(
        text("""
            INSERT INTO users (username, password_hash, display_name, is_active, created_at)
            VALUES (:username, :password_hash, :display_name, true, NOW())
            RETURNING id, username, display_name, is_active, created_at
        """).bindparams(
            username=username,
            password_hash=password_hash,
            display_name=display_name or username
        )
    )
    await db.commit()
    user = result.fetchone()
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None
    }


async def delete_user(db: AsyncSession, user_id: int, current_user_id: int) -> bool:
    """Delete a user by ID"""
    from sqlalchemy import text

    # Prevent self-deletion
    if user_id == current_user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    # Check if user exists
    existing = await db.execute(
        text("SELECT id FROM users WHERE id = :user_id").bindparams(user_id=user_id)
    )
    if not existing.fetchone():
        raise HTTPException(status_code=404, detail="User not found")

    # Delete user
    await db.execute(
        text("DELETE FROM users WHERE id = :user_id").bindparams(user_id=user_id)
    )
    await db.commit()
    return True
