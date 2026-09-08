"""Provider-independent AIS search request data structure.

Defines the spatio-temporal parameters required by online or offline AIS data
providers (e.g. MarineTraffic, Spire, NOAA, or local historical stores).
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
import pandas as pd

from ais.filtering.spatial import (
    EARTH_RADIUS_KM,
    LAT_MAX,
    LAT_MIN,
    LON_MAX,
    LON_MIN,
    derive_bounding_box,
)


def _validate_utc_timestamp(
    ts_val: Union[str, pd.Timestamp, datetime, np.datetime64],
    field_name: str,
) -> pd.Timestamp:
    """Validate and normalize a timestamp to UTC-aware pd.Timestamp.

    Raises:
        ValueError: If ts_val is null, unparseable, NaT, or timezone-naive.
    """
    if ts_val is None:
        raise ValueError(f"{field_name} must be provided and non-null")

    try:
        ts = pd.Timestamp(ts_val)
    except Exception as exc:
        raise ValueError(
            f"Invalid {field_name}: {ts_val}. Could not parse datetime."
        ) from exc

    if pd.isna(ts) or ts is pd.NaT:
        raise ValueError(f"Invalid {field_name}: {ts_val}. Value is null or NaT.")

    if ts.tzinfo is None:
        raise ValueError(
            f"{field_name} must be timezone-aware (expected UTC), got naive timestamp '{ts_val}'"
        )

    return ts.tz_convert("UTC")


@dataclasses.dataclass(frozen=True)
class AISSearchRequest:
    """Provider-independent request for AIS vessel position queries.

    Encapsulates geographic search center, radius, search buffer, bounding box,
    and UTC time window. Completely decoupled from any specific external API.

    Attributes:
        latitude: Center latitude in WGS84 degrees [-90.0, 90.0].
        longitude: Center longitude in WGS84 degrees [-180.0, 180.0].
        radius_km: Base search radius in kilometers (finite and > 0).
        start_time: Query window start time (UTC-aware pd.Timestamp).
        end_time: Query window end time (UTC-aware pd.Timestamp, >= start_time).
        buffer_km: Search buffer in kilometers (finite and >= 0.0). Default 0.0.
        bounding_box: Conservative geographic bounding box (min_lat, max_lat, min_lon, max_lon).
            Derived automatically if None.
        source_timestamp: Optional origin/spill event timestamp (UTC-aware).
        candidate_rank: Optional zero-based rank/index of candidate origin.
    """

    latitude: float
    longitude: float
    radius_km: float
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    buffer_km: float = 0.0
    bounding_box: Optional[Tuple[float, float, float, float]] = None
    source_timestamp: Optional[pd.Timestamp] = None
    candidate_rank: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate search parameters and derive bounding box if needed."""
        # 1. Validate latitude
        if (
            self.latitude is None
            or not isinstance(self.latitude, (int, float, np.floating, np.integer))
            or not np.isfinite(self.latitude)
            or not (LAT_MIN <= self.latitude <= LAT_MAX)
        ):
            raise ValueError(
                f"Latitude must be a finite number in [{LAT_MIN}, {LAT_MAX}], got {self.latitude}"
            )
        object.__setattr__(self, "latitude", float(self.latitude))

        # 2. Validate longitude
        if (
            self.longitude is None
            or not isinstance(self.longitude, (int, float, np.floating, np.integer))
            or not np.isfinite(self.longitude)
            or not (LON_MIN <= self.longitude <= LON_MAX)
        ):
            raise ValueError(
                f"Longitude must be a finite number in [{LON_MIN}, {LON_MAX}], got {self.longitude}"
            )
        object.__setattr__(self, "longitude", float(self.longitude))

        # 3. Validate radius_km
        if (
            self.radius_km is None
            or not isinstance(self.radius_km, (int, float, np.floating, np.integer))
            or not np.isfinite(self.radius_km)
            or self.radius_km <= 0.0
        ):
            raise ValueError(
                f"radius_km must be a finite number > 0, got {self.radius_km}"
            )
        object.__setattr__(self, "radius_km", float(self.radius_km))

        # 4. Validate buffer_km
        if (
            self.buffer_km is None
            or not isinstance(self.buffer_km, (int, float, np.floating, np.integer))
            or not np.isfinite(self.buffer_km)
            or self.buffer_km < 0.0
        ):
            raise ValueError(
                f"buffer_km must be a finite non-negative number, got {self.buffer_km}"
            )
        object.__setattr__(self, "buffer_km", float(self.buffer_km))

        # 5. Validate timestamps
        norm_start = _validate_utc_timestamp(self.start_time, "start_time")
        norm_end = _validate_utc_timestamp(self.end_time, "end_time")

        if norm_end < norm_start:
            raise ValueError(
                f"end_time ({norm_end}) must be greater than or equal to start_time ({norm_start})"
            )
        object.__setattr__(self, "start_time", norm_start)
        object.__setattr__(self, "end_time", norm_end)

        # 6. Validate source_timestamp if provided
        if self.source_timestamp is not None:
            norm_source = _validate_utc_timestamp(
                self.source_timestamp, "source_timestamp"
            )
            object.__setattr__(self, "source_timestamp", norm_source)

        # 7. Validate candidate_rank if provided
        if self.candidate_rank is not None:
            if (
                not isinstance(self.candidate_rank, (int, np.integer))
                or self.candidate_rank < 0
            ):
                raise ValueError(
                    f"candidate_rank must be a non-negative integer, got {self.candidate_rank}"
                )
            object.__setattr__(self, "candidate_rank", int(self.candidate_rank))

        # 8. Bounding box resolution & validation
        if self.bounding_box is None:
            eff_radius = self.radius_km + self.buffer_km
            derived_bbox = derive_bounding_box(
                center_latitude=self.latitude,
                center_longitude=self.longitude,
                radius_km=eff_radius,
            )
            object.__setattr__(self, "bounding_box", derived_bbox)
        else:
            if (
                not isinstance(self.bounding_box, (tuple, list))
                or len(self.bounding_box) != 4
            ):
                raise ValueError(
                    "bounding_box must be a 4-tuple of (min_lat, max_lat, min_lon, max_lon)"
                )
            min_lat, max_lat, min_lon, max_lon = self.bounding_box
            for coord, name in [
                (min_lat, "min_latitude"),
                (max_lat, "max_latitude"),
                (min_lon, "min_longitude"),
                (max_lon, "max_longitude"),
            ]:
                if not isinstance(coord, (int, float, np.floating, np.integer)) or not np.isfinite(coord):
                    raise ValueError(f"bounding_box {name} must be a finite float, got {coord}")
            object.__setattr__(
                self,
                "bounding_box",
                (float(min_lat), float(max_lat), float(min_lon), float(max_lon)),
            )

    @property
    def effective_radius_km(self) -> float:
        """Effective search radius including buffer (radius_km + buffer_km)."""
        return self.radius_km + self.buffer_km

    @property
    def min_latitude(self) -> float:
        """Minimum latitude of bounding box."""
        return self.bounding_box[0]

    @property
    def max_latitude(self) -> float:
        """Maximum latitude of bounding box."""
        return self.bounding_box[1]

    @property
    def min_longitude(self) -> float:
        """Minimum longitude of bounding box."""
        return self.bounding_box[2]

    @property
    def max_longitude(self) -> float:
        """Maximum longitude of bounding box."""
        return self.bounding_box[3]

    @property
    def duration_seconds(self) -> float:
        """Total query duration in seconds."""
        return (self.end_time - self.start_time).total_seconds()

    @property
    def duration_minutes(self) -> float:
        """Total query duration in minutes."""
        return self.duration_seconds / 60.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert request to a JSON-serializable dictionary."""
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "radius_km": self.radius_km,
            "buffer_km": self.buffer_km,
            "effective_radius_km": self.effective_radius_km,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_minutes": self.duration_minutes,
            "bounding_box": {
                "min_latitude": self.min_latitude,
                "max_latitude": self.max_latitude,
                "min_longitude": self.min_longitude,
                "max_longitude": self.max_longitude,
            },
            "source_timestamp": (
                self.source_timestamp.isoformat()
                if self.source_timestamp is not None
                else None
            ),
            "candidate_rank": self.candidate_rank,
        }
