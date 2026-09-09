"""OilTrace Schemas Package."""

from backend.schemas.common import (
    BoundingBox,
    ErrorResponse,
    GeoPoint,
    PipelineStatusEnum,
    ProvenanceMetadata,
)
from backend.schemas.investigation import (
    InvestigationCreate,
    InvestigationResponse,
    InvestigationStatusResponse,
)
from backend.schemas.spill import (
    GisMeasurementSchema,
    SpillGeometryResponse,
    SpillMetadataSchema,
)
from backend.schemas.drift import (
    DriftSimulateRequest,
    OceanDriftResponse,
    ProbableOriginSchema,
    SpatialUncertaintySchema,
)
from backend.schemas.vessel import (
    CandidateVessel,
    CandidateVesselMetrics,
    CandidateVesselScores,
    VesselResponse,
)
from backend.schemas.attribution import AISSearchSummary, AttributionResponse
from backend.schemas.pipeline import (
    EndToEndResultResponse,
    PipelineExecutionStatus,
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineStatusResponse,
)
from backend.schemas.report import ReportCreate, ReportResponse
from backend.schemas.layer import GeoJSONFeature, GeoJSONFeatureCollection

__all__ = [
    "BoundingBox",
    "ErrorResponse",
    "GeoPoint",
    "PipelineStatusEnum",
    "ProvenanceMetadata",
    "InvestigationCreate",
    "InvestigationResponse",
    "InvestigationStatusResponse",
    "GisMeasurementSchema",
    "SpillGeometryResponse",
    "SpillMetadataSchema",
    "DriftSimulateRequest",
    "OceanDriftResponse",
    "ProbableOriginSchema",
    "SpatialUncertaintySchema",
    "CandidateVessel",
    "CandidateVesselMetrics",
    "CandidateVesselScores",
    "VesselResponse",
    "AISSearchSummary",
    "AttributionResponse",
    "EndToEndResultResponse",
    "PipelineExecutionStatus",
    "PipelineRunRequest",
    "PipelineRunResponse",
    "PipelineStatusResponse",
    "ReportCreate",
    "ReportResponse",
    "GeoJSONFeature",
    "GeoJSONFeatureCollection",
]
