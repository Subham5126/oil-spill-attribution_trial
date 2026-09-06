"""AIS Kinematics Calculations.

Provides vectorized great-circle distance (Haversine) and inter-ping kinematic
derivation (time delta, distance, derived speed) grouped deterministically by vessel MMSI.
"""

from typing import Union

import numpy as np
import pandas as pd

from ais.data_loader.schema import REQUIRED_COLUMNS

# Earth volumetric mean radius according to IUGG / WGS84: 6371.0088 km
EARTH_RADIUS_KM: float = 6371.0088
# Exact international definition: 1 nautical mile = 1852 meters = 1.852 km
KM_PER_NM: float = 1.852
# Earth radius in nautical miles
EARTH_RADIUS_NM: float = EARTH_RADIUS_KM / KM_PER_NM  # ~3440.0695 nm


def haversine_distance_nm(
    lat1: Union[float, np.ndarray, pd.Series],
    lon1: Union[float, np.ndarray, pd.Series],
    lat2: Union[float, np.ndarray, pd.Series],
    lon2: Union[float, np.ndarray, pd.Series],
) -> Union[float, np.ndarray, pd.Series]:
    """Calculate great-circle distance between coordinate pairs in nautical miles.

    Uses the spherical Haversine formula assuming Earth radius R = 3440.0695 NM
    (derived from WGS84 volumetric mean radius 6371.0088 km and 1852 m/NM).

    Args:
        lat1: Latitude of starting point(s) in decimal degrees [-90, 90].
        lon1: Longitude of starting point(s) in decimal degrees [-180, 180].
        lat2: Latitude of destination point(s) in decimal degrees [-90, 90].
        lon2: Longitude of destination point(s) in decimal degrees [-180, 180].

    Returns:
        Great-circle distance in nautical miles (float or ndarray/Series).
        Returns NaN if any coordinate input is NaN.
    """
    # Convert degrees to radians
    r_lat1 = np.radians(lat1)
    r_lon1 = np.radians(lon1)
    r_lat2 = np.radians(lat2)
    r_lon2 = np.radians(lon2)

    dlat = r_lat2 - r_lat1
    dlon = r_lon2 - r_lon1

    # Haversine formula
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(r_lat1) * np.cos(r_lat2) * np.sin(dlon / 2.0) ** 2
    )
    # Clip to [0.0, 1.0] to safeguard against numerical precision errors beyond 1.0
    a = np.clip(a, 0.0, 1.0)
    c = 2.0 * np.arcsin(np.sqrt(a))

    return EARTH_RADIUS_NM * c


def compute_inter_ping_kinematics(
    df: pd.DataFrame,
    min_time_delta_seconds: float = 1.0,
) -> pd.DataFrame:
    """Compute elapsed time, distance, and derived speed between consecutive pings per vessel.

    Calculates movement metrics separately for each vessel (MMSI) in chronological order.
    Movement is NEVER computed between different vessels. The first ping of each vessel
    receives NaN/NaT for all inter-ping metrics.

    Args:
        df: Canonical AIS DataFrame containing at least 'mmsi', 'timestamp',
            'latitude', and 'longitude'.
        min_time_delta_seconds: Minimum seconds elapsed to compute derived speed.
            If elapsed time is less than this, derived speed is set to NaN.

    Returns:
        A copy of the DataFrame with added kinematic columns:
        - 'previous_timestamp': Timestamp of preceding ping for the vessel (UTC datetime).
        - 'time_delta_s': Elapsed time in seconds from previous ping (float).
        - 'distance_nm': Great-circle distance from previous ping in nautical miles (float).
        - 'derived_speed_knots': Speed over ground derived from distance/time (knots).

    Raises:
        ValueError: If required columns are missing or if timestamps are not datetime.
    """
    if df.empty:
        res = df.copy()
        for col in [
            "previous_timestamp",
            "time_delta_s",
            "distance_nm",
            "derived_speed_knots",
        ]:
            if col not in res.columns:
                if col == "previous_timestamp":
                    res[col] = pd.Series(dtype="datetime64[ns, UTC]")
                else:
                    res[col] = pd.Series(dtype="float64")
        return res

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            f"Cannot compute kinematics: missing required column(s) {missing}"
        )

    # Do not mutate caller's DataFrame
    res = df.copy()

    # Ensure timestamps are datetime64 with UTC
    if not pd.api.types.is_datetime64_any_dtype(res["timestamp"]):
        res["timestamp"] = pd.to_datetime(res["timestamp"], utc=True)
    elif str(getattr(res["timestamp"].dt, "tz", None)) != "UTC":
        res["timestamp"] = res["timestamp"].dt.tz_convert("UTC")

    # Sort deterministically by MMSI and timestamp
    res = res.sort_values(by=["mmsi", "timestamp"]).reset_index(drop=True)

    grouped = res.groupby("mmsi")

    # Shifted values per vessel
    res["previous_timestamp"] = grouped["timestamp"].shift(1)
    prev_lat = grouped["latitude"].shift(1)
    prev_lon = grouped["longitude"].shift(1)

    # Compute time delta in seconds
    res["time_delta_s"] = (
        res["timestamp"] - res["previous_timestamp"]
    ).dt.total_seconds()

    # Compute great-circle distance in nautical miles
    res["distance_nm"] = haversine_distance_nm(
        prev_lat, prev_lon, res["latitude"], res["longitude"]
    )

    # Compute derived speed in knots: distance (NM) / (time_delta_s / 3600.0)
    # Only calculate when time_delta_s >= min_time_delta_seconds
    valid_time_mask = (
        (res["time_delta_s"] >= min_time_delta_seconds)
        & res["distance_nm"].notna()
    )
    hours = res["time_delta_s"] / 3600.0
    res["derived_speed_knots"] = np.where(
        valid_time_mask,
        res["distance_nm"] / hours,
        np.nan,
    )

    return res
