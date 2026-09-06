"""AIS Vessel Position Interpolation module.

Provides scientifically defensible great-circle shortest-path kinematic
position interpolation strictly within individual continuous AIS-04 trajectory segments.
"""

from ais.interpolation.config import InterpolationConfig
from ais.interpolation.interpolator import (
    InterpolatedSegment,
    InterpolationReport,
    InterpolationResult,
    interpolate_at_timestamp,
    interpolate_coordinates,
    interpolate_trajectories,
    resample_trajectory,
)

__all__ = [
    "InterpolationConfig",
    "InterpolatedSegment",
    "InterpolationReport",
    "InterpolationResult",
    "interpolate_at_timestamp",
    "interpolate_coordinates",
    "interpolate_trajectories",
    "resample_trajectory",
]
