"""AIS Vessel Position Interpolation Configuration.

Defines configuration settings, constraints, and validation for kinematic
trajectory interpolation strictly adhering to maritime domain standards and
spatial-temporal physics.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class InterpolationConfig:
    """Configuration settings for vessel position interpolation.

    Attributes:
        max_gap_seconds: Maximum elapsed time in seconds between two consecutive
            actual AIS observations across which interpolation is scientifically
            permissible. Defaults to 3600.0 seconds (1.0 hour).

            Scientific Rationale:
            - While trajectory reconstruction (AIS-04) groups observations up to 2.0 hours
              (7200 s) to maintain vessel identity across typical S-AIS constellation revisits,
              dead-reckoning accuracy degrades significantly beyond 1.0 hour (3600 s) due to
              unobserved vessel maneuvers (course or speed alterations) and environmental
              current/wind drift.
            - Restricting interpolation to intervals <= 3600 s ensures high geometric fidelity
              and prevents generating false linear assumptions across long blackout intervals.
        method: Interpolation algorithm. For MVP, strictly "linear" (great-circle shortest-path
            angular interpolation for longitude, linear for latitude). Defaults to "linear".
    """

    max_gap_seconds: float = 3600.0
    method: str = "linear"

    def __post_init__(self) -> None:
        """Validate configuration settings.

        Raises:
            ValueError: If max_gap_seconds <= 0 or method is not 'linear'.
        """
        if self.max_gap_seconds <= 0.0:
            raise ValueError(
                f"max_gap_seconds must be positive, got {self.max_gap_seconds}"
            )
        if self.method != "linear":
            raise ValueError(
                f"Unsupported interpolation method: '{self.method}'. Only 'linear' is supported."
            )
