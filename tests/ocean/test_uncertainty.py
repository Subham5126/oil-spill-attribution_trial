"""Tests for the uncertainty estimation module (DRIFT-06)."""

import pytest
import pandas as pd
import numpy as np

from ocean.drift.uncertainty import calculate_uncertainty, UncertaintyError
from ocean.drift.particle import Particle
from ocean.drift.forecasting import forecast_particles
from ocean.drift.hindcast import hindcast_particles
from ocean.currents import load_currents
from ocean.wind import load_wind
from pathlib import Path


def create_synthetic_trajectories(time_coords: list) -> pd.DataFrame:
    """Helper to create minimal valid trajectory DataFrames."""
    history = []
    for t_str, coords in time_coords:
        t_stamp = pd.Timestamp(t_str)
        for i, (lon, lat, active) in enumerate(coords):
            history.append({
                "particle_id": i + 1,
                "timestamp": t_stamp,
                "longitude": lon,
                "latitude": lat,
                "active": active
            })
    return pd.DataFrame(history)


def test_empty_dataframe_rejected():
    with pytest.raises(UncertaintyError, match="cannot be empty"):
        calculate_uncertainty(pd.DataFrame())


def test_missing_columns_rejected():
    df = pd.DataFrame({"particle_id": [1], "longitude": [10.0]})
    with pytest.raises(UncertaintyError, match="missing required columns"):
        calculate_uncertainty(df)


def test_invalid_coordinates_rejected():
    df = create_synthetic_trajectories([
        ("2025-01-01T00:00:00Z", [(np.nan, 10.0, True)])
    ])
    with pytest.raises(UncertaintyError, match="invalid \\(NaN/Inf\\) coordinates"):
        calculate_uncertainty(df)


def test_invalid_confidence_level_rejected():
    df = create_synthetic_trajectories([
        ("2025-01-01T00:00:00Z", [(10.0, 10.0, True)])
    ])
    with pytest.raises(UncertaintyError, match="confidence_level must be between"):
        calculate_uncertainty(df, confidence_level=-0.1)
    with pytest.raises(UncertaintyError, match="confidence_level must be between"):
        calculate_uncertainty(df, confidence_level=1.5)


def test_missing_timestamp_rejected():
    df = create_synthetic_trajectories([
        ("2025-01-01T00:00:00Z", [(10.0, 10.0, True)])
    ])
    with pytest.raises(UncertaintyError, match="No active particles found at timestamp"):
        calculate_uncertainty(df, timestamp="2026-01-01T00:00:00Z")


def test_single_particle_has_zero_uncertainty():
    df = create_synthetic_trajectories([
        ("2025-01-01T00:00:00Z", [(10.0, 10.0, True)])
    ])
    res = calculate_uncertainty(df)
    assert res.spread_km == 0.0
    assert res.uncertainty_radius_km == 0.0
    assert res.particle_count == 1


def test_identical_particles_have_zero_uncertainty():
    df = create_synthetic_trajectories([
        ("2025-01-01T00:00:00Z", [(10.0, 10.0, True), (10.0, 10.0, True), (10.0, 10.0, True)])
    ])
    res = calculate_uncertainty(df)
    assert res.spread_km == 0.0
    assert res.uncertainty_radius_km == 0.0
    assert res.particle_count == 3


def test_wider_distribution_has_larger_uncertainty():
    tight_df = create_synthetic_trajectories([
        ("2025-01-01T00:00:00Z", [(10.0, 10.0, True), (10.001, 10.0, True), (9.999, 10.0, True)])
    ])
    wide_df = create_synthetic_trajectories([
        ("2025-01-01T00:00:00Z", [(10.0, 10.0, True), (10.1, 10.0, True), (9.9, 10.0, True)])
    ])
    
    tight_res = calculate_uncertainty(tight_df, confidence_level=1.0)
    wide_res = calculate_uncertainty(wide_df, confidence_level=1.0)
    
    assert wide_res.spread_km > tight_res.spread_km
    assert wide_res.uncertainty_radius_km > tight_res.uncertainty_radius_km


def test_particle_order_independence():
    df1 = create_synthetic_trajectories([
        ("2025-01-01T00:00:00Z", [(10.0, 10.0, True), (10.1, 10.1, True), (9.9, 9.9, True)])
    ])
    df2 = create_synthetic_trajectories([
        ("2025-01-01T00:00:00Z", [(9.9, 9.9, True), (10.0, 10.0, True), (10.1, 10.1, True)])
    ])
    
    res1 = calculate_uncertainty(df1)
    res2 = calculate_uncertainty(df2)
    
    assert res1.spread_km == res2.spread_km
    assert res1.uncertainty_radius_km == res2.uncertainty_radius_km


def test_input_dataframe_not_mutated():
    df = create_synthetic_trajectories([
        ("2025-01-01T00:00:00Z", [(10.0, 10.0, True), (10.1, 10.1, True)])
    ])
    original_df = df.copy(deep=True)
    calculate_uncertainty(df)
    
    pd.testing.assert_frame_equal(df, original_df)


@pytest.mark.parametrize(
    ("current_path", "wind_path"),
    [
        (Path("data/sample/copernicus/current_test.nc"), Path("data/sample/era5/wind_test.nc")),
    ]
)
def test_integration_with_forward_drift_forecast(current_path, wind_path):
    """Test integration with DRIFT-04 forward forecasting output."""
    if not current_path.is_file() or not wind_path.is_file():
        pytest.skip("Sample NetCDF files not available")
        
    current_ds = load_currents(current_path)
    wind_ds = load_wind(wind_path)
    
    lon = float(current_ds["longitude"].values.mean())
    lat = float(current_ds["latitude"].values.mean())
    
    start_time = pd.Timestamp(current_ds["time"].values[0]).tz_localize("UTC")
    
    particles = [
        Particle(1, lon, lat),
        Particle(2, lon + 0.01, lat),
        Particle(3, lon - 0.01, lat),
    ]
    
    df = forecast_particles(particles, current_ds, wind_ds, start_time, duration_seconds=3600, timestep_seconds=3600)
    
    # Calculate uncertainty at the latest (forecast) timestamp
    res = calculate_uncertainty(df)
    
    assert res.particle_count == 3
    assert res.spread_km > 0
    assert res.uncertainty_radius_km > 0


@pytest.mark.parametrize(
    ("current_path", "wind_path"),
    [
        (Path("data/sample/copernicus/current_test.nc"), Path("data/sample/era5/wind_test.nc")),
    ]
)
def test_integration_with_backward_hindcast(current_path, wind_path):
    """Test integration with OCEAN-07 hindcast output."""
    if not current_path.is_file() or not wind_path.is_file():
        pytest.skip("Sample NetCDF files not available")
        
    current_ds = load_currents(current_path)
    wind_ds = load_wind(wind_path)
    
    lon = float(current_ds["longitude"].values.mean())
    lat = float(current_ds["latitude"].values.mean())
    
    obs_time = pd.Timestamp(current_ds["time"].values[-1]).tz_localize("UTC")
    
    particles = [
        Particle(1, lon, lat),
        Particle(2, lon + 0.01, lat),
        Particle(3, lon - 0.01, lat),
    ]
    
    df = hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=3600, timestep_seconds=3600)
    
    # Calculate uncertainty at the historical timestamp (which is the oldest/minimum timestamp)
    hist_time = df["timestamp"].min()
    res = calculate_uncertainty(df, timestamp=hist_time)
    
    assert res.particle_count == 3
    assert res.spread_km > 0
    assert res.uncertainty_radius_km > 0
