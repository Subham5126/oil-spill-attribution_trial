"""Lagrangian oil-particle advection model."""

import dataclasses
from typing import Any, List
import numpy as np
import pandas as pd
import xarray as xr

from ocean.time.synchronization import normalize_timestamp
from ocean.interpolation.environment import interpolate_currents, interpolate_wind, InterpolationError


class ParticleModelError(ValueError):
    """Raised when particle model configuration or execution fails."""
    pass


class SpatialBoundaryConditionError(ParticleModelError):
    """Raised when a particle trajectory reaches or exceeds environmental dataset spatial bounds."""

    def __init__(
        self,
        message: str,
        dimension: str = "latitude",
        query_value: float = 0.0,
        dataset_bounds: tuple[float, float] = (0.0, 0.0),
        step: int = 0,
        particle_id: int = 1,
    ):
        super().__init__(message)
        self.dimension = dimension
        self.query_value = query_value
        self.dataset_bounds = dataset_bounds
        self.step = step
        self.particle_id = particle_id


@dataclasses.dataclass
class Particle:
    """Represents a simulated oil parcel."""
    particle_id: int
    longitude: float
    latitude: float
    timestamp: pd.Timestamp = None
    active: bool = True


def geographic_displacement(eastward_meters: np.ndarray, northward_meters: np.ndarray, latitude: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convert metric displacement to geographic degree changes using a geodesic approximation."""
    R = 6371000.0
    m_per_deg_lat = np.pi * R / 180.0
    
    # Avoid division by zero at the exact poles
    safe_lat = np.clip(latitude, -89.99, 89.99)
    m_per_deg_lon = m_per_deg_lat * np.cos(np.radians(safe_lat))
    
    dlat = northward_meters / m_per_deg_lat
    dlon = eastward_meters / m_per_deg_lon
    
    return dlon, dlat


def simulate_particles(
    particles: List[Particle],
    current_dataset: xr.Dataset,
    wind_dataset: xr.Dataset,
    start_time: Any,
    num_steps: int,
    timestep_seconds: int = 3600,
    windage: float = 0.03,
) -> pd.DataFrame:
    """
    Simulate particle trajectories using explicit forward Euler integration.
    
    Args:
        particles: Initial particles to simulate.
        current_dataset: xarray Dataset with standardized 'uo', 'vo' current velocities.
        wind_dataset: xarray Dataset with standardized 'u10', 'v10' wind velocities.
        start_time: UTC timestamp representing the start time of the simulation.
        num_steps: Number of integration steps to perform.
        timestep_seconds: Duration of each integration step in seconds.
        windage: Dimensionless coefficient determining wind influence (oil_velocity = current + windage * wind).
        
    Returns:
        A pandas DataFrame containing the simulation history (one record per particle per timestep).
        
    Raises:
        ParticleModelError: If inputs are invalid or environmental constraints are violated.
    """
    if not particles:
        raise ParticleModelError("Initial particles list cannot be empty.")
    if num_steps < 1:
        raise ParticleModelError("num_steps must be at least 1.")
    if timestep_seconds <= 0:
        raise ParticleModelError("timestep_seconds must be greater than 0.")
    if not np.isfinite(windage) or windage < 0:
        raise ParticleModelError("windage must be a finite, non-negative value.")
        
    # Check variables
    if "uo" not in current_dataset.data_vars or "vo" not in current_dataset.data_vars:
        raise ParticleModelError("Missing required current variables ('uo', 'vo').")
    if "u10" not in wind_dataset.data_vars or "v10" not in wind_dataset.data_vars:
        raise ParticleModelError("Missing required wind variables ('u10', 'v10').")

    try:
        normalized_time = normalize_timestamp(start_time, assume_naive_utc=False)
    except Exception as e:
        raise ParticleModelError(f"Invalid start_time: {e}") from e

    # Internal state tracking arrays
    ids = np.array([p.particle_id for p in particles])
    lons = np.array([p.longitude for p in particles], dtype=float)
    lats = np.array([p.latitude for p in particles], dtype=float)
    active = np.array([p.active for p in particles], dtype=bool)
    
    if not np.isfinite(lons).all() or not np.isfinite(lats).all():
        raise ParticleModelError("Longitude and latitude must be finite.")
    if (lats < -90).any() or (lats > 90).any():
        raise ParticleModelError("Latitude must be between -90 and 90 degrees.")

    current_time = normalized_time
    
    # To store trajectory history
    history = []
    
    def record_history(t_stamp):
        for i in range(len(ids)):
            history.append({
                "particle_id": ids[i],
                "timestamp": t_stamp,
                "longitude": lons[i],
                "latitude": lats[i],
                "active": active[i]
            })

    # Record initial state
    record_history(current_time)

    for step in range(num_steps):
        # We only update active particles
        active_idx = np.where(active)[0]
        if len(active_idx) == 0:
            # Advance time and just record inactive states
            current_time += pd.Timedelta(seconds=timestep_seconds)
            record_history(current_time)
            continue
            
        # We need a tz-naive time for OCEAN-04 compatibility (since xarray/numpy datetime64 works best naive)
        time_arg = current_time.tz_localize(None)

        try:
            # Query OCEAN-04 for active particles
            uo, vo = interpolate_currents(current_dataset, lons[active_idx], lats[active_idx], time_arg)
            u10, v10 = interpolate_wind(wind_dataset, lons[active_idx], lats[active_idx], time_arg)
            
            # OCEAN-04 might return scalar if 1 particle, we ensure 1D arrays for consistency
            if np.isscalar(uo):
                uo = np.array([uo])
                vo = np.array([vo])
                u10 = np.array([u10])
                v10 = np.array([v10])
                
        except InterpolationError as e:
            err_msg = str(e)
            if "outside the available dataset range" in err_msg:
                dim = "latitude" if "latitude" in err_msg else ("longitude" if "longitude" in err_msg else "time")
                if dim in ("latitude", "longitude"):
                    bounds = (float(current_dataset[dim].min().values), float(current_dataset[dim].max().values))
                    query_val = float(lats[active_idx][0]) if dim == "latitude" else float(lons[active_idx][0])
                    p_id = int(ids[active_idx][0])
                    raise SpatialBoundaryConditionError(
                        f"Forward trajectory reached {dim} boundary: {err_msg}",
                        dimension=dim,
                        query_value=query_val,
                        dataset_bounds=bounds,
                        step=step,
                        particle_id=p_id,
                    ) from e
            raise ParticleModelError(f"Environmental interpolation failed: {e}") from e

        # Explicit forward Euler: oil_velocity = current + windage * wind
        vx = uo + windage * u10
        vy = vo + windage * v10
        
        # Ensure environmental values are valid
        if np.isnan(vx).any() or np.isnan(vy).any():
            raise ParticleModelError("Environmental interpolation produced NaN values.")

        # Displacement in meters
        dx_meters = vx * timestep_seconds
        dy_meters = vy * timestep_seconds
        
        # Geographic displacement
        dlon, dlat = geographic_displacement(dx_meters, dy_meters, lats[active_idx])
        
        # Update state
        lons[active_idx] += dlon
        lats[active_idx] += dlat
        
        # Advance time
        current_time += pd.Timedelta(seconds=timestep_seconds)
        
        # Record state
        record_history(current_time)
        
    return pd.DataFrame(history)
