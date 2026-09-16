"""Attribution & Suspect Ranking API Router."""

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.schemas.attribution import AttributionResponse
from backend.services.attribution_service import AttributionService

router = APIRouter(prefix="/attribution", tags=["Attribution"])


@router.get("/{investigation_id}", response_model=AttributionResponse)
def get_attribution(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve candidate vessels, evidence breakdown, and suspect ranking for an incident."""
    service = AttributionService(db)
    return service.get_attribution(investigation_id)
