"""AIS Track & Observation ORM Model with PostGIS Point Geometry."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Float, Index, Integer, JSON, String
from backend.core.database import Base
from backend.models.base import SafeGeometry, TimestampMixin


class AISTrackModel(Base, TimestampMixin):
    """AIS kinematic observation or reconstructed waypoint."""

    __tablename__ = "ais_tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    investigation_id = Column(String(64), nullable=False, index=True)
    mmsi = Column(BigInteger, nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    speed_knots = Column(Float, nullable=True)
    course_deg = Column(Float, nullable=True)
    heading_deg = Column(Float, nullable=True)
    distance_to_origin_km = Column(Float, nullable=True)

    # PostGIS Spatial Field
    geom = Column(SafeGeometry("POINT", srid=4326), nullable=True)
    metadata_json = Column(JSON, default=dict)

    __table_args__ = (
        Index("idx_ais_inv_mmsi_time", "investigation_id", "mmsi", "timestamp"),
        Index("idx_ais_lat_lon", "latitude", "longitude"),
    )
