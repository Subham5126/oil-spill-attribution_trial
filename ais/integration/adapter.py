"""Member 4 Drift Origin Adapter for AIS Provider Integration.

Translates Member 4 ocean.drift.origin.analyze_origin() results into both:
1. Provider-independent AISSearchRequest instances for querying AIS services.
2. Standardized origin_data dictionaries conforming to the Member 4 -> Member 5
   filtering contracts for spatial and temporal filtering.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from ais.filtering.spatial import (
    LAT_MAX,
    LAT_MIN,
    LON_MAX,
    LON_MIN,
    derive_bounding_box,
)
from ais.integration.search_request import (
    AISSearchRequest,
    _validate_utc_timestamp,
)


def _is_valid_positive_number(val: Any) -> bool:
    """Check if a value is numeric, finite, and strictly greater than zero."""
    if val is None or isinstance(val, bool):
        return False
    try:
        f = float(val)
        return bool(np.isfinite(f) and f > 0.0)
    except (TypeError, ValueError):
        return False


def _resolve_radius_km(
    region: Any,
    default_radius_km: float,
) -> float:
    """Resolve search radius in kilometers following Step 5 precedence.

    1. If region.radius_km exists and is valid: use region.radius_km directly.
    2. Otherwise, if region.area_sq_meters exists and is valid:
           radius_km = sqrt(area_sq_meters / pi) / 1000
    3. Otherwise: use default_radius_km.

    If both radius_km and area_sq_meters are present and valid, radius_km is authoritative.
    """
    raw_radius_km = getattr(region, "radius_km", None)
    if raw_radius_km is None and isinstance(region, dict):
        raw_radius_km = region.get("radius_km")

    if _is_valid_positive_number(raw_radius_km):
        return float(raw_radius_km)

    raw_area = getattr(region, "area_sq_meters", None)
    if raw_area is None and isinstance(region, dict):
        raw_area = region.get("area_sq_meters")

    if _is_valid_positive_number(raw_area):
        radius_m = math.sqrt(float(raw_area) / math.pi)
        return radius_m / 1000.0

    return float(default_radius_km)


def _extract_region_coordinates(region: Any) -> Tuple[float, float]:
    """Extract and validate (latitude, longitude) from region object or dictionary.

    Raises:
        ValueError: If coordinates are missing, non-numeric, non-finite, or out of bounds.
    """
    lat = getattr(region, "centroid_lat", None)
    if lat is None:
        lat = getattr(region, "centroid_latitude", None)
    if lat is None:
        lat = getattr(region, "latitude", None)
    if lat is None and isinstance(region, dict):
        lat = region.get("centroid_lat")
        if lat is None:
            lat = region.get("centroid_latitude")
        if lat is None:
            lat = region.get("latitude")

    lon = getattr(region, "centroid_lon", None)
    if lon is None:
        lon = getattr(region, "centroid_longitude", None)
    if lon is None:
        lon = getattr(region, "longitude", None)
    if lon is None and isinstance(region, dict):
        lon = region.get("centroid_lon")
        if lon is None:
            lon = region.get("centroid_longitude")
        if lon is None:
            lon = region.get("longitude")

    if lat is None or lon is None:
        raise ValueError(
            f"Region coordinates must be provided, got latitude={lat}, longitude={lon}"
        )

    if (
        not isinstance(lat, (int, float, np.floating, np.integer))
        or not np.isfinite(lat)
        or not (LAT_MIN <= lat <= LAT_MAX)
    ):
        raise ValueError(
            f"Latitude must be a finite number in [{LAT_MIN}, {LAT_MAX}], got {lat}"
        )

    if (
        not isinstance(lon, (int, float, np.floating, np.integer))
        or not np.isfinite(lon)
        or not (LON_MIN <= lon <= LON_MAX)
    ):
        raise ValueError(
            f"Longitude must be a finite number in [{LON_MIN}, {LON_MAX}], got {lon}"
        )

    return float(lat), float(lon)


def _extract_candidate_timestamp(candidate: Any, fallback_ts: Any = None) -> pd.Timestamp:
    """Extract and normalize candidate timestamp to UTC pd.Timestamp."""
    ts_val = getattr(candidate, "timestamp", None)
    if ts_val is None and isinstance(candidate, dict):
        ts_val = candidate.get("timestamp")
    if ts_val is None:
        ts_val = fallback_ts
    if ts_val is None:
        raise ValueError("Candidate timestamp is missing and non-recoverable")
    return _validate_utc_timestamp(ts_val, "candidate timestamp")


def _serialize_candidate(
    candidate: Any,
    default_radius_km: float,
) -> Dict[str, Any]:
    """Convert an OriginCandidate into a standardized JSON-serializable dictionary."""
    region = getattr(candidate, "region", None)
    if region is None and isinstance(candidate, dict):
        region = candidate.get("region", candidate)
    if region is None:
        region = candidate

    lat, lon = _extract_region_coordinates(region)
    cand_ts = _extract_candidate_timestamp(candidate, None)
    cand_radius = _resolve_radius_km(region, default_radius_km)

    h_score = getattr(candidate, "heuristic_score", None)
    if h_score is None and isinstance(candidate, dict):
        h_score = candidate.get("heuristic_score")

    conc = getattr(candidate, "concentration", None)
    if conc is None and isinstance(candidate, dict):
        conc = candidate.get("concentration")

    dens = getattr(candidate, "density_strength", None)
    if dens is None and isinstance(candidate, dict):
        dens = candidate.get("density_strength")

    stab = getattr(candidate, "temporal_stability", None)
    if stab is None and isinstance(candidate, dict):
        stab = candidate.get("temporal_stability")

    cov = getattr(region, "coverage_level", None)
    if cov is None and isinstance(region, dict):
        cov = region.get("coverage_level")

    area = getattr(region, "area_sq_meters", None)
    if area is None and isinstance(region, dict):
        area = region.get("area_sq_meters")

    return {
        "timestamp": cand_ts.isoformat(),
        "latitude": float(lat),
        "longitude": float(lon),
        "heuristic_score": float(h_score) if h_score is not None else None,
        "radius_km": float(cand_radius),
        "coverage_level": float(cov) if cov is not None else None,
        "area_sq_meters": float(area) if area is not None else None,
        "concentration": float(conc) if conc is not None else None,
        "density_strength": float(dens) if dens is not None else None,
        "temporal_stability": float(stab) if stab is not None else None,
    }


@dataclasses.dataclass(frozen=True)
class AISIntegrationResult:
    """Container for adapter results connecting Member 4 to Member 5.

    Provides structured access to both the standardized origin metadata dictionary
    (for existing filter_spatial and filter_temporal modules) and the provider-independent
    AISSearchRequest (for external AIS services).
    """

    origin_data: Dict[str, Any]
    search_request: AISSearchRequest

    def get(self, key: str, default: Any = None) -> Any:
        """Convenience getter for dictionary-like access matching origin_data."""
        return self.origin_data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        """Convenience indexer matching origin_data."""
        return self.origin_data[key]

    def __contains__(self, key: str) -> bool:
        """Convenience containment check matching origin_data."""
        return key in self.origin_data

    @property
    def origin(self) -> Dict[str, Any]:
        """Extracted origin dictionary."""
        return self.origin_data.get("origin", {})

    @property
    def uncertainty(self) -> Dict[str, Any]:
        """Extracted uncertainty dictionary."""
        return self.origin_data.get("uncertainty", {})

    @property
    def candidate_origins(self) -> List[Dict[str, Any]]:
        """List of all standardized candidate release origins."""
        return self.origin_data.get("candidate_origins", [])

    @property
    def spill_observation(self) -> Optional[Dict[str, Any]]:
        """Optional spill observation metadata."""
        return self.origin_data.get("spill_observation")

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a comprehensive JSON-serializable dictionary."""
        return {
            "origin_data": self.origin_data,
            "search_request": self.search_request.to_dict(),
        }


def adapt_drift_origin_result(
    member4_output: Any,
    spill_observation: Optional[Dict[str, Any]] = None,
    default_radius_km: float = 5.0,
    buffer_km: float = 1.0,
    before_minutes: float = 30.0,
    after_minutes: float = 30.0,
) -> AISIntegrationResult:
    """Convert Member 4 origin analysis output into an AIS search request and origin_data.

    Supports both current Member 4 output (OriginCandidate with area_sq_meters)
    and future Member 4 outputs (explicit radius_km).

    Args:
        member4_output: Output from Member 4 analyze_origin() (dict or OriginCandidate).
        spill_observation: Optional dictionary with observed spill metadata (latitude, longitude, timestamp).
        default_radius_km: Fallback radius in km if neither radius_km nor area_sq_meters is valid.
        buffer_km: Search buffer in kilometers added to radius for spatial querying.
        before_minutes: Minutes prior to origin timestamp for query window start.
        after_minutes: Minutes after origin timestamp for query window end.

    Returns:
        AISIntegrationResult containing standardized origin_data and AISSearchRequest.

    Raises:
        ValueError: If inputs are missing, coordinates are invalid, timestamps are naive/invalid,
            or time window parameters are negative.
    """
    if member4_output is None:
        raise ValueError("member4_output must be provided and non-null")

    # 1. Validate numeric window & radius configuration
    if (
        default_radius_km is None
        or not isinstance(default_radius_km, (int, float, np.floating, np.integer))
        or not np.isfinite(default_radius_km)
        or default_radius_km <= 0.0
    ):
        raise ValueError(
            f"default_radius_km must be a finite number > 0, got {default_radius_km}"
        )

    if (
        buffer_km is None
        or not isinstance(buffer_km, (int, float, np.floating, np.integer))
        or not np.isfinite(buffer_km)
        or buffer_km < 0.0
    ):
        raise ValueError(
            f"buffer_km must be a finite non-negative number, got {buffer_km}"
        )

    if (
        before_minutes is None
        or not isinstance(before_minutes, (int, float, np.floating, np.integer))
        or not np.isfinite(before_minutes)
        or before_minutes < 0.0
    ):
        raise ValueError(
            f"before_minutes must be a finite non-negative number, got {before_minutes}"
        )

    if (
        after_minutes is None
        or not isinstance(after_minutes, (int, float, np.floating, np.integer))
        or not np.isfinite(after_minutes)
        or after_minutes < 0.0
    ):
        raise ValueError(
            f"after_minutes must be a finite non-negative number, got {after_minutes}"
        )

    # 2. Extract best candidate and ranked candidates
    if isinstance(member4_output, dict):
        best_candidate = member4_output.get("best_candidate")
        ranked_candidates = member4_output.get("ranked_candidates")
        best_time = member4_output.get("best_time")

        if best_candidate is None:
            if ranked_candidates and len(ranked_candidates) > 0:
                best_candidate = ranked_candidates[0]
            else:
                raise ValueError(
                    "member4_output must contain 'best_candidate' or non-empty 'ranked_candidates'"
                )

        if ranked_candidates is None:
            ranked_candidates = [best_candidate]
    else:
        # Passed candidate object directly
        best_candidate = member4_output
        ranked_candidates = [best_candidate]
        best_time = getattr(best_candidate, "timestamp", None)

    # 3. Extract region from best_candidate
    region = getattr(best_candidate, "region", None)
    if region is None and isinstance(best_candidate, dict):
        region = best_candidate.get("region")
    if region is None:
        region = best_candidate

    # 4. Extract coordinates from region
    lat, lon = _extract_region_coordinates(region)

    # 5. Extract timestamp from best_candidate
    origin_ts = _extract_candidate_timestamp(best_candidate, best_time)

    # 6. Resolve radius (Step 5 logic)
    radius_km = _resolve_radius_km(region, default_radius_km)

    # 7. Extract scores and metadata
    heuristic_score = getattr(best_candidate, "heuristic_score", None)
    if heuristic_score is None and isinstance(best_candidate, dict):
        heuristic_score = best_candidate.get("heuristic_score")

    coverage_level = getattr(region, "coverage_level", None)
    if coverage_level is None and isinstance(region, dict):
        coverage_level = region.get("coverage_level")

    # 8. Time window calculation
    start_time = origin_ts - pd.Timedelta(minutes=float(before_minutes))
    end_time = origin_ts + pd.Timedelta(minutes=float(after_minutes))

    # 9. Bounding box calculation using existing spatial utility
    eff_search_radius = radius_km + float(buffer_km)
    bbox = derive_bounding_box(
        center_latitude=lat,
        center_longitude=lon,
        radius_km=eff_search_radius,
    )

    # 10. Construct provider-independent AISSearchRequest
    search_request = AISSearchRequest(
        latitude=lat,
        longitude=lon,
        radius_km=radius_km,
        start_time=start_time,
        end_time=end_time,
        buffer_km=float(buffer_km),
        bounding_box=bbox,
        source_timestamp=origin_ts,
        candidate_rank=0,
    )

    # 11. Serialize candidate_origins list
    serialized_candidates = [
        _serialize_candidate(cand, default_radius_km)
        for cand in ranked_candidates
    ]

    # 12. Build standardized origin_data dictionary
    origin_dict = {
        "timestamp": origin_ts.isoformat(),
        "latitude": float(lat),
        "longitude": float(lon),
        "relative_score": (
            float(heuristic_score) if heuristic_score is not None else None
        ),
    }

    uncertainty_dict = {
        "centroid_latitude": float(lat),
        "centroid_longitude": float(lon),
        "radius_km": float(radius_km),
        "confidence_level": (
            float(coverage_level) if coverage_level is not None else None
        ),
        "min_latitude": float(bbox[0]),
        "max_latitude": float(bbox[1]),
        "min_longitude": float(bbox[2]),
        "max_longitude": float(bbox[3]),
    }

    standardized_origin_data: Dict[str, Any] = {
        "origin": origin_dict,
        "uncertainty": uncertainty_dict,
        "candidate_origins": serialized_candidates,
    }

    # 13. Spill observation handling (optional, non-fabricated)
    if spill_observation is not None:
        if not isinstance(spill_observation, dict):
            raise ValueError(
                f"spill_observation must be a dictionary, got {type(spill_observation)}"
            )
        obs_ts_raw = spill_observation.get("timestamp")
        obs_lat_raw = spill_observation.get("latitude")
        obs_lon_raw = spill_observation.get("longitude")

        if obs_ts_raw is not None:
            obs_ts = _validate_utc_timestamp(obs_ts_raw, "spill_observation.timestamp")
            obs_ts_iso = obs_ts.isoformat()
        else:
            obs_ts_iso = None

        if obs_lat_raw is not None:
            if (
                not isinstance(obs_lat_raw, (int, float, np.floating, np.integer))
                or not np.isfinite(obs_lat_raw)
                or not (LAT_MIN <= obs_lat_raw <= LAT_MAX)
            ):
                raise ValueError(
                    f"spill_observation latitude must be a finite number in [{LAT_MIN}, {LAT_MAX}], got {obs_lat_raw}"
                )
            obs_lat = float(obs_lat_raw)
        else:
            obs_lat = None

        if obs_lon_raw is not None:
            if (
                not isinstance(obs_lon_raw, (int, float, np.floating, np.integer))
                or not np.isfinite(obs_lon_raw)
                or not (LON_MIN <= obs_lon_raw <= LON_MAX)
            ):
                raise ValueError(
                    f"spill_observation longitude must be a finite number in [{LON_MIN}, {LON_MAX}], got {obs_lon_raw}"
                )
            obs_lon = float(obs_lon_raw)
        else:
            obs_lon = None

        standardized_origin_data["spill_observation"] = {
            "timestamp": obs_ts_iso,
            "latitude": obs_lat,
            "longitude": obs_lon,
        }

    return AISIntegrationResult(
        origin_data=standardized_origin_data,
        search_request=search_request,
    )
