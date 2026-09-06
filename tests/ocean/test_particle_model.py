import pytest
import numpy as np
import pandas as pd
import xarray as xr
from pathlib import Path

from ocean.drift import Particle, ParticleModelError, simulate_particles
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


def test_zero_current_zero_wind_produces_stationary_particles(stationary_env):
    current_ds, wind_ds = stationary_env
    particles = [Particle(1, 10.0, 10.0)]
    start_time = pd.Timestamp("2025-01-01 00:00:00+00:00")
    
    df = simulate_particles(particles, current_ds, wind_ds, start_time, num_steps=2)
    
    assert len(df) == 3 # 0, 1, 2
    assert (df["longitude"] == 10.0).all()
    assert (df["latitude"] == 10.0).all()

def test_pure_eastward_current_moves_longitude_eastward(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    start_time = pd.Timestamp("2025-01-01 00:00:00+00:00")
    
    df = simulate_particles(particles, current_ds, wind_ds, start_time, num_steps=1)
    
    assert df.iloc[1]["longitude"] > 10.0
    assert df.iloc[1]["latitude"] == 10.0

def test_pure_northward_current_moves_latitude_northward(northward_env):
    current_ds, wind_ds = northward_env
    particles = [Particle(1, 10.0, 10.0)]
    start_time = pd.Timestamp("2025-01-01 00:00:00+00:00")
    
    df = simulate_particles(particles, current_ds, wind_ds, start_time, num_steps=1)
    
    assert df.iloc[1]["longitude"] == 10.0
    assert df.iloc[1]["latitude"] > 10.0

def test_windage_contributes_correctly(mixed_env):
    current_ds, wind_ds = mixed_env
    particles = [Particle(1, 10.0, 10.0)]
    start_time = pd.Timestamp("2025-01-01 00:00:00+00:00")
    
    # current = 1.0, wind = 10.0, windage = 0.03 => oil velocity = 1.3 m/s
    df_with_wind = simulate_particles(particles, current_ds, wind_ds, start_time, num_steps=1, windage=0.03)
    
    # current = 1.0, wind = 10.0, windage = 0.0 => oil velocity = 1.0 m/s
    df_no_wind = simulate_particles(particles, current_ds, wind_ds, start_time, num_steps=1, windage=0.0)
    
    dist_with_wind = df_with_wind.iloc[1]["longitude"] - 10.0
    dist_no_wind = df_no_wind.iloc[1]["longitude"] - 10.0
    
    # Should move exactly 1.3x faster
    assert np.isclose(dist_with_wind / dist_no_wind, 1.3)

def test_numerical_displacement_accuracy(eastward_env):
    current_ds, wind_ds = eastward_env
    # Current is 1 m/s eastward
    particles = [Particle(1, 10.0, 0.0)] # at equator
    start_time = pd.Timestamp("2025-01-01 00:00:00+00:00")
    
    # 3600 seconds * 1 m/s = 3600 meters
    df = simulate_particles(particles, current_ds, wind_ds, start_time, num_steps=1, timestep_seconds=3600)
    
    R = 6371000.0
    expected_dlon = np.degrees(3600.0 / R)
    
    actual_dlon = df.iloc[1]["longitude"] - 10.0
    assert np.isclose(actual_dlon, expected_dlon, rtol=1e-5)

def test_one_hour_timestep_advances_exactly_one_hour(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    start_time = pd.Timestamp("2025-01-01 00:00:00+00:00")
    
    df = simulate_particles(particles, current_ds, wind_ds, start_time, num_steps=1, timestep_seconds=3600)
    
    assert df.iloc[1]["timestamp"] - df.iloc[0]["timestamp"] == pd.Timedelta(seconds=3600)

def test_multiple_timesteps_cumulative_trajectory(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    start_time = pd.Timestamp("2025-01-01 00:00:00+00:00")
    
    df = simulate_particles(particles, current_ds, wind_ds, start_time, num_steps=3)
    
    assert len(df) == 4
    lons = df["longitude"].values
    assert lons[0] < lons[1] < lons[2] < lons[3]
    
    # Since latitude is constant (pure eastward at constant lat), displacement should be perfectly linear
    assert np.isclose(lons[3] - lons[2], lons[1] - lons[0])

def test_multiple_particles_simulated_independently(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0), Particle(2, 10.0, 20.0)]
    start_time = pd.Timestamp("2025-01-01 00:00:00+00:00")
    
    df = simulate_particles(particles, current_ds, wind_ds, start_time, num_steps=1)
    
    assert len(df) == 4 # 2 particles * 2 steps
    
    # Particle 2 is at higher latitude, so it moves more in degrees longitude for the same meters
    p1 = df[df["particle_id"] == 1]
    p2 = df[df["particle_id"] == 2]
    
    dlon1 = p1.iloc[1]["longitude"] - p1.iloc[0]["longitude"]
    dlon2 = p2.iloc[1]["longitude"] - p2.iloc[0]["longitude"]
    
    assert dlon2 > dlon1 # cosine(20) < cosine(10), so dividing by a smaller number gives a larger degree change

def test_particle_ids_and_ordering_preserved(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(10, 10.0, 10.0), Particle(5, 10.0, 10.0)]
    start_time = pd.Timestamp("2025-01-01 00:00:00+00:00")
    
    df = simulate_particles(particles, current_ds, wind_ds, start_time, num_steps=1)
    
    assert df.iloc[0]["particle_id"] == 10
    assert df.iloc[1]["particle_id"] == 5
    assert df.iloc[2]["particle_id"] == 10
    assert df.iloc[3]["particle_id"] == 5

def test_utc_timestamps_remain_utc(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    start_time = pd.Timestamp("2025-01-01 00:00:00+00:00")
    
    df = simulate_particles(particles, current_ds, wind_ds, start_time, num_steps=1)
    
    assert df.iloc[0]["timestamp"].tz.tzname(None) == "UTC"
    assert df.iloc[1]["timestamp"].tz.tzname(None) == "UTC"

def test_ist_input_produces_equivalent_utc(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    
    start_utc = pd.Timestamp("2025-01-01 00:00:00+00:00")
    start_ist = pd.Timestamp("2025-01-01 05:30:00+05:30")
    
    df_utc = simulate_particles(particles, current_ds, wind_ds, start_utc, num_steps=1)
    df_ist = simulate_particles(particles, current_ds, wind_ds, start_ist, num_steps=1)
    
    pd.testing.assert_frame_equal(df_utc, df_ist)

def test_invalid_timestep_raises_error(eastward_env):
    current_ds, wind_ds = eastward_env
    with pytest.raises(ParticleModelError, match="timestep_seconds must be greater than 0"):
        simulate_particles([Particle(1, 10.0, 10.0)], current_ds, wind_ds, pd.Timestamp("2025-01-01 00:00:00+00:00"), 1, 0)
    
    with pytest.raises(ParticleModelError, match="timestep_seconds must be greater than 0"):
        simulate_particles([Particle(1, 10.0, 10.0)], current_ds, wind_ds, pd.Timestamp("2025-01-01 00:00:00+00:00"), 1, -3600)

def test_invalid_latitude_raises_error(eastward_env):
    current_ds, wind_ds = eastward_env
    with pytest.raises(ParticleModelError, match="between -90 and 90"):
        simulate_particles([Particle(1, 10.0, 95.0)], current_ds, wind_ds, pd.Timestamp("2025-01-01 00:00:00+00:00"), 1)

def test_empty_particles_raises_error(eastward_env):
    current_ds, wind_ds = eastward_env
    with pytest.raises(ParticleModelError, match="cannot be empty"):
        simulate_particles([], current_ds, wind_ds, pd.Timestamp("2025-01-01 00:00:00+00:00"), 1)

def test_invalid_windage_raises_error(eastward_env):
    current_ds, wind_ds = eastward_env
    with pytest.raises(ParticleModelError, match="finite, non-negative"):
        simulate_particles([Particle(1, 10.0, 10.0)], current_ds, wind_ds, pd.Timestamp("2025-01-01 00:00:00+00:00"), 1, windage=-0.1)

def test_missing_variables_raise_error(eastward_env):
    current_ds, wind_ds = eastward_env
    
    bad_current = current_ds.drop_vars("uo")
    with pytest.raises(ParticleModelError, match="Missing required current variables"):
        simulate_particles([Particle(1, 10.0, 10.0)], bad_current, wind_ds, pd.Timestamp("2025-01-01 00:00:00+00:00"), 1)
        
    bad_wind = wind_ds.drop_vars("u10")
    with pytest.raises(ParticleModelError, match="Missing required wind variables"):
        simulate_particles([Particle(1, 10.0, 10.0)], current_ds, bad_wind, pd.Timestamp("2025-01-01 00:00:00+00:00"), 1)

def test_nan_values_raise_error(eastward_env):
    current_ds, wind_ds = eastward_env
    current_ds["uo"][:] = np.nan
    with pytest.raises(ParticleModelError, match="Environmental interpolation failed"):
        simulate_particles([Particle(1, 10.0, 10.0)], current_ds, wind_ds, pd.Timestamp("2025-01-01 00:00:00+00:00"), 1)

def test_out_of_domain_query_handled_by_policy(eastward_env):
    current_ds, wind_ds = eastward_env
    # Dataset domain is 0 to 20 for lat/lon. Query at 50 is out of domain.
    with pytest.raises(ParticleModelError, match="Environmental interpolation failed"):
        simulate_particles([Particle(1, 50.0, 50.0)], current_ds, wind_ds, pd.Timestamp("2025-01-01 00:00:00+00:00"), 1)

def test_original_input_not_mutated(eastward_env):
    current_ds, wind_ds = eastward_env
    particles = [Particle(1, 10.0, 10.0)]
    simulate_particles(particles, current_ds, wind_ds, pd.Timestamp("2025-01-01 00:00:00+00:00"), 1)
    
    assert particles[0].longitude == 10.0
    assert particles[0].latitude == 10.0

def test_repeated_runs_identical_trajectories(eastward_env):
    current_ds, wind_ds = eastward_env
    particles1 = [Particle(1, 10.0, 10.0)]
    particles2 = [Particle(1, 10.0, 10.0)]
    start_time = pd.Timestamp("2025-01-01 00:00:00+00:00")
    
    df1 = simulate_particles(particles1, current_ds, wind_ds, start_time, num_steps=2)
    df2 = simulate_particles(particles2, current_ds, wind_ds, start_time, num_steps=2)
    
    pd.testing.assert_frame_equal(df1, df2)

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
    
    # Find a valid middle point
    lon = float(current_ds["longitude"].values.mean())
    lat = float(current_ds["latitude"].values.mean())
    start_time = pd.Timestamp(current_ds["time"].values[len(current_ds["time"]) // 2]).tz_localize("UTC")
    
    particles = [Particle(1, lon, lat)]
    
    df = simulate_particles(particles, current_ds, wind_ds, start_time, num_steps=3, timestep_seconds=3600)
    
    assert len(df) == 4
    assert df.iloc[0]["longitude"] == lon
    assert df.iloc[0]["latitude"] == lat
    
    # Make sure it actually moved
    assert df.iloc[3]["longitude"] != lon or df.iloc[3]["latitude"] != lat
    assert df["timestamp"].iloc[0].tz.tzname(None) == "UTC"
