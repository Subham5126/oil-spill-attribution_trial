"""
DRIFT-06: Spatial Uncertainty Estimation.

This module provides deterministic spatial uncertainty estimation for 
particle trajectories. Spatial uncertainty here is defined as the empirical 
geographic spread (dispersion) of the simulated oil-spill particles at a given 
timestamp. The centroid is the mean geographic position, and the uncertainty 
radius is the metric distance enclosing a requested percentage (confidence_level) 
of the particles.

This is a deterministic spatial dispersion estimate based on the provided 
particle ensemble. The radius is NOT a calibrated probability of oil presence, 
nor is this a full stochastic/ensemble oceanographic uncertainty model.
"""

from typing import Any
import numpy as np
import pandas as pd
from dataclasses import dataclass

from ocean.drift.origin import _haversine_distance


class UncertaintyError(ValueError):
    """Raised when uncertainty calculation fails due to invalid inputs."""
    pass


@dataclass
class UncertaintyResult:
    """Structured result for spatial uncertainty at a specific timestamp."""
    timestamp: pd.Timestamp
    particle_count: int
    centroid_longitude: float
    centroid_latitude: float
    spread_km: float
    uncertainty_radius_km: float
    min_longitude: float
    max_longitude: float
    min_latitude: float
    max_latitude: float
    confidence_level: float


def calculate_uncertainty(
    trajectories: pd.DataFrame,
    timestamp: Any = None,
    confidence_level: float = 0.95,
) -> UncertaintyResult:
    """
    Calculate the spatial uncertainty/spread of particles at a specific timestamp.
    
    Args:
        trajectories: DataFrame output from DRIFT-04 or OCEAN-07.
        timestamp: The timestamp to evaluate. If None, evaluates the latest available timestamp.
        confidence_level: The fraction of particles to bound (0.0 < confidence_level <= 1.0).
            For example, 0.95 means the returned uncertainty_radius_km will enclose 
            95% of the particles closest to the centroid.
            
    Returns:
        UncertaintyResult containing spatial dispersion statistics.
        
    Raises:
        UncertaintyError: If inputs are invalid or no particles exist.
    """
    if trajectories is None or trajectories.empty:
        raise UncertaintyError("Trajectories DataFrame cannot be empty.")
        
    if not (0.0 < confidence_level <= 1.0):
        raise UncertaintyError("confidence_level must be between 0.0 (exclusive) and 1.0.")
        
    required_cols = {"particle_id", "timestamp", "longitude", "latitude", "active"}
    if not required_cols.issubset(trajectories.columns):
        raise UncertaintyError(f"Trajectories DataFrame is missing required columns: {required_cols}")
        
    # We evaluate only active particles
    df_active = trajectories[trajectories["active"]].copy()
    if df_active.empty:
        raise UncertaintyError("No active particles found in trajectories.")
        
    if not np.isfinite(df_active["longitude"]).all() or not np.isfinite(df_active["latitude"]).all():
        raise UncertaintyError("Trajectories contain invalid (NaN/Inf) coordinates.")
        
    if timestamp is None:
        # Default behavior: pick the latest timestamp
        t_val = df_active["timestamp"].max()
    else:
        # User specified a timestamp
        t_val = pd.Timestamp(timestamp)
        # Attempt to align timezone if the dataframe uses timezone-aware timestamps and input is naive (or vice versa)
        if t_val.tz is None and getattr(df_active["timestamp"].iloc[0], "tz", None) is not None:
            t_val = t_val.tz_localize("UTC")
        elif t_val.tz is not None and getattr(df_active["timestamp"].iloc[0], "tz", None) is None:
            t_val = t_val.tz_localize(None)

    # Filter to requested timestamp
    df_t = df_active[df_active["timestamp"] == t_val]
    if df_t.empty:
        raise UncertaintyError(f"No active particles found at timestamp {t_val}.")
        
    lons = df_t["longitude"].values
    lats = df_t["latitude"].values
    count = len(lons)
    
    centroid_lon = float(np.mean(lons))
    centroid_lat = float(np.mean(lats))
    
    min_lon = float(np.min(lons))
    max_lon = float(np.max(lons))
    min_lat = float(np.min(lats))
    max_lat = float(np.max(lats))
    
    if count == 1:
        spread_km = 0.0
        radius_km = 0.0
    else:
        # Calculate distances of all particles from the centroid using vectorized Haversine
        distances_m = _haversine_distance(centroid_lon, centroid_lat, lons, lats)
        distances_km = distances_m / 1000.0
        
        # Spread is the mean distance from the centroid
        spread_km = float(np.mean(distances_km))
        
        # Uncertainty radius enclosing `confidence_level` percent of particles (percentile)
        radius_km = float(np.percentile(distances_km, confidence_level * 100.0))
        
    return UncertaintyResult(
        timestamp=pd.Timestamp(t_val),
        particle_count=count,
        centroid_longitude=centroid_lon,
        centroid_latitude=centroid_lat,
        spread_km=spread_km,
        uncertainty_radius_km=radius_km,
        min_longitude=min_lon,
        max_longitude=max_lon,
        min_latitude=min_lat,
        max_latitude=max_lat,
        confidence_level=confidence_level
    )
