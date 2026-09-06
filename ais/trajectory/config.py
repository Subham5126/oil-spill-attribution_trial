"""AIS Trajectory Reconstruction Configuration.

Defines configuration settings and constraints for segmenting AIS observations
into continuous, gap-bounded vessel trajectories according to maritime domain standards.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TrajectoryConfig:
    """Configuration for vessel trajectory reconstruction and temporal gap segmentation.

    Attributes:
        max_gap_seconds: Maximum allowed elapsed time in seconds between consecutive
            observations for the same vessel before splitting into a new trajectory segment.
            Defaults to 7200.0 seconds (2.0 hours).

            Scientific & Domain Rationale:
            - Terrestrial AIS (T-AIS) typically broadcasts dynamic position reports every
              2 to 10 seconds under way, and every 3 minutes at anchor (ITU-R M.1371).
            - Satellite AIS (S-AIS) constellation orbital passes introduce revisit latencies
              typically ranging from 15 minutes to 1 hour in open oceans.
            - When observation blackouts exceed 2 hours (7200 s), maritime dead reckoning
              and linear kinematic assumptions degrade significantly due to unobserved
              course/speed changes, tidal currents, and wind drift.
            - Connecting points across gaps > 2 hours introduces severe trajectory uncertainty.
              Segmenting the track at > 2 hours preserves scientific rigor for downstream
              interpolation (AIS-05) and spatial-temporal spill origin correlation (AIS-06/07).
        min_observations_per_segment: Minimum observations required for a segment to be
            retained. Defaults to 1 (preserves single-ping observations).
    """

    max_gap_seconds: float = 7200.0  # 2 hours
    min_observations_per_segment: int = 1

    def __post_init__(self) -> None:
        """Validate configuration settings.

        Raises:
            ValueError: If max_gap_seconds <= 0 or min_observations_per_segment < 1.
        """
        if self.max_gap_seconds <= 0.0:
            raise ValueError(
                f"max_gap_seconds must be positive, got {self.max_gap_seconds}"
            )
        if self.min_observations_per_segment < 1:
            raise ValueError(
                f"min_observations_per_segment must be >= 1, got {self.min_observations_per_segment}"
            )
