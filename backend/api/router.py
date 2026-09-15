"""Master API Router for OilTrace Backend."""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.attribution import router as attribution_router
from backend.api.drift import router as drift_router
from backend.api.health import router as health_router
from backend.api.images import router as images_router
from backend.api.investigations import router as investigations_router
from backend.api.layers import router as layers_router
from backend.api.notifications import router as notifications_router
from backend.api.pipeline import router as pipeline_router
from backend.api.profile import router as profile_router
from backend.api.reports import router as reports_router
from backend.api.settings import router as settings_router
from backend.api.spills import router as spills_router
from backend.api.vessels import router as vessels_router

api_router = APIRouter(prefix="/api")

api_router.include_router(health_router)
api_router.include_router(images_router)
api_router.include_router(investigations_router)
api_router.include_router(notifications_router)
api_router.include_router(pipeline_router)
api_router.include_router(spills_router)
api_router.include_router(drift_router)
api_router.include_router(vessels_router)
api_router.include_router(attribution_router)
api_router.include_router(layers_router)
api_router.include_router(reports_router)
api_router.include_router(profile_router)
api_router.include_router(settings_router)
