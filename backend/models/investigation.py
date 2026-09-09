"""Investigation ORM Model."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, Index, Integer, JSON, String
from sqlalchemy.orm import relationship
from backend.core.database import Base
from backend.models.base import TimestampMixin


class InvestigationModel(Base, TimestampMixin):
    """Investigation record tracking an oil spill attribution incident."""

    __tablename__ = "investigations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    investigation_id = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    status = Column(String(32), default="Active", nullable=False, index=True)
    priority = Column(String(16), default="Medium", nullable=False)
    region = Column(String(128), nullable=False)
    observation_timestamp = Column(DateTime(timezone=True), nullable=True)
    centroid_lat = Column(Float, nullable=True)
    centroid_lon = Column(Float, nullable=True)
    spill_area_km2 = Column(Float, nullable=True)
    suspect_vessel = Column(String(128), nullable=True)
    match_confidence = Column(Float, nullable=True)
    evidence_nodes_count = Column(Integer, default=0)
    sar_epoch = Column(String(32), nullable=True)
    metadata_json = Column(JSON, default=dict)

    # Relationships
    spills = relationship("SpillDetectionModel", back_populates="investigation", cascade="all, delete-orphan")
    drift_runs = relationship("DriftRunModel", back_populates="investigation", cascade="all, delete-orphan")
    origin_candidates = relationship("OriginCandidateModel", back_populates="investigation", cascade="all, delete-orphan")
    attribution_results = relationship("AttributionResultModel", back_populates="investigation", cascade="all, delete-orphan")
    reports = relationship("ReportModel", back_populates="investigation", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_investigation_status_priority", "status", "priority"),
    )
