"""Investigation Schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from backend.schemas.common import GeoPoint


class InvestigationCreate(BaseModel):
    """Payload for creating a new investigation."""

    name: str = Field(..., description="Investigation name/title")
    region: str = Field(..., description="Geographic region, e.g. Arabian Sea (Sector IND-West)")
    observation_timestamp: Optional[datetime] = Field(None, description="Observation time UTC")
    priority: str = Field("Medium", description="Priority level: High, Medium, Low")
    coordinates: Optional[GeoPoint] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InvestigationResponse(BaseModel):
    """Investigation model matching frontend Investigation interface."""

    id: str
    title: str
    status: str
    priority: str
    region: str
    coordinates: GeoPoint
    spill_area_km2: float
    detection_time: str
    suspect_vessel: Optional[str] = None
    match_confidence: Optional[float] = None
    evidence_nodes_count: int = 0
    sar_epoch: str = "N/A"
    created_at: Optional[str] = None


class InvestigationStatusResponse(BaseModel):
    """Current processing state of an investigation."""

    investigation_id: str
    status: str
    stage: Optional[str] = None
    progress_percentage: Optional[int] = None
    updated_at: Optional[str] = None
    message: Optional[str] = None
