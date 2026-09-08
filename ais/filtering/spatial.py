"""AIS Spatial Filtering Implementation.

Provides Earth-aware great-circle spatial filtering, bounding-box filtering
with anti-meridian crossing support, Member 4 spill origin uncertainty envelope
integration, and polymorphic trajectory segment filtering.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np
import pandas as pd

from ais.filtering.config import SpatialFilterConfig

# Earth volumetric mean radius according to IUGG / WGS84: 6371.0088 km
# Exactly consistent with ais.preprocessing.kinematics (6371.0088 km / 1.852 km/NM)
EARTH_RADIUS_KM: float = 6371.0088

# Canonical coordinate bounds
LAT_MIN: float = -90.0
LAT_MAX: float = 90.0
LON_MIN: float = -180.0
LON_MAX: float = 180.0


@dataclass(frozen=True)
class SpatialFilterReport:
    """Audit metrics and summary statistics for AIS spatial filtering.

    Attributes:
        total_input_records: Total AIS observation rows passed to the filter.
        matched_records: Number of observation records within the spatial search region.
        unique_vessels_in: Distinct MMSIs present in the input.
        unique_vessels_matched: Distinct candidate MMSIs retained.
        center_latitude: Latitude of the spatial search center in degrees.
        center_longitude: Longitude of the spatial search center in degrees.
        base_radius_km: Base search radius in kilometers (e.g. from uncertainty.radius_km).
        buffer_km: Additional empirical buffer added to the radius.
        effective_radius_km: Total effective search radius (base_radius_km + buffer_km).
        segments_matched: Count of distinct trajectory segments with matching observations.
    """

    total_input_records: int
    matched_records: int
    unique_vessels_in: int
    unique_vessels_matched: int
    center_latitude: float
    center_longitude: float
    base_radius_km: float
    buffer_km: float
    effective_radius_km: float
    segments_matched: int


@dataclass
class SpatialFilterResult:
    """Result container for AIS spatial filtering.

    Attributes:
        data: Filtered DataFrame with preserved AIS attributes and 'distance_km'.
        report: SpatialFilterReport audit summary.
    """

    data: pd.DataFrame
    report: SpatialFilterReport

    def to_dataframe(self) -> pd.DataFrame:
        """Return a copy of the filtered DataFrame."""
        return self.data.copy()

    @property
    def candidate_mmsis(self) -> Set[int]:
        """Set of distinct vessel MMSIs that qualified within the spatial region."""
        if "mmsi" in self.data.columns and not self.data.empty:
            return set(self.data["mmsi"].astype(int).unique())
        return set()

    @property
    def candidate_segment_ids(self) -> Set[str]:
        """Set of distinct trajectory segment IDs that qualified."""
        if "trajectory_segment_id" in self.data.columns and not self.data.empty:
            return set(
                self.data["trajectory_segment_id"].dropna().astype(str).unique()
            )
        return set()


def haversine_distance_km(
    lat1: Union[float, np.ndarray, pd.Series],
    lon1: Union[float, np.ndarray, pd.Series],
    lat2: Union[float, np.ndarray, pd.Series],
    lon2: Union[float, np.ndarray, pd.Series],
) -> Union[float, np.ndarray, pd.Series]:
    """Calculate great-circle distance between coordinate pairs in kilometers.

    Uses the spherical Haversine formula assuming Earth volumetric mean radius
    R = 6371.0088 km (IUGG / WGS84 standard).

    Args:
        lat1: Latitude of starting point(s) in decimal degrees [-90, 90].
        lon1: Longitude of starting point(s) in decimal degrees [-180, 180].
        lat2: Latitude of destination point(s) in decimal degrees [-90, 90].
        lon2: Longitude of destination point(s) in decimal degrees [-180, 180].

    Returns:
        Great-circle distance in kilometers (float, ndarray, or pd.Series).
        Returns NaN if any coordinate input is NaN.
    """
    r_lat1 = np.radians(lat1)
    r_lon1 = np.radians(lon1)
    r_lat2 = np.radians(lat2)
    r_lon2 = np.radians(lon2)

    dlat = r_lat2 - r_lat1
    dlon = r_lon2 - r_lon1

    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(r_lat1) * np.cos(r_lat2) * np.sin(dlon / 2.0) ** 2
    )
    # Clip to [0.0, 1.0] to safeguard against numerical precision errors
    a = np.clip(a, 0.0, 1.0)
    c = 2.0 * np.arcsin(np.sqrt(a))

    return EARTH_RADIUS_KM * c


def _validate_center_coordinates(latitude: float, longitude: float) -> None:
    """Validate search center coordinates.

    Raises:
        ValueError: If latitude or longitude is null, non-numeric, non-finite,
            or outside WGS84 bounds.
    """
    if latitude is None or not np.isfinite(latitude) or not (LAT_MIN <= latitude <= LAT_MAX):
        raise ValueError(
            f"Center latitude must be a finite number in [{LAT_MIN}, {LAT_MAX}], got {latitude}"
        )
    if longitude is None or not np.isfinite(longitude) or not (LON_MIN <= longitude <= LON_MAX):
        raise ValueError(
            f"Center longitude must be a finite number in [{LON_MIN}, {LON_MAX}], got {longitude}"
        )


def _validate_ais_coordinates(df: pd.DataFrame) -> None:
    """Validate that AIS DataFrame coordinates are valid and physically bounded.

    Raises:
        ValueError: If required coordinate columns are missing, contain NaNs,
            non-finite numbers, or exceed WGS84 coordinate bounds.
    """
    if "latitude" not in df.columns or "longitude" not in df.columns:
        raise ValueError(
            "AIS DataFrame must contain 'latitude' and 'longitude' columns"
        )

    lats = pd.to_numeric(df["latitude"], errors="coerce")
    lons = pd.to_numeric(df["longitude"], errors="coerce")

    if lats.isna().any() or lons.isna().any() or not np.isfinite(lats).all() or not np.isfinite(lons).all():
        raise ValueError(
            "AIS DataFrame contains null, non-numeric, or non-finite latitude/longitude coordinates"
        )

    invalid_lat = (lats < LAT_MIN) | (lats > LAT_MAX)
    if invalid_lat.any():
        raise ValueError(
            f"AIS DataFrame contains latitude coordinates outside [{LAT_MIN}, {LAT_MAX}]"
        )

    invalid_lon = (lons < LON_MIN) | (lons > LON_MAX)
    if invalid_lon.any():
        raise ValueError(
            f"AIS DataFrame contains longitude coordinates outside [{LON_MIN}, {LON_MAX}]"
        )


def _extract_dataframe(data: Any) -> pd.DataFrame:
    """Extract a pandas DataFrame from supported polymorphic inputs.

    Supports:
        - pd.DataFrame
        - TrajectoryResult (from AIS-04)
        - InterpolationResult (from AIS-05)
        - TrajectorySegment / InterpolatedSegment
        - List of TrajectorySegment / InterpolatedSegment
    """
    if isinstance(data, pd.DataFrame):
        return data.copy()
    if hasattr(data, "to_dataframe") and callable(data.to_dataframe):
        return data.to_dataframe()
    if hasattr(data, "_dataframe") and isinstance(data._dataframe, pd.DataFrame):
        return data._dataframe.copy()
    if isinstance(data, list):
        dfs = [
            item.data
            for item in data
            if hasattr(item, "data") and isinstance(item.data, pd.DataFrame)
        ]
        if dfs:
            return pd.concat(dfs, ignore_index=True)
        return pd.DataFrame()
    if hasattr(data, "data") and isinstance(data.data, pd.DataFrame):
        return data.data.copy()

    raise TypeError(
        f"Unsupported data type for spatial filtering: {type(data)}. "
        "Expected pd.DataFrame, TrajectoryResult, InterpolationResult, TrajectorySegment, or list of segments."
    )


def derive_bounding_box(
    center_latitude: float,
    center_longitude: float,
    radius_km: float,
) -> Tuple[float, float, float, float]:
    """Derive conservative geographic bounding box around a center and radius.

    Correctly handles polar limits and spherical anti-meridian (+/-180 deg) wrapping.

    Args:
        center_latitude: Latitude in [-90, 90].
        center_longitude: Longitude in [-180, 180].
        radius_km: Search radius in kilometers.

    Returns:
        Tuple of (min_latitude, max_latitude, min_longitude, max_longitude).
        When the bounding box spans the anti-meridian, min_longitude > max_longitude.
    """
    _validate_center_coordinates(center_latitude, center_longitude)
    if not np.isfinite(radius_km) or radius_km < 0.0:
        raise ValueError(
            f"radius_km must be a finite non-negative number, got {radius_km}"
        )

    # Angular distance in degrees for latitude: (radius_km / R) * (180 / pi)
    dlat_deg = (radius_km / EARTH_RADIUS_KM) * (180.0 / np.pi)

    min_lat = max(LAT_MIN, center_latitude - dlat_deg)
    max_lat = min(LAT_MAX, center_latitude + dlat_deg)

    # Longitude delta depends on latitude
    max_abs_lat = max(abs(min_lat), abs(max_lat))
    if max_abs_lat >= 89.9:
        # Near poles, longitude spans full globe
        return min_lat, max_lat, LON_MIN, LON_MAX

    cos_lat = np.cos(np.radians(max_abs_lat))
    dlon_deg = dlat_deg / cos_lat if cos_lat > 1e-6 else 180.0

    if dlon_deg >= 180.0:
        return min_lat, max_lat, LON_MIN, LON_MAX

    raw_min_lon = center_longitude - dlon_deg
    raw_max_lon = center_longitude + dlon_deg

    # Normalize into [-180, 180]
    norm_min_lon = (raw_min_lon + 180.0) % 360.0 - 180.0
    norm_max_lon = (raw_max_lon + 180.0) % 360.0 - 180.0

    # Preserve exact +/-180 boundary values
    if abs(raw_min_lon - (-180.0)) < 1e-9:
        norm_min_lon = -180.0
    if abs(raw_max_lon - 180.0) < 1e-9:
        norm_max_lon = 180.0

    # If raw spans across the anti-meridian (e.g. center=179, dlon=3 -> raw_max=182 -> norm_max=-178)
    # Then norm_min_lon > norm_max_lon, which signals anti-meridian crossing
    return min_lat, max_lat, float(norm_min_lon), float(norm_max_lon)


def filter_by_bounding_box(
    data: Union[pd.DataFrame, Any],
    min_latitude: float,
    max_latitude: float,
    min_longitude: float,
    max_longitude: float,
) -> pd.DataFrame:
    """Filter AIS observations within a geographic bounding box with anti-meridian support.

    Handles both standard boxes (min_longitude <= max_longitude) and anti-meridian
    spanning boxes (min_longitude > max_longitude, e.g. spanning 175° to -175°).

    Args:
        data: Input DataFrame or polymorphic trajectory object.
        min_latitude: Minimum latitude in [-90.0, 90.0].
        max_latitude: Maximum latitude in [-90.0, 90.0].
        min_longitude: Minimum longitude in [-180.0, 180.0].
        max_longitude: Maximum longitude in [-180.0, 180.0].

    Returns:
        Filtered copy of DataFrame with preserved columns. Does not mutate input.

    Raises:
        ValueError: If coordinate bounds are invalid or AIS data has invalid coordinates.
    """
    if not np.isfinite(min_latitude) or not (LAT_MIN <= min_latitude <= LAT_MAX):
        raise ValueError(
            f"min_latitude must be a finite number in [{LAT_MIN}, {LAT_MAX}], got {min_latitude}"
        )
    if not np.isfinite(max_latitude) or not (LAT_MIN <= max_latitude <= LAT_MAX):
        raise ValueError(
            f"max_latitude must be a finite number in [{LAT_MIN}, {LAT_MAX}], got {max_latitude}"
        )
    if min_latitude > max_latitude:
        raise ValueError(
            f"min_latitude ({min_latitude}) cannot be greater than max_latitude ({max_latitude})"
        )

    if not np.isfinite(min_longitude) or not (LON_MIN <= min_longitude <= LON_MAX):
        raise ValueError(
            f"min_longitude must be a finite number in [{LON_MIN}, {LON_MAX}], got {min_longitude}"
        )
    if not np.isfinite(max_longitude) or not (LON_MIN <= max_longitude <= LON_MAX):
        raise ValueError(
            f"max_longitude must be a finite number in [{LON_MIN}, {LON_MAX}], got {max_longitude}"
        )

    df = _extract_dataframe(data)
    if df.empty:
        return df.copy()

    _validate_ais_coordinates(df)

    lat_mask = (df["latitude"] >= min_latitude) & (df["latitude"] <= max_latitude)

    # Anti-meridian logic:
    # If min_longitude <= max_longitude: standard longitude interval [min_lon, max_lon]
    # If min_longitude > max_longitude: interval wraps across +/-180°, so
    # a point is inside if lon >= min_longitude OR lon <= max_longitude.
    if min_longitude <= max_longitude:
        lon_mask = (df["longitude"] >= min_longitude) & (
            df["longitude"] <= max_longitude
        )
    else:
        lon_mask = (df["longitude"] >= min_longitude) | (
            df["longitude"] <= max_longitude
        )

    matched = df[lat_mask & lon_mask].copy()
    return matched.reset_index(drop=True)


def filter_by_radius(
    data: Union[pd.DataFrame, Any],
    center_latitude: float,
    center_longitude: float,
    radius_km: float,
    buffer_km: float = 0.0,
    use_bounding_box: bool = True,
) -> pd.DataFrame:
    """Filter AIS observations within radius_km + buffer_km of a center coordinate.

    Calculates great-circle distance using the spherical Haversine formula.
    Preserves all original columns and adds 'distance_km'.
    Observations exactly on the boundary (distance_km == effective_radius_km) are included.

    Args:
        data: Input DataFrame or polymorphic trajectory object.
        center_latitude: Latitude of center fix in decimal degrees [-90, 90].
        center_longitude: Longitude of center fix in decimal degrees [-180, 180].
        radius_km: Base spatial search radius in kilometers. Must be a finite non-negative number.
        buffer_km: Optional additional empirical buffer in kilometers. Must be a finite non-negative number.
        use_bounding_box: If True (default), applies a coarse bounding box pre-filter
            to discard distant points before computing Haversine distance.

    Returns:
        pd.DataFrame containing observations within the search radius with added 'distance_km'.
        Does not mutate the caller's input DataFrame.

    Raises:
        ValueError: If center coordinates or radii are invalid or non-finite,
            or if AIS coordinates are out of bounds, NaN, or non-finite.
    """
    _validate_center_coordinates(center_latitude, center_longitude)

    if not np.isfinite(radius_km) or radius_km < 0.0:
        raise ValueError(
            f"radius_km must be a finite non-negative number, got {radius_km}"
        )
    if not np.isfinite(buffer_km) or buffer_km < 0.0:
        raise ValueError(
            f"buffer_km must be a finite non-negative number, got {buffer_km}"
        )

    df = _extract_dataframe(data)

    if df.empty:
        empty_res = df.copy()
        if "distance_km" not in empty_res.columns:
            empty_res["distance_km"] = pd.Series(dtype="float64")
        return empty_res

    _validate_ais_coordinates(df)

    effective_radius_km = float(radius_km + buffer_km)

    # 1. Coarse Bounding Box Filter for Performance (if enabled)
    # Only applicable when effective radius does not cover the entire globe
    if use_bounding_box and effective_radius_km < 20000.0:
        bbox_min_lat, bbox_max_lat, bbox_min_lon, bbox_max_lon = derive_bounding_box(
            center_latitude=center_latitude,
            center_longitude=center_longitude,
            radius_km=effective_radius_km,
        )
        candidates = filter_by_bounding_box(
            data=df,
            min_latitude=bbox_min_lat,
            max_latitude=bbox_max_lat,
            min_longitude=bbox_min_lon,
            max_longitude=bbox_max_lon,
        )
    else:
        candidates = df.copy()

    if candidates.empty:
        empty_res = candidates.copy()
        empty_res["distance_km"] = pd.Series(dtype="float64")
        return empty_res

    # 2. Exact Haversine Great-Circle Distance Calculation
    distances = haversine_distance_km(
        lat1=center_latitude,
        lon1=center_longitude,
        lat2=candidates["latitude"].values,
        lon2=candidates["longitude"].values,
    )

    # Boundary rule: inclusive (distance <= effective_radius_km)
    mask = distances <= effective_radius_km
    matched = candidates[mask].copy()
    matched["distance_km"] = distances[mask]

    return matched.reset_index(drop=True)


def filter_by_origin_uncertainty(
    data: Union[pd.DataFrame, Any],
    origin_data: Dict[str, Any],
    config: Optional[SpatialFilterConfig] = None,
    buffer_km: Optional[float] = None,
) -> pd.DataFrame:
    """Filter AIS data using Member 4 origin and uncertainty handoff data contract.

    Extracts:
        - Center: uncertainty.centroid_latitude, uncertainty.centroid_longitude
          (fallback to origin.latitude, origin.longitude if centroid is absent)
        - Base radius: uncertainty.radius_km (fallback to config.radius_km if absent)
        - Effective radius: uncertainty.radius_km + buffer_km

    Authoritative Spatial Constraint:
        The authoritative spatial boundary is strictly governed by the Earth-aware
        Haversine distance from the uncertainty centroid:
        R_search = uncertainty.radius_km + buffer_km.
        Member 4's bounding-box values (min_latitude, max_latitude, min_longitude, max_longitude)
        in 'uncertainty' serve as optional metadata/reference only. They are NOT used to
        restrict or truncate the search circle, ensuring that no observation falling within
        the authoritative Haversine uncertainty radius can ever be excluded.

    Important Scientific Semantics:
        - origin.relative_score is a heuristic ranking weight, NOT a calibrated probability.
        - uncertainty.radius_km is an empirical spatial uncertainty radius, NOT a probability radius.
        - confidence_level is documented but NOT treated as a probability.

    Args:
        data: Input DataFrame or polymorphic trajectory object.
        origin_data: Dictionary conforming to Member 4 -> Member 5 handoff contract.
        config: Optional SpatialFilterConfig instance.
        buffer_km: Optional override for buffer_km.

    Returns:
        pd.DataFrame containing matching observations with 'distance_km'.
    """
    if config is None:
        config = SpatialFilterConfig()

    uncertainty = origin_data.get("uncertainty", {})
    origin = origin_data.get("origin", {})

    # 1. Resolve search center coordinates using explicit 'is not None' checks
    # (0.0 is a valid geographic coordinate and must not be treated as falsy)
    center_lat = uncertainty.get("centroid_latitude")
    if center_lat is None:
        center_lat = origin.get("latitude")

    center_lon = uncertainty.get("centroid_longitude")
    if center_lon is None:
        center_lon = origin.get("longitude")

    if center_lat is None or center_lon is None:
        raise ValueError(
            "origin_data must contain centroid_latitude/longitude in 'uncertainty' "
            "or latitude/longitude in 'origin'"
        )

    # 2. Resolve base radius and buffer with explicit 'is not None' checks
    base_radius = uncertainty.get("radius_km")
    if base_radius is None:
        base_radius = config.radius_km

    active_buffer = (
        buffer_km if buffer_km is not None else config.buffer_km
    )

    return filter_by_radius(
        data=data,
        center_latitude=float(center_lat),
        center_longitude=float(center_lon),
        radius_km=float(base_radius),
        buffer_km=float(active_buffer),
        use_bounding_box=config.use_bounding_box,
    )


def filter_trajectories_spatially(
    data: Union[pd.DataFrame, Any],
    center_latitude: float,
    center_longitude: float,
    radius_km: float,
    buffer_km: float = 0.0,
    retain_full_segments: bool = False,
    use_bounding_box: bool = True,
) -> pd.DataFrame:
    """Filter vessel trajectories spatially against a search circle.

    Args:
        data: Input AIS DataFrame, TrajectoryResult, or InterpolationResult.
        center_latitude: Latitude of search center.
        center_longitude: Longitude of search center.
        radius_km: Base search radius in km.
        buffer_km: Optional additional search buffer in km.
        retain_full_segments: If False (default), returns only the specific
            observations falling within R_search.
            If True, if ANY observation in a continuous trajectory segment
            falls within R_search, ALL observations of that qualifying segment
            are retained (with distance_km calculated to the search center).
            NOTE ON FALLBACK: When 'trajectory_segment_id' is absent from the dataset
            (e.g. raw or unsegmented observations), an MMSI-level fallback is applied,
            retaining all observations for an MMSI if any observation matches.
        use_bounding_box: If True, applies coarse bounding box optimization.

    Returns:
        pd.DataFrame containing qualifying observations with 'distance_km'.
    """
    df = _extract_dataframe(data)
    if df.empty:
        empty_res = df.copy()
        if "distance_km" not in empty_res.columns:
            empty_res["distance_km"] = pd.Series(dtype="float64")
        return empty_res

    # Find observations inside the search radius
    matched_obs = filter_by_radius(
        data=df,
        center_latitude=center_latitude,
        center_longitude=center_longitude,
        radius_km=radius_km,
        buffer_km=buffer_km,
        use_bounding_box=use_bounding_box,
    )

    if not retain_full_segments or matched_obs.empty:
        return matched_obs

    # Retain all observations belonging to qualifying segments
    if "trajectory_segment_id" in df.columns:
        qualifying_segment_ids = set(
            matched_obs["trajectory_segment_id"].dropna().unique()
        )
        mask = df["trajectory_segment_id"].isin(qualifying_segment_ids)
    else:
        # Documented MMSI-level fallback: when trajectory_segment_id is absent
        # (e.g. raw or unsegmented AIS data), qualify all observations belonging
        # to an MMSI that had at least one observation within R_search.
        qualifying_mmsis = set(matched_obs["mmsi"].unique())
        mask = df["mmsi"].isin(qualifying_mmsis)

    retained_df = df[mask].copy().reset_index(drop=True)

    # Compute distance_km for all retained rows
    retained_df["distance_km"] = haversine_distance_km(
        lat1=center_latitude,
        lon1=center_longitude,
        lat2=retained_df["latitude"].values,
        lon2=retained_df["longitude"].values,
    )

    return retained_df


def filter_spatial(
    data: Union[pd.DataFrame, Any],
    config: Optional[SpatialFilterConfig] = None,
    center_latitude: Optional[float] = None,
    center_longitude: Optional[float] = None,
    origin_data: Optional[Dict[str, Any]] = None,
    retain_full_segments: bool = False,
) -> SpatialFilterResult:
    """High-level spatial filtering orchestrator returning a SpatialFilterResult.

    Accepts explicit coordinates or Member 4 origin_data handoff dictionary.

    Args:
        data: Input DataFrame or polymorphic trajectory object.
        config: Optional SpatialFilterConfig.
        center_latitude: Optional explicit search center latitude.
        center_longitude: Optional explicit search center longitude.
        origin_data: Optional Member 4 origin/uncertainty dictionary.
        retain_full_segments: If True, retains all points of qualifying segments.

    Returns:
        SpatialFilterResult containing filtered DataFrame and SpatialFilterReport.
    """
    if config is None:
        config = SpatialFilterConfig()

    df_in = _extract_dataframe(data)
    total_input = len(df_in)
    unique_vessels_in = int(df_in["mmsi"].nunique()) if not df_in.empty and "mmsi" in df_in.columns else 0

    # Determine center and radius using explicit 'is not None' checks
    # (0.0 is a valid geographic coordinate and must not be treated as falsy)
    if origin_data is not None:
        uncertainty = origin_data.get("uncertainty", {})
        origin = origin_data.get("origin", {})

        c_lat = uncertainty.get("centroid_latitude")
        if c_lat is None:
            c_lat = origin.get("latitude")
        if c_lat is None and center_latitude is not None:
            c_lat = center_latitude

        c_lon = uncertainty.get("centroid_longitude")
        if c_lon is None:
            c_lon = origin.get("longitude")
        if c_lon is None and center_longitude is not None:
            c_lon = center_longitude

        if c_lat is None or c_lon is None:
            raise ValueError(
                "origin_data must contain centroid coordinates in 'uncertainty' "
                "or latitude/longitude in 'origin', or explicit coordinates must be provided"
            )

        center_lat = float(c_lat)
        center_lon = float(c_lon)

        u_rad = uncertainty.get("radius_km")
        base_radius = float(u_rad) if u_rad is not None else float(config.radius_km)
    else:
        if center_latitude is None or center_longitude is None:
            raise ValueError(
                "Either (center_latitude, center_longitude) or origin_data must be provided"
            )
        center_lat = float(center_latitude)
        center_lon = float(center_longitude)
        base_radius = float(config.radius_km)

    effective_radius = float(base_radius + config.buffer_km)

    filtered_df = filter_trajectories_spatially(
        data=df_in,
        center_latitude=center_lat,
        center_longitude=center_lon,
        radius_km=base_radius,
        buffer_km=config.buffer_km,
        retain_full_segments=retain_full_segments,
        use_bounding_box=config.use_bounding_box,
    )

    matched_records = len(filtered_df)
    unique_vessels_matched = (
        int(filtered_df["mmsi"].nunique())
        if not filtered_df.empty and "mmsi" in filtered_df.columns
        else 0
    )
    segments_matched = (
        int(filtered_df["trajectory_segment_id"].dropna().nunique())
        if not filtered_df.empty and "trajectory_segment_id" in filtered_df.columns
        else 0
    )

    report = SpatialFilterReport(
        total_input_records=total_input,
        matched_records=matched_records,
        unique_vessels_in=unique_vessels_in,
        unique_vessels_matched=unique_vessels_matched,
        center_latitude=center_lat,
        center_longitude=center_lon,
        base_radius_km=base_radius,
        buffer_km=config.buffer_km,
        effective_radius_km=effective_radius,
        segments_matched=segments_matched,
    )

    return SpatialFilterResult(
        data=filtered_df,
        report=report,
    )
