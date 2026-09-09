"""Integration Data Contracts for Ocean/Drift (Member 4) -> AIS/Attribution (Member 5).

Defines strongly typed, validated boundary contracts:
- SpillObservation: Ingests observed spill geometry and timestamp from GIS/remote sensing.
- OceanDriftResult: Aggregates Member 4 simulation, hindcast, origin analysis, and uncertainty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
import pandas as pd

from ocean.drift.origin import OriginCandidate
from ocean.drift.uncertainty import UncertaintyResult


# Canonical spatial limits (WGS84 EPSG:4326)
LAT_MIN: float = -90.0
LAT_MAX: float = 90.0
LON_MIN: float = -180.0
LON_MAX: float = 180.0


def _validate_utc_timestamp(val: Any, field_name: str) -> pd.Timestamp:
    """Validate that a timestamp is non-null, parseable, and timezone-aware in UTC."""
    if val is None or isinstance(val, bool):
        raise ValueError(f"{field_name} must be provided and non-null")

    try:
        ts = pd.Timestamp(val)
    except Exception as exc:
        raise ValueError(
            f"Invalid {field_name}: '{val}'. Could not parse datetime: {exc}"
        ) from exc

    if pd.isna(ts) or ts is pd.NaT:
        raise ValueError(f"Invalid {field_name}: value is null or NaT")

    if ts.tzinfo is None:
        raise ValueError(
            f"{field_name} must be timezone-aware (expected UTC), got naive timestamp '{val}'"
        )

    try:
        return ts.tz_convert("UTC")
    except Exception as exc:
        raise ValueError(
            f"Failed to convert {field_name} '{val}' to UTC: {exc}"
        ) from exc


@dataclass(frozen=True)
class SpillObservation:
    """Observed marine oil spill geometry and observation metadata.

    Attributes:
        latitude: Observed centroid latitude [-90.0, 90.0].
        longitude: Observed centroid longitude [-180.0, 180.0].
        timestamp: Observation time (strictly UTC-aware).
        spill_id: Optional unique identifier for the spill detection.
        area_sq_m: Optional estimated surface area in square meters.
        polygon: Optional spatial polygon representation (e.g. list of (lon, lat) tuples).
    """

    latitude: float
    longitude: float
    timestamp: pd.Timestamp
    spill_id: Optional[str] = None
    area_sq_m: Optional[float] = None
    polygon: Optional[Any] = None
    perimeter_m: Optional[float] = None
    bounding_box: Optional[Tuple[float, float, float, float]] = None
    compactness: Optional[float] = None
    aspect_ratio: Optional[float] = None
    source_sensor: Optional[str] = None
    confidence: Optional[float] = None

    def __post_init__(self) -> None:
        """Validate observed spill geographic and temporal bounds."""
        object.__setattr__(
            self,
            "timestamp",
            _validate_utc_timestamp(self.timestamp, "SpillObservation.timestamp"),
        )

        if not np.isfinite(self.latitude) or not (LAT_MIN <= float(self.latitude) <= LAT_MAX):
            raise ValueError(
                f"SpillObservation latitude must be in [{LAT_MIN}, {LAT_MAX}], got {self.latitude}"
            )
        object.__setattr__(self, "latitude", float(self.latitude))

        if not np.isfinite(self.longitude) or not (LON_MIN <= float(self.longitude) <= LON_MAX):
            raise ValueError(
                f"SpillObservation longitude must be in [{LON_MIN}, {LON_MAX}], got {self.longitude}"
            )
        object.__setattr__(self, "longitude", float(self.longitude))

        if self.area_sq_m is not None:
            if not np.isfinite(self.area_sq_m) or float(self.area_sq_m) < 0.0:
                raise ValueError(
                    f"SpillObservation area_sq_m must be non-negative, got {self.area_sq_m}"
                )
            object.__setattr__(self, "area_sq_m", float(self.area_sq_m))

        if self.perimeter_m is not None:
            if not np.isfinite(self.perimeter_m) or float(self.perimeter_m) < 0.0:
                raise ValueError(
                    f"SpillObservation perimeter_m must be non-negative, got {self.perimeter_m}"
                )
            object.__setattr__(self, "perimeter_m", float(self.perimeter_m))

        if self.confidence is not None:
            if not np.isfinite(self.confidence) or not (0.0 <= float(self.confidence) <= 1.0):
                raise ValueError(
                    f"SpillObservation confidence must be in [0.0, 1.0], got {self.confidence}"
                )
            object.__setattr__(self, "confidence", float(self.confidence))

    @classmethod
    def from_oil_spill_geometry(
        cls,
        spill: Any,
        measurement: Optional[Any] = None,
    ) -> SpillObservation:
        """Create SpillObservation from a Member 3 OilSpillGeometry or Polygon/MultiPolygon.

        Args:
            spill: OilSpillGeometry, Polygon, or MultiPolygon.
            measurement: Optional pre-computed SpillMeasurement.

        Returns:
            SpillObservation with centroid coordinates, physical metrics, and polygon.
        """
        from gis.geometry.models import OilSpillGeometry
        from gis.measurements.models import measure_oil_spill

        if measurement is None:
            measurement = measure_oil_spill(spill)

        if isinstance(spill, OilSpillGeometry):
            spill_id = spill.spill_id
            polygon_geom = spill.geometry
            source_sensor = spill.source_sensor
            confidence = spill.confidence
            timestamp = spill.detection_timestamp
        else:
            spill_id = getattr(measurement, "spill_id", None)
            polygon_geom = spill
            source_sensor = "Satellite SAR"
            confidence = 1.0
            timestamp = pd.Timestamp.now(tz="UTC")

        return cls(
            latitude=measurement.centroid.lat,
            longitude=measurement.centroid.lon,
            timestamp=timestamp,
            spill_id=spill_id,
            area_sq_m=measurement.area_sq_m,
            polygon=polygon_geom,
            perimeter_m=measurement.perimeter_m,
            bounding_box=measurement.bounding_box.to_tuple() if measurement.bounding_box else None,
            compactness=measurement.compactness,
            aspect_ratio=measurement.aspect_ratio,
            source_sensor=source_sensor,
            confidence=confidence,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dictionary."""
        d = {
            "spill_id": self.spill_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timestamp": self.timestamp.isoformat(),
            "area_sq_m": self.area_sq_m,
            "polygon": str(self.polygon) if self.polygon is not None else None,
        }
        if self.perimeter_m is not None:
            d["perimeter_m"] = self.perimeter_m
        if self.bounding_box is not None:
            d["bounding_box"] = list(self.bounding_box)
        if self.compactness is not None:
            d["compactness"] = self.compactness
        if self.aspect_ratio is not None:
            d["aspect_ratio"] = self.aspect_ratio
        if self.source_sensor is not None:
            d["source_sensor"] = self.source_sensor
        if self.confidence is not None:
            d["confidence"] = self.confidence
        return d


@dataclass
class OceanDriftResult:
    """Comprehensive output container for Member 4 Ocean and Drift modelling.

    Aggregates:
    - spill_observation: Source observation if available
    - best_candidate: Top-scoring probable release origin candidate
    - ranked_candidates: All candidate release origins ranked by heuristic score
    - uncertainty: Empirical spatial dispersion estimate at best candidate origin
    - hindcast_trajectories: Complete backward particle trajectories DataFrame
    - forecast_trajectories: Optional forward particle trajectories DataFrame
    - drift_direction_deg: Optional explicit drift vector angle (0..360° from North)
    """

    best_candidate: OriginCandidate
    ranked_candidates: List[OriginCandidate]
    spill_observation: Optional[SpillObservation] = None
    uncertainty: Optional[UncertaintyResult] = None
    hindcast_trajectories: Optional[pd.DataFrame] = None
    forecast_trajectories: Optional[pd.DataFrame] = None
    drift_direction_deg: Optional[float] = None

    def __post_init__(self) -> None:
        """Validate candidates consistency."""
        if not self.ranked_candidates:
            raise ValueError("ranked_candidates cannot be empty")
        if self.best_candidate is None:
            self.best_candidate = self.ranked_candidates[0]

        if self.drift_direction_deg is not None:
            if not np.isfinite(self.drift_direction_deg):
                raise ValueError(
                    f"drift_direction_deg must be a finite number, got {self.drift_direction_deg}"
                )
            self.drift_direction_deg = float(self.drift_direction_deg) % 360.0

    @property
    def probable_origin_latitude(self) -> float:
        """Latitude of the highest scoring candidate origin."""
        return float(self.best_candidate.region.centroid_lat)

    @property
    def probable_origin_longitude(self) -> float:
        """Longitude of the highest scoring candidate origin."""
        return float(self.best_candidate.region.centroid_lon)

    @property
    def probable_origin_timestamp(self) -> pd.Timestamp:
        """Timestamp of the highest scoring candidate origin."""
        return pd.Timestamp(self.best_candidate.timestamp)

    @property
    def probable_origin_score(self) -> float:
        """Relative heuristic origin score of the top candidate."""
        return float(self.best_candidate.heuristic_score)

    @property
    def uncertainty_radius_km(self) -> float:
        """Authoritative uncertainty radius in km (prefers UncertaintyResult, falls back to HDR area)."""
        if self.uncertainty is not None and np.isfinite(self.uncertainty.uncertainty_radius_km):
            return float(self.uncertainty.uncertainty_radius_km)
        # Fallback to equivalent circular radius from CandidateRegion area
        area = getattr(self.best_candidate.region, "area_sq_meters", None)
        if area is not None and np.isfinite(area) and area > 0:
            import math
            return (math.sqrt(float(area) / math.pi)) / 1000.0
        return 5.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to standardized dictionary conforming to Member 4 -> Member 5 expectations."""
        d: Dict[str, Any] = {
            "status": "success",
            "best_candidate": self.best_candidate,
            "ranked_candidates": self.ranked_candidates,
            "best_time": self.probable_origin_timestamp,
        }
        if self.spill_observation is not None:
            d["spill_observation"] = self.spill_observation.to_dict()

        if self.uncertainty is not None:
            d["uncertainty"] = {
                "timestamp": self.uncertainty.timestamp.isoformat(),
                "particle_count": self.uncertainty.particle_count,
                "centroid_latitude": float(self.uncertainty.centroid_latitude),
                "centroid_longitude": float(self.uncertainty.centroid_longitude),
                "spread_km": float(self.uncertainty.spread_km),
                "radius_km": float(self.uncertainty.uncertainty_radius_km),
                "confidence_level": float(self.uncertainty.confidence_level),
                "min_latitude": float(self.uncertainty.min_latitude),
                "max_latitude": float(self.uncertainty.max_latitude),
                "min_longitude": float(self.uncertainty.min_longitude),
                "max_longitude": float(self.uncertainty.max_longitude),
            }

        if self.drift_direction_deg is not None:
            d["drift_direction_deg"] = float(self.drift_direction_deg)

        return d
