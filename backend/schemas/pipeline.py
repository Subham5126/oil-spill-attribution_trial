"""Pipeline Schemas matching frontend EndToEndResult."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from backend.schemas.common import PipelineStatusEnum, ProvenanceMetadata
from backend.schemas.spill import GisMeasurementSchema, SpillMetadataSchema
from backend.schemas.drift import OceanDriftResponse
from backend.schemas.vessel import CandidateVessel
from backend.schemas.attribution import AISSearchSummary


class GisExportConfig(BaseModel):
    map_view_config: Dict[str, Any]
    feature_collection_summary: Optional[Dict[str, Any]] = None


class PipelineExecutionStatus(BaseModel):
    status: str = "PASS"
    stage_statuses: Dict[str, str] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)
    execution_timestamp: str


class PipelineRunRequest(BaseModel):
    """Request to initiate pipeline execution."""

    investigation_id: Optional[str] = None
    spill_id: Optional[str] = None
    observation_lat: Optional[float] = None
    observation_lon: Optional[float] = None
    observation_time: Optional[str] = None
    particles_count: int = Field(40, ge=5, le=500)
    hindcast_duration_hours: float = Field(4.0, gt=0.0, le=72.0)
    forward_steps: int = Field(2, ge=0, le=24)
    sync: bool = Field(False, description="If True, executes synchronously instead of queueing to Celery")


class PipelineRunResponse(BaseModel):
    investigation_id: str
    task_id: Optional[str] = None
    status: PipelineStatusEnum
    message: str


class PipelineStatusResponse(BaseModel):
    investigation_id: str
    status: PipelineStatusEnum
    stage: Optional[str] = None
    progress_percentage: int = 0
    notes: List[str] = Field(default_factory=list)
    stage_statuses: Dict[str, str] = Field(default_factory=dict)
    error: Optional[str] = None


class EndToEndResultResponse(BaseModel):
    """The canonical end-to-end result consumed by frontend."""

    spill_metadata: SpillMetadataSchema
    gis_measurement: GisMeasurementSchema
    ocean_drift: OceanDriftResponse
    ais_search: AISSearchSummary
    candidate_vessels: List[CandidateVessel] = Field(default_factory=list)
    attribution_ranking: List[CandidateVessel] = Field(default_factory=list)
    primary_suspect: Optional[CandidateVessel] = None
    gis_export: GisExportConfig
    pipeline_execution: PipelineExecutionStatus
    provenance: Optional[ProvenanceMetadata] = None
