"""Ocean & Drift Schemas matching Member 4 and frontend contracts."""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ProbableOriginSchema(BaseModel):
    latitude: float
    longitude: float
    timestamp: str
    relative_heuristic_score: float
    drift_direction_deg: Optional[float] = 270.0


class BoundingEnvelope(BaseModel):
    min_lat: Optional[float] = None
    max_lat: Optional[float] = None
    min_lon: Optional[float] = None
    max_lon: Optional[float] = None


class SpatialUncertaintySchema(BaseModel):
    radius_km: float
    empirical_coverage_level: float = 0.95
    dispersion_description: str = "95% empirical spatial dispersion estimate"
    spread_km: Optional[float] = None
    bounding_envelope: Optional[BoundingEnvelope] = None


class ForecastConfig(BaseModel):
    steps: int = 2
    timestep_seconds: int = 3600
    duration_hours: float = 2.0


class HindcastConfig(BaseModel):
    duration_hours: float = 4.0
    timestep_seconds: int = 3600
    observation_time: str


class OceanDriftResponse(BaseModel):
    model_type: str = "Lagrangian Forward/Backward Euler"
    particles_simulated: int = 40
    forecast: ForecastConfig
    hindcast: HindcastConfig
    probable_origin: ProbableOriginSchema
    uncertainty: SpatialUncertaintySchema


class DriftSimulateRequest(BaseModel):
    """Payload for POST /api/drift/simulate matching frontend runCustomDriftSimulation."""

    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    durationHours: float = Field(4.0, gt=0.0, le=72.0)
    timestepSeconds: int = Field(3600, gt=60, le=86400)
    mode: str = Field("hindcast", description="'hindcast' or 'forecast'")
    particleCount: Optional[int] = Field(20, ge=1, le=500)
