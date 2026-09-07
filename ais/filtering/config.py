"""AIS Spatial Filtering Configuration.

Defines the configuration dataclass and parameter validation constraints for
Earth-aware spatial filtering of AIS observations and vessel trajectories.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class SpatialFilterConfig:
    """Configuration settings for AIS spatial filtering.

    Attributes:
        radius_km: Base spatial search radius in kilometers. Defaults to 10.0 km.
            When Member 4 uncertainty data is supplied, uncertainty.radius_km
            serves as the empirical base radius.
        buffer_km: Additional empirical buffer in kilometers added to the base
            radius (R_search = base_radius + buffer_km). Defaults to 0.0 km.
        use_bounding_box: If True (default), applies a coarse geographic bounding box
            filter before calculating exact great-circle Haversine distances to optimize
            throughput on large datasets.
        min_latitude: Optional bounding box minimum latitude in [-90.0, 90.0].
        max_latitude: Optional bounding box maximum latitude in [-90.0, 90.0].
        min_longitude: Optional bounding box minimum longitude in [-180.0, 180.0].
        max_longitude: Optional bounding box maximum longitude in [-180.0, 180.0].
        distance_metric: Distance formula to use. Strictly 'haversine'.
    """

    radius_km: float = 10.0
    buffer_km: float = 0.0
    use_bounding_box: bool = True
    min_latitude: Optional[float] = None
    max_latitude: Optional[float] = None
    min_longitude: Optional[float] = None
    max_longitude: Optional[float] = None
    distance_metric: str = "haversine"

    def __post_init__(self) -> None:
        """Validate spatial filter configuration constraints.

        Raises:
            ValueError: If radius, buffer, coordinates, or distance metric are invalid
                or non-finite.
        """
        if not np.isfinite(self.radius_km) or self.radius_km < 0.0:
            raise ValueError(
                f"radius_km must be a finite non-negative number, got {self.radius_km}"
            )
        if not np.isfinite(self.buffer_km) or self.buffer_km < 0.0:
            raise ValueError(
                f"buffer_km must be a finite non-negative number, got {self.buffer_km}"
            )
        if self.distance_metric != "haversine":
            raise ValueError(
                f"Unsupported distance metric: '{self.distance_metric}'. Only 'haversine' is supported."
            )

        # Validate latitude bounds if provided
        for lat_name, lat_val in [
            ("min_latitude", self.min_latitude),
            ("max_latitude", self.max_latitude),
        ]:
            if lat_val is not None:
                if not np.isfinite(lat_val) or not (-90.0 <= lat_val <= 90.0):
                    raise ValueError(
                        f"{lat_name} must be a finite number in [-90.0, 90.0], got {lat_val}"
                    )

        if self.min_latitude is not None and self.max_latitude is not None:
            if self.min_latitude > self.max_latitude:
                raise ValueError(
                    f"min_latitude ({self.min_latitude}) cannot be greater than max_latitude ({self.max_latitude})"
                )

        # Validate longitude bounds if provided
        for lon_name, lon_val in [
            ("min_longitude", self.min_longitude),
            ("max_longitude", self.max_longitude),
        ]:
            if lon_val is not None:
                if not np.isfinite(lon_val) or not (-180.0 <= lon_val <= 180.0):
                    raise ValueError(
                        f"{lon_name} must be a finite number in [-180.0, 180.0], got {lon_val}"
                    )
