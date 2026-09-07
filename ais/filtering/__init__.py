"""AIS Spatial Filtering Module.

Provides Earth-aware great-circle spatial filtering, bounding box filtering
with anti-meridian handling, trajectory segment qualification, and Member 4
uncertainty envelope integration.
"""

from ais.filtering.config import SpatialFilterConfig
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
]
