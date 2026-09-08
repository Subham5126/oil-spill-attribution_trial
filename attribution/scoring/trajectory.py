"""Trajectory and Kinematic Behaviour Scoring for Oil Spill Attribution.

Implements directional alignment against explicit drift vectors, geometric track
intersections, speed compatibility, loitering detection, and telemetry continuity.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ais.filtering.spatial import EARTH_RADIUS_KM, haversine_distance_km
from attribution.scoring.config import AttributionScoringConfig


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate geodetic forward azimuth (bearing) in degrees [0.0, 360.0).

    Args:
        lat1, lon1: Origin coordinates in decimal degrees.
        lat2, lon2: Destination coordinates in decimal degrees.

    Returns:
        float: Initial bearing in degrees from true North [0.0, 360.0).
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlam = math.radians(lon2 - lon1)

    y = math.sin(dlam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)

    bearing_deg = math.degrees(math.atan2(y, x))
    return float((bearing_deg + 360.0) % 360.0)


def determine_vessel_direction(
    df_vessel: pd.DataFrame,
    cpa_timestamp: Optional[pd.Timestamp] = None,
) -> Optional[float]:
    """Determine the effective movement direction of a vessel in degrees [0.0, 360.0).

    Follows the approved deterministic hierarchy:
    1. Telemetry Course Over Ground (COG) at or near CPA if valid, finite, and SOG >= 0.5 kn.
    2. Derived forward azimuth (bearing fallback) from chronological position fixes
       if at least 2 distinct observations separated by > 10 meters exist.
    3. Returns None if vessel is observed only once (N=1) or points are co-located.

    Args:
        df_vessel: DataFrame containing vessel observations.
        cpa_timestamp: Optional CPA timestamp to locate proximate COG.

    Returns:
        Optional[float]: Direction in degrees [0.0, 360.0), or None if uncomputable.
    """
    if df_vessel.empty or len(df_vessel) == 0:
        return None

    df_sorted = df_vessel.sort_values(by="timestamp", ascending=True)

    # 1. COG near CPA check
    if "cog" in df_sorted.columns:
        valid_cog_df = df_sorted[df_sorted["cog"].notna()]
        if not valid_cog_df.empty:
            # Check SOG if available to ensure vessel is underway
            underway_mask = pd.Series(True, index=valid_cog_df.index)
            if "sog" in valid_cog_df.columns:
                underway_mask = valid_cog_df["sog"].isna() | (valid_cog_df["sog"] >= 0.5)

            candidates = valid_cog_df[underway_mask]
            if not candidates.empty:
                if cpa_timestamp is not None and "timestamp" in candidates.columns:
                    cpa_ts = pd.to_datetime(cpa_timestamp, utc=True)
                    row_ts = pd.to_datetime(candidates["timestamp"], utc=True)
                    best_idx = (row_ts - cpa_ts).abs().idxmin()
                    cog_val = candidates.loc[best_idx, "cog"]
                else:
                    cog_val = candidates["cog"].iloc[0]

                if isinstance(cog_val, (int, float, np.integer, np.floating)) and np.isfinite(cog_val):
                    val = float(cog_val)
                    if 0.0 <= val < 360.0:
                        return val
                    if val == 360.0:
                        return 0.0

    # 2. Bearing fallback from consecutive positions
    if len(df_sorted) >= 2 and "latitude" in df_sorted.columns and "longitude" in df_sorted.columns:
        first_row = df_sorted.iloc[0]
        last_row = df_sorted.iloc[-1]

        lat1, lon1 = float(first_row["latitude"]), float(first_row["longitude"])
        lat2, lon2 = float(last_row["latitude"]), float(last_row["longitude"])

        dist_m = float(haversine_distance_km(lat1, lon1, lat2, lon2)) * 1000.0
        if dist_m > 10.0:
            return calculate_bearing(lat1, lon1, lat2, lon2)

    # 3. Single observation or uncomputable
    return None


def calculate_trajectory_score(
    vessel_direction_deg: Optional[float],
    explicit_drift_direction_deg: Optional[float],
    trajectory_intersects_origin: Optional[bool] = None,
    spatial_score: Optional[float] = None,
) -> Optional[float]:
    """Calculate normalized trajectory compatibility score in [0.0, 1.0].

    CRITICAL DRIFT CONTRACT:
    - If explicit_drift_direction_deg is provided through an approved interface,
      computes angular alignment between vessel track and drift vector.
    - NEVER infers drift direction from spill_observation.
    - If explicit drift is absent, evaluates geographic trajectory intersection fallback.
    - Returns None if direction and intersection are uncomputable (e.g. N=1).

    Args:
        vessel_direction_deg: Movement direction in degrees [0.0, 360.0), or None.
        explicit_drift_direction_deg: Explicit drift vector direction from approved
            interface, or None.
        trajectory_intersects_origin: Boolean indicating whether track crossed origin radius.
        spatial_score: Spatial proximity score used as fallback when passing nearby.

    Returns:
        Optional[float]: Trajectory score in [0.0, 1.0], or None if uncomputable.
    """
    # Case 1: Explicit drift direction is available and vessel direction is known
    if explicit_drift_direction_deg is not None and vessel_direction_deg is not None:
        v_dir = float(vessel_direction_deg) % 360.0
        d_dir = float(explicit_drift_direction_deg) % 360.0

        raw_diff = abs(v_dir - d_dir)
        delta_theta = min(raw_diff, 360.0 - raw_diff)  # in [0.0, 180.0]

        alignment = (1.0 + math.cos(math.radians(delta_theta))) / 2.0
        return float(max(0.0, min(1.0, alignment)))

    # Case 2: No explicit drift direction available -> Geographic fallback
    if trajectory_intersects_origin is True:
        return 1.0
    if trajectory_intersects_origin is False and spatial_score is not None:
        return float(max(0.0, min(1.0, spatial_score)))

    # Case 3: Direction or trajectory cannot be evaluated (e.g. single fix)
    return None


def analyze_ais_gaps(
    df_vessel: pd.DataFrame,
    origin_radius_km: float = 0.0,
    gap_threshold_seconds: float = 1800.0,
) -> Tuple[int, bool, float]:
    """Neutrally evaluate AIS telemetry broadcast continuity gaps.

    Does NOT infer intent or claim 'intentional deactivation'. Evaluates strictly
    whether elapsed time between consecutive fixes exceeded gap_threshold_seconds.

    Args:
        df_vessel: DataFrame containing vessel observations.
        origin_radius_km: Uncertainty radius of origin in km.
        gap_threshold_seconds: Interval in seconds defining an AIS gap (default 1800s).

    Returns:
        Tuple of:
            - gap_count (int): Number of intervals > gap_threshold_seconds.
            - gap_near_origin (bool): True if any gap occurred within origin proximity.
            - max_gap_minutes (float): Maximum gap duration in minutes.
    """
    if df_vessel.empty or len(df_vessel) < 2:
        return 0, False, 0.0

    # Filter to actual observations for gap analysis where possible
    if "is_interpolated" in df_vessel.columns:
        actual_df = df_vessel[~df_vessel["is_interpolated"].astype(bool)]
        # If all fixes were interpolated, use all fixes
        df_eval = actual_df if len(actual_df) >= 2 else df_vessel
    else:
        df_eval = df_vessel

    if len(df_eval) < 2 or "timestamp" not in df_eval.columns:
        return 0, False, 0.0

    df_sorted = df_eval.sort_values(by="timestamp", ascending=True)
    timestamps = pd.to_datetime(df_sorted["timestamp"], utc=True)
    time_diffs = timestamps.diff().dropna().dt.total_seconds()

    gap_mask = time_diffs > gap_threshold_seconds
    gap_count = int(gap_mask.sum())

    if gap_count == 0:
        return 0, False, 0.0

    max_gap_seconds = float(time_diffs.max())
    max_gap_minutes = max_gap_seconds / 60.0

    # Check whether any gap occurred near the origin
    gap_near_origin = False
    proximity_limit = float(origin_radius_km) + 5.0
    if "distance_km" in df_sorted.columns:
        gap_indices = gap_mask[gap_mask].index
        for idx in gap_indices:
            # Check distance at the boundary fixes of the gap
            loc_pos = df_sorted.index.get_loc(idx)
            prev_loc = max(0, loc_pos - 1)
            d1 = float(df_sorted["distance_km"].iloc[prev_loc])
            d2 = float(df_sorted["distance_km"].iloc[loc_pos])
            if d1 <= proximity_limit or d2 <= proximity_limit:
                gap_near_origin = True
                break

    return gap_count, gap_near_origin, max_gap_minutes


def calculate_behaviour_score(
    df_vessel: pd.DataFrame,
    origin_radius_km: float = 0.0,
    config: Optional[AttributionScoringConfig] = None,
) -> Optional[float]:
    """Calculate deterministic behaviour score combining kinematics and telemetry continuity.

    Follows the 3-tier deterministic speed rule:
    1. Observed SOG: computed from actual AIS fixes if available.
    2. Derived speed: computed from consecutive fixes if SOG missing and N >= 2.
    3. Neutral fallback: 0.70 if speed is uncomputable (never penalize missing speed).

    Continuity evaluates broadcast gaps neutrally without inferring intent.
    Interpolated fixes are not treated as raw AIS telemetry evidence.

    Args:
        df_vessel: DataFrame containing vessel observations.
        origin_radius_km: Origin uncertainty radius in km.
        config: Scoring configuration options.

    Returns:
        Optional[float]: Behaviour score in [0.0, 1.0], or None if df_vessel is empty.
    """
    if df_vessel.empty:
        return None

    if config is None:
        config = AttributionScoringConfig()

    df_sorted = df_vessel.sort_values(by="timestamp", ascending=True)

    # -------------------------------------------------------------------------
    # 1. Speed Suitability Component (s_sog)
    # -------------------------------------------------------------------------
    mean_speed: Optional[float] = None

    # Priority A: Observed SOG in actual AIS telemetry
    if "sog" in df_sorted.columns:
        actual_fixes = df_sorted
        if "is_interpolated" in df_sorted.columns:
            non_interp = df_sorted[~df_sorted["is_interpolated"].astype(bool)]
            if not non_interp.empty:
                actual_fixes = non_interp

        valid_sog = actual_fixes["sog"].dropna()
        valid_sog = valid_sog[valid_sog.apply(lambda x: isinstance(x, (int, float, np.integer, np.floating)) and np.isfinite(x) and x >= 0.0)]
        if not valid_sog.empty:
            mean_speed = float(valid_sog.mean())

    # Priority B: Derivable speed from consecutive fixes (N >= 2)
    if mean_speed is None and len(df_sorted) >= 2 and "latitude" in df_sorted.columns and "longitude" in df_sorted.columns:
        timestamps = pd.to_datetime(df_sorted["timestamp"], utc=True)
        total_time_sec = float((timestamps.iloc[-1] - timestamps.iloc[0]).total_seconds())
        if total_time_sec > 1.0:
            lat1, lon1 = float(df_sorted["latitude"].iloc[0]), float(df_sorted["longitude"].iloc[0])
            lat2, lon2 = float(df_sorted["latitude"].iloc[-1]), float(df_sorted["longitude"].iloc[-1])
            dist_km = float(haversine_distance_km(lat1, lon1, lat2, lon2))
            # Convert km/h to knots (1 km = 0.539957 NM)
            speed_knots = (dist_km / (total_time_sec / 3600.0)) * 0.539957
            if np.isfinite(speed_knots) and speed_knots >= 0.0:
                mean_speed = speed_knots

    # Priority C: Neutral fallback (0.70) if neither observed nor derivable
    if mean_speed is None:
        s_sog = float(config.neutral_speed_score)
    else:
        # Evaluate speed suitability curve
        if mean_speed < 0.5:
            s_sog = 0.4
        elif 0.5 <= mean_speed < config.min_transit_sog_knots:
            slope = (1.0 - 0.4) / (config.min_transit_sog_knots - 0.5)
            s_sog = 0.4 + slope * (mean_speed - 0.5)
        elif config.min_transit_sog_knots <= mean_speed <= config.max_transit_sog_knots:
            s_sog = 1.0
        elif config.max_transit_sog_knots < mean_speed <= 30.0:
            slope = (1.0 - 0.3) / (30.0 - config.max_transit_sog_knots)
            s_sog = 1.0 - slope * (mean_speed - config.max_transit_sog_knots)
        else:
            s_sog = 0.3

    # -------------------------------------------------------------------------
    # 2. Speed Variation & Loitering Component (s_var)
    # -------------------------------------------------------------------------
    s_var = 0.70  # Default neutral baseline
    if "sog" in df_sorted.columns and len(df_sorted) >= 2:
        valid_sog = df_sorted["sog"].dropna()
        valid_sog = valid_sog[valid_sog.apply(lambda x: isinstance(x, (int, float, np.integer, np.floating)) and np.isfinite(x) and x >= 0.0)]
        if len(valid_sog) >= 2:
            sog_min = float(valid_sog.min())
            sog_max = float(valid_sog.max())
            delta_sog = sog_max - sog_min
            if sog_min <= 1.0 and sog_max >= 6.0:
                s_var = 0.90  # Stopped or drastically slowed
            elif delta_sog <= 3.0:
                s_var = 0.75  # Uniform cruising
            elif delta_sog > 15.0:
                s_var = 0.50  # Highly erratic speed changes
            else:
                s_var = 0.70

    # -------------------------------------------------------------------------
    # 3. AIS Telemetry Continuity Component (s_continuity)
    # -------------------------------------------------------------------------
    gap_count, gap_near_origin, _ = analyze_ais_gaps(
        df_vessel=df_sorted,
        origin_radius_km=origin_radius_km,
        gap_threshold_seconds=config.gap_threshold_seconds,
    )

    if gap_count >= 1 and gap_near_origin:
        s_continuity = 0.4
    elif gap_count >= 1:
        s_continuity = 0.7
    else:
        s_continuity = 1.0

    # Composite score
    behaviour_score = 0.50 * s_sog + 0.30 * s_var + 0.20 * s_continuity
    return float(max(0.0, min(1.0, behaviour_score)))
