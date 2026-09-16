"""Test suite for investigation artifact endpoints and dynamic SAR rendering."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture(scope="module")
def client():
    from backend.core.database import get_session
    from backend.models.investigation import InvestigationModel
    from datetime import datetime, timezone

    db = get_session()
    if db:
        inv = db.query(InvestigationModel).filter_by(investigation_id="INV-2017-00052").first()
        if not inv:
            inv = InvestigationModel(
                investigation_id="INV-2017-00052",
                title="Sentinel-1 SAR Detection // Persian Gulf (Sirri Oil Field)",
                status="Completed",
                priority="High",
                region="Persian Gulf (Sirri Oil Field)",
                image_id="00052",
                observation_timestamp=datetime(2017, 3, 11, 2, 15, 11, tzinfo=timezone.utc),
                centroid_lat=25.6818,
                centroid_lon=54.7934,
                spill_area_km2=24.85,
                pipeline_status="COMPLETED",
            )
            db.add(inv)
            db.commit()
        db.close()

    with TestClient(app) as c:
        yield c


def test_investigation_detail_contains_artifacts(client):
    """Investigation detail endpoint must expose structured artifacts mapping."""
    res = client.get("/api/investigations/INV-2017-00052")
    assert res.status_code == 200
    data = res.json()
    assert "artifacts" in data
    artifacts = data["artifacts"]
    assert artifacts is not None
    assert "detection_overlay" in artifacts
    assert "segmentation_mask" in artifacts
    assert "source_tiff" in artifacts
    assert "INV-2017-00052" in artifacts["detection_overlay"]
    assert "INV-2017-00052" in artifacts["segmentation_mask"]


def test_detection_overlay_endpoint_scene_00052(client):
    """Detection overlay for Scene 00052 must return real 200 image/png."""
    res = client.get("/api/investigations/INV-2017-00052/artifacts/detection-overlay")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert len(res.content) > 100_000  # Genuine high-res 2048x2048 rendered image


def test_segmentation_mask_endpoint_scene_00052(client):
    """AI segmentation mask for Scene 00052 must return real 200 image/png."""
    res = client.get("/api/investigations/INV-2017-00052/artifacts/segmentation-mask")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert len(res.content) > 1_000


def test_detection_overlay_endpoint_scene_00643(client):
    """Detection overlay for Scene 00643 must return real 200 image/png."""
    res = client.get("/api/investigations/INV-2019-00643/artifacts/detection-overlay")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert len(res.content) > 100_000


def test_segmentation_mask_endpoint_scene_00643(client):
    """AI segmentation mask for Scene 00643 must return real 200 image/png."""
    res = client.get("/api/investigations/INV-2019-00643/artifacts/segmentation-mask")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert len(res.content) > 1_000


def test_scenes_are_distinct(client):
    """Detection overlays and segmentation masks for 00052 vs 00643 must be completely distinct."""
    res_ov_52 = client.get("/api/investigations/INV-2017-00052/artifacts/detection-overlay")
    res_ov_43 = client.get("/api/investigations/INV-2019-00643/artifacts/detection-overlay")
    assert res_ov_52.content != res_ov_43.content

    res_mk_52 = client.get("/api/investigations/INV-2017-00052/artifacts/segmentation-mask")
    res_mk_43 = client.get("/api/investigations/INV-2019-00643/artifacts/segmentation-mask")
    assert res_mk_52.content != res_mk_43.content


def test_missing_detection_overlay_returns_404_not_fallback(client):
    """Missing detection overlay must return 404 with clear message, never another image."""
    res = client.get("/api/investigations/INV-NONEXISTENT-99999/artifacts/detection-overlay")
    assert res.status_code == 404
    detail = res.json().get("detail", "")
    assert "SAR detection artifact unavailable" in detail


def test_missing_segmentation_mask_returns_404_not_fallback(client):
    """Missing segmentation mask must return 404 with clear message, never another image."""
    res = client.get("/api/investigations/INV-NONEXISTENT-99999/artifacts/segmentation-mask")
    assert res.status_code == 404
    detail = res.json().get("detail", "")
    assert "Segmentation artifact unavailable" in detail


def test_source_tiff_endpoint_valid_and_invalid(client):
    """Source TIFF endpoint downloads raw GeoTIFF for valid scene, returns 404 for invalid."""
    res_valid = client.get("/api/investigations/INV-2017-00052/artifacts/source-tiff")
    assert res_valid.status_code == 200
    assert "image/tiff" in res_valid.headers["content-type"]

    res_invalid = client.get("/api/investigations/INV-NONEXISTENT-99999/artifacts/source-tiff")
    assert res_invalid.status_code == 404
