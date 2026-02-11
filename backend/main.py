"""
Forecasting Application - FastAPI Backend
"""
import os
import logging
import sys
from datetime import timedelta
from contextlib import asynccontextmanager

# Configure logging to output to stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db, async_engine
from auth import (
    Token, UserLogin, UserResponse, UserCreate,
    authenticate_user, create_access_token, get_current_user, get_admin_user,
    get_all_users, create_user, delete_user,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from typing import List
from api import forecast, sync, export, budget, accuracy, evolution, crossref, explain, config, historical, resos, backtest, sync_bookings, resos_sync, reports, special_dates, backup, public, bookability, competitor_rates, reconciliation
from scheduler import start_scheduler, shutdown_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup: clean up any scrape batches orphaned by previous shutdown
    try:
        from services.booking_scraper import cleanup_stale_batches
        from database import SyncSessionLocal
        db = SyncSessionLocal()
        try:
            cleanup_stale_batches(db, max_age_minutes=10)
        finally:
            db.close()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Stale batch cleanup on startup failed: {e}")

    start_scheduler()
    yield
    # Shutdown
    shutdown_scheduler()


app = FastAPI(
    title="Finance API",
    description="Hotel & Restaurant Finance Service",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(forecast.router, prefix="/forecast", tags=["Forecasts"])
app.include_router(sync.router, prefix="/sync", tags=["Data Sync"])
app.include_router(export.router, prefix="/export", tags=["Exports"])
app.include_router(budget.router, prefix="/budget", tags=["Budgets"])
app.include_router(accuracy.router, prefix="/accuracy", tags=["Accuracy"])
app.include_router(evolution.router, prefix="/evolution", tags=["Forecast Evolution"])
app.include_router(crossref.router, prefix="/crossref", tags=["Cross-Reference"])
app.include_router(explain.router, prefix="/explain", tags=["Explainability"])
app.include_router(config.router, prefix="/config", tags=["Configuration"])
app.include_router(historical.router, prefix="/historical", tags=["Historical Data"])
app.include_router(resos.router, prefix="/resos", tags=["Resos Mapping"])
app.include_router(backtest.router, prefix="/backtest", tags=["Backtesting"])
app.include_router(sync_bookings.router, prefix="/sync", tags=["Data Sync"])
app.include_router(resos_sync.router, prefix="/sync", tags=["Data Sync"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])
app.include_router(special_dates.router, prefix="/settings", tags=["Settings"])
app.include_router(backup.router, prefix="/backup", tags=["Backup & Restore"])
app.include_router(public.router, prefix="/public", tags=["Public API"])
app.include_router(bookability.router, prefix="/bookability", tags=["Bookability"])
app.include_router(competitor_rates.router, prefix="/competitor-rates", tags=["Competitor Rates"])
app.include_router(reconciliation.router, prefix="/reconciliation", tags=["Reconciliation"])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "finance-api"}


@app.get("/health/db")
async def db_health_check(db: AsyncSession = Depends(get_db)):
    """Database health check"""
    try:
        result = await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unhealthy: {str(e)}")


@app.post("/auth/login", response_model=Token)
async def login(user_login: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return JWT token"""
    user = await authenticate_user(db, user_login.username, user_login.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user.get("role", "admin")}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user info"""
    return current_user


@app.get("/auth/users", response_model=List[dict])
async def list_users(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all users"""
    return await get_all_users(db)


@app.post("/auth/users", response_model=dict)
async def add_user(
    user_data: UserCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new user"""
    return await create_user(db, user_data.username, user_data.password, user_data.display_name, user_data.role or 'admin')


@app.delete("/auth/users/{user_id}")
async def remove_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a user"""
    await delete_user(db, user_id, current_user["id"])
    return {"message": "User deleted successfully"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
