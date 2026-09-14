"""Unit and integration tests for Copernicus dataset selection and error handling."""

from datetime import datetime, timezone
import pytest

from ocean.copernicus import (
    CopernicusClient,
    COPERNICUS_MULTIYEAR_DAILY,
    COPERNICUS_ANALYSISFORECAST_DAILY,
    SpatialUnavailableError,
    TemporalUnavailableError,
    InsufficientTimeWindowError,
)
from backend.adapters.ocean_adapter import OceanAdapter


def test_test1_00052_persian_gulf_multiyear_selection():
    """TEST 1: Scene 00052 (2017-03-11, Persian Gulf) -> MULTIYEAR dataset."""
    client = CopernicusClient()
    start_time = datetime(2017, 3, 8, 0, 0, 0, tzinfo=timezone.utc)
    end_time = datetime(2017, 3, 12, 0, 0, 0, tzinfo=timezone.utc)
    lat, lon = 25.6238, 54.6108

    dataset = client.select_dataset(lat, lon, start_time, end_time)
    assert dataset.dataset_id == COPERNICUS_MULTIYEAR_DAILY.dataset_id
    assert dataset.product_id == "GLOBAL_MULTIYEAR_PHY_001_030"
    assert dataset.temporal_coverage_type == "MULTIYEAR"


def test_test2_00643_red_sea_multiyear_selection():
    """TEST 2: Scene 00643 (2019-10-14, Red Sea) -> MULTIYEAR dataset."""
    client = CopernicusClient()
    start_time = datetime(2019, 10, 11, 0, 0, 0, tzinfo=timezone.utc)
    end_time = datetime(2019, 10, 15, 0, 0, 0, tzinfo=timezone.utc)
    lat, lon = 18.23, 39.52

    dataset = client.select_dataset(lat, lon, start_time, end_time)
    assert dataset.dataset_id == COPERNICUS_MULTIYEAR_DAILY.dataset_id
    assert dataset.product_id == "GLOBAL_MULTIYEAR_PHY_001_030"
    assert dataset.temporal_coverage_type == "MULTIYEAR"


def test_test3_north_sea_analysis_forecast_selection():
    """TEST 3: North Sea Investigation (2026-09-12, ~55.0653°N, 5.7436°E) -> ANALYSIS/FORECAST dataset."""
    client = CopernicusClient()
    start_time = datetime(2026, 9, 9, 0, 0, 0, tzinfo=timezone.utc)
    end_time = datetime(2026, 9, 13, 0, 0, 0, tzinfo=timezone.utc)
    lat, lon = 55.0653, 5.7436

    dataset = client.select_dataset(lat, lon, start_time, end_time)
    assert dataset.dataset_id == COPERNICUS_ANALYSISFORECAST_DAILY.dataset_id
    assert dataset.product_id == "GLOBAL_ANALYSISFORECAST_PHY_001_024"
    assert dataset.temporal_coverage_type == "ANALYSIS_FORECAST"


def test_spatial_out_of_bounds_error():
    """Verify that coordinates outside global limits raise SPATIAL_UNAVAILABLE."""
    client = CopernicusClient()
    start_time = datetime(2017, 3, 8, tzinfo=timezone.utc)
    end_time = datetime(2017, 3, 12, tzinfo=timezone.utc)

    with pytest.raises(SpatialUnavailableError) as exc_info:
        client.select_dataset(95.0, 50.0, start_time, end_time)
    assert exc_info.value.code == "SPATIAL_UNAVAILABLE"


def test_temporal_prior_to_archive_error():
    """Verify that dates prior to 1993 raise TEMPORAL_UNAVAILABLE."""
    client = CopernicusClient()
    start_time = datetime(1985, 5, 1, tzinfo=timezone.utc)
    end_time = datetime(1985, 5, 5, tzinfo=timezone.utc)

    with pytest.raises(TemporalUnavailableError) as exc_info:
        client.select_dataset(55.0, 5.0, start_time, end_time)
    assert exc_info.value.code == "TEMPORAL_UNAVAILABLE"


def test_temporal_far_future_error():
    """Verify that dates beyond forecast horizon raise TEMPORAL_UNAVAILABLE."""
    client = CopernicusClient()
    start_time = datetime(2035, 1, 1, tzinfo=timezone.utc)
    end_time = datetime(2035, 1, 5, tzinfo=timezone.utc)

    with pytest.raises(TemporalUnavailableError) as exc_info:
        client.select_dataset(55.0, 5.0, start_time, end_time)
    assert exc_info.value.code == "TEMPORAL_UNAVAILABLE"


def test_adapter_test1_00052_persian_gulf():
    """Verify OceanAdapter acquires Persian Gulf currents NetCDF and selects MULTIYEAR."""
    adapter = OceanAdapter()
    res = adapter.acquire_ocean_currents(25.6238, 54.6108, datetime(2017, 3, 11, 2, 15, tzinfo=timezone.utc))
    assert res.status == "COMPLETED"
    assert res.file_path is not None
    assert "persian_gulf" in res.file_path.name
    assert res.dataset.dataset_id == COPERNICUS_MULTIYEAR_DAILY.dataset_id
    assert res.is_cached is True


def test_adapter_test2_00643_red_sea():
    """Verify OceanAdapter acquires Red Sea currents NetCDF and selects MULTIYEAR."""
    adapter = OceanAdapter()
    res = adapter.acquire_ocean_currents(18.23, 39.52, datetime(2019, 10, 14, 3, 15, tzinfo=timezone.utc))
    assert res.status == "COMPLETED"
    assert res.file_path is not None
    assert "red_sea" in res.file_path.name
    assert res.dataset.dataset_id == COPERNICUS_MULTIYEAR_DAILY.dataset_id
    assert res.is_cached is True


def test_adapter_test3_north_sea_forecast():
    """Verify OceanAdapter acquires North Sea currents and selects ANALYSIS/FORECAST."""
    adapter = OceanAdapter()
    res = adapter.acquire_ocean_currents(55.0653, 5.7436, datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc))
    assert res.status == "COMPLETED"
    assert res.file_path is not None
    assert res.dataset.dataset_id == COPERNICUS_ANALYSISFORECAST_DAILY.dataset_id
    assert res.dataset.product_id == "GLOBAL_ANALYSISFORECAST_PHY_001_024"
    assert res.file_path.exists()
