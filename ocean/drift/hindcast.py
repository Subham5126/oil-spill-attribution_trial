"""Lagrangian oil-particle backward advection (hindcasting) model."""

from typing import Any, List
import numpy as np
import pandas as pd
import xarray as xr

from ocean.time.synchronization import normalize_timestamp
from ocean.interpolation.environment import interpolate_currents, interpolate_wind, InterpolationError
from ocean.drift.particle import Particle, ParticleModelError, geographic_displacement


def hindcast_particles(
    particles: List[Particle],
    current_dataset: xr.Dataset,
    wind_dataset: xr.Dataset,
    observation_time: Any,
    duration_seconds: int,
    timestep_seconds: int = 3600,
    windage: float = 0.03,
) -> pd.DataFrame:
    """
    Simulate historical particle trajectories using explicit backward Euler integration.
    
    Args:
        particles: Initial (observed) particles to simulate backward in time.
        current_dataset: xarray Dataset with standardized 'uo', 'vo' current velocities.
        wind_dataset: xarray Dataset with standardized 'u10', 'v10' wind velocities.
        observation_time: UTC timestamp representing the start time of the hindcast (the spill observation).
        duration_seconds: Total duration of the hindcast in seconds.
        timestep_seconds: Duration of each integration step backward in seconds.
        windage: Dimensionless coefficient determining wind influence (oil_velocity = current + windage * wind).
        
    Returns:
        A pandas DataFrame containing the historical simulation history (one record per particle per timestep).
        
    Raises:
        ParticleModelError: If inputs are invalid, datasets are missing required variables, or environmental constraints are violated.
    """
    if not particles:
        raise ParticleModelError("Initial particles list cannot be empty.")
    if duration_seconds <= 0:
        raise ParticleModelError("duration_seconds must be greater than 0.")
    if timestep_seconds <= 0:
        raise ParticleModelError("timestep_seconds must be greater than 0.")
    if duration_seconds % timestep_seconds != 0:
        raise ParticleModelError("duration_seconds must be a multiple of timestep_seconds.")
    if not np.isfinite(windage) or windage < 0:
        raise ParticleModelError("windage must be a finite, non-negative value.")
        
    # Check variables
    if "uo" not in current_dataset.data_vars or "vo" not in current_dataset.data_vars:
        raise ParticleModelError("Missing required current variables ('uo', 'vo').")
    if "u10" not in wind_dataset.data_vars or "v10" not in wind_dataset.data_vars:
        raise ParticleModelError("Missing required wind variables ('u10', 'v10').")

    try:
        normalized_time = normalize_timestamp(observation_time, assume_naive_utc=False)
    except Exception as e:
        raise ParticleModelError(f"Invalid observation_time: {e}") from e

    num_steps = duration_seconds // timestep_seconds

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

    # Record initial (observation) state
    record_history(current_time)

    for step in range(num_steps):
        # We only update active particles
        active_idx = np.where(active)[0]
        if len(active_idx) == 0:
            # Advance time backward and just record inactive states
            current_time -= pd.Timedelta(seconds=timestep_seconds)
            record_history(current_time)
            continue
            
        # We need a tz-naive time for OCEAN-04 compatibility (since xarray/numpy datetime64 works best naive)
        time_arg = current_time.tz_localize(None)

        try:
            # Query OCEAN-04 for active particles at CURRENT timestamp and location
            uo, vo = interpolate_currents(current_dataset, lons[active_idx], lats[active_idx], time_arg)
            u10, v10 = interpolate_wind(wind_dataset, lons[active_idx], lats[active_idx], time_arg)
            
            # OCEAN-04 might return scalar if 1 particle, we ensure 1D arrays for consistency
            if np.isscalar(uo):
                uo = np.array([uo])
                vo = np.array([vo])
                u10 = np.array([u10])
                v10 = np.array([v10])
                
        except InterpolationError as e:
            # Fail clearly on out-of-domain rather than inventing physics, as requested by MVP
            raise ParticleModelError(f"Environmental interpolation failed: {e}") from e

        # V_oil = V_current + windage * V_wind
        vx = uo + windage * u10
        vy = vo + windage * v10
        
        # Ensure environmental values are valid
        if np.isnan(vx).any() or np.isnan(vy).any():
            raise ParticleModelError("Environmental interpolation produced NaN values.")

        # Displacement in meters for backward integration:
        # X(t-dt) = X(t) - V_oil * dt
        dx_meters = vx * timestep_seconds
        dy_meters = vy * timestep_seconds
        
        # Geographic displacement
        dlon, dlat = geographic_displacement(dx_meters, dy_meters, lats[active_idx])
        
        # Backward update state
        lons[active_idx] -= dlon
        lats[active_idx] -= dlat
        
        # Move time backwards
        current_time -= pd.Timedelta(seconds=timestep_seconds)
        
        # Record state
        record_history(current_time)
        
    return pd.DataFrame(history)
