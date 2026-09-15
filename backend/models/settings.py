"""Attribution Scoring Configuration & Calibration ORM Model."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, Float, Index, Integer, JSON, String

from backend.core.database import Base
from backend.models.base import TimestampMixin


class AttributionCalibrationModel(Base, TimestampMixin):
    """Persisted scoring calibration configuration with version provenance."""

    __tablename__ = "attribution_calibrations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(64), unique=True, nullable=False, index=True)

    # Weights normalized to sum to 1.0 (or 100%)
    spatial_proximity_weight = Column(Float, default=0.35, nullable=False)
    temporal_overlap_weight = Column(Float, default=0.25, nullable=False)
    drift_consistency_weight = Column(Float, default=0.15, nullable=False)
    track_consistency_weight = Column(Float, default=0.10, nullable=False)
    vessel_type_relevance_weight = Column(Float, default=0.08, nullable=False)
    ais_quality_weight = Column(Float, default=0.07, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False, index=True)
    notes = Column(String(255), nullable=True)
    extra_params = Column(JSON, default=dict)

    def to_weights_dict(self) -> dict:
        return {
            "spatial_proximity": self.spatial_proximity_weight,
            "temporal_overlap": self.temporal_overlap_weight,
            "drift_consistency": self.drift_consistency_weight,
            "track_consistency": self.track_consistency_weight,
            "vessel_type_relevance": self.vessel_type_relevance_weight,
            "ais_quality": self.ais_quality_weight,
        }
