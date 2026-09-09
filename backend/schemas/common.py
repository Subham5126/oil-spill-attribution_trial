"""OilTrace Common Pydantic Schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PipelineStatusEnum(str, Enum):
    """Canonical lifecycle states for attribution pipeline execution."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SATELLITE_PROCESSING = "SATELLITE_PROCESSING"
    AI_SEGMENTATION = "AI_SEGMENTATION"
    GIS_PROCESSING = "GIS_PROCESSING"
    OCEAN_PROCESSING = "OCEAN_PROCESSING"
    DRIFT_HINDCAST = "DRIFT_HINDCAST"
    ORIGIN_ANALYSIS = "ORIGIN_ANALYSIS"
    AIS_PROCESSING = "AIS_PROCESSING"
    ATTRIBUTION = "ATTRIBUTION"
    PERSISTING_RESULTS = "PERSISTING_RESULTS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class GeoPoint(BaseModel):
    """Geographic point coordinate."""

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)


class BoundingBox(BaseModel):
    """Axis-aligned bounding box."""

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    width_meters: Optional[float] = None
    height_meters: Optional[float] = None


class ProvenanceMetadata(BaseModel):
    """Provenance tracking distinguishing DEMO vs REAL data source."""

    data_source_mode: str = Field("DEMO", description="DEMO or REAL")
    sensor: Optional[str] = None
    satellite_provider: Optional[str] = None
    ocean_provider: Optional[str] = None
    ais_provider: Optional[str] = None
    pipeline_version: str = "1.0.0"
    executed_at: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standardized API error response payload."""

    status: str = "FAILED"
    error_code: str
    message: str
    stage: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
