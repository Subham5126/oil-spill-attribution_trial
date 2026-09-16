"""Investigation Artifact ORM Model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import relationship

from backend.core.database import Base
from backend.models.base import TimestampMixin


class InvestigationArtifactModel(Base, TimestampMixin):
    """Immutable forensic evidence artifact record scoped to an investigation and execution."""

    __tablename__ = "investigation_artifacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    artifact_id = Column(String(64), unique=True, nullable=False, index=True)
    investigation_id = Column(String(64), ForeignKey("investigations.investigation_id", ondelete="CASCADE"), nullable=False, index=True)
    pipeline_run_id = Column(String(64), nullable=True, index=True)
    image_id = Column(String(64), nullable=True, index=True)

    artifact_type = Column(String(64), nullable=False)
    artifact_name = Column(String(255), nullable=False)
    category = Column(String(64), nullable=False)  # SATELLITE, DETECTION, SEGMENTATION, GIS, OCEAN_DRIFT, AIS_ATTRIBUTION, LEGAL_REPORT
    storage_path = Column(String(512), nullable=True)
    file_name = Column(String(255), nullable=False)
    mime_type = Column(String(128), default="application/octet-stream")
    byte_size = Column(BigInteger, default=0)
    sha256 = Column(String(64), nullable=True)

    provenance_source = Column(String(255), nullable=True)
    preview_type = Column(String(64), default="none")
    status = Column(String(32), default="AVAILABLE")  # AVAILABLE, UNAVAILABLE, CORRUPTED
    unavailable_reason = Column(String(512), nullable=True)
    metadata_json = Column(JSON, default=dict)

    __table_args__ = (
        Index("idx_artifact_inv_run", "investigation_id", "pipeline_run_id"),
        Index("idx_artifact_type", "investigation_id", "artifact_type"),
    )
