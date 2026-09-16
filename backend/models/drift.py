"""Drift Run ORM Model."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import relationship
from backend.core.database import Base
from backend.models.base import TimestampMixin


class DriftRunModel(Base, TimestampMixin):
    """Execution record of forward/backward Lagrangian particle drift simulation."""

    __tablename__ = "drift_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    investigation_id = Column(String(64), ForeignKey("investigations.investigation_id", ondelete="CASCADE"), nullable=False, index=True)
    model_name = Column(String(128), default="Lagrangian Forward/Backward Euler", nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    particle_count = Column(Integer, default=50)
    windage = Column(Float, default=0.03)
    timestep_seconds = Column(Integer, default=3600)
    duration_hours = Column(Float, default=4.0)
    status = Column(String(32), default="COMPLETED", nullable=False)
    probable_origin_lat = Column(Float, nullable=True)
    probable_origin_lon = Column(Float, nullable=True)
    probable_origin_timestamp = Column(DateTime(timezone=True), nullable=True)
    uncertainty_radius_km = Column(Float, nullable=True)
    uncertainty_spread_km = Column(Float, nullable=True)
    uncertainty_coverage_level = Column(Float, default=0.95)
    forecast_data = Column(JSON, default=dict)
    hindcast_data = Column(JSON, default=dict)
    metadata_json = Column(JSON, default=dict)

    investigation = relationship("InvestigationModel", back_populates="drift_runs")

    __table_args__ = (
        Index("idx_drift_investigation_status", "investigation_id", "status"),
    )
