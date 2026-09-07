"""AIS Spatial Filtering Module.

Provides Earth-aware great-circle spatial filtering, bounding box filtering
with anti-meridian handling, trajectory segment qualification, and Member 4
uncertainty envelope integration.
"""

from ais.filtering.config import SpatialFilterConfig, TemporalFilterConfig
from ais.filtering.spatial import (
    EARTH_RADIUS_KM,
    SpatialFilterReport,
    SpatialFilterResult,
    derive_bounding_box,
    filter_by_bounding_box,
    filter_by_origin_uncertainty,
    filter_by_radius,
    filter_spatial,
    filter_trajectories_spatially,
    haversine_distance_km,
)
from ais.filtering.temporal import (
    TemporalFilterReport,
    TemporalFilterResult,
    filter_by_origin_time,
    filter_by_time_window,
    filter_temporal,
    filter_trajectories_temporally,
)

__all__ = [
    "SpatialFilterConfig",
    "SpatialFilterReport",
    "SpatialFilterResult",
    "EARTH_RADIUS_KM",
    "haversine_distance_km",
    "derive_bounding_box",
    "filter_by_bounding_box",
    "filter_by_radius",
    "filter_by_origin_uncertainty",
    "filter_trajectories_spatially",
    "filter_spatial",
    "TemporalFilterConfig",
    "TemporalFilterReport",
    "TemporalFilterResult",
    "filter_by_time_window",
    "filter_by_origin_time",
    "filter_trajectories_temporally",
    "filter_temporal",
]
