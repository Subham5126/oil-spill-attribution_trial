import pytest
import numpy as np
import pandas as pd
import xarray as xr
from pathlib import Path

from ocean.drift import Particle, ParticleModelError, hindcast_particles
from ocean.currents import load_currents
from ocean.wind import load_wind

def create_synthetic_datasets(uo_val, vo_val, u10_val, v10_val):
    """Create synthetic current and wind datasets with constant values."""
    time = pd.date_range("2025-01-01", periods=2, tz=None).values  # Naive for xarray
    lat = np.array([0.0, 20.0])
    lon = np.array([0.0, 20.0])
    
    uo_data = np.full((2, 2, 2), uo_val, dtype=float)
    vo_data = np.full((2, 2, 2), vo_val, dtype=float)
    u10_data = np.full((2, 2, 2), u10_val, dtype=float)
    v10_data = np.full((2, 2, 2), v10_val, dtype=float)
    
    current_ds = xr.Dataset(
        {
            "uo": (("time", "latitude", "longitude"), uo_data, {"units": "m/s"}),
            "vo": (("time", "latitude", "longitude"), vo_data, {"units": "m/s"}),
        },
        coords={"time": time, "latitude": lat, "longitude": lon}
    )
    
    wind_ds = xr.Dataset(
        {
            "u10": (("time", "latitude", "longitude"), u10_data, {"units": "m/s"}),
            "v10": (("time", "latitude", "longitude"), v10_data, {"units": "m/s"}),
        },
        coords={"time": time, "latitude": lat, "longitude": lon}
    )
    
    return current_ds, wind_ds

@pytest.fixture
def stationary_env():
    return create_synthetic_datasets(0.0, 0.0, 0.0, 0.0)

@pytest.fixture
def eastward_env():
    return create_synthetic_datasets(1.0, 0.0, 0.0, 0.0)

@pytest.fixture
def northward_env():
    return create_synthetic_datasets(0.0, 1.0, 0.0, 0.0)

@pytest.fixture
def mixed_env():
    return create_synthetic_datasets(1.0, 0.0, 10.0, 0.0)


def test_pure_eastward_current_hindcasts_westward(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    obs_time = pd.Timestamp("2025-01-01 02:00:00+00:00")
    
    # Pure eastward current means historically it was FURTHER WEST.
    df = hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=3600)
    
    assert len(df) == 2
    assert df.iloc[1]["longitude"] < 10.0
    assert df.iloc[1]["latitude"] == 10.0

def test_pure_northward_current_hindcasts_southward(northward_env):
    current_ds, wind_ds = northward_env
    particles = [Particle(1, 10.0, 10.0)]
    obs_time = pd.Timestamp("2025-01-01 02:00:00+00:00")
    
    # Pure northward current means historically it was FURTHER SOUTH.
    df = hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=3600)
    
    assert df.iloc[1]["longitude"] == 10.0
    assert df.iloc[1]["latitude"] < 10.0

def test_windage_contributes_correctly(mixed_env):
    current_ds, wind_ds = mixed_env
    particles = [Particle(1, 10.0, 10.0)]
    obs_time = pd.Timestamp("2025-01-01 02:00:00+00:00")
    
    # current = 1.0, wind = 10.0, windage = 0.03 => oil velocity = 1.3 m/s
    df_with_wind = hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=3600, windage=0.03)
    
    # current = 1.0, wind = 10.0, windage = 0.0 => oil velocity = 1.0 m/s
    df_no_wind = hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=3600, windage=0.0)
    
    # Both move westward (negative displacement).
    dist_with_wind = 10.0 - df_with_wind.iloc[1]["longitude"]
    dist_no_wind = 10.0 - df_no_wind.iloc[1]["longitude"]
    
    assert np.isclose(dist_with_wind / dist_no_wind, 1.3)

def test_zero_windage_removes_wind_influence(mixed_env):
    current_ds, wind_ds = mixed_env
    particles = [Particle(1, 10.0, 10.0)]
    obs_time = pd.Timestamp("2025-01-01 02:00:00+00:00")
    df = hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=3600, windage=0.0)
    # With windage=0, only eastward current (1.0) is active. Backward, it should move just as if there was no wind.
    assert df.iloc[1]["longitude"] < 10.0

def test_configurable_timestep(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    obs_time = pd.Timestamp("2025-01-01 02:00:00+00:00")
    
    # Duration 3600, timestep 1800 => 2 steps. Output = 3 records (t=0, t=1, t=2)
    df = hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=3600, timestep_seconds=1800)
    
    assert len(df) == 3
    assert df.iloc[1]["timestamp"] == pd.Timestamp("2025-01-01 01:30:00+00:00")
    assert df.iloc[2]["timestamp"] == pd.Timestamp("2025-01-01 01:00:00+00:00")

def test_configurable_duration(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    obs_time = pd.Timestamp("2025-01-01 02:00:00+00:00")
    
    df = hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=7200, timestep_seconds=3600)
    assert len(df) == 3 # 0, 1, 2 steps
    assert df.iloc[-1]["timestamp"] == pd.Timestamp("2025-01-01 00:00:00+00:00")

def test_timestamps_move_backward_exactly_by_timestep(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    obs_time = pd.Timestamp("2025-01-01 02:00:00+00:00")
    
    df = hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=3600, timestep_seconds=3600)
    assert df.iloc[0]["timestamp"] - df.iloc[1]["timestamp"] == pd.Timedelta(seconds=3600)

def test_utc_and_equivalent_timezone_produce_equivalent_results(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    
    obs_utc = pd.Timestamp("2025-01-01 02:00:00+00:00")
    obs_ist = pd.Timestamp("2025-01-01 07:30:00+05:30")
    
    df_utc = hindcast_particles(particles, current_ds, wind_ds, obs_utc, duration_seconds=3600)
    df_ist = hindcast_particles(particles, current_ds, wind_ds, obs_ist, duration_seconds=3600)
    
    pd.testing.assert_frame_equal(df_utc, df_ist)

def test_invalid_timestamp_handling_follows_ocean05(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    obs_naive = pd.Timestamp("2025-01-01 02:00:00")
    
    with pytest.raises(ParticleModelError, match="Timezone information is required"):
        hindcast_particles(particles, current_ds, wind_ds, obs_naive, duration_seconds=3600)

def test_multiple_particles_remain_independent(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0), Particle(2, 10.0, 20.0)]
    obs_time = pd.Timestamp("2025-01-01 02:00:00+00:00")
    
    df = hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=3600)
    
    # 2 particles, 2 timesteps -> 4 records
    assert len(df) == 4
    p1 = df[df["particle_id"] == 1]
    p2 = df[df["particle_id"] == 2]
    
    # Since particle 2 is at lat 20, it should have a larger absolute change in longitude than particle 1 (lat 10)
    dlon1 = abs(p1.iloc[1]["longitude"] - p1.iloc[0]["longitude"])
    dlon2 = abs(p2.iloc[1]["longitude"] - p2.iloc[0]["longitude"])
    
    assert dlon2 > dlon1

def test_particle_ids_preserved(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(99, 10.0, 10.0)]
    obs_time = pd.Timestamp("2025-01-01 02:00:00+00:00")
    
    df = hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=3600)
    assert (df["particle_id"] == 99).all()

def test_input_particles_not_mutated(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    obs_time = pd.Timestamp("2025-01-01 02:00:00+00:00")
    
    hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=3600)
    
    assert particles[0].longitude == 10.0
    assert particles[0].latitude == 10.0

def test_deterministic_repeated_execution(eastward_env):
    current_ds, wind_ds = eastward_env
    particles1 = [Particle(1, 10.0, 10.0)]
    particles2 = [Particle(1, 10.0, 10.0)]
    obs_time = pd.Timestamp("2025-01-01 02:00:00+00:00")
    
    df1 = hindcast_particles(particles1, current_ds, wind_ds, obs_time, duration_seconds=3600)
    df2 = hindcast_particles(particles2, current_ds, wind_ds, obs_time, duration_seconds=3600)
    
    pd.testing.assert_frame_equal(df1, df2)

def test_invalid_duration_and_timestep_rejected(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    obs_time = pd.Timestamp("2025-01-01 02:00:00+00:00")
    
    with pytest.raises(ParticleModelError, match="duration_seconds must be greater than 0"):
        hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=0)
        
    with pytest.raises(ParticleModelError, match="timestep_seconds must be greater than 0"):
        hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=3600, timestep_seconds=0)
        
    with pytest.raises(ParticleModelError, match="multiple of timestep_seconds"):
        hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=3600, timestep_seconds=1000)

def test_out_of_domain_handled_explicitly(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 50.0, 50.0)] # Domain is 0 to 20
    obs_time = pd.Timestamp("2025-01-01 02:00:00+00:00")
    
    with pytest.raises(ParticleModelError, match="Environmental interpolation failed"):
        hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=3600)

def test_nan_values_never_converted_to_zero(eastward_env):
    current_ds, wind_ds = eastward_env
    current_ds["uo"][:] = np.nan
    particles = [Particle(1, 10.0, 10.0)]
    obs_time = pd.Timestamp("2025-01-01 02:00:00+00:00")
    
    with pytest.raises(ParticleModelError, match="Environmental interpolation failed"):
        hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=3600)

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
    
    # We pick an observation time near the end of the dataset to hindcast backward
    obs_time = pd.Timestamp(current_ds["time"].values[-2]).tz_localize("UTC")
    
    particles = [Particle(1, lon, lat)]
    
    df = hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=7200, timestep_seconds=3600)
    
    assert len(df) == 3
    assert df.iloc[0]["longitude"] == lon
    assert df.iloc[0]["latitude"] == lat
    
    # Timestamps move backward
    assert df.iloc[1]["timestamp"] < df.iloc[0]["timestamp"]
    assert df.iloc[2]["timestamp"] < df.iloc[1]["timestamp"]
    
    # Coordinate changed
    assert df.iloc[2]["longitude"] != lon or df.iloc[2]["latitude"] != lat
    assert np.isfinite(df.iloc[2]["longitude"])
    assert np.isfinite(df.iloc[2]["latitude"])
