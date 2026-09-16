"""Unit and Integration Tests for Header Search, Notifications, and Profile API."""

import io
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.database import get_db, _create_tables, get_engine
from backend.models.investigation import InvestigationModel
from backend.models.attribution import AttributionResultModel
from backend.models.spill import SpillDetectionModel
from backend.models.notification import NotificationModel
from backend.services.investigation_service import InvestigationService


@pytest.fixture(scope="module")
def client():
    """Create FastAPI test client and ensure tables exist."""
    engine = get_engine()
    if engine:
        _create_tables(engine)
    return TestClient(app)


def test_investigation_search_exact_title(client):
    """Verify search returns matching investigation when searched by exact title."""
    res = client.get("/api/investigations/search?q=Sentinel-1 SAR Detection")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    if len(data) > 0:
        # First match should have title match
        assert "Sentinel-1 SAR Detection" in data[0]["title"]


def test_investigation_search_short_query(client):
    """Verify query shorter than 2 chars returns empty list."""
    res = client.get("/api/investigations/search?q=a")
    # Pydantic Query min_length=2 returns 422
    assert res.status_code == 422


def test_investigation_search_id_priority(client):
    """Verify exact case ID search matches with highest priority."""
    # List investigations to get a real ID
    invs = client.get("/api/investigations?limit=1").json()
    if invs and len(invs) > 0:
        target_id = invs[0].get("id") or invs[0].get("investigation_id")
        res = client.get(f"/api/investigations/search?q={target_id}")
        assert res.status_code == 200
        matches = res.json()
        assert len(matches) > 0
        assert matches[0]["investigation_id"] == target_id
        assert matches[0]["match_type"] == "id"


def test_notifications_lifecycle(client):
    """Verify notification listing, unread count, and marking as read."""
    # 1. Fetch notifications
    res = client.get("/api/notifications")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "unread_count" in data
    assert isinstance(data["items"], list)

    # 2. Check unread count endpoint
    res_count = client.get("/api/notifications/unread-count")
    assert res_count.status_code == 200
    assert "unread_count" in res_count.json()

    # 3. Mark one read if available
    if len(data["items"]) > 0:
        first_id = data["items"][0]["id"]
        res_read = client.patch(f"/api/notifications/{first_id}/read")
        assert res_read.status_code == 200
        assert res_read.json()["is_read"] is True

    # 4. Mark all read
    res_all = client.post("/api/notifications/mark-all-read")
    assert res_all.status_code == 200
    assert res_all.json()["status"] == "SUCCESS"

    # Count should now be 0
    res_after = client.get("/api/notifications/unread-count")
    assert res_after.json()["unread_count"] == 0


def test_profile_get_and_update(client):
    """Verify GET and PUT for analyst user profile."""
    # 1. GET profile
    res = client.get("/api/profile")
    assert res.status_code == 200
    profile = res.json()
    assert "full_name" in profile
    assert "department" in profile
    assert "specialization" in profile

    # 2. PUT update profile
    update_payload = {
        "full_name": "Cmdr. Rajesh K. Varma (Lead)",
        "department": "Maritime Environmental Enforcement Division",
        "specialization": "Satellite SAR & Hydrodynamic Drift Attribution",
    }
    res_put = client.put("/api/profile", json=update_payload)
    assert res_put.status_code == 200
    updated = res_put.json()
    assert updated["full_name"] == "Cmdr. Rajesh K. Varma (Lead)"
    assert updated["department"] == "Maritime Environmental Enforcement Division"


def test_profile_photo_validation(client):
    """Verify photo upload rejects invalid file types and accepts valid JPG/PNG."""
    # 1. Reject invalid file type (e.g. .exe / text/plain)
    invalid_file = io.BytesIO(b"malicious executable content")
    res_invalid = client.post(
        "/api/profile/photo",
        files={"file": ("malicious.exe", invalid_file, "application/octet-stream")},
    )
    assert res_invalid.status_code == 400
    assert "Invalid file type" in res_invalid.json()["detail"]

    # 2. Accept valid PNG
    valid_png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    valid_file = io.BytesIO(valid_png_data)
    res_valid = client.post(
        "/api/profile/photo",
        files={"file": ("avatar.png", valid_file, "image/png")},
    )
    assert res_valid.status_code == 200
    data = res_valid.json()
    assert data["avatar_url"] is not None
    assert data["avatar_url"].startswith("data:image/png;base64,")

    # 3. Delete photo
    res_del = client.delete("/api/profile/photo")
    assert res_del.status_code == 200
    assert res_del.json()["avatar_url"] is None
