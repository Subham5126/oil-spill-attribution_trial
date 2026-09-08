"""Temporal Compatibility Scoring for Oil Spill Attribution.

Implements temporal alignment evaluation, CPA timestamp resolution, and decay
models assessing coincidence between vessel tracks and estimated release windows.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from attribution.scoring.spatial import find_closest_approach


def calculate_temporal_score(
    time_diff_seconds: float,
    acceptable_window_seconds: float = 1800.0,
    max_time_diff_seconds: float = 7200.0,
    decay_method: str = "linear",
) -> float:
    """Calculate normalized temporal compatibility score in [0.0, 1.0].

    Follows the approved piecewise-linear plateau specification:
    - If time_diff_seconds <= acceptable_window_seconds: score is 1.0.
    - If time_diff_seconds >= max_time_diff_seconds: score is 0.0.
    - Between acceptable_window_seconds and max_time_diff_seconds: decays monotonically.

    Args:
        time_diff_seconds: Absolute time difference in seconds between t_CPA and
            origin timestamp (|t_CPA - t_origin| >= 0.0).
        acceptable_window_seconds: Tolerance plateau window in seconds (default 1800s / 30m).
        max_time_diff_seconds: Upper cutoff window in seconds (default 7200s / 2h).
        decay_method: 'linear' (default) or 'gaussian'.

    Returns:
        float: Normalized temporal score in [0.0, 1.0].

    Raises:
        ValueError: If time parameters are negative, non-finite, or decay_method is invalid.
    """
    if time_diff_seconds is None or isinstance(time_diff_seconds, bool):
        raise ValueError("time_diff_seconds must be a non-boolean number")
    try:
        dt = float(time_diff_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid time_diff_seconds: {time_diff_seconds}") from exc

    if not np.isfinite(dt) or dt < 0.0:
        raise ValueError(f"time_diff_seconds must be a finite non-negative number, got {dt}")

    if acceptable_window_seconds is None or isinstance(acceptable_window_seconds, bool):
        raise ValueError("acceptable_window_seconds must be a non-boolean number")
    try:
        w_acc = float(acceptable_window_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid acceptable_window_seconds: {acceptable_window_seconds}") from exc

    if not np.isfinite(w_acc) or w_acc < 0.0:
        raise ValueError(f"acceptable_window_seconds must be a finite non-negative number, got {w_acc}")

    if max_time_diff_seconds is None or isinstance(max_time_diff_seconds, bool):
        raise ValueError("max_time_diff_seconds must be a non-boolean number")
    try:
        w_max = float(max_time_diff_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid max_time_diff_seconds: {max_time_diff_seconds}") from exc

    if not np.isfinite(w_max):
        raise ValueError(f"max_time_diff_seconds must be a finite number, got {w_max}")

    if w_max < w_acc:
        raise ValueError(f"max_time_diff_seconds ({w_max}) must be >= acceptable_window_seconds ({w_acc})")

    # Boundary 1: Degenerate setting where max_window <= acceptable_window
    if w_max <= w_acc:
        return 1.0 if dt <= w_acc else 0.0

    # Boundary 2: Within acceptable tolerance plateau
    if dt <= w_acc:
        return 1.0

    # Boundary 3: Beyond maximum cutoff window
    if dt >= w_max:
        return 0.0

    # Intermediate decay
    span = w_max - w_acc
    excess = dt - w_acc

    if decay_method == "linear":
        score = 1.0 - (excess / span)
    elif decay_method == "gaussian":
        sigma = span / 3.0
        score = math.exp(-0.5 * (excess / sigma) ** 2)
    else:
        raise ValueError(f"Unsupported temporal decay method: '{decay_method}'. Must be 'linear' or 'gaussian'.")

    return float(max(0.0, min(1.0, score)))


def resolve_time_of_closest_approach(
    df_vessel: pd.DataFrame,
    origin_timestamp: pd.Timestamp,
    origin_lat: float,
    origin_lon: float,
) -> Tuple[pd.Timestamp, float, bool]:
    """Resolve the closest approach timestamp (t_CPA) and time offset from origin.

    Evaluates across all valid observation fixes. Interpolated fixes MAY determine
    t_CPA and closest approach distance.

    Args:
        df_vessel: DataFrame containing candidate vessel observations.
        origin_timestamp: Reference spill release timestamp (UTC-aware).
        origin_lat: Origin center latitude.
        origin_lon: Origin center longitude.

    Returns:
        Tuple of:
            - t_cpa (pd.Timestamp): UTC timestamp of closest approach.
            - time_diff_seconds (float): Absolute difference |t_CPA - origin_timestamp| in seconds.
            - is_interpolated (bool): True if the CPA fix was an interpolated point.

    Raises:
        ValueError: If df_vessel is empty or timestamps are invalid.
    """
    if df_vessel.empty:
        raise ValueError("Cannot resolve t_CPA on an empty vessel DataFrame")

    _, cpa_row, is_interp = find_closest_approach(
        df_vessel=df_vessel,
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        origin_timestamp=origin_timestamp,
    )

    if "timestamp" not in cpa_row.index or pd.isna(cpa_row["timestamp"]):
        raise ValueError("CPA observation row is missing 'timestamp'")

    t_cpa = pd.Timestamp(cpa_row["timestamp"])
    if t_cpa.tzinfo is None:
        raise ValueError(f"CPA timestamp must be timezone-aware (UTC), got naive: {t_cpa}")
    t_cpa = t_cpa.tz_convert("UTC")

    t_origin = pd.Timestamp(origin_timestamp)
    if t_origin.tzinfo is None:
        raise ValueError(f"Origin timestamp must be timezone-aware (UTC), got naive: {t_origin}")
    t_origin = t_origin.tz_convert("UTC")

    time_diff_seconds = float(abs((t_cpa - t_origin).total_seconds()))

    return t_cpa, time_diff_seconds, is_interp
