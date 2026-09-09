"""Spills API Router."""

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.schemas.spill import SpillGeometryResponse
from backend.services.spill_service import SpillService

router = APIRouter(prefix="/spills", tags=["Spills"])


@router.get("/{investigation_id}")
def get_spill(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve spill metadata and geodesic measurements for an investigation."""
    service = SpillService(db)
    return service.get_spill(investigation_id)


@router.get("/{investigation_id}/geometry", response_model=SpillGeometryResponse)
def get_spill_geometry(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve GeoJSON polygon and physical shape metrics for the detected slick."""
    service = SpillService(db)
    return service.get_spill_geometry(investigation_id)
