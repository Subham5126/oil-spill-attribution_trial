"""Investigations API Router."""

from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.schemas.investigation import (
    InvestigationCreate,
    InvestigationResponse,
    InvestigationStatusResponse,
)
from backend.services.investigation_service import InvestigationService
from backend.services.pipeline_service import PipelineService

router = APIRouter(prefix="/investigations", tags=["Investigations"])


@router.get("", response_model=List[InvestigationResponse])
def list_investigations(db: Session = Depends(get_db)):
    """List all oil spill attribution investigations."""
    service = InvestigationService(db)
    return service.list_investigations()


@router.post("", response_model=InvestigationResponse, status_code=status.HTTP_201_CREATED)
def create_investigation(payload: InvestigationCreate, db: Session = Depends(get_db)):
    """Create a new investigation incident record."""
    service = InvestigationService(db)
    return service.create_investigation(payload)


@router.get("/{investigation_id}", response_model=InvestigationResponse)
def get_investigation(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve details of a specific investigation."""
    service = InvestigationService(db)
    return service.get_investigation(investigation_id)


@router.get("/{investigation_id}/status", response_model=InvestigationStatusResponse)
def get_investigation_status(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve processing lifecycle status of an investigation."""
    service = InvestigationService(db)
    return service.get_investigation_status(investigation_id)


@router.get("/{investigation_id}/result")
def get_investigation_result(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve complete end-to-end attribution result for an investigation."""
    pipeline_service = PipelineService(db)
    return pipeline_service.get_result_by_investigation(investigation_id)
