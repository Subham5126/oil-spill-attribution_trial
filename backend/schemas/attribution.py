"""Attribution & AIS Search Schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from backend.schemas.common import GeoPoint
from backend.schemas.vessel import CandidateVessel


class AISSearchWindow(BaseModel):
    start_time: str
    end_time: str


class AISSearchSummary(BaseModel):
    data_mode: str = "DEMO / SYNTHETIC AIS"
    search_center: GeoPoint
    effective_radius_km: float
    search_window: AISSearchWindow
    raw_records_matched: int
    vessels_tracked: int
    vessels_surviving_filter: int


class AttributionResponse(BaseModel):
    investigation_id: str
    primary_suspect: Optional[CandidateVessel] = None
    attribution_ranking: List[CandidateVessel] = []
    ais_search: Optional[AISSearchSummary] = None
    provenance: Optional[Dict[str, Any]] = None
