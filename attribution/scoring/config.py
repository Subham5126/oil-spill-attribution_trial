"""Attribution Scoring Configuration.

Defines the configuration dataclass and parameter validation constraints
for multi-criteria vessel attribution scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, Set

import numpy as np


VALID_DECAY_METHODS: Set[str] = {"linear", "gaussian"}
VALID_TIE_BREAKERS: Set[str] = {"spatial"}


def _is_finite_number(val: Any) -> bool:
    """Check if value is a non-boolean finite number."""
    if val is None or isinstance(val, bool):
        return False
    try:
        f = float(val)
        return bool(np.isfinite(f) and not math.isnan(f))
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class AttributionScoringConfig:
    """Configuration settings for vessel attribution scoring.

    Attributes:
        spatial_weight: Weight allocated to spatial proximity [0.0, 1.0].
        temporal_weight: Weight allocated to temporal compatibility [0.0, 1.0].
        trajectory_weight: Weight allocated to trajectory/drift alignment [0.0, 1.0].
        behaviour_weight: Weight allocated to kinematics and telemetry continuity [0.0, 1.0].
        max_distance_km: Distance cutoff beyond which spatial score drops to 0.0.
        spatial_decay: Decay model for spatial score ('linear' or 'gaussian').
        acceptable_window_seconds: Plateau duration where temporal score is 1.0.
        max_time_diff_seconds: Time difference cutoff beyond which temporal score drops to 0.0.
        temporal_decay: Decay model for temporal score ('linear' or 'gaussian').
        min_transit_sog_knots: Lower bound for normal cruising transit speed.
        max_transit_sog_knots: Upper bound for normal cruising transit speed.
        gap_threshold_seconds: Time interval threshold for defining an AIS broadcast gap.
        neutral_speed_score: Neutral score assigned when speed is unavailable.
        tie_breaker: Deterministic secondary tie-breaking method.
    """

    # Dimension weights
    spatial_weight: float = 0.40
    temporal_weight: float = 0.35
    trajectory_weight: float = 0.15
    behaviour_weight: float = 0.10

    # Spatial parameters
    max_distance_km: float = 25.0
    spatial_decay: str = "linear"

    # Temporal parameters
    acceptable_window_seconds: float = 1800.0
    max_time_diff_seconds: float = 7200.0
    temporal_decay: str = "linear"

    # Kinematic & Telemetry parameters
    min_transit_sog_knots: float = 6.0
    max_transit_sog_knots: float = 18.0
    gap_threshold_seconds: float = 1800.0
    neutral_speed_score: float = 0.70

    # Ranking tie-breaker
    tie_breaker: str = "spatial"

    def __post_init__(self) -> None:
        """Validate attribution scoring configuration constraints.

        Raises:
            ValueError: If weights, thresholds, decay methods, or parameters are invalid.
        """
        # 1. Validate weights
        weights = [
            ("spatial_weight", self.spatial_weight),
            ("temporal_weight", self.temporal_weight),
            ("trajectory_weight", self.trajectory_weight),
            ("behaviour_weight", self.behaviour_weight),
        ]
        for name, val in weights:
            if not _is_finite_number(val) or float(val) < 0.0:
                raise ValueError(
                    f"{name} must be a finite non-negative number >= 0.0, got {val}"
                )

        weight_sum = (
            float(self.spatial_weight)
            + float(self.temporal_weight)
            + float(self.trajectory_weight)
            + float(self.behaviour_weight)
        )
        if weight_sum <= 0.0:
            raise ValueError(
                f"Sum of attribution scoring weights must be strictly positive > 0.0, got {weight_sum}"
            )

        # 2. Validate spatial parameters
        if not _is_finite_number(self.max_distance_km) or float(self.max_distance_km) <= 0.0:
            raise ValueError(
                f"max_distance_km must be a finite positive number > 0.0, got {self.max_distance_km}"
            )

        if self.spatial_decay not in VALID_DECAY_METHODS:
            raise ValueError(
                f"spatial_decay must be one of {sorted(list(VALID_DECAY_METHODS))}, got '{self.spatial_decay}'"
            )

        # 3. Validate temporal parameters
        if (
            not _is_finite_number(self.acceptable_window_seconds)
            or float(self.acceptable_window_seconds) < 0.0
        ):
            raise ValueError(
                f"acceptable_window_seconds must be a finite non-negative number >= 0.0, got {self.acceptable_window_seconds}"
            )

        if not _is_finite_number(self.max_time_diff_seconds):
            raise ValueError(
                f"max_time_diff_seconds must be a finite number, got {self.max_time_diff_seconds}"
            )

        if float(self.max_time_diff_seconds) < float(self.acceptable_window_seconds):
            raise ValueError(
                f"max_time_diff_seconds ({self.max_time_diff_seconds}) must be >= acceptable_window_seconds ({self.acceptable_window_seconds})"
            )

        if self.temporal_decay not in VALID_DECAY_METHODS:
            raise ValueError(
                f"temporal_decay must be one of {sorted(list(VALID_DECAY_METHODS))}, got '{self.temporal_decay}'"
            )

        # 4. Validate kinematic parameters
        if (
            not _is_finite_number(self.min_transit_sog_knots)
            or float(self.min_transit_sog_knots) < 0.0
        ):
            raise ValueError(
                f"min_transit_sog_knots must be a finite non-negative number >= 0.0, got {self.min_transit_sog_knots}"
            )

        if (
            not _is_finite_number(self.max_transit_sog_knots)
            or float(self.max_transit_sog_knots) <= float(self.min_transit_sog_knots)
        ):
            raise ValueError(
                f"max_transit_sog_knots must be greater than min_transit_sog_knots ({self.min_transit_sog_knots}), got {self.max_transit_sog_knots}"
            )

        if (
            not _is_finite_number(self.gap_threshold_seconds)
            or float(self.gap_threshold_seconds) <= 0.0
        ):
            raise ValueError(
                f"gap_threshold_seconds must be a finite positive number > 0.0, got {self.gap_threshold_seconds}"
            )

        if (
            not _is_finite_number(self.neutral_speed_score)
            or not (0.0 <= float(self.neutral_speed_score) <= 1.0)
        ):
            raise ValueError(
                f"neutral_speed_score must be in [0.0, 1.0], got {self.neutral_speed_score}"
            )

        # 5. Validate tie-breaker
        if self.tie_breaker not in VALID_TIE_BREAKERS:
            raise ValueError(
                f"tie_breaker must be one of {sorted(list(VALID_TIE_BREAKERS))}, got '{self.tie_breaker}'"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize configuration to a JSON-compatible dictionary."""
        return {
            "spatial_weight": float(self.spatial_weight),
            "temporal_weight": float(self.temporal_weight),
            "trajectory_weight": float(self.trajectory_weight),
            "behaviour_weight": float(self.behaviour_weight),
            "max_distance_km": float(self.max_distance_km),
            "spatial_decay": str(self.spatial_decay),
            "acceptable_window_seconds": float(self.acceptable_window_seconds),
            "max_time_diff_seconds": float(self.max_time_diff_seconds),
            "temporal_decay": str(self.temporal_decay),
            "min_transit_sog_knots": float(self.min_transit_sog_knots),
            "max_transit_sog_knots": float(self.max_transit_sog_knots),
            "gap_threshold_seconds": float(self.gap_threshold_seconds),
            "neutral_speed_score": float(self.neutral_speed_score),
            "tie_breaker": str(self.tie_breaker),
        }
