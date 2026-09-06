"""Forward Drift Forecasting."""

from typing import Any, List
import pandas as pd
import xarray as xr

from ocean.drift.particle import Particle, ParticleModelError, simulate_particles

def forecast_particles(
    particles: List[Particle],
    current_dataset: xr.Dataset,
    wind_dataset: xr.Dataset,
    start_time: Any,
    duration_seconds: int,
    timestep_seconds: int = 3600,
    windage: float = 0.03,
) -> pd.DataFrame:
    """
    Simulate future particle trajectories for forecasting.
    
    This function wraps the existing explicit forward Euler integration
    model (OCEAN-06) to orchestrate forward drift forecasting. It uses future/current
    environmental data through the existing interpolation layer. The output is
    deterministic particle trajectories; it does not represent uncertainty/probability.
    
    Args:
        particles: Initial (observed) particles to forecast forward in time.
        current_dataset: xarray Dataset with standardized 'uo', 'vo' current velocities.
        wind_dataset: xarray Dataset with standardized 'u10', 'v10' wind velocities.
        start_time: UTC timestamp representing the start time of the forecast.
        duration_seconds: Total duration of the forecast in seconds.
        timestep_seconds: Duration of each integration step in seconds.
        windage: Dimensionless coefficient determining wind influence (oil_velocity = current + windage * wind).
        
    Returns:
        A pandas DataFrame containing the forecast simulation history (one record per particle per timestep).
        
    Raises:
        ParticleModelError: If inputs are invalid, datasets are missing required variables, 
            or environmental constraints are violated.
    """
    if duration_seconds <= 0:
        raise ParticleModelError("duration_seconds must be greater than 0.")
    if timestep_seconds <= 0:
        raise ParticleModelError("timestep_seconds must be greater than 0.")
    if duration_seconds % timestep_seconds != 0:
        raise ParticleModelError("duration_seconds must be a multiple of timestep_seconds.")
        
    num_steps = duration_seconds // timestep_seconds
    
    # We rely on OCEAN-06's simulate_particles to handle:
    # - Empty particle list validation
    # - Missing dataset variables validation
    # - windage validation
    # - UTC time normalization (OCEAN-05)
    # - Environmental interpolation out-of-bounds errors (OCEAN-04)
    # - Forward physics integration
    
    return simulate_particles(
        particles=particles,
        current_dataset=current_dataset,
        wind_dataset=wind_dataset,
        start_time=start_time,
        num_steps=num_steps,
        timestep_seconds=timestep_seconds,
        windage=windage
    )
