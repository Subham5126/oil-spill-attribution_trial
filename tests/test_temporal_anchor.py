"""Test suite for authoritative SAR acquisition temporal anchor resolution, conflict detection, and manual UTC entry."""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.config import settings
from backend.services.temporal_service import (
    resolve_sar_temporal_anchor,
    resolve_sar_acquisition_time,
    validate_user_utc_timestamp,
    to_utc_iso,
    KNOWN_BENCHMARK_TIMESTAMPS,
)
from ocean.copernicus.exceptions import SarAcquisitionTimeUnavailableError

client = TestClient(app)


def test_1_benchmark_scene_00052_temporal_anchor():
    """TEST 1: Scene 00052 (Persian Gulf) resolves to 2017-03-11T02:15:11Z from project scene catalog."""
    res = resolve_sar_temporal_anchor(image_id="00052")
    assert res["status"] == "resolved"
    assert res["sar_acquisition_time"] == "2017-03-11T02:15:11Z"
    assert res["source"] == "project_scene_catalog"
    assert res["verified"] is True
    assert res["requires_user_action"] is False
    assert "CATALOG" in res["provenance_badge"]


def test_2_benchmark_scene_00643_temporal_anchor():
    """TEST 2: Scene 00643 (Red Sea) resolves to 2019-10-14T03:15:03Z from project scene catalog."""
    res = resolve_sar_temporal_anchor(image_id="00643")
    assert res["status"] == "resolved"
    assert res["sar_acquisition_time"] == "2019-10-14T03:15:03Z"
    assert res["source"] == "project_scene_catalog"
    assert res["verified"] is True
    assert res["requires_user_action"] is False


def test_3_internal_uploaded_filename_stem_mapping():
    """TEST 3: Internal server upload filename s1_xxxxxxxx_00052.tif correctly maps to catalog stem 00052."""
    res = resolve_sar_temporal_anchor(filename="s1_e2c8bbbf_00052.tif")
    assert res["status"] == "resolved"
    assert res["sar_acquisition_time"] == "2017-03-11T02:15:11Z"
    assert res["source"] == "project_scene_catalog"
    assert res["verified"] is True


def test_4_sentinel_standard_filename_parsing():
    """TEST 4: Sentinel-1 standard product filename parses timestamp directly with HIGH confidence."""
    fname = "S1A_IW_GRDH_1SDV_20210515T183045_037890_04781A_C3D4.tif"
    res = resolve_sar_temporal_anchor(filename=fname)
    assert res["status"] == "resolved"
    assert res["sar_acquisition_time"] == "2021-05-15T18:30:45Z"
    assert res["source"] == "sentinel_filename"
    assert res["verified"] is True
    assert "AUTO" in res["provenance_badge"]


def test_5_geotiff_metadata_tags_resolution():
    """TEST 5: GeoTIFF embedded tags (ACQUISITION_DATETIME) take precedence as SOURCE 1."""
    tags = {
        "ACQUISITION_DATETIME": "2020-08-12T14:20:00Z",
        "TIFFTAG_DATETIME": "2020-08-12 14:20:00",
    }
    res = resolve_sar_temporal_anchor(metadata=tags)
    assert res["status"] == "resolved"
    assert res["sar_acquisition_time"] == "2020-08-12T14:20:00Z"
    assert res["source"] == "geotiff_metadata"
    assert res["verified"] is True


def test_6_unresolved_scene_without_metadata():
    """TEST 6: Scene with no metadata or filename timestamp returns unresolved and requires user action."""
    res = resolve_sar_temporal_anchor(
        image_id="random_unknown_99999",
        filename="custom_coastal_survey.tif",
        metadata={},
    )
    assert res["status"] == "unresolved"
    assert res["sar_acquisition_time"] is None
    assert res["requires_user_action"] is True
    assert "UNRESOLVED" in res["provenance_badge"]

    with pytest.raises(SarAcquisitionTimeUnavailableError):
        resolve_sar_acquisition_time(
            image_id="random_unknown_99999",
            filename="custom_coastal_survey.tif",
            raise_if_missing=True,
        )


def test_7_metadata_conflict_detection():
    """TEST 7: Disagreement > 60s between sources triggers conflict state."""
    res = resolve_sar_temporal_anchor(
        filename="S1A_IW_GRDH_1SDV_20210515T183045_037890_04781A_C3D4.tif",
        metadata={"ACQUISITION_DATETIME": "2020-01-01T00:00:00Z"},
    )
    assert res["status"] == "conflict"
    assert res["sar_acquisition_time"] is None
    assert res["requires_user_action"] is True
    assert len(res["conflicts"]) >= 1
    assert "CONFLICT" in res["provenance_badge"]


def test_8_user_provided_manual_temporal_anchor():
    """TEST 8: Operator-provided UTC timestamp resolves cleanly with USER PROVIDED badge."""
    res = resolve_sar_temporal_anchor(
        filename="custom_coastal_survey.tif",
        user_provided_timestamp="2022-04-18T12:30:00Z",
    )
    assert res["status"] == "resolved"
    assert res["sar_acquisition_time"] == "2022-04-18T12:30:00Z"
    assert res["source"] == "user_provided"
    assert res["verified"] is False
    assert "USER PROVIDED" in res["provenance_badge"]
    assert res["requires_user_action"] is False


def test_9_validate_user_utc_timestamp_rejections():
    """TEST 9: validate_user_utc_timestamp rejects invalid dates, future dates, and pre-2014 dates."""
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_user_utc_timestamp("")

    with pytest.raises(ValueError, match="precedes the Sentinel-1 mission launch"):
        validate_user_utc_timestamp("1999-01-01T00:00:00Z")

    with pytest.raises(ValueError, match="cannot be in the future"):
        validate_user_utc_timestamp("2099-01-01T00:00:00Z")

    dt = validate_user_utc_timestamp("2018-09-04 15:45:00")
    assert dt.year == 2018
    assert dt.month == 9
    assert dt.day == 4
    assert dt.tzinfo == timezone.utc


def test_10_api_temporal_anchor_endpoints():
    """TEST 10: API endpoints for temporal anchor confirmation and resolution."""
    res = client.post(
        "/api/investigations/temporal-anchor/resolve",
        params={"filename": "S1A_IW_GRDH_1SDV_20200812T142000_033875_03EE4B_88E2.tif"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "resolved"
    assert data["sar_acquisition_time"] == "2020-08-12T14:20:00Z"

    confirm_res = client.post(
        "/api/investigations/upload/sentinel/test_upload_id_123/temporal-anchor",
        json={
            "date": "2021-07-20",
            "time": "16:45:30",
            "timezone": "UTC",
        },
    )
    assert confirm_res.status_code == 200
    c_data = confirm_res.json()
    assert c_data["status"] == "resolved"
    assert c_data["sar_acquisition_time"] == "2021-07-20T16:45:30Z"
    assert c_data["source"] == "user_provided"
    assert c_data["verified"] is False
