"""Vessels API Router."""

from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.schemas.vessel import VesselResponse
from backend.services.vessel_service import VesselService

router = APIRouter(prefix="/vessels", tags=["Vessels"])


@router.get("", response_model=List[VesselResponse])
def list_vessels(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List registered maritime vessels in domain."""
    service = VesselService(db)
    return service.list_vessels(limit=limit, offset=offset)


@router.get("/{mmsi}", response_model=VesselResponse)
def get_vessel(mmsi: int, db: Session = Depends(get_db)):
    """Retrieve details for a specific vessel by Maritime Mobile Service Identity (MMSI)."""
    service = VesselService(db)
    return service.get_vessel(mmsi)
