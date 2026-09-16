"""Comprehensive unit and integration tests for Global Fishing Watch (GFW) AIS Provider.

Tests cover:
A. Provider Configuration, Parameter Validation, and Uppercase Enums
B. Health Checks with and without token / mock responses
C. GeoJSON Polygon Construction & Red Sea Benchmark Request
D. Successful Fetch, Schema Normalization, and Provenance / Data Limitation Flags
E. Error Handling: 401 Unauthorized, 403 Forbidden, 429 Rate Limit Backoff + Jitter
F. 524 Gateway Timeout & /last-report Polling, Error, and 404 Expiry Handling
G. Concurrency Guard (Thread Lock Serialization)
H. Empty Result Handling and Schema Consistency
I. Pipeline Integration with Member 4 Drift Origin Adapter
J. Live Integration Test (conditionally executed only if valid GFW_API_TOKEN is present)
"""

import json
import os
import threading
import time
from unittest.mock import MagicMock, call, patch

from dotenv import load_dotenv

# Load local environment configuration if present
load_dotenv()

import numpy as np
import pandas as pd
import pytest
import requests

from ais.data_loader.schema import REQUIRED_COLUMNS
from ais.integration.adapter import adapt_drift_origin_result
from ais.integration.search_request import AISSearchRequest
from ais.providers import (
    AISProvider,
    AISProviderConfigError,
    AISProviderConnectionError,
    AISProviderError,
    GFWAISProvider,
    GlobalFishingWatchAISProvider,
)
from ais.providers.gfw import RED_SEA_BENCHMARK, VALID_GROUP_BY_ENUMS


# ---------------------------------------------------------------------------
# Test Fixtures & Synthetic Mock Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_search_request() -> AISSearchRequest:
    """Create a standard search request around Gulf of Mexico coordinates."""
    return AISSearchRequest(
        latitude=28.0,
        longitude=-90.0,
        radius_km=20.0,
        start_time=pd.Timestamp("2024-01-15T00:00:00Z"),
        end_time=pd.Timestamp("2024-01-15T06:00:00Z"),
        buffer_km=5.0,
    )


@pytest.fixture
def sample_gfw_json_response() -> dict:
    """Create a realistic GFW 4Wings report response for public-global-presence:latest."""
    return {
        "total": 3,
        "limit": None,
        "offset": None,
        "nextOffset": None,
        "metadata": {},
        "entries": [
            {
                "public-global-presence:latest": [
                    {
                        "date": "2024-01-15T01:00:00.000Z",
                        "entryTimestamp": "2024-01-15T01:15:00.000Z",
                        "exitTimestamp": "2024-01-15T02:00:00.000Z",
                        "vesselId": "vessel-111222333",
                        "mmsi": "111222333",
                        "shipName": "OIL TRACE ONE",
                        "imo": "9123456",
                        "callsign": "WDC1111",
                        "vesselType": "cargo",
                        "flag": "PAN",
                        "lat": 28.05,
                        "lon": -90.02,
                        "hours": 0.75,
                    },
                    {
                        "date": "2024-01-15T02:00:00.000Z",
                        "entryTimestamp": "2024-01-15T02:15:00.000Z",
                        "exitTimestamp": "2024-01-15T03:00:00.000Z",
                        "vesselId": "vessel-111222333",
                        "mmsi": "111222333",
                        "shipName": "OIL TRACE ONE",
                        "imo": "9123456",
                        "callsign": "WDC1111",
                        "vesselType": "cargo",
                        "flag": "PAN",
                        "lat": 28.08,
                        "lon": -90.04,
                        "hours": 0.75,
                    },
                    {
                        "date": "2024-01-15T01:30:00.000Z",
                        "entryTimestamp": "2024-01-15T01:30:00.000Z",
                        "exitTimestamp": "2024-01-15T02:30:00.000Z",
                        "vessel_id": "vessel-222333444",
                        "mmsi": "222333444",
                        "shipName": "CARRIER TWO",
                        "imo": "9876543",
                        "callsign": "WDC2222",
                        "vessel_type": "tanker",
                        "flag": "LBR",
                        "lat": 28.01,
                        "lon": -89.98,
                        "hours": 1.0,
                    },
                    # Far away observation (should be filtered out by radius)
                    {
                        "date": "2024-01-15T01:00:00.000Z",
                        "entryTimestamp": "2024-01-15T01:00:00.000Z",
                        "vesselId": "vessel-333444555",
                        "mmsi": "333444555",
                        "shipName": "DISTANT VESSEL",
                        "lat": 35.0,
                        "lon": -75.0,
                        "hours": 1.0,
                    },
                ]
            }
        ],
    }


# ---------------------------------------------------------------------------
# Group A: Provider Configuration, Parameter Validation, and Uppercase Enums
# ---------------------------------------------------------------------------

def test_gfw_provider_alias_equivalence():
    """GFWAISProvider must be an identical alias of GlobalFishingWatchAISProvider."""
    assert GFWAISProvider is GlobalFishingWatchAISProvider
    assert issubclass(GlobalFishingWatchAISProvider, AISProvider)


def test_gfw_provider_init_default_params():
    """Provider initializes with default 4Wings parameters, uppercase group_by, and bounded timeouts."""
    provider = GlobalFishingWatchAISProvider(api_token="test-token-123")
    assert provider.name == "gfw"
    assert provider.api_token == "test-token-123"
    assert provider.dataset == "public-global-presence:latest"
    assert provider.spatial_resolution == "LOW"
    assert provider.temporal_resolution == "HOURLY"
    assert provider.group_by == "VESSEL_ID"
    assert provider.timeout == (10.0, 105.0)
    assert provider.max_retries == 3
    assert provider.max_recovery_timeout == 60.0


def test_gfw_provider_timeout_configurations():
    """Provider supports float or (connect, read) tuple timeouts with validation."""
    # Single float sets (min(10.0, float), float)
    p1 = GlobalFishingWatchAISProvider(api_token="tok", timeout=45.0)
    assert p1.timeout == (10.0, 45.0)

    p2 = GlobalFishingWatchAISProvider(api_token="tok", timeout=5.0)
    assert p2.timeout == (5.0, 5.0)

    # Tuple sets (connect, read)
    p3 = GlobalFishingWatchAISProvider(api_token="tok", timeout=(3.0, 60.0))
    assert p3.timeout == (3.0, 60.0)

    # Invalid timeouts rejected
    with pytest.raises(AISProviderConfigError, match="timeout"):
        GlobalFishingWatchAISProvider(api_token="tok", timeout=-5.0)

    with pytest.raises(AISProviderConfigError, match="timeout"):
        GlobalFishingWatchAISProvider(api_token="tok", timeout=(10.0, -1.0))

    with pytest.raises(AISProviderConfigError, match="max_recovery_timeout"):
        GlobalFishingWatchAISProvider(api_token="tok", max_recovery_timeout=0)


def test_token_redaction_in_errors_and_logs():
    """API token is redacted and never exposed in exception messages or logs."""
    secret_token = "secret_gfw_token_xyz_987"
    mock_session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = f"Server error mentioning token: {secret_token}"
    mock_session.post.return_value = mock_resp

    provider = GlobalFishingWatchAISProvider(api_token=secret_token, session=mock_session)
    req = AISSearchRequest(
        latitude=28.0,
        longitude=-90.0,
        radius_km=10.0,
        start_time=pd.Timestamp("2024-01-15T00:00:00Z"),
        end_time=pd.Timestamp("2024-01-15T01:00:00Z"),
    )

    with pytest.raises(AISProviderError) as exc_info:
        provider.fetch_ais_data(req)

    # The actual token must NOT be present in exception string
    err_str = str(exc_info.value)
    assert secret_token not in err_str
    assert "[REDACTED_GFW_TOKEN]" in err_str
    """Lowercase or invalid group_by enums are normalized or rejected."""
    # Normalized if valid
    p1 = GlobalFishingWatchAISProvider(api_token="tok", group_by="mmsi")
    assert p1.group_by == "MMSI"

    p2 = GlobalFishingWatchAISProvider(api_token="tok", group_by="FLAG")
    assert p2.group_by == "FLAG"

    # Invalid enum rejected
    with pytest.raises(AISProviderConfigError, match="Invalid group_by"):
        GlobalFishingWatchAISProvider(api_token="tok", group_by="invalid_enum")


def test_gfw_provider_init_from_env(monkeypatch):
    """Provider picks up GFW_API_TOKEN from environment if not passed explicitly."""
    monkeypatch.setenv("GFW_API_TOKEN", "env-token-xyz")
    provider = GlobalFishingWatchAISProvider()
    assert provider.api_token == "env-token-xyz"


def test_gfw_provider_invalid_configuration():
    """Invalid init parameters raise AISProviderConfigError."""
    with pytest.raises(AISProviderConfigError, match="dataset"):
        GlobalFishingWatchAISProvider(api_token="tok", dataset="")

    with pytest.raises(AISProviderConfigError, match="base_url"):
        GlobalFishingWatchAISProvider(api_token="tok", base_url="")

    with pytest.raises(AISProviderConfigError, match="timeout"):
        GlobalFishingWatchAISProvider(api_token="tok", timeout=0)

    with pytest.raises(AISProviderConfigError, match="max_retries"):
        GlobalFishingWatchAISProvider(api_token="tok", max_retries=0)

    with pytest.raises(AISProviderConfigError, match="backoff_factor"):
        GlobalFishingWatchAISProvider(api_token="tok", backoff_factor=0.5)


# ---------------------------------------------------------------------------
# Group B: Health Checks
# ---------------------------------------------------------------------------

def test_health_check_returns_false_when_no_token(monkeypatch):
    """Health check fails immediately when no token is configured."""
    monkeypatch.delenv("GFW_API_TOKEN", raising=False)
    provider = GlobalFishingWatchAISProvider(api_token=None)
    assert provider.health_check() is False


def test_health_check_returns_true_on_successful_probe():
    """Health check passes when probe returns 200/204/405/400."""
    mock_session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_session.options.return_value = mock_resp

    provider = GlobalFishingWatchAISProvider(api_token="valid-token", session=mock_session)
    assert provider.health_check() is True


def test_health_check_returns_false_on_unauthorized_probe():
    """Health check fails when probe returns 401 Unauthorized."""
    mock_session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_session.options.return_value = mock_resp

    provider = GlobalFishingWatchAISProvider(api_token="bad-token", session=mock_session)
    assert provider.health_check() is False


# ---------------------------------------------------------------------------
# Group C: GeoJSON Polygon Construction & Red Sea Benchmark
# ---------------------------------------------------------------------------

def test_build_geojson_polygon(sample_search_request: AISSearchRequest):
    """GeoJSON polygon has 5 points forming a closed clockwise/counter-clockwise ring."""
    provider = GlobalFishingWatchAISProvider(api_token="tok")
    polygon = provider._build_geojson_polygon(sample_search_request.bounding_box)

    assert polygon["type"] == "Polygon"
    coords = polygon["coordinates"][0]
    assert len(coords) == 5
    assert coords[0] == coords[-1]
    min_lat, max_lat, min_lon, max_lon = sample_search_request.bounding_box
    assert coords[0] == [min_lon, min_lat]
    assert coords[2] == [max_lon, max_lat]


def test_create_red_sea_request():
    """Verify standard 2019-10-14 Red Sea incident AISSearchRequest parameters."""
    req = GlobalFishingWatchAISProvider.create_red_sea_request()
    assert req.start_time == pd.Timestamp("2019-10-11T00:00:00Z")
    assert req.end_time == pd.Timestamp("2019-10-17T23:59:59Z")
    assert req.min_latitude == 17.5
    assert req.max_latitude == 20.0
    assert req.min_longitude == 38.6
    assert req.max_longitude == 40.4
    assert req.radius_km > 0.0


# ---------------------------------------------------------------------------
# Group D: Successful Fetch, Schema Normalization & Provenance Flags
# ---------------------------------------------------------------------------

def test_successful_fetch_ais_data(
    sample_search_request: AISSearchRequest,
    sample_gfw_json_response: dict,
):
    """Fetch AIS data verifies request body, uppercase enums, and data limitation flags."""
    mock_session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = sample_gfw_json_response
    mock_session.post.return_value = mock_resp

    provider = GlobalFishingWatchAISProvider(api_token="valid-token", session=mock_session)
    df = provider.fetch_ais_data(sample_search_request)

    # 1. Verify HTTP request params have uppercase enum values
    mock_session.post.assert_called_once()
    call_args = mock_session.post.call_args
    assert call_args[0][0].endswith("/report")
    assert call_args[1]["headers"]["Authorization"] == "Bearer valid-token"
    assert call_args[1]["params"]["datasets[0]"] == "public-global-presence:latest"
    assert call_args[1]["params"]["group-by"] == "VESSEL_ID"
    assert call_args[1]["params"]["temporal-resolution"] == "HOURLY"
    assert call_args[1]["params"]["spatial-resolution"] == "LOW"
    assert call_args[1]["params"]["spatial-aggregation"] == "false"
    assert "geojson" in call_args[1]["json"]

    # 2. Verify DataFrame schema and provenance columns
    assert not df.empty
    for col in REQUIRED_COLUMNS:
        assert col in df.columns
    assert "distance_km" in df.columns
    assert "is_grid_cell_center" in df.columns
    assert "is_raw_trajectory" in df.columns
    assert "data_source" in df.columns
    assert "presence_hours" in df.columns

    # 3. Verify provenance values: Grid-cell centers, NOT raw trajectories
    assert (df["is_grid_cell_center"] == True).all()
    assert (df["is_raw_trajectory"] == False).all()
    assert (df["data_source"] == "gfw_vessel_presence").all()
    assert "data_limitation_note" in df.attrs

    # 4. In-range vs filtered out by radius
    assert 333444555 not in df["mmsi"].values
    assert 111222333 in df["mmsi"].values
    assert 222333444 in df["mmsi"].values

    # 5. Metadata fields (both camelCase and snake_case parsed)
    assert df.loc[df["mmsi"] == 111222333, "vessel_name"].iloc[0] == "OIL TRACE ONE"
    assert df.loc[df["mmsi"] == 111222333, "vessel_type"].iloc[0] == "cargo"
    assert df.loc[df["mmsi"] == 222333444, "vessel_type"].iloc[0] == "tanker"


# ---------------------------------------------------------------------------
# Group E: Error Handling: 401, 403, 429 Backoff + Jitter
# ---------------------------------------------------------------------------

def test_fetch_raises_config_error_on_401(sample_search_request):
    """HTTP 401 Unauthorized raises AISProviderConfigError without printing token."""
    mock_session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = '{"error": "Unauthorized"}'
    mock_session.post.return_value = mock_resp

    provider = GlobalFishingWatchAISProvider(api_token="invalid-token", session=mock_session)
    with pytest.raises(AISProviderConfigError, match="authentication failed.*401"):
        provider.fetch_ais_data(sample_search_request)


def test_fetch_raises_connection_error_on_403(sample_search_request):
    """HTTP 403 Forbidden raises AISProviderConnectionError with dataset message."""
    mock_session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = '{"error": "Forbidden"}'
    mock_session.post.return_value = mock_resp

    provider = GlobalFishingWatchAISProvider(api_token="tok", session=mock_session)
    with pytest.raises(AISProviderConnectionError, match="access forbidden.*403"):
        provider.fetch_ais_data(sample_search_request)


def test_fetch_handles_429_retry_with_backoff_and_succeeds(
    sample_search_request: AISSearchRequest,
    sample_gfw_json_response: dict,
):
    """HTTP 429 retries with backoff and jitter, succeeding on next attempt."""
    mock_session = MagicMock(spec=requests.Session)

    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.headers = {"Retry-After": "0.05"}
    resp_429.text = '{"error": "Too Many Requests"}'

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = sample_gfw_json_response

    mock_session.post.side_effect = [resp_429, resp_200]

    with patch("time.sleep") as mock_sleep:
        provider = GlobalFishingWatchAISProvider(
            api_token="tok",
            max_retries=2,
            session=mock_session,
        )
        df = provider.fetch_ais_data(sample_search_request)
        assert not df.empty
        assert mock_session.post.call_count == 2
        mock_sleep.assert_called_once_with(0.05)


def test_fetch_429_unresolved_raises_connection_error(sample_search_request: AISSearchRequest):
    """Persistent 429 errors beyond max_retries raise AISProviderConnectionError."""
    mock_session = MagicMock(spec=requests.Session)
    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.headers = {}
    resp_429.text = '{"error": "Too Many Requests"}'
    mock_session.post.return_value = resp_429

    with patch("time.sleep"):
        provider = GlobalFishingWatchAISProvider(
            api_token="tok",
            max_retries=2,
            session=mock_session,
        )
        with pytest.raises(AISProviderConnectionError, match="rate limit or concurrency quota exceeded"):
            provider.fetch_ais_data(sample_search_request)


# ---------------------------------------------------------------------------
# Group F: 524 Gateway Timeout & /last-report Polling, Error, and 404 Expiry
# ---------------------------------------------------------------------------

def test_fetch_handles_524_timeout_polling_and_recovery(
    sample_search_request: AISSearchRequest,
    sample_gfw_json_response: dict,
):
    """HTTP 524 Gateway Timeout polls /last-report and recovers data when finished."""
    mock_session = MagicMock(spec=requests.Session)

    resp_524 = MagicMock()
    resp_524.status_code = 524
    resp_524.text = "Gateway Timeout"
    mock_session.post.return_value = resp_524

    # First poll: status="running", Second poll: completed with response json
    resp_running = MagicMock()
    resp_running.status_code = 200
    resp_running.json.return_value = {"status": "running", "uri": "/v3/4wings/report"}

    resp_done = MagicMock()
    resp_done.status_code = 200
    resp_done.json.return_value = sample_gfw_json_response

    mock_session.get.side_effect = [resp_running, resp_done]

    with patch("time.sleep") as mock_sleep:
        provider = GlobalFishingWatchAISProvider(api_token="tok", session=mock_session)
        df = provider.fetch_ais_data(sample_search_request)

        assert not df.empty
        assert mock_session.get.call_count == 2
        mock_sleep.assert_called_once()


def test_fetch_handles_524_last_report_404_expired(sample_search_request: AISSearchRequest):
    """When /last-report returns 404, raises descriptive timeout/expired exception."""
    mock_session = MagicMock(spec=requests.Session)

    resp_524 = MagicMock()
    resp_524.status_code = 524
    resp_524.text = "Gateway Timeout"
    mock_session.post.return_value = resp_524

    resp_404 = MagicMock()
    resp_404.status_code = 404
    mock_session.get.return_value = resp_404

    provider = GlobalFishingWatchAISProvider(api_token="tok", max_retries=1, session=mock_session)
    with pytest.raises(AISProviderConnectionError, match="report timed out.*524"):
        provider.fetch_ais_data(sample_search_request)


def test_524_recovery_stops_at_bounded_timeout_without_infinite_loop(
    sample_search_request: AISSearchRequest,
):
    """When /last-report stays in 'running' state, polling terminates when max_recovery_timeout is reached."""
    mock_session = MagicMock(spec=requests.Session)

    resp_524 = MagicMock()
    resp_524.status_code = 524
    resp_524.text = "Gateway Timeout"
    mock_session.post.return_value = resp_524

    resp_running = MagicMock()
    resp_running.status_code = 200
    resp_running.json.return_value = {"status": "running", "uri": "/v3/4wings/report"}
    mock_session.get.return_value = resp_running

    provider = GlobalFishingWatchAISProvider(
        api_token="tok",
        max_recovery_timeout=0.05,  # Very short recovery limit
        session=mock_session,
    )

    with patch("time.sleep"):
        with pytest.raises(AISProviderConnectionError, match="could not be recovered.*bounded recovery limit"):
            provider.fetch_ais_data(sample_search_request)

    # Must have stopped polling without looping infinitely
    assert mock_session.get.call_count >= 1


# ---------------------------------------------------------------------------
# Group G: Concurrency Guard (Thread Lock Serialization)
# ---------------------------------------------------------------------------

def test_concurrency_guard_serializes_calls(
    sample_search_request: AISSearchRequest,
    sample_gfw_json_response: dict,
):
    """Concurrency guard guarantees only one active report request at a time per process."""
    mock_session = MagicMock(spec=requests.Session)
    active_requests = 0
    max_simultaneous = 0
    lock = threading.Lock()

    def fake_post(*args, **kwargs):
        nonlocal active_requests, max_simultaneous
        with lock:
            active_requests += 1
            if active_requests > max_simultaneous:
                max_simultaneous = active_requests
        # Simulate slight processing delay
        time.sleep(0.05)
        with lock:
            active_requests -= 1

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_gfw_json_response
        return mock_resp

    mock_session.post.side_effect = fake_post

    provider = GlobalFishingWatchAISProvider(api_token="tok", session=mock_session)

    # Launch 3 threads concurrently
    threads = [
        threading.Thread(target=provider.fetch_ais_data, args=(sample_search_request,))
        for _ in range(3)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Thanks to the concurrency guard, max simultaneous requests to API must be exactly 1
    assert max_simultaneous == 1


# ---------------------------------------------------------------------------
# Group H: Empty Result Handling and Schema Consistency
# ---------------------------------------------------------------------------

def test_empty_results_returns_canonical_dataframe(sample_search_request: AISSearchRequest):
    """When GFW returns zero records, returns empty DataFrame with canonical & provenance columns."""
    mock_session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"total": 0, "entries": []}
    mock_session.post.return_value = mock_resp

    provider = GlobalFishingWatchAISProvider(api_token="tok", session=mock_session)
    df = provider.fetch_ais_data(sample_search_request)

    assert df.empty
    for col in REQUIRED_COLUMNS:
        assert col in df.columns
    assert "distance_km" in df.columns
    assert "is_grid_cell_center" in df.columns
    assert "data_source" in df.columns


# ---------------------------------------------------------------------------
# Group I: Pipeline Integration with Member 4 Drift Origin Adapter
# ---------------------------------------------------------------------------

def test_integration_with_drift_origin_adapter(sample_gfw_json_response: dict):
    """GFW Provider works seamlessly with AISSearchRequest from adapt_drift_origin_result."""
    mock_session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = sample_gfw_json_response
    mock_session.post.return_value = mock_resp

    m4_output = {
        "best_candidate": {
            "timestamp": "2024-01-15T02:00:00Z",
            "region": {
                "centroid_lat": 28.0,
                "centroid_lon": -90.0,
                "radius_km": 15.0,
            },
            "heuristic_score": 0.88,
        }
    }

    adapter_result = adapt_drift_origin_result(
        m4_output,
        before_minutes=120.0,
        after_minutes=120.0,
        buffer_km=5.0,
    )

    provider = GlobalFishingWatchAISProvider(api_token="tok", session=mock_session)
    df = provider.fetch_ais_data(adapter_result.search_request)

    assert not df.empty
    assert all(df["distance_km"] <= adapter_result.search_request.effective_radius_km)


# ---------------------------------------------------------------------------
# Group J: Live Integration Test (conditionally executed)
# ---------------------------------------------------------------------------

LIVE_TOKEN = os.getenv("GFW_API_TOKEN")
RUN_LIVE = os.getenv("RUN_LIVE_GFW_TEST", "0").lower() in ("1", "true", "yes")
SKIP_LIVE = (
    not RUN_LIVE
    or not LIVE_TOKEN
    or LIVE_TOKEN.strip() == ""
    or "PASTE_" in LIVE_TOKEN
    or "your_gfw_api_token" in LIVE_TOKEN
)

@pytest.mark.skipif(
    SKIP_LIVE,
    reason="Live GFW_API_TOKEN test requires RUN_LIVE_GFW_TEST=1 in environment to avoid unnecessary API calls",
)
def test_live_gfw_api_query_red_sea():
    """Live query against GFW 4Wings API for the Red Sea benchmark (only run if real token configured)."""
    provider = GlobalFishingWatchAISProvider()
    assert provider.health_check() is True

    # Use a small 6-hour slice of the Red Sea benchmark to minimize quota consumption
    req = AISSearchRequest(
        latitude=18.75,
        longitude=39.5,
        radius_km=30.0,
        start_time=pd.Timestamp("2019-10-14T00:00:00Z"),
        end_time=pd.Timestamp("2019-10-14T06:00:00Z"),
        buffer_km=5.0,
        bounding_box=(17.5, 20.0, 38.6, 40.4),
    )

    df = provider.fetch_ais_data(req)
    assert isinstance(df, pd.DataFrame)
    for col in REQUIRED_COLUMNS:
        assert col in df.columns
    assert "distance_km" in df.columns
    assert (df["is_grid_cell_center"] == True).all()
    assert (df["data_source"] == "gfw_vessel_presence").all()
