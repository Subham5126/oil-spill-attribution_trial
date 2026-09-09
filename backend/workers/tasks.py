"""Celery Asynchronous Tasks."""

from __future__ import annotations

from typing import Any, Dict, Optional
from backend.core.database import get_db
from backend.core.logging import logger
from backend.services.pipeline_service import PipelineService
from backend.workers.celery_app import celery_app


@celery_app.task(bind=True, name="oiltrace.run_pipeline_task")
def run_pipeline_task(
    self,
    investigation_id: Optional[str] = None,
    particles_count: int = 40,
    hindcast_duration_hours: float = 4.0,
    forward_steps: int = 2,
) -> Dict[str, Any]:
    """Execute attribution pipeline asynchronously in background worker."""
    task_id = self.request.id
    logger.info(f"Celery task {task_id} started for investigation: {investigation_id}")

    db_gen = get_db()
    db = next(db_gen)
    try:
        service = PipelineService(db=db)
        result = service.run_pipeline(
            investigation_id=investigation_id,
            particles_count=particles_count,
            hindcast_duration_hours=hindcast_duration_hours,
            forward_steps=forward_steps,
        )
        return {
            "status": "COMPLETED",
            "task_id": task_id,
            "investigation_id": investigation_id,
            "spill_id": result.get("spill_metadata", {}).get("spill_id"),
        }
    except Exception as exc:
        logger.error(f"Celery task {task_id} failed: {exc}", exc_info=True)
        raise exc
    finally:
        try:
            next(db_gen, None)
        except Exception:
            pass
