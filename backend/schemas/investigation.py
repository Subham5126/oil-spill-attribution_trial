"""Investigation Schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from backend.schemas.common import GeoPoint


class InvestigationCreate(BaseModel):
    """Payload for creating a new investigation."""

    name: Optional[str] = Field(None, description="Investigation name/title")
    title: Optional[str] = Field(None, description="Investigation title")
    region: Optional[str] = Field("Offshore Waters", description="Geographic region")
    image_id: Optional[str] = Field(None, description="Sentinel-1 Image ID (e.g. 00052, 00053, 00643, or upload ID)")
    source_image_path: Optional[str] = Field(None, description="Filesystem path to uploaded GeoTIFF")
    observation_timestamp: Optional[datetime] = Field(None, description="Observation time UTC")
    sar_acquisition_time: Optional[datetime] = Field(None, description="Authoritative Sentinel-1 SAR acquisition timestamp UTC")
    sar_acquisition_time_source: Optional[str] = Field(None, description="Provenance source of SAR acquisition timestamp")
    sar_acquisition_time_verified: Optional[bool] = Field(None, description="Whether SAR acquisition timestamp is verified against metadata")
    priority: str = Field("Medium", description="Priority level: High, Medium, Low")
    coordinates: Optional[GeoPoint] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UploadInitRequest(BaseModel):
    """Payload to initiate a chunked GeoTIFF upload."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    filename: str = Field(
        ...,
        validation_alias=AliasChoices("filename", "fileName", "name"),
        description="Original filename with .tif or .tiff extension",
    )
    file_size: int = Field(
        ...,
        gt=0,
        validation_alias=AliasChoices("file_size", "fileSize", "size"),
        description="Total file size in bytes",
    )
    total_chunks: Optional[int] = Field(
        None,
        validation_alias=AliasChoices("total_chunks", "totalChunks", "chunks"),
        description="Total number of chunks",
    )
    chunk_size: Optional[int] = Field(
        None,
        validation_alias=AliasChoices("chunk_size", "chunkSize"),
        description="Optional chunk size in bytes",
    )
    content_type: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("content_type", "contentType", "mime_type", "mimeType"),
        description="Optional MIME content type",
    )
    investigation_id: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("investigation_id", "investigationId"),
        description="Optional draft or existing investigation ID",
    )


class UploadInitResponse(BaseModel):
    """Response returned upon successful upload initialization."""

    upload_id: str
    filename: str
    safe_filename: str
    chunk_size: int
    total_chunks: int
    max_file_size: int
    investigation_id: Optional[str] = None


class UploadChunkResponse(BaseModel):
    """Response returned after writing an individual chunk."""

    upload_id: str
    chunk_index: int
    chunks_received: int
    total_chunks: int
    received_bytes: int
    progress_percentage: int


class UploadCompleteRequest(BaseModel):
    """Payload to finalize a chunked upload."""

    upload_id: str


class TemporalAnchorCandidate(BaseModel):
    """Candidate Sentinel-1 acquisition timestamp resolved from an authoritative source."""

    source: str
    timestamp: str
    confidence: str
    description: str


class TemporalAnchorConflict(BaseModel):
    """Metadata conflict between two automated timestamp sources."""

    source_a: str
    timestamp_a: str
    source_b: str
    timestamp_b: str
    difference_seconds: float


class TemporalAnchorResponse(BaseModel):
    """Authoritative Sentinel-1 temporal anchor and provenance status."""

    status: str  # "resolved", "unresolved", "conflict"
    sar_acquisition_time: Optional[str] = None
    source: Optional[str] = None
    verified: bool = False
    provenance_badge: str
    description: str
    candidates: List[TemporalAnchorCandidate] = Field(default_factory=list)
    conflicts: List[TemporalAnchorConflict] = Field(default_factory=list)
    requires_user_action: bool = False


class TemporalAnchorConfirmRequest(BaseModel):
    """Operator confirmation or manual UTC entry payload."""

    sar_acquisition_time: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    timezone: str = "UTC"
    source: str = "user_provided"


class UploadedSceneResponse(BaseModel):
    """Metadata response for a validated, uploaded Sentinel-1 GeoTIFF."""

    status: str
    upload_id: str
    image_id: str
    filename: str
    safe_filename: str
    file_path: str
    file_size: int
    file_size_formatted: str
    width: int
    height: int
    num_bands: int
    crs: str
    pixel_res_m: float
    bounds: Dict[str, float]
    centroid_lat: Optional[float] = None
    centroid_lon: Optional[float] = None
    region: str
    acquisition_time: Optional[str] = None
    temporal_anchor: Optional[TemporalAnchorResponse] = None
    source_file: str
    is_uploaded: bool = True


class InvestigationResponse(BaseModel):
    """Investigation model matching frontend Investigation interface."""

    id: str
    title: str
    status: str
    priority: str
    region: str
    image_id: Optional[str] = None
    coordinates: Optional[GeoPoint] = None
    spill_area_km2: float = 0.0
    detection_time: Optional[str] = None
    suspect_vessel: Optional[str] = None
    match_confidence: Optional[float] = None
    evidence_nodes_count: int = 0
    sar_epoch: str = "N/A"
    sar_acquisition_time: Optional[str] = None
    sar_acquisition_time_source: Optional[str] = None
    sar_acquisition_time_verified: Optional[bool] = None
    temporal_anchor: Optional[TemporalAnchorResponse] = None
    created_at: Optional[str] = None
    is_starred: bool = False
    is_archived: bool = False
    is_deleted: bool = False
    parent_investigation_id: Optional[str] = None
    artifacts: Optional[Dict[str, Optional[str]]] = None


class InvestigationPatch(BaseModel):
    """Payload for updating mutable fields of an investigation."""

    title: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    is_starred: Optional[bool] = None
    is_archived: Optional[bool] = None


class DashboardSummaryResponse(BaseModel):
    """Aggregated real-time metrics for Dashboard view."""

    total_investigations: int = 0
    completed_investigations: int = 0
    active_investigations: int = 0
    running_investigations: int = 0
    failed_investigations: int = 0
    total_spill_area_km2: float = 0.0
    candidate_vessels_tracked: int = 0
    recent_investigations: List[InvestigationResponse] = Field(default_factory=list)
    latest_completed_investigation: Optional[InvestigationResponse] = None


class TimelineEvent(BaseModel):
    """Single chronological activity audit record."""

    event: str
    timestamp: str
    details: str = ""
    user: str = "Forensic Analyst"


class EvidenceItem(BaseModel):
    """Evidence artifact record with provenance."""

    name: str
    category: str  # "SATELLITE", "SEGMENTATION", "GIS", "OCEAN_DRIFT", "AIS_ATTRIBUTION", "LEGAL_REPORT"
    status: str    # "AVAILABLE", "GENERATING", "UNAVAILABLE"
    file_name: str
    file_path: Optional[str] = None
    file_size_bytes: int = 0
    generated_at: Optional[str] = None
    provenance_source: str
    download_url: Optional[str] = None
    preview_type: str = "none"  # "image", "json", "geojson", "text", "table", "none"


class InvestigationStatusResponse(BaseModel):
    """Current processing state of an investigation."""

    investigation_id: str
    status: str
    stage: Optional[str] = None
    progress_percentage: Optional[int] = None
    updated_at: Optional[str] = None
    message: Optional[str] = None
    stages: Dict[str, str] = Field(default_factory=dict)
