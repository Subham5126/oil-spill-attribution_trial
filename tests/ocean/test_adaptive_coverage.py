"""Unit and regression tests for M4 adaptive spatial coverage and boundary condition handling."""

from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from ocean.copernicus.client import compute_adaptive_aoi, CopernicusClient
from ocean.copernicus.cache import OceanDataCache, CachedDatasetMetadata
from ocean.currents import load_currents
from ocean.drift.particle import Particle, ParticleModelError, SpatialBoundaryConditionError
from ocean.drift.hindcast import hindcast_particles


# ---------------------------------------------------------------------------
# Test 1: Geodesic Drift Envelope Calculation
# ---------------------------------------------------------------------------
def test_drift_envelope_calculation():
    """Verify compute_adaptive_aoi produces physically consistent geodesic bounding boxes."""
    lat, lon = 18.8822, 39.2876
    lat_min, lat_max, lon_min, lon_max = compute_adaptive_aoi(
        lat, lon, hindcast_hours=72, forecast_hours=24, max_current_speed_m_s=1.0, safety_factor=1.5
    )

    # 96 hours total * 3600s * 1.0 m/s * 1.5 = 518,400 meters (~4.66 deg lat)
    assert lat_min < lat - 1.0
    assert lat_max > lat + 1.0
    assert lon_min < lon - 1.0
    assert lon_max > lon + 1.0

    # Ensure latitude bounds within global coordinates
    assert -80.0 <= lat_min <= 90.0
    assert -80.0 <= lat_max <= 90.0
    assert -180.0 <= lon_min <= 180.0
    assert -180.0 <= lon_max <= 180.0


# ---------------------------------------------------------------------------
# Test 2: Spatial Boundary Excursion Detection
# ---------------------------------------------------------------------------
def test_spatial_boundary_condition_detected():
    """Verify that when a particle trajectory reaches the domain edge, SpatialBoundaryConditionError is raised."""
    # Use the smaller subset which is known to be too small for a 72h hindcast from 18.8822
    small_subset = Path("data/cache/ocean/cmems_mod_glo_phy_my_0_083deg_P1D_m_18.13_19.63_38.54_40.04_20191011_20191015.nc")
    if not small_subset.exists():
        pytest.skip("Small subset file not present in local cache")

    curr_ds = load_currents(small_subset, select_surface=True)
    obs_time = datetime(2019, 10, 14, 3, 15, 3, tzinfo=timezone.utc)
    c_lat, c_lon = 18.8822, 39.2876

    wind_ds = xr.Dataset(
        {
            "u10": (curr_ds["uo"].dims, np.zeros_like(curr_ds["uo"].values), {"units": "m/s"}),
            "v10": (curr_ds["vo"].dims, np.zeros_like(curr_ds["vo"].values), {"units": "m/s"}),
        },
        coords=curr_ds.coords,
    )

    with pytest.raises(SpatialBoundaryConditionError) as exc_info:
        hindcast_particles(
            [Particle(particle_id=1, latitude=c_lat, longitude=c_lon)],
            curr_ds,
            wind_ds,
            obs_time,
            72 * 3600,
            3600,
            windage=0.0,
        )

    err = exc_info.value
    assert err.dimension == "latitude"
    assert err.query_value < float(curr_ds.latitude.min().values)
    assert err.step > 0


# ---------------------------------------------------------------------------
# Test 3: Sufficiently Large Dataset Completes Without Expansion
# ---------------------------------------------------------------------------
def test_complete_hindcast_on_large_dataset():
    """Verify that red_sea_current_2019.nc (17.5-20.0 N) completes the full 72h hindcast."""
    large_subset = Path("data/sample/copernicus/red_sea_current_2019.nc")
    if not large_subset.exists():
        pytest.skip("red_sea_current_2019.nc not present in sample dir")

    curr_ds = load_currents(large_subset, select_surface=True)
    obs_time = datetime(2019, 10, 14, 3, 15, 3, tzinfo=timezone.utc)
    c_lat, c_lon = 18.8822, 39.2876

    wind_ds = xr.Dataset(
        {
            "u10": (curr_ds["uo"].dims, np.zeros_like(curr_ds["uo"].values), {"units": "m/s"}),
            "v10": (curr_ds["vo"].dims, np.zeros_like(curr_ds["vo"].values), {"units": "m/s"}),
        },
        coords=curr_ds.coords,
    )

    df_hindcast = hindcast_particles(
        [Particle(particle_id=1, latitude=c_lat, longitude=c_lon)],
        curr_ds,
        wind_ds,
        obs_time,
        72 * 3600,
        3600,
        windage=0.0,
    )

    assert len(df_hindcast) == 73  # Initial point + 72 hourly steps
    # Verify coordinates remained strictly inside dataset bounds
    assert float(df_hindcast["latitude"].min()) >= float(curr_ds.latitude.min().values)
    assert float(df_hindcast["latitude"].max()) <= float(curr_ds.latitude.max().values)
    assert float(df_hindcast["longitude"].min()) >= float(curr_ds.longitude.min().values)
    assert float(df_hindcast["longitude"].max()) <= float(curr_ds.longitude.max().values)


# ---------------------------------------------------------------------------
# Test 4: Cache Spatial Prioritization (Prefers Larger Enclosing Dataset)
# ---------------------------------------------------------------------------
def test_cache_prefers_larger_enclosing_dataset():
    """Verify that when expanded coverage is requested, cache selects red_sea_current_2019.nc instead of smaller subset."""
    cache = OceanDataCache(
        cache_dir=Path("data/cache/ocean"),
        sample_dir=Path("data/sample/copernicus"),
    )

    # Request an expanded bounding box [17.8, 19.8] that requires more than the 0.75 deg subset
    matched = cache.find_cached_dataset(
        lat_min=17.8,
        lat_max=19.8,
        lon_min=38.8,
        lon_max=40.0,
        time_min=datetime(2019, 10, 11, 3, 15, 3, tzinfo=timezone.utc),
        time_max=datetime(2019, 10, 15, 3, 15, 3, tzinfo=timezone.utc),
    )

    assert matched is not None
    # Must match red_sea_current_2019.nc because it covers 17.5..20.0
    assert "red_sea_current_2019" in matched.name


# ---------------------------------------------------------------------------
# Test 5: Cache Rejection of Too-Small Dataset
# ---------------------------------------------------------------------------
def test_cache_rejects_smaller_subset_for_large_request():
    """Verify that requesting bounds outside a subset's coverage correctly rejects the subset."""
    small_subset = Path("data/cache/ocean/cmems_mod_glo_phy_my_0_083deg_P1D_m_18.13_19.63_38.54_40.04_20191011_20191015.nc")
    if not small_subset.exists():
        pytest.skip("Small subset file not present in local cache")

    meta = CachedDatasetMetadata(
        path=small_subset,
        lat_min=18.167,
        lat_max=19.583,
        lon_min=38.583,
        lon_max=40.0,
        time_min=datetime(2019, 10, 11, 0, 0, tzinfo=timezone.utc),
        time_max=datetime(2019, 10, 16, 0, 0, tzinfo=timezone.utc),
        variables=("uo", "vo"),
    )

    # Request requiring south down to 17.8 deg
    assert not meta.contains(
        lat_min=17.8,
        lat_max=19.6,
        lon_min=38.6,
        lon_max=40.0,
        time_min=datetime(2019, 10, 11, 3, 0, tzinfo=timezone.utc),
        time_max=datetime(2019, 10, 15, 3, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Test 6: Temporal Unavailable Condition Does Not Trigger Spatial Loop
# ---------------------------------------------------------------------------
def test_temporal_unavailable_no_spatial_retry():
    """Verify that temporal mismatch produces TEMPORAL_UNAVAILABLE immediately without looping."""
    client = CopernicusClient(
        cache_dir=Path("data/cache/ocean"),
        sample_dir=Path("data/sample/copernicus"),
    )
    # A date far in the future
    future_time = datetime(2099, 1, 1, 0, 0, tzinfo=timezone.utc)
    res = client.acquire_currents(lat=18.88, lon=39.28, obs_time=future_time)
    assert res.status == "TEMPORAL_UNAVAILABLE"
