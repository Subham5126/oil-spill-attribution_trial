"""Spill Detection ORM Model with PostGIS Geometry."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import relationship
from backend.core.database import Base
from backend.models.base import SafeGeometry, TimestampMixin


class SpillDetectionModel(Base, TimestampMixin):
    """Spill detection record holding GIS geometry and morphological measurements."""

    __tablename__ = "spill_detections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    investigation_id = Column(String(64), ForeignKey("investigations.investigation_id", ondelete="CASCADE"), nullable=False, index=True)
    spill_id = Column(String(64), unique=True, nullable=False, index=True)
    sensor = Column(String(128), nullable=False)
    confidence = Column(Float, nullable=False, default=0.9)
    observation_timestamp = Column(DateTime(timezone=True), nullable=False)

    # PostGIS Spatial Fields
    geometry = Column(SafeGeometry("POLYGON", srid=4326), nullable=True)
    centroid_geom = Column(SafeGeometry("POINT", srid=4326), nullable=True)

    # Geographic / Morphological metrics
    centroid_lat = Column(Float, nullable=False)
    centroid_lon = Column(Float, nullable=False)
    area_sq_km = Column(Float, nullable=False)
    area_sq_m = Column(Float, nullable=True)
    perimeter_km = Column(Float, nullable=True)
    perimeter_m = Column(Float, nullable=True)
    bounding_box = Column(JSON, nullable=True)
    compactness = Column(Float, nullable=True)
    aspect_ratio = Column(Float, nullable=True)
    crs = Column(String(32), default="EPSG:4326")
    properties = Column(JSON, default=dict)

    investigation = relationship("InvestigationModel", back_populates="spills")

    __table_args__ = (
        Index("idx_spill_detection_time", "observation_timestamp"),
        Index("idx_spill_centroid", "centroid_lat", "centroid_lon"),
    )
