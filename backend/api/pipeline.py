"""Pipeline Orchestration API Router."""

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.database import get_db
from backend.core.logging import logger
from backend.schemas.common import PipelineStatusEnum
from backend.schemas.pipeline import (
    EndToEndResultResponse,
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineStatusResponse,
)
from backend.services.pipeline_service import PipelineService
from backend.workers.celery_app import check_redis_health
from backend.workers.tasks import run_pipeline_task

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


@router.get("/latest", response_model=EndToEndResultResponse)
def get_latest_pipeline_result(db: Session = Depends(get_db)):
    """Retrieve the latest complete end-to-end attribution result for dashboard display."""
    service = PipelineService(db)
    return service.get_latest_result()


@router.get("/{investigation_id}", response_model=EndToEndResultResponse)
def get_pipeline_result(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve full pipeline result for a given investigation."""
    service = PipelineService(db)
    return service.get_result_by_investigation(investigation_id)


@router.get("/{investigation_id}/status", response_model=PipelineStatusResponse)
def get_pipeline_status(investigation_id: str, db: Session = Depends(get_db)):
    """Check current execution lifecycle status for a running or completed pipeline."""
    service = PipelineService(db)
    return service.get_status(investigation_id)


@router.post("/run", response_model=PipelineRunResponse, status_code=status.HTTP_202_ACCEPTED)
def run_pipeline(
    payload: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Trigger the unified attribution pipeline for an investigation.

    Uses Celery background queue if Redis is running, with fallback to FastAPI background execution.
    """
    inv_id = payload.investigation_id or f"SAR-IND-{int(time_stamp())}"
    redis_ok = check_redis_health() == "ok"

    if redis_ok and not payload.sync and not settings.CELERY_TASK_ALWAYS_EAGER:
        try:
            task = run_pipeline_task.delay(
                investigation_id=inv_id,
                particles_count=payload.particles_count,
                hindcast_duration_hours=payload.hindcast_duration_hours,
                forward_steps=payload.forward_steps,
            )
            return PipelineRunResponse(
                investigation_id=inv_id,
                task_id=task.id,
                status=PipelineStatusEnum.QUEUED,
                message="Pipeline job enqueued to Celery Redis worker.",
            )
        except Exception as exc:
            logger.warning(f"Could not enqueue to Celery ({exc}). Falling back to local background task.")

    # Synchronous or local background execution
    service = PipelineService(db)
    if payload.sync:
        service.run_pipeline(
            investigation_id=inv_id,
            particles_count=payload.particles_count,
            hindcast_duration_hours=payload.hindcast_duration_hours,
            forward_steps=payload.forward_steps,
        )
        return PipelineRunResponse(
            investigation_id=inv_id,
            task_id="sync-execution",
            status=PipelineStatusEnum.COMPLETED,
            message="Pipeline executed synchronously.",
        )
    else:
        background_tasks.add_task(
            service.run_pipeline,
            investigation_id=inv_id,
            particles_count=payload.particles_count,
            hindcast_duration_hours=payload.hindcast_duration_hours,
            forward_steps=payload.forward_steps,
        )
        return PipelineRunResponse(
            investigation_id=inv_id,
            task_id="local-async",
            status=PipelineStatusEnum.RUNNING,
            message="Pipeline running in background service.",
        )


def time_stamp() -> float:
    import time
    return time.time()
