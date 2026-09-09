"""Attribution Result ORM Model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import relationship
from backend.core.database import Base
from backend.models.base import TimestampMixin


class AttributionResultModel(Base, TimestampMixin):
    """Vessel attribution score breakdown and ranking record."""

    __tablename__ = "attribution_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    investigation_id = Column(String(64), ForeignKey("investigations.investigation_id", ondelete="CASCADE"), nullable=False, index=True)
    mmsi = Column(BigInteger, nullable=False, index=True)
    vessel_name = Column(String(128), nullable=False)
    imo = Column(String(32), nullable=True)
    vessel_type = Column(String(64), nullable=True)

    # 4-tier score breakdown
    overall_score = Column(Float, nullable=False)
    spatial_score = Column(Float, nullable=False)
    temporal_score = Column(Float, nullable=False)
    trajectory_score = Column(Float, nullable=False)
    behaviour_score = Column(Float, nullable=False)

    # Physical correlation metrics
    min_distance_km = Column(Float, nullable=False)
    time_difference_minutes = Column(Float, nullable=False)
    transit_speed_knots = Column(Float, nullable=True)

    rank = Column(Integer, nullable=False, default=1)
    suspicious_flags_json = Column(JSON, default=list)
    explanation_json = Column(JSON, default=list)
    metadata_json = Column(JSON, default=dict)

    investigation = relationship("InvestigationModel", back_populates="attribution_results")

    __table_args__ = (
        Index("idx_attribution_inv_rank", "investigation_id", "rank"),
        Index("idx_attribution_overall", "overall_score"),
    )
