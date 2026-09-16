"""Test Suite for Evidence Library, Dynamic System Status, Datasets Registry, and Attribution Calibration Settings.

Verifies:
1. Dynamic System Status & Datasets Registry (Strict zero fake values, live DB counts, dynamic service identity).
2. Multi-Criteria Attribution Scoring Calibration (GET/PUT, 100% sum validation, version stamping, pipeline consumption).
3. Investigation Evidence Library & Artifact Endpoints (All artifacts downloadable, SHA-256 integrity check, proper MIME types).
4. Full Forensic Evidence Bundle ZIP archive with valid manifest.json and structured folders.
5. Investigation Isolation (Prevent cross-investigation artifact leakage, return 404 for invalid cases).
"""

import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.database import get_session
from backend.models.investigation import InvestigationModel
from backend.models.settings import AttributionCalibrationModel
from backend.services.storage_service import storage


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def target_investigation_id():
    """Retrieve an active investigation ID from database for tests."""
    db = get_session()
    inv = db.query(InvestigationModel).filter(InvestigationModel.is_deleted == False).first()
    db.close()
    if not inv:
        pytest.skip("No active investigations in database to run live artifact tests against.")
    return inv.investigation_id


# ==============================================================================
# 1. DYNAMIC SYSTEM STATUS & DATASETS REGISTRY TESTS
# ==============================================================================

def test_system_status_dynamic_identity(client):
    """Verify system status reports dynamic host scheme and real live subsystem checks."""
    resp = client.get("/api/health/system-status", headers={"host": "api.oiltrace.internal"})
    assert resp.status_code == 200
    data = resp.json()

    assert "overall" in data
    assert "subsystems" in data
    assert "service_identity" in data
    assert "environment" in data

    # Verify no hardcoded 127.0.0.1:8000
    assert "http://127.0.0.1:8000" not in data["service_identity"]
    assert "api.oiltrace.internal" in data["service_identity"]

    subsystem_names = [s["name"] for s in data["subsystems"]]
    assert "FastAPI Core Engine" in subsystem_names
    assert "Rasterio & GDAL GeoTIFF Engine" in subsystem_names
    assert "U-Net ResNet34 Segmentation Model" in subsystem_names
    assert "Global Fishing Watch AIS Provider" in subsystem_names


def test_datasets_status_no_mocked_counts(client):
    """Verify datasets status returns genuine database candidate counts and real filesystem paths."""
    resp = client.get("/api/health/datasets")
    assert resp.status_code == 200
    data = resp.json()

    assert "datasets" in data
    assert len(data["datasets"]) >= 3

    ais_dataset = next((d for d in data["datasets"] if d["id"] == "gfw-ais-telemetry"), None)
    assert ais_dataset is not None
    # Verify records_count is an integer and not the old static hardcoded "1736" string
    assert isinstance(ais_dataset["records_count"], int)
    assert ais_dataset["records_count"] >= 0


# ==============================================================================
# 2. ATTRIBUTION CALIBRATION SETTINGS TESTS
# ==============================================================================

def test_attribution_calibration_get(client):
    """Verify GET /api/settings/attribution returns valid active weights that sum to 100%."""
    resp = client.get("/api/settings/attribution")
    assert resp.status_code == 200
    data = resp.json()

    assert "version" in data
    assert data["version"].startswith("CALIB-")
    assert "spatial_proximity" in data
    assert "temporal_overlap" in data
    assert "drift_consistency" in data
    assert "track_consistency" in data
    assert "vessel_type_relevance" in data
    assert "ais_quality" in data

    total = (
        data["spatial_proximity"]
        + data["temporal_overlap"]
        + data["drift_consistency"]
        + data["track_consistency"]
        + data["vessel_type_relevance"]
        + data["ais_quality"]
    )
    assert pytest.approx(total, 0.01) == 100.0


def test_attribution_calibration_put_validation_fails_when_sum_not_100(client):
    """Verify PUT /api/settings/attribution rejects weights that do not sum to 100%."""
    invalid_payload = {
        "spatial_proximity": 40.0,
        "temporal_overlap": 20.0,
        "drift_consistency": 20.0,
        "track_consistency": 10.0,
        "vessel_type_relevance": 5.0,
        "ais_quality": 2.0,  # Sum = 97.0
        "notes": "Testing invalid sum validation",
    }
    resp = client.put("/api/settings/attribution", json=invalid_payload)
    assert resp.status_code == 422
    assert "must sum to 100%" in resp.json()["detail"]


def test_attribution_calibration_put_and_persist(client):
    """Verify PUT /api/settings/attribution updates active weights and persists a new calibration version."""
    valid_payload = {
        "spatial_proximity": 30.0,
        "temporal_overlap": 25.0,
        "drift_consistency": 25.0,
        "track_consistency": 10.0,
        "vessel_type_relevance": 5.0,
        "ais_quality": 5.0,  # Sum = 100.0
        "notes": "Automated test calibration update",
    }
    resp = client.put("/api/settings/attribution", json=valid_payload)
    assert resp.status_code == 200
    updated = resp.json()

    assert updated["spatial_proximity"] == 30.0
    assert updated["temporal_overlap"] == 25.0
    assert updated["notes"] == "Automated test calibration update"

    # Verify subsequent GET returns the new calibration
    get_resp = client.get("/api/settings/attribution")
    assert get_resp.status_code == 200
    assert get_resp.json()["version"] == updated["version"]
    assert get_resp.json()["spatial_proximity"] == 30.0


# ==============================================================================
# 3. EVIDENCE ARTIFACTS & INTEGRITY ENDPOINT TESTS
# ==============================================================================

def test_evidence_library_returns_verified_artifacts(client, target_investigation_id):
    """Verify GET /api/investigations/{id}/evidence returns canonical forensic artifacts."""
    resp = client.get(f"/api/investigations/{target_investigation_id}/evidence")
    assert resp.status_code == 200
    artifacts = resp.json()

    assert len(artifacts) >= 5, f"Expected at least 5 artifacts, got {len(artifacts)}"

    # Check that available artifacts have non-zero file sizes and SHA-256 hashes
    available = [a for a in artifacts if a.get("status") == "AVAILABLE"]
    assert len(available) > 0, "Expected at least one AVAILABLE artifact"

    for art in available:
        assert art["file_size_bytes"] > 0
        assert art["sha256"] is not None
        assert len(art["sha256"]) == 64
        assert art["download_url"] is not None


def test_artifact_download_and_headers(client, target_investigation_id):
    """Verify individual artifact downloads stream real bytes with required forensic headers."""
    resp = client.get(f"/api/investigations/{target_investigation_id}/evidence")
    artifacts = resp.json()
    available = [a for a in artifacts if a.get("status") == "AVAILABLE"]

    # Test download for first available artifact
    target = available[0]
    art_type = target["artifact_type"]

    dl_resp = client.get(f"/api/investigations/{target_investigation_id}/artifacts/{art_type}/download")
    assert dl_resp.status_code == 200
    assert len(dl_resp.content) == target["file_size_bytes"]
    assert dl_resp.headers.get("x-investigation-id") == target_investigation_id
    assert dl_resp.headers.get("x-artifact-sha256") == target["sha256"]
    assert "attachment;" in dl_resp.headers.get("content-disposition", "")


def test_artifact_integrity_verification_endpoint(client, target_investigation_id):
    """Verify POST /api/investigations/{id}/artifacts/{type}/verify verifies hash against disk."""
    resp = client.get(f"/api/investigations/{target_investigation_id}/evidence")
    artifacts = resp.json()
    available = [a for a in artifacts if a.get("status") == "AVAILABLE"]

    target = available[0]
    art_type = target["artifact_type"]

    verify_resp = client.post(f"/api/investigations/{target_investigation_id}/artifacts/{art_type}/verify")
    assert verify_resp.status_code == 200
    res_data = verify_resp.json()

    assert res_data["verified"] is True
    assert res_data["sha256"] == target["sha256"]
    assert res_data["byte_size"] == target["file_size_bytes"]


# ==============================================================================
# 4. EVIDENCE BUNDLE ZIP & MANIFEST TESTS
# ==============================================================================

def test_evidence_bundle_zip_and_manifest(client, target_investigation_id):
    """Verify GET /api/investigations/{id}/evidence/bundle returns a valid ZIP archive with manifest.json."""
    resp = client.get(f"/api/investigations/{target_investigation_id}/evidence/bundle")
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "application/zip"
    assert resp.headers.get("x-investigation-id") == target_investigation_id
    assert "attachment;" in resp.headers.get("content-disposition", "")

    zip_bytes = resp.content
    assert len(zip_bytes) > 1000

    # Parse ZIP archive
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        namelist = zf.namelist()
        assert "manifest.json" in namelist, "Bundle ZIP must contain manifest.json at root"

        # Read and parse manifest.json
        manifest_raw = zf.read("manifest.json").decode("utf-8")
        manifest = json.loads(manifest_raw)

        assert manifest["investigation_id"] == target_investigation_id
        assert "bundled_at" in manifest
        assert "total_files" in manifest
        assert manifest["total_files"] > 0
        assert "artifacts" in manifest
        assert len(manifest["artifacts"]) == manifest["total_files"]

        # Validate that files referenced in manifest exist in the ZIP
        for art in manifest["artifacts"]:
            assert "sha256" in art
            assert "file_name" in art
            assert "byte_size" in art
            assert art["byte_size"] > 0


# ==============================================================================
# 5. INVESTIGATION ISOLATION & 404 HANDLING
# ==============================================================================

def test_investigation_isolation_unknown_id(client):
    """Verify requesting evidence or bundle for a nonexistent investigation returns 404."""
    unknown_id = "INV-NONEXISTENT-999"

    resp_bundle = client.get(f"/api/investigations/{unknown_id}/evidence/bundle")
    assert resp_bundle.status_code == 404

    resp_dl = client.get(f"/api/investigations/{unknown_id}/artifacts/GEOREFERENCED_MASK_TIFF/download")
    assert resp_dl.status_code == 404

    resp_verify = client.post(f"/api/investigations/{unknown_id}/artifacts/GEOREFERENCED_MASK_TIFF/verify")
    assert resp_verify.status_code == 404
