"""Spatial Proximity Scoring for Oil Spill Attribution.

Implements distance decay models, closest-approach detection, and spatial
compatibility evaluation between vessel tracks and spill release envelopes.
"""

from __future__ import annotations

import math
from typing import Any, Optional, Tuple, Union

import numpy as np
import pandas as pd

from ais.filtering.spatial import EARTH_RADIUS_KM, haversine_distance_km


def calculate_spatial_score(
    min_distance_km: float,
    origin_radius_km: float = 0.0,
    max_distance_km: float = 25.0,
    decay_method: str = "linear",
) -> float:
    """Calculate normalized spatial compatibility score in [0.0, 1.0].

    Follows the approved piecewise-linear uncertainty plateau specification:
    - If min_distance_km <= origin_radius_km: score is 1.0 (inside uncertainty envelope).
    - If min_distance_km >= max_distance_km: score is 0.0 (beyond spatial cutoff).
    - Between origin_radius_km and max_distance_km: decays monotonically.

    Args:
        min_distance_km: Closest approach distance to origin center in kilometers (>= 0.0).
        origin_radius_km: Origin uncertainty radius in kilometers (>= 0.0).
        max_distance_km: Distance cutoff where score becomes 0.0 (> 0.0).
        decay_method: 'linear' (default) or 'gaussian'.

    Returns:
        float: Normalized spatial score in [0.0, 1.0].

    Raises:
        ValueError: If distance or radius parameters are negative, non-finite,
            or decay_method is invalid.
    """
    if min_distance_km is None or isinstance(min_distance_km, bool):
        raise ValueError("min_distance_km must be a non-boolean number")
    try:
        d_min = float(min_distance_km)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid min_distance_km: {min_distance_km}") from exc

    if not np.isfinite(d_min) or d_min < 0.0:
        raise ValueError(f"min_distance_km must be a finite non-negative number, got {d_min}")

    if origin_radius_km is None or isinstance(origin_radius_km, bool):
        raise ValueError("origin_radius_km must be a non-boolean number")
    try:
        r_orig = float(origin_radius_km)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid origin_radius_km: {origin_radius_km}") from exc

    if not np.isfinite(r_orig) or r_orig < 0.0:
        raise ValueError(f"origin_radius_km must be a finite non-negative number, got {r_orig}")

    if max_distance_km is None or isinstance(max_distance_km, bool):
        raise ValueError("max_distance_km must be a non-boolean number")
    try:
        d_max = float(max_distance_km)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid max_distance_km: {max_distance_km}") from exc

    if not np.isfinite(d_max) or d_max <= 0.0:
        raise ValueError(f"max_distance_km must be a finite positive number > 0.0, got {d_max}")

    # Boundary 1: Degenerate parameter setting where max_distance <= origin_radius
    if d_max <= r_orig:
        return 1.0 if d_min <= r_orig else 0.0

    # Boundary 2: Inside the uncertainty plateau
    if d_min <= r_orig:
        return 1.0

    # Boundary 3: Beyond spatial cutoff
    if d_min >= d_max:
        return 0.0

    # Intermediate decay
    span = d_max - r_orig
    excess = d_min - r_orig

    if decay_method == "linear":
        score = 1.0 - (excess / span)
    elif decay_method == "gaussian":
        sigma = span / 3.0
        score = math.exp(-0.5 * (excess / sigma) ** 2)
    else:
        raise ValueError(f"Unsupported spatial decay method: '{decay_method}'. Must be 'linear' or 'gaussian'.")

    return float(max(0.0, min(1.0, score)))


def find_closest_approach(
    df_vessel: pd.DataFrame,
    origin_lat: float,
    origin_lon: float,
    origin_timestamp: Optional[pd.Timestamp] = None,
) -> Tuple[float, pd.Series, bool]:
    """Find the point of closest approach (CPA) for a candidate vessel track.

    Evaluates across all valid observation fixes (actual and interpolated).
    Interpolated fixes MAY determine the closest approach distance and timestamp.

    If multiple fixes tie for the exact minimum distance:
    1. Selects the fix minimizing |timestamp - origin_timestamp|.
    2. If still tied, selects the fix with the earliest timestamp.

    Args:
        df_vessel: DataFrame containing vessel observations.
        origin_lat: Origin center latitude in degrees.
        origin_lon: Origin center longitude in degrees.
        origin_timestamp: Optional origin release timestamp for tie-breaking.

    Returns:
        Tuple of:
            - min_distance_km (float): Closest approach distance.
            - cpa_row (pd.Series): The observation row corresponding to CPA.
            - is_interpolated (bool): True if the CPA fix was an interpolated point.

    Raises:
        ValueError: If df_vessel is empty or required coordinate columns are missing.
    """
    if df_vessel.empty:
        raise ValueError("Cannot find closest approach on an empty vessel DataFrame")

    df = df_vessel.copy()

    # Calculate or use distance_km
    if "distance_km" not in df.columns:
        if "latitude" not in df.columns or "longitude" not in df.columns:
            raise ValueError("Vessel DataFrame must contain 'latitude' and 'longitude' or 'distance_km'")
        df["distance_km"] = haversine_distance_km(
            df["latitude"].values,
            df["longitude"].values,
            origin_lat,
            origin_lon,
        )

    # Find minimum distance
    min_dist = float(df["distance_km"].min())

    # Get candidates that match min_dist within float tolerance
    candidates = df[np.isclose(df["distance_km"], min_dist, atol=1e-7, rtol=1e-7)]

    if len(candidates) == 1:
        cpa_row = candidates.iloc[0]
    else:
        # Tie-break by closeness to origin_timestamp if available
        if origin_timestamp is not None and "timestamp" in candidates.columns:
            ts_origin = pd.Timestamp(origin_timestamp)
            cand_ts = pd.to_datetime(candidates["timestamp"], utc=True)
            time_diffs = (cand_ts - ts_origin).abs()
            min_td = time_diffs.min()
            sub_cands = candidates[time_diffs == min_td]
            # If still tied, take earliest timestamp
            cpa_row = sub_cands.sort_values(by="timestamp", ascending=True).iloc[0]
        else:
            # Sort by timestamp ascending if available, or first row
            if "timestamp" in candidates.columns:
                cpa_row = candidates.sort_values(by="timestamp", ascending=True).iloc[0]
            else:
                cpa_row = candidates.iloc[0]

    # Check whether CPA fix was interpolated
    is_interp = False
    if "is_interpolated" in cpa_row.index:
        val = cpa_row["is_interpolated"]
        if pd.notna(val) and not isinstance(val, (int, float, np.integer, np.floating)) and isinstance(val, bool):
            is_interp = bool(val)
        elif pd.notna(val):
            is_interp = bool(val)

    return min_dist, cpa_row, is_interp
