"""
Forecasting Application - FastAPI Backend
"""
import os
from datetime import timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db, async_engine
from auth import (
    Token, UserLogin, UserResponse,
    authenticate_user, create_access_token, get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from api import forecast, sync, export, budget, accuracy, evolution, crossref, explain, config
from scheduler import start_scheduler, shutdown_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    start_scheduler()
    yield
    # Shutdown
    shutdown_scheduler()


app = FastAPI(
    title="Forecasting API",
    description="Hotel & Restaurant Forecasting Service",
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


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "forecasting-api"}


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
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user info"""
    return current_user


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
