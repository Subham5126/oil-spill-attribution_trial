"""Tests for the forward drift forecasting module (DRIFT-04)."""

import pytest
import pandas as pd
import numpy as np
import xarray as xr
from pathlib import Path

from ocean.drift.particle import Particle, ParticleModelError
from ocean.drift.forecasting import forecast_particles
from ocean.currents import load_currents
from ocean.wind import load_wind

@pytest.fixture
def eastward_env():
    """Returns basic eastward current/wind synthetic datasets."""
    lon = np.linspace(0, 20, 5)
    lat = np.linspace(0, 20, 5)
    time = pd.date_range("2025-01-01 00:00:00", periods=5, freq="h")

    ds_curr = xr.Dataset(
        {
            "uo": (["time", "latitude", "longitude"], np.ones((5, 5, 5)), {"units": "m/s"}),
            "vo": (["time", "latitude", "longitude"], np.zeros((5, 5, 5)), {"units": "m/s"})
        },
        coords={"time": time, "latitude": lat, "longitude": lon}
    )
    
    ds_wind = xr.Dataset(
        {
            "u10": (["time", "latitude", "longitude"], np.ones((5, 5, 5)) * 10.0, {"units": "m/s"}),
            "v10": (["time", "latitude", "longitude"], np.zeros((5, 5, 5)), {"units": "m/s"})
        },
        coords={"time": time, "latitude": lat, "longitude": lon}
    )
    return ds_curr, ds_wind

def test_basic_forecast(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    start_time = pd.Timestamp("2025-01-01 01:00:00+00:00")
    
    df = forecast_particles(particles, current_ds, wind_ds, start_time, duration_seconds=3600)
    
    # 2 records: t=0 and t=1
    assert len(df) == 2
    # Verify particles move forward (eastward)
    assert df.iloc[1]["longitude"] > 10.0

def test_multiple_particles_remain_independent(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0), Particle(2, 10.0, 20.0)]
    start_time = pd.Timestamp("2025-01-01 01:00:00+00:00")
    
    df = forecast_particles(particles, current_ds, wind_ds, start_time, duration_seconds=3600)
    
    assert len(df) == 4
    assert set(df["particle_id"].unique()) == {1, 2}

def test_timestamps_move_forward_exactly_by_timestep(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    start_time = pd.Timestamp("2025-01-01 01:00:00+00:00")
    
    df = forecast_particles(particles, current_ds, wind_ds, start_time, duration_seconds=3600, timestep_seconds=3600)
    assert df.iloc[1]["timestamp"] - df.iloc[0]["timestamp"] == pd.Timedelta(seconds=3600)

def test_utc_and_equivalent_timezone_produce_equivalent_results(eastward_env):
    current_ds, wind_ds = eastward_env
    particles1 = [Particle(1, 10.0, 10.0)]
    particles2 = [Particle(1, 10.0, 10.0)]
    
    obs_utc = pd.Timestamp("2025-01-01 01:00:00+00:00")
    obs_ist = pd.Timestamp("2025-01-01 06:30:00+05:30")
    
    df_utc = forecast_particles(particles1, current_ds, wind_ds, obs_utc, duration_seconds=3600)
    df_ist = forecast_particles(particles2, current_ds, wind_ds, obs_ist, duration_seconds=3600)
    
    pd.testing.assert_frame_equal(df_utc, df_ist)

def test_invalid_duration_and_timestep_rejected(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    start_time = pd.Timestamp("2025-01-01 01:00:00+00:00")
    
    with pytest.raises(ParticleModelError, match="duration_seconds must be greater than 0"):
        forecast_particles(particles, current_ds, wind_ds, start_time, duration_seconds=0)
        
    with pytest.raises(ParticleModelError, match="timestep_seconds must be greater than 0"):
        forecast_particles(particles, current_ds, wind_ds, start_time, duration_seconds=3600, timestep_seconds=0)
        
    with pytest.raises(ParticleModelError, match="multiple of timestep_seconds"):
        forecast_particles(particles, current_ds, wind_ds, start_time, duration_seconds=3600, timestep_seconds=1000)

def test_out_of_domain_handled_explicitly(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 50.0, 50.0)] # Domain is 0 to 20
    start_time = pd.Timestamp("2025-01-01 01:00:00+00:00")
    
    with pytest.raises(ParticleModelError, match="Environmental interpolation failed"):
        forecast_particles(particles, current_ds, wind_ds, start_time, duration_seconds=3600)

def test_deterministic_repeated_execution(eastward_env):
    current_ds, wind_ds = eastward_env
    particles1 = [Particle(1, 10.0, 10.0)]
    particles2 = [Particle(1, 10.0, 10.0)]
    start_time = pd.Timestamp("2025-01-01 01:00:00+00:00")
    
    df1 = forecast_particles(particles1, current_ds, wind_ds, start_time, duration_seconds=3600)
    df2 = forecast_particles(particles2, current_ds, wind_ds, start_time, duration_seconds=3600)
    
    pd.testing.assert_frame_equal(df1, df2)

def test_windage_effect(eastward_env):
    current_ds, wind_ds = eastward_env
    particles1 = [Particle(1, 10.0, 10.0)]
    particles2 = [Particle(1, 10.0, 10.0)]
    start_time = pd.Timestamp("2025-01-01 01:00:00+00:00")
    
    df_no_wind = forecast_particles(particles1, current_ds, wind_ds, start_time, duration_seconds=3600, windage=0.0)
    df_with_wind = forecast_particles(particles2, current_ds, wind_ds, start_time, duration_seconds=3600, windage=0.05)
    
    dist_no = df_no_wind.iloc[1]["longitude"] - 10.0
    dist_wind = df_with_wind.iloc[1]["longitude"] - 10.0
    
    assert dist_wind > dist_no

@pytest.mark.parametrize(
    ("current_path", "wind_path"),
    [
        (Path("data/sample/copernicus/current_test.nc"), Path("data/sample/era5/wind_test.nc")),
    ]
)
def test_integration_with_real_datasets(current_path, wind_path):
    if not current_path.is_file() or not wind_path.is_file():
        pytest.skip("Sample NetCDF files not available")
        
    current_ds = load_currents(current_path)
    wind_ds = load_wind(wind_path)
    
    lon = float(current_ds["longitude"].values.mean())
    lat = float(current_ds["latitude"].values.mean())
    
    # We pick an early observation time to forecast forward
    start_time = pd.Timestamp(current_ds["time"].values[0]).tz_localize("UTC")
    
    particles = [Particle(1, lon, lat)]
    
    df = forecast_particles(particles, current_ds, wind_ds, start_time, duration_seconds=7200, timestep_seconds=3600)
    
    assert len(df) == 3
    assert df.iloc[0]["longitude"] == lon
    assert df.iloc[0]["latitude"] == lat
    
    # Timestamps move forward
    assert df.iloc[1]["timestamp"] > df.iloc[0]["timestamp"]
    assert df.iloc[2]["timestamp"] > df.iloc[1]["timestamp"]
    
    # Coordinate changed
    assert df.iloc[2]["longitude"] != lon or df.iloc[2]["latitude"] != lat
    assert np.isfinite(df.iloc[2]["longitude"])
    assert np.isfinite(df.iloc[2]["latitude"])
