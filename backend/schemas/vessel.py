"""Vessel & Candidate Schemas matching Member 5 and frontend contracts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel


class CandidateVesselScores(BaseModel):
    overall: float
    spatial: float
    temporal: float
    trajectory: float
    behaviour: float


class CandidateVesselMetrics(BaseModel):
    min_distance_km: float
    time_difference_minutes: float
    transit_speed_knots: float


class CandidateVessel(BaseModel):
    rank: int
    mmsi: int
    vessel_name: str
    imo: Optional[str] = "N/A"
    vessel_type: Union[int, str] = 0
    scores: CandidateVesselScores
    metrics: CandidateVesselMetrics
    suspicious_flags: List[str] = []
    explanation: Optional[List[str]] = None
    confidence_category: Optional[str] = None


class VesselResponse(BaseModel):
    mmsi: int
    imo: Optional[str] = None
    vessel_name: str
    flag: Optional[str] = None
    vessel_type: Optional[str] = None
    call_sign: Optional[str] = None
    length_m: Optional[int] = None
    width_m: Optional[int] = None
    draft_m: Optional[int] = None
