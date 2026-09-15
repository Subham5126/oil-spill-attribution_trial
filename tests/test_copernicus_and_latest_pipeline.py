"""Tests for Copernicus CMEMS availability service and /api/pipeline/latest endpoint."""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from ocean.copernicus import (
    CopernicusAvailabilityService,
    CopernicusStatus,
    get_copernicus_availability_service,
)
from backend.schemas.pipeline import EndToEndResultResponse


@pytest.fixture
def client():
    return TestClient(app)


def test_copernicus_availability_global():
    """Global (unscoped) check should detect local NetCDF cache."""
    service = get_copernicus_availability_service()
    result = service.check_availability()
    assert result.status in (CopernicusStatus.CACHE_AVAILABLE, CopernicusStatus.READY)
    assert result.total_indexed_files >= 11
    assert result.is_cached is True


def test_copernicus_availability_persian_gulf_2017():
    """Historical Persian Gulf 2017 observation should match local NetCDF cache."""
    service = get_copernicus_availability_service()
    obs_time = datetime(2017, 3, 11, 2, 15, 11, tzinfo=timezone.utc)
    lat = 25.5
    lon = 54.5

    result = service.check_availability(obs_time=obs_time, lat=lat, lon=lon)
    assert result.status == CopernicusStatus.READY
    assert result.is_cached is True
    assert result.matched_file == "persian_gulf_current_2017.nc"
    assert result.spatial_bounds is not None


def test_copernicus_availability_out_of_bounds():
    """Coordinates outside the global domain [-80, 90] should return NO_COMPATIBLE_DATA."""
    service = get_copernicus_availability_service()
    obs_time = datetime(2020, 1, 1, tzinfo=timezone.utc)

    # Invalid latitude
    res_lat = service.check_availability(obs_time=obs_time, lat=95.0, lon=50.0)
    assert res_lat.status == CopernicusStatus.NO_COMPATIBLE_DATA

    # Date before CMEMS reanalysis baseline (1993)
    pre_1993 = datetime(1985, 6, 15, tzinfo=timezone.utc)
    res_time = service.check_availability(obs_time=pre_1993, lat=25.0, lon=55.0)
    assert res_time.status == CopernicusStatus.NO_COMPATIBLE_DATA


def test_copernicus_availability_simulated_errors():
    """Simulated errors verify standardized status mapping."""
    service = get_copernicus_availability_service()
    res_net = service.check_availability(simulate_error="NETWORK_ERROR")
    assert res_net.status == CopernicusStatus.NETWORK_ERROR

    res_auth = service.check_availability(simulate_error="AUTHENTICATION_REQUIRED")
    assert res_auth.status == CopernicusStatus.AUTHENTICATION_REQUIRED

    res_temp = service.check_availability(simulate_error="TEMPORARILY_UNAVAILABLE")
    assert res_temp.status == CopernicusStatus.TEMPORARILY_UNAVAILABLE


def test_copernicus_dataset_inventory():
    """Inventory should return metadata for all 11 indexed datasets."""
    service = get_copernicus_availability_service()
    inv = service.get_dataset_inventory()
    assert len(inv) >= 11
    filenames = [item["filename"] for item in inv]
    assert "persian_gulf_current_2017.nc" in filenames
    assert "red_sea_current_2019.nc" in filenames


def test_health_system_status_endpoint(client):
    """System status endpoint must report Copernicus as Operational and not false 'Unavailable'."""
    response = client.get("/api/health/system-status")
    assert response.status_code == 200
    data = response.json()
    assert data["overall"] in ("Operational", "Warning")

    copernicus_sub = next(
        (s for s in data["subsystems"] if "Copernicus" in s["name"]), None
    )
    assert copernicus_sub is not None
    assert copernicus_sub["status"] in ("Operational", "Operational (Remote)")
    assert "NetCDF grid files" in copernicus_sub["details"]


def test_health_datasets_endpoint(client):
    """Datasets endpoint must report Copernicus records count reflecting real NetCDF files."""
    response = client.get("/api/health/datasets")
    assert response.status_code == 200
    data = response.json()

    cop_dataset = next(
        (d for d in data["datasets"] if "copernicus" in d["id"]), None
    )
    assert cop_dataset is not None
    assert cop_dataset["records_count"] >= 11
    assert cop_dataset["status"] == "Operational"
    assert cop_dataset["verified"] is True


def test_get_latest_pipeline_result_schema(client):
    """GET /api/pipeline/latest must return 200 with complete EndToEndResultResponse schema."""
    response = client.get("/api/pipeline/latest")
    assert response.status_code == 200
    data = response.json()

    # Validate against strict Pydantic model
    validated = EndToEndResultResponse.model_validate(data)
    assert validated.spill_metadata is not None
    assert validated.gis_measurement is not None
    assert validated.gis_measurement.bounding_box.min_lon is not None
    assert validated.ocean_drift is not None
    assert validated.ocean_drift.probable_origin is not None
    assert validated.pipeline_execution is not None
    assert validated.pipeline_execution.execution_timestamp is not None
    assert len(validated.pipeline_execution.execution_timestamp) > 5


def test_get_pipeline_result_by_id_and_isolation(client):
    """Investigation result endpoint should return valid schema and maintain investigation isolation."""
    # Retrieve latest to get a known valid investigation ID
    r_latest = client.get("/api/pipeline/latest")
    assert r_latest.status_code == 200
    inv_id = r_latest.json().get("investigation_id") or "INV-2026-47A3D8"

    response = client.get(f"/api/pipeline/{inv_id}")
    assert response.status_code == 200
    data = response.json()

    validated = EndToEndResultResponse.model_validate(data)
    assert validated.spill_metadata.spill_id == inv_id
    assert validated.pipeline_execution.status in ("COMPLETED", "PASS", "PENDING")
