"""Unit tests for the M2 -> M1 Client Adapter (satellite/preprocessing/m1_client.py).

These tests mock HTTP interactions and verify input validation, serialization,
request construction, header passing, response extraction, and error handling
without requiring a live M1 server.
"""

import io
import json
from pathlib import Path
import tempfile
import zipfile

import numpy as np
import pytest
import requests

from satellite.preprocessing.m1_client import (
    M1Client,
    M1InferenceError,
    M1InferenceResult,
    M1ValidationError,
)


def _create_mock_zip(tile_ids: list[str]) -> bytes:
    """Create an in-memory ZIP archive mimicking M1's output format."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "metadata.json",
            json.dumps({
                "source": {"tile_count": len(tile_ids)},
                "tiles": [{"tile_id": tid, "prediction": {"oil_pixel_count": 42}} for tid in tile_ids],
            }),
        )
        for tid in tile_ids:
            zf.writestr(f"predicted_masks/{tid}.tif", b"MOCK_TIFF_MASK")
            zf.writestr(f"probabilities/{tid}.tif", b"MOCK_TIFF_PROB")
    return buf.getvalue()


class MockResponse:
    """Mock requests response."""

    def __init__(self, status_code: int = 200, content: bytes = b"", text: str = "") -> None:
        self.status_code = status_code
        self.content = content
        self.text = text or (content.decode("utf-8", errors="ignore") if content else "")


class TestM1ClientConfig:
    """Tests for M1Client initialization, URLs, and authentication configuration."""

    def test_default_url(self, monkeypatch):
        monkeypatch.delenv("M1_API_URL", raising=False)
        client = M1Client(api_key="test-key")
        assert client.base_url == "http://127.0.0.1:8001"
        assert client.endpoint_url == "http://127.0.0.1:8001/predict-tiles"

    def test_custom_url_and_trailing_slash(self):
        client = M1Client(base_url="http://remote-server:9000/", api_key="test-key")
        assert client.base_url == "http://remote-server:9000"
        assert client.endpoint_url == "http://remote-server:9000/predict-tiles"

    def test_env_var_url(self, monkeypatch):
        monkeypatch.setenv("M1_API_URL", "http://env-server:8001")
        client = M1Client(api_key="test-key")
        assert client.endpoint_url == "http://env-server:8001/predict-tiles"

    def test_repr_masks_api_key(self):
        client = M1Client(api_key="SUPER_SECRET_KEY")
        repr_str = repr(client)
        assert "SUPER_SECRET_KEY" not in repr_str
        assert "***" in repr_str


class TestM1ClientValidation:
    """Tests for input contract validation."""

    def setup_method(self):
        self.client = M1Client(api_key="test-key")
        self.valid_images = np.zeros((2, 2, 256, 256), dtype=np.float32)
        self.valid_meta = [
            {"tile_id": "tile_0001", "bands": ["VV", "VH"]},
            {"tile_id": "tile_0002", "bands": ["VV", "VH"]},
        ]

    def test_valid_input_passes(self):
        self.client.validate_inputs(self.valid_images, self.valid_meta)

    def test_non_ndarray_rejected(self):
        with pytest.raises(M1ValidationError, match="numpy.ndarray"):
            self.client.validate_inputs([[1, 2], [3, 4]], self.valid_meta)

    def test_invalid_ndim_rejected(self):
        bad_images = np.zeros((2, 256, 256), dtype=np.float32)
        with pytest.raises(M1ValidationError, match="4 dimensions"):
            self.client.validate_inputs(bad_images, self.valid_meta)

    def test_invalid_channels_rejected(self):
        bad_images = np.zeros((2, 3, 256, 256), dtype=np.float32)
        with pytest.raises(M1ValidationError, match="exactly 2 channels"):
            self.client.validate_inputs(bad_images, self.valid_meta)

    def test_invalid_spatial_dimensions_rejected(self):
        bad_images = np.zeros((2, 2, 128, 128), dtype=np.float32)
        with pytest.raises(M1ValidationError, match="spatial dimensions must be \\(256, 256\\)"):
            self.client.validate_inputs(bad_images, self.valid_meta)

    def test_invalid_dtype_rejected(self):
        bad_images = np.zeros((2, 2, 256, 256), dtype=np.float64)
        with pytest.raises(M1ValidationError, match="dtype must be float32"):
            self.client.validate_inputs(bad_images, self.valid_meta)

    def test_tile_count_mismatch_rejected(self):
        with pytest.raises(M1ValidationError, match="Tile count mismatch"):
            self.client.validate_inputs(self.valid_images, [self.valid_meta[0]])

    def test_channel_order_mismatch_rejected(self):
        bad_meta = [
            {"tile_id": "tile_0001", "polarization_order": ["VH", "VV"]},
            {"tile_id": "tile_0002", "polarization_order": ["VV", "VH"]},
        ]
        with pytest.raises(M1ValidationError, match="Channel ordering mismatch"):
            self.client.validate_inputs(self.valid_images, bad_meta)


class TestM1ClientSerialization:
    """Tests for in-memory serialization to .npy and .json."""

    def setup_method(self):
        self.client = M1Client(api_key="test-key")

    def test_serialize_tiles_npy(self):
        images = np.random.rand(4, 2, 256, 256).astype(np.float32)
        npy_bytes = self.client.serialize_tiles_npy(images)
        assert isinstance(npy_bytes, bytes)

        buf = io.BytesIO(npy_bytes)
        deserialized = np.load(buf)
        assert deserialized.shape == (4, 2, 256, 256)
        assert deserialized.dtype == np.float32
        np.testing.assert_array_equal(images, deserialized)

    def test_serialize_metadata_json(self):
        from datetime import datetime, timezone
        meta = [
            {
                "tile_id": "scene_tile_001",
                "crs": "EPSG:4326",
                "transform": (0.0001, 0.0, 10.0, 0.0, -0.0001, 20.0),
                "acquisition_time": datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
            }
        ]
        json_bytes = self.client.serialize_metadata_json(meta)
        deserialized = json.loads(json_bytes.decode("utf-8"))
        assert len(deserialized) == 1
        assert deserialized[0]["tile_id"] == "scene_tile_001"
        assert deserialized[0]["crs"] == "EPSG:4326"
        assert deserialized[0]["transform"] == [0.0001, 0.0, 10.0, 0.0, -0.0001, 20.0]
        assert "2026-09-09T12:00:00" in deserialized[0]["acquisition_time"]


class TestM1ClientInference:
    """Tests for predict_tiles execution with mock HTTP responses."""

    def test_predict_tiles_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("M1_API_KEY", raising=False)
        client = M1Client(api_key=None)
        images = np.zeros((1, 2, 256, 256), dtype=np.float32)
        meta = [{"tile_id": "t1"}]
        with pytest.raises(M1InferenceError, match="API key is not configured"):
            client.predict_tiles(images, meta)

    def test_successful_inference_flow(self, monkeypatch, tmp_path):
        client = M1Client(api_key="SECRET_TOKEN_XYZ", base_url="http://127.0.0.1:8001")

        tile_ids = ["s1_tile_000", "s1_tile_001"]
        images = np.zeros((2, 2, 256, 256), dtype=np.float32)
        meta = [{"tile_id": tid, "crs": "EPSG:4326"} for tid in tile_ids]

        mock_zip = _create_mock_zip(tile_ids)
        captured_call = {}

        def mock_post(url, files=None, headers=None, timeout=None):
            captured_call["url"] = url
            captured_call["files"] = files
            captured_call["headers"] = headers
            captured_call["timeout"] = timeout
            return MockResponse(status_code=200, content=mock_zip)

        monkeypatch.setattr(requests, "post", mock_post)

        out_dir = tmp_path / "inference_output"
        result = client.predict_tiles(images, meta, output_dir=out_dir, extract=True)

        # 1. Verify request construction
        assert captured_call["url"] == "http://127.0.0.1:8001/predict-tiles"
        assert captured_call["headers"]["X-API-Key"] == "SECRET_TOKEN_XYZ"
        assert "tiles" in captured_call["files"]
        assert "metadata" in captured_call["files"]

        # Verify .npy in request files
        tiles_filename, tiles_data, tiles_mime = captured_call["files"]["tiles"]
        assert tiles_filename == "m2_tiles.npy"
        assert tiles_mime == "application/octet-stream"
        reconstructed = np.load(io.BytesIO(tiles_data))
        assert reconstructed.shape == (2, 2, 256, 256)

        # 2. Verify result object
        assert isinstance(result, M1InferenceResult)
        assert result.status_code == 200
        assert result.is_success is True
        assert result.zip_path.exists()
        assert result.extracted_dir.exists()
        assert result.num_tiles == 2
        assert result.num_masks == 2
        assert result.num_probabilities == 2

        # 3. Verify original tile_ids are preserved
        assert result.tile_ids == tile_ids
        for tid in tile_ids:
            assert tid in result.predicted_mask_paths
            assert result.predicted_mask_paths[tid].exists()
            assert tid in result.probability_paths
            assert result.probability_paths[tid].exists()

    def test_http_401_authentication_error(self, monkeypatch):
        client = M1Client(api_key="WRONG_KEY")

        def mock_post(*args, **kwargs):
            return MockResponse(status_code=401, text="Invalid or missing API key.")

        monkeypatch.setattr(requests, "post", mock_post)

        images = np.zeros((1, 2, 256, 256), dtype=np.float32)
        meta = [{"tile_id": "t1"}]

        with pytest.raises(M1InferenceError, match="Authentication failed \\(401\\)"):
            client.predict_tiles(images, meta)

    def test_http_400_validation_error(self, monkeypatch):
        client = M1Client(api_key="VALID_KEY")

        def mock_post(*args, **kwargs):
            return MockResponse(status_code=400, text="Tile count mismatch.")

        monkeypatch.setattr(requests, "post", mock_post)

        images = np.zeros((1, 2, 256, 256), dtype=np.float32)
        meta = [{"tile_id": "t1"}]

        with pytest.raises(M1InferenceError, match="Input validation rejected by M1 \\(400\\)"):
            client.predict_tiles(images, meta)

    def test_http_500_server_error(self, monkeypatch):
        client = M1Client(api_key="VALID_KEY")

        def mock_post(*args, **kwargs):
            return MockResponse(status_code=500, text="Internal Model Failure")

        monkeypatch.setattr(requests, "post", mock_post)

        images = np.zeros((1, 2, 256, 256), dtype=np.float32)
        meta = [{"tile_id": "t1"}]

        with pytest.raises(M1InferenceError, match="M1 server error \\(500\\)"):
            client.predict_tiles(images, meta)

    def test_connection_error_handling(self, monkeypatch):
        client = M1Client(api_key="VALID_KEY")

        def mock_post(*args, **kwargs):
            raise requests.exceptions.ConnectionError("Connection refused")

        monkeypatch.setattr(requests, "post", mock_post)

        images = np.zeros((1, 2, 256, 256), dtype=np.float32)
        meta = [{"tile_id": "t1"}]

        with pytest.raises(M1InferenceError, match="Failed to connect to M1 API"):
            client.predict_tiles(images, meta)
