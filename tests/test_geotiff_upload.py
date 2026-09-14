"""Integration & Unit Tests for Sentinel-1 GeoTIFF Upload and Validation System."""

import io
import os
from pathlib import Path
import shutil
import tempfile
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.config import settings
from backend.core.database import get_session, get_db
from backend.models.investigation import InvestigationModel
from backend.services.upload_service import UploadService, MAX_FILE_SIZE

client = TestClient(app)

REAL_TIFF_00052 = settings.REPO_ROOT / "01_Train_Val_Oil_Spill_images" / "Oil" / "00052.tif"
REAL_TIFF_00643 = settings.REPO_ROOT / "01_Train_Val_Oil_Spill_images" / "Oil" / "00643.tif"


def test_upload_init_rejects_unsupported_extensions():
    """Verify that file extensions other than .tif and .tiff are rejected immediately."""
    for invalid_name in ["slick.jpg", "satellite.png", "data.pdf", "archive.zip", "test.txt"]:
        res = client.post(
            "/api/investigations/upload/sentinel/init",
            json={
                "filename": invalid_name,
                "file_size": 1024 * 1024,
                "total_chunks": 1,
            },
        )
        assert res.status_code == 400
        assert "Unsupported file type" in res.json()["detail"]


def test_upload_init_enforces_1_gib_limit():
    """Verify that file size > 1 GiB is rejected with HTTP 413."""
    oversized_bytes = (1024 * 1024 * 1024) + 1  # 1 GiB + 1 byte
    res = client.post(
        "/api/investigations/upload/sentinel/init",
        json={
            "filename": "huge_sentinel_scene.tif",
            "file_size": oversized_bytes,
            "total_chunks": 200,
        },
    )
    assert res.status_code == 413
    assert "File exceeds the 1 GB maximum size." in res.json()["detail"]


def test_upload_rejects_fake_renamed_geotiff():
    """Verify that non-GeoTIFF files (e.g. JPEG renamed to .tif) fail rasterio validation."""
    fake_data = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"A" * 1024  # Fake JPEG header
    file_payload = ("fake_scene.tif", io.BytesIO(fake_data), "image/tiff")

    res = client.post(
        "/api/investigations/upload/sentinel",
        files={"file": file_payload},
    )
    assert res.status_code == 400
    assert "Invalid GeoTIFF" in res.json()["detail"]


def test_chunked_upload_and_validation_real_geotiff():
    """Verify chunked upload (3 chunks) of a real Sentinel-1 GeoTIFF extracts authentic metadata."""
    assert REAL_TIFF_00052.exists(), "Test fixture 00052.tif must exist in repo"

    file_bytes = REAL_TIFF_00052.read_bytes()
    total_size = len(file_bytes)
    chunk_size = (total_size // 3) + 1
    total_chunks = 3

    # 1. Init chunked upload
    init_res = client.post(
        "/api/investigations/upload/sentinel/init",
        json={
            "filename": "Uploaded_Sentinel1_Sirri_00052.tif",
            "file_size": total_size,
            "total_chunks": total_chunks,
        },
    )
    assert init_res.status_code == 200
    init_data = init_res.json()
    upload_id = init_data["upload_id"]
    assert upload_id is not None

    # 2. Upload chunks
    for i in range(total_chunks):
        start = i * chunk_size
        end = min(start + chunk_size, total_size)
        chunk_data = file_bytes[start:end]

        chunk_res = client.post(
            "/api/investigations/upload/sentinel/chunk",
            data={"upload_id": upload_id, "chunk_index": i},
            files={"chunk": ("blob", io.BytesIO(chunk_data), "application/octet-stream")},
        )
        assert chunk_res.status_code == 200
        chunk_info = chunk_res.json()
        assert chunk_info["chunks_received"] == i + 1

    # 3. Complete chunked upload & validate GeoTIFF
    complete_res = client.post(
        "/api/investigations/upload/sentinel/complete",
        json={"upload_id": upload_id},
    )
    assert complete_res.status_code == 200
    meta = complete_res.json()

    assert meta["status"] == "SUCCESS"
    assert meta["filename"] == "Uploaded_Sentinel1_Sirri_00052.tif"
    assert meta["width"] == 2048
    assert meta["height"] == 2048
    assert meta["num_bands"] == 2
    assert "EPSG" in meta["crs"]
    assert meta["is_uploaded"] is True
    assert meta["acquisition_time"] == "2017-03-11T02:15:11Z"
    assert "Persian Gulf" in meta["region"]
    assert Path(meta["file_path"]).exists()

    uploaded_path = Path(meta["file_path"])

    # 4. Create investigation using uploaded GeoTIFF
    inv_res = client.post(
        "/api/investigations",
        json={
            "title": "Uploaded Scene Investigation 00052",
            "image_id": meta["image_id"],
            "source_image_path": meta["file_path"],
            "region": meta["region"],
            "priority": "High",
            "observation_timestamp": meta["acquisition_time"],
        },
    )
    assert inv_res.status_code == 201
    inv_data = inv_res.json()
    inv_id = inv_data["id"]

    # 5. Check investigation record in DB
    db = get_session()
    try:
        db_inv = db.query(InvestigationModel).filter_by(investigation_id=inv_id).first()
        assert db_inv is not None
        assert db_inv.source_image_path == str(uploaded_path)
        assert db_inv.observation_timestamp.strftime("%Y-%m-%d") == "2017-03-11"
    finally:
        db.close()


def test_cancel_upload_purges_disk_file():
    """Verify that cancelling an upload purges the in-progress file from server storage."""
    init_res = client.post(
        "/api/investigations/upload/sentinel/init",
        json={
            "filename": "temporary_scene.tif",
            "file_size": 1024 * 1024,
            "total_chunks": 1,
        },
    )
    upload_id = init_res.json()["upload_id"]

    # Cancel session
    cancel_res = client.delete(f"/api/investigations/upload/sentinel/{upload_id}")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"


def test_cross_investigation_independence():
    """Verify that multiple uploaded scenes belong strictly to their respective investigations."""
    assert REAL_TIFF_00052.exists() and REAL_TIFF_00643.exists()

    # Upload Scene A (00052)
    meta_a = UploadService.validate_and_extract_metadata(
        file_path=REAL_TIFF_00052,
        original_filename="Scene_A_00052.tif",
        upload_id="session_a_12345",
    )

    # Upload Scene B (00643)
    meta_b = UploadService.validate_and_extract_metadata(
        file_path=REAL_TIFF_00643,
        original_filename="Scene_B_00643.tif",
        upload_id="session_b_67890",
    )

    # Create Inv A
    res_a = client.post(
        "/api/investigations",
        json={
            "title": "Investigation A - Scene 00052",
            "image_id": meta_a["image_id"],
            "source_image_path": meta_a["file_path"],
            "region": meta_a["region"],
            "observation_timestamp": meta_a["acquisition_time"],
        },
    )
    assert res_a.status_code == 201

    # Create Inv B
    res_b = client.post(
        "/api/investigations",
        json={
            "title": "Investigation B - Scene 00643",
            "image_id": meta_b["image_id"],
            "source_image_path": meta_b["file_path"],
            "region": meta_b["region"],
            "observation_timestamp": meta_b["acquisition_time"],
        },
    )
    assert res_b.status_code == 201

    inv_a_id = res_a.json()["id"]
    inv_b_id = res_b.json()["id"]

    db = get_session()
    try:
        inv_a = db.query(InvestigationModel).filter_by(investigation_id=inv_a_id).first()
        inv_b = db.query(InvestigationModel).filter_by(investigation_id=inv_b_id).first()

        assert inv_a.source_image_path == str(REAL_TIFF_00052)
        assert inv_b.source_image_path == str(REAL_TIFF_00643)
        assert inv_a.source_image_path != inv_b.source_image_path
        assert inv_a.observation_timestamp != inv_b.observation_timestamp
    finally:
        db.close()
