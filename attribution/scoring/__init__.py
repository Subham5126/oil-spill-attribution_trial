"""Attribution Scoring Package.

Provides spatial, temporal, trajectory, and kinematic behaviour scoring,
configuration, and evaluation engine for candidate vessel attribution.
"""

from attribution.scoring.config import AttributionScoringConfig
from attribution.scoring.engine import attribute_vessels, score_candidates
from attribution.scoring.spatial import calculate_spatial_score, find_closest_approach
from attribution.scoring.temporal import calculate_temporal_score, resolve_time_of_closest_approach
from attribution.scoring.trajectory import (
    analyze_ais_gaps,
    calculate_bearing,
    calculate_behaviour_score,
    calculate_trajectory_score,
    determine_vessel_direction,
)

__all__ = [
    "AttributionScoringConfig",
    "score_candidates",
    "attribute_vessels",
    "calculate_spatial_score",
    "find_closest_approach",
    "calculate_temporal_score",
    "resolve_time_of_closest_approach",
    "calculate_bearing",
    "determine_vessel_direction",
    "calculate_trajectory_score",
    "calculate_behaviour_score",
    "analyze_ais_gaps",
]
