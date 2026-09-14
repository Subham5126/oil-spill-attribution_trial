"""Vessel & Candidate Schemas matching Member 5 and frontend contracts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, model_validator


class CandidateVesselScores(BaseModel):
    overall: float = 0.0
    spatial: float = 0.0
    temporal: float = 0.0
    trajectory: float = 0.0
    behaviour: float = 0.0


class CandidateVesselMetrics(BaseModel):
    min_distance_km: float = 0.0
    time_difference_minutes: float = 0.0
    transit_speed_knots: float = 0.0


class ConfidenceFactors(BaseModel):
    spatial_proximity: Optional[float] = None
    temporal_overlap: Optional[float] = None
    drift_consistency: Optional[float] = None
    track_consistency: Optional[float] = None
    vessel_type_relevance: Optional[float] = None
    ais_quality: Optional[float] = None
    supporting: List[str] = []
    limitations: List[str] = []


class CandidateVessel(BaseModel):
    rank: int = 1
    mmsi: int
    vessel_name: str
    imo: Optional[str] = "N/A"
    vessel_type: Union[int, str] = "OTHER"
    scores: Optional[CandidateVesselScores] = None
    metrics: Optional[CandidateVesselMetrics] = None
    suspicious_flags: List[str] = []
    explanation: Optional[List[str]] = None
    confidence_category: Optional[str] = None
    confidence_score: float = 0.0
    confidence_level: str = "VERY LOW"
    confidence_factors: Optional[ConfidenceFactors] = None
    min_distance_km: Optional[float] = None
    distance_to_spill_km: Optional[float] = None
    distance_to_track_km: Optional[float] = None
    callsign: Optional[str] = None
    flag: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timestamp: Optional[str] = None
    presence_hours: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def ensure_metrics_and_scores(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("metrics"):
                dist = data.get("min_distance_km") or data.get("distance_to_track_km") or data.get("distance_to_spill_km") or 0.0
                data["metrics"] = {
                    "min_distance_km": float(dist),
                    "time_difference_minutes": 0.0,
                    "transit_speed_knots": 0.0,
                }
            if not data.get("scores"):
                data["scores"] = {
                    "overall": 0.5,
                    "spatial": 0.5,
                    "temporal": 0.5,
                    "trajectory": 0.5,
                    "behaviour": 0.5,
                }
            
            # Automatically populate confidence_score and confidence_level if missing
            if not data.get("confidence_score") and not data.get("confidence_factors"):
                from backend.services.confidence_scoring import compute_vessel_confidence
                scores_dict = data.get("scores") or {}
                metrics_dict = data.get("metrics") or {}
                conf = compute_vessel_confidence(
                    spatial_score=scores_dict.get("spatial"),
                    temporal_score=scores_dict.get("temporal"),
                    trajectory_score=scores_dict.get("trajectory"),
                    behaviour_score=scores_dict.get("behaviour"),
                    overall_score=scores_dict.get("overall"),
                    min_distance_km=metrics_dict.get("min_distance_km") or data.get("min_distance_km"),
                    time_difference_minutes=metrics_dict.get("time_difference_minutes"),
                    vessel_type=data.get("vessel_type"),
                    transit_speed_knots=metrics_dict.get("transit_speed_knots"),
                )
                data["confidence_score"] = conf["confidence_score"]
                data["confidence_level"] = conf["confidence_level"]
                data["confidence_factors"] = conf["confidence_factors"]
        return data


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
