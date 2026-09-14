"""Celery Application Module.

Configures Celery distributed background job queue using Redis.
Provides graceful initialization when Redis is offline.
"""

from __future__ import annotations

import os

from backend.core.config import settings
from backend.core.logging import logger

try:
    from celery import Celery
    celery_app = Celery(
        "oiltrace_workers",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=["backend.workers.tasks"],
    )
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=3600,  # 1 hour max
        task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    )
except ImportError:
    celery_app = None


def check_redis_health() -> str:
    """Check Redis liveness for health endpoint."""
    try:
        import redis
        client = redis.from_url(settings.REDIS_URL, socket_timeout=1.0)
        client.ping()
        return "ok"
    except Exception:
        return "unavailable"
