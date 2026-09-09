"""Health Check API Router."""

from __future__ import annotations

from fastapi import APIRouter
from backend.core.config import settings
from backend.core.database import check_db_health
from backend.workers.celery_app import check_redis_health

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """System health and operational status endpoint. Checks backend, DB, and Redis liveness."""
    db_status = check_db_health()
    redis_status = check_redis_health()
    overall = "healthy" if db_status == "ok" or settings.DEMO_MODE else "degraded"

    return {
        "status": overall,
        "backend": "ok",
        "database": db_status,
        "redis": redis_status,
        "demo_mode": settings.DEMO_MODE,
        "app_env": settings.APP_ENV,
        "service": settings.APP_NAME,
        "version": "1.0.0",
    }
