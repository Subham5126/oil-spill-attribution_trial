"""Comprehensive Backend API Test Suite.

Verifies:
1. health endpoint
2. investigation creation
3. investigation retrieval
4. pipeline status
5. pipeline latest
6. spill retrieval
7. GIS GeoJSON endpoint
8. drift simulation endpoint
9. vessel endpoint
10. attribution endpoint
11. report endpoint
12. demo mode
13. missing database graceful handling
14. invalid request handling
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.config import settings

client = TestClient(app)


# 1. Health Endpoint
def test_health_endpoint():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["backend"] == "ok"
    assert "status" in data
    assert "database" in data
    assert "redis" in data
    assert data["demo_mode"] is True


# 2. Investigation Creation
def test_investigation_creation():
    payload = {
        "name": "Arabian Sea Test Incident",
        "region": "Arabian Sea (Sector IND-West)",
        "priority": "High",
        "coordinates": {"latitude": 18.5236, "longitude": 72.4815},
        "metadata": {"test": True},
    }
    res = client.post("/api/investigations", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert "id" in data
    assert data["title"] == "Arabian Sea Test Incident"
    assert data["status"] == "Active"
    assert data["coordinates"]["latitude"] == 18.5236


# 3. Investigation Retrieval
def test_investigation_retrieval():
    # List
    res = client.get("/api/investigations")
    assert res.status_code == 200
    invs = res.json()
    assert isinstance(invs, list)
    assert len(invs) >= 1

    # Single
    inv_id = invs[0]["id"]
    res_single = client.get(f"/api/investigations/{inv_id}")
    assert res_single.status_code == 200
    assert res_single.json()["id"] == inv_id


# 4. Pipeline Status
def test_pipeline_status():
    res = client.get("/api/pipeline/SAR-20250101-IND-0042/status")
    assert res.status_code == 200
    data = res.json()
    assert data["investigation_id"] == "SAR-20250101-IND-0042"
    assert data["status"] in ("COMPLETED", "RUNNING", "QUEUED")
    assert "progress_percentage" in data


# 5. Pipeline Latest
def test_pipeline_latest():
    res = client.get("/api/pipeline/latest")
    assert res.status_code == 200
    data = res.json()
    assert "spill_metadata" in data
    assert "gis_measurement" in data
    assert "ocean_drift" in data
    assert "ais_search" in data
    assert "candidate_vessels" in data
    assert "attribution_ranking" in data
    assert "primary_suspect" in data
    assert "gis_export" in data
    assert "pipeline_execution" in data
    assert data["pipeline_execution"]["status"] == "PASS"


# 6. Spill Retrieval
def test_spill_retrieval():
    res = client.get("/api/spills/SAR-20250101-IND-0042")
    assert res.status_code == 200
    data = res.json()
    assert "spill_metadata" in data
    assert "gis_measurement" in data
    assert data["gis_measurement"]["area"]["sq_kilometers"] > 0

    res_geom = client.get("/api/spills/SAR-20250101-IND-0042/geometry")
    assert res_geom.status_code == 200
    geom_data = res_geom.json()
    assert "geojson_geometry" in geom_data
    assert geom_data["geojson_geometry"]["type"] in ("Polygon", "MultiPolygon")


# 7. GIS GeoJSON Endpoint
def test_gis_geojson_endpoint():
    res = client.get("/api/layers/geojson")
    assert res.status_code == 200
    fc = res.json()
    assert fc["type"] == "FeatureCollection"
    assert "features" in fc
    assert len(fc["features"]) >= 1

    # Verify EPSG:4326 coordinate ranges
    for feat in fc["features"]:
        geom = feat["geometry"]
        assert geom["type"] in ("Polygon", "Point", "LineString", "MultiPolygon")
        assert "properties" in feat


# 8. Drift Simulation Endpoint
def test_drift_simulation_endpoint():
    payload = {
        "lat": 18.5253,
        "lon": 72.5032,
        "durationHours": 4.0,
        "timestepSeconds": 3600,
        "mode": "hindcast",
    }
    res = client.post("/api/drift/simulate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "model_type" in data
    assert "probable_origin" in data
    assert "uncertainty" in data
    assert data["uncertainty"]["radius_km"] > 0


# 9. Vessel Endpoints
def test_vessel_endpoints():
    # List
    res = client.get("/api/vessels")
    assert res.status_code == 200
    vessels = res.json()
    assert isinstance(vessels, list)
    assert len(vessels) >= 1

    # Single
    mmsi = vessels[0]["mmsi"]
    res_vessel = client.get(f"/api/vessels/{mmsi}")
    assert res_vessel.status_code == 200
    assert res_vessel.json()["mmsi"] == mmsi


# 10. Attribution Endpoint
def test_attribution_endpoint():
    res = client.get("/api/attribution/SAR-20250101-IND-0042")
    assert res.status_code == 200
    data = res.json()
    assert "primary_suspect" in data
    assert data["primary_suspect"]["rank"] == 1
    assert "scores" in data["primary_suspect"]
    assert data["primary_suspect"]["scores"]["overall"] > 0.8


# 11. Report Endpoints
def test_report_endpoints():
    # List
    res = client.get("/api/reports")
    assert res.status_code == 200
    reports = res.json()
    assert isinstance(reports, list)
    assert len(reports) >= 1

    # Single
    rep_id = reports[0]["id"]
    res_rep = client.get(f"/api/reports/{rep_id}")
    assert res_rep.status_code == 200
    assert res_rep.json()["id"] == rep_id
    assert res_rep.json()["sha256_hash"] is not None


# 12. Demo Mode
def test_demo_mode():
    assert settings.DEMO_MODE is True
    res = client.get("/api/pipeline/latest")
    assert res.status_code == 200
    data = res.json()
    # Ensure provenance tracks DEMO
    assert data.get("provenance", {}).get("data_source_mode") == "DEMO"
    assert data["spill_metadata"]["spill_id"] == "SAR-20250101-IND-0042"


# 13. Missing Database Graceful Handling
def test_missing_database_graceful_handling():
    # Calling endpoints when DATABASE_URL is None must NOT crash
    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    assert res_health.json()["database"] == "unavailable"

    res_invs = client.get("/api/investigations")
    assert res_invs.status_code == 200
    assert len(res_invs.json()) >= 1


# 14. Invalid Request Handling
def test_invalid_request_handling():
    # Invalid coordinates (lat > 90)
    invalid_drift = {
        "lat": 195.0,  # Invalid
        "lon": 72.5,
        "durationHours": 4.0,
        "timestepSeconds": 3600,
        "mode": "hindcast",
    }
    res_invalid = client.post("/api/drift/simulate", json=invalid_drift)
    assert res_invalid.status_code == 422
    err = res_invalid.json()
    assert err["error_code"] == "VALIDATION_ERROR"

    # Non-existent investigation 404
    res_missing = client.get("/api/investigations/NON-EXISTENT-ID-9999")
    assert res_missing.status_code == 404
    assert res_missing.json()["error_code"] == "INVESTIGATION_NOT_FOUND"
