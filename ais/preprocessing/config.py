"""AIS Data Cleaning Configuration.

Defines the configuration dataclass and validation constraints for AIS kinematic
cleaning, anomaly detection, and trajectory quality filtering.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CleaningConfig:
    """Configuration settings for AIS kinematic cleaning and validation.

    All thresholds represent physically grounded maritime kinematic boundaries.
    These flags and filters are DATA-QUALITY FLAGS ONLY and do not represent
    proof or claims of vessel wrongdoing or guilt.

    Attributes:
        max_speed_knots: Maximum physically plausible speed for maritime commercial
            vessels (cargo, tankers, fishing, bulkers). Defaults to 60.0 knots.
            Derived velocities exceeding this threshold represent GPS glitches,
            multipath errors, or sensor resets.
        min_time_delta_seconds: Minimum elapsed time in seconds between pings required
            to compute derived velocity. Avoids division-by-zero or mathematical
            instability from near-simultaneous multi-receiver pings. Defaults to 1.0 second.
        max_acceleration_knots_per_s: Optional maximum plausible acceleration or deceleration.
            Defaults to None (omitted) to avoid inventing arbitrary physical assumptions.
        filter_anomalies: If True (default), rows classified as anomalous position jumps
            or spikes are removed from the cleaned output. If False, all rows are
            retained and only annotated with boolean quality flags.
        filter_suspicious_zero_jumps: If True (default), (0.0, 0.0) coordinate pings that
            represent discontinuous trajectory jumps away from active navigation positions
            are removed. Legitimate tracks near (0, 0) are strictly preserved.
        sog_inconsistency_threshold_knots: Conservative tolerance (in knots) between reported
            SOG (from vessel transponder) and derived velocity (from inter-ping distance/time)
            used to flag is_sog_inconsistent. Defaults to 20.0 knots.
    """

    max_speed_knots: float = 60.0
    min_time_delta_seconds: float = 1.0
    max_acceleration_knots_per_s: Optional[float] = None
    filter_anomalies: bool = True
    filter_suspicious_zero_jumps: bool = True
    sog_inconsistency_threshold_knots: float = 20.0

    def __post_init__(self) -> None:
        """Validate configuration thresholds.

        Raises:
            ValueError: If any numeric threshold is non-positive or invalid.
        """
        if self.max_speed_knots <= 0.0:
            raise ValueError(
                f"max_speed_knots must be positive, got {self.max_speed_knots}"
            )
        if self.min_time_delta_seconds < 0.0:
            raise ValueError(
                f"min_time_delta_seconds must be non-negative, got {self.min_time_delta_seconds}"
            )
        if (
            self.max_acceleration_knots_per_s is not None
            and self.max_acceleration_knots_per_s <= 0.0
        ):
            raise ValueError(
                f"max_acceleration_knots_per_s must be positive, got {self.max_acceleration_knots_per_s}"
            )
        if self.sog_inconsistency_threshold_knots <= 0.0:
            raise ValueError(
                f"sog_inconsistency_threshold_knots must be positive, got {self.sog_inconsistency_threshold_knots}"
            )
