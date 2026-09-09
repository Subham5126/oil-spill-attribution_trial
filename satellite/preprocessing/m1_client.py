"""M2 to M1 AI Inference Client Adapter.

This module bridges the Sentinel-1 preprocessing pipeline (M2) with the
downstream U-Net oil spill segmentation API (M1).

It formats, validates, and dispatches batched SAR tiles (N, 2, 256, 256) and
associated geospatial metadata to the M1 FastAPI inference service via
HTTP POST multipart requests, then captures and unpacks the georeferenced
segmentation results.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Any, Sequence
import zipfile

from dotenv import load_dotenv
import numpy as np
import requests

load_dotenv()

from satellite.sentinel1.exceptions import Sentinel1DataError, Sentinel1Error

if TYPE_CHECKING:
    from satellite.sentinel1.pipeline import Sentinel1PipelineResult


class M1ClientError(Sentinel1Error):
    """Base exception for M1 client errors."""
    pass


class M1ValidationError(M1ClientError, Sentinel1DataError):
    """Raised when M2 input tensors or metadata violate the M1 contract."""
    pass


class M1InferenceError(M1ClientError):
    """Raised when the M1 inference service returns an error or fails."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


@dataclass
class M1InferenceResult:
    """Encapsulates the response and artifacts returned by M1 inference.

    Attributes:
        status_code: HTTP response status code.
        zip_path: Path to the downloaded result ZIP archive.
        extracted_dir: Directory where the ZIP archive was extracted, or None.
        metadata: Consolidated metadata returned by M1 (source + inference stats).
        predicted_mask_paths: Mapping of tile_id to extracted mask GeoTIFF Path.
        probability_paths: Mapping of tile_id to extracted probability GeoTIFF Path.
        tile_ids: List of original tile IDs processed in this batch.
    """

    status_code: int
    zip_path: Path
    extracted_dir: Path | None
    metadata: dict[str, Any]
    predicted_mask_paths: dict[str, Path]
    probability_paths: dict[str, Path]
    tile_ids: list[str]

    @property
    def is_success(self) -> bool:
        """Return True if HTTP status indicates success (2xx)."""
        return 200 <= self.status_code < 300

    @property
    def num_tiles(self) -> int:
        """Return total number of tiles processed."""
        return len(self.tile_ids)

    @property
    def num_masks(self) -> int:
        """Return number of extracted predicted mask files."""
        return len(self.predicted_mask_paths)

    @property
    def num_probabilities(self) -> int:
        """Return number of extracted probability files."""
        return len(self.probability_paths)


def _json_serializable(val: Any) -> Any:
    """Helper to serialize datetime, NumPy, and dataclass objects into JSON."""
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return val.isoformat()
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, (np.ndarray,)):
        return val.tolist()
    if isinstance(val, (tuple, set)):
        return list(val)
    if hasattr(val, "to_dict"):
        return val.to_dict()
    if is_dataclass(val) and not isinstance(val, type):
        return asdict(val)
    return str(val)


class M1Client:
    """HTTP client adapter connecting M2 preprocessing with the M1 inference service."""

    DEFAULT_BASE_URL: str = "http://127.0.0.1:8001"
    ENDPOINT_PATH: str = "/predict-tiles"

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        """Initialize the M1 client adapter.

        Args:
            base_url: Base URL for the M1 service. Defaults to M1_API_URL env var
                      or 'http://127.0.0.1:8001'.
            api_key: M1 secret key. Defaults to M1_API_KEY env var.
                     SECURITY: Never log, print, or expose this key.
            timeout_seconds: HTTP request timeout in seconds.
        """
        raw_url = base_url or os.getenv("M1_API_URL") or self.DEFAULT_BASE_URL
        self._base_url = raw_url.rstrip("/")
        self._endpoint_url = f"{self._base_url}{self.ENDPOINT_PATH}"
        raw_key = api_key or os.getenv("M1_API_KEY")
        self._api_key = raw_key.strip() if raw_key else None
        self._timeout_seconds = float(timeout_seconds)

    @property
    def endpoint_url(self) -> str:
        """Return the complete endpoint URL for tile prediction."""
        return self._endpoint_url

    @property
    def base_url(self) -> str:
        """Return the configured base URL."""
        return self._base_url

    def __repr__(self) -> str:
        return f"M1Client(endpoint_url='{self._endpoint_url}', api_key='***')"

    def validate_inputs(
        self,
        batch_images: np.ndarray,
        batch_metadata: Sequence[dict[str, Any]],
    ) -> None:
        """Validate that input tensor and metadata comply with the M1 contract.

        Validation rules:
        - batch_images is a numpy.ndarray
        - dtype is float32
        - ndim is 4 with shape (N, 2, 256, 256)
        - N equals len(batch_metadata)
        - Channels: Channel 0 is VV, Channel 1 is VH

        Raises:
            M1ValidationError: If any validation condition is violated.
        """
        if not isinstance(batch_images, np.ndarray):
            raise M1ValidationError(
                f"batch_images must be a numpy.ndarray; got {type(batch_images).__name__}."
            )

        if batch_images.ndim != 4:
            raise M1ValidationError(
                f"batch_images must have 4 dimensions (N, 2, 256, 256); got shape {batch_images.shape}."
            )

        n_tiles, channels, height, width = batch_images.shape

        if channels != 2:
            raise M1ValidationError(
                f"batch_images must have exactly 2 channels (VV, VH); got {channels} in shape {batch_images.shape}."
            )

        if height != 256 or width != 256:
            raise M1ValidationError(
                f"batch_images spatial dimensions must be (256, 256); got ({height}, {width})."
            )

        if batch_images.dtype != np.float32:
            raise M1ValidationError(
                f"batch_images dtype must be float32; got {batch_images.dtype}."
            )

        if not isinstance(batch_metadata, Sequence):
            raise M1ValidationError(
                f"batch_metadata must be a sequence of metadata dictionaries; got {type(batch_metadata).__name__}."
            )

        if len(batch_metadata) != n_tiles:
            raise M1ValidationError(
                f"Tile count mismatch: batch_images has {n_tiles} tiles, but batch_metadata has {len(batch_metadata)} records."
            )

        # Validate channel ordering if specified in metadata
        for idx, meta in enumerate(batch_metadata):
            if not isinstance(meta, dict):
                raise M1ValidationError(
                    f"batch_metadata[{idx}] must be a dictionary; got {type(meta).__name__}."
                )
            pol_order = meta.get("polarization_order") or meta.get("bands")
            if pol_order is not None:
                pols = tuple(pol_order)
                if len(pols) >= 2 and (pols[0] != "VV" or pols[1] != "VH"):
                    raise M1ValidationError(
                        f"Channel ordering mismatch in tile {idx}: expected ('VV', 'VH'), found {pols}."
                    )

    def serialize_tiles_npy(self, batch_images: np.ndarray) -> bytes:
        """Serialize batch_images array into in-memory .npy binary bytes."""
        buf = io.BytesIO()
        np.save(buf, batch_images)
        return buf.getvalue()

    def serialize_metadata_json(
        self,
        batch_metadata: Sequence[dict[str, Any]],
    ) -> bytes:
        """Serialize batch_metadata list into in-memory JSON bytes."""
        # Convert to list of dicts if needed
        clean_list: list[dict[str, Any]] = []
        for item in batch_metadata:
            if is_dataclass(item) and not isinstance(item, type):
                clean_list.append(asdict(item))
            elif isinstance(item, dict):
                clean_list.append(dict(item))
            else:
                clean_list.append({"raw_metadata": str(item)})

        json_text = json.dumps(clean_list, default=_json_serializable, indent=2)
        return json_text.encode("utf-8")

    def predict_tiles(
        self,
        batch_images: np.ndarray,
        batch_metadata: Sequence[dict[str, Any]],
        output_dir: str | Path | None = None,
        extract: bool = True,
        session: requests.Session | None = None,
    ) -> M1InferenceResult:
        """Send M2 tiles and metadata to the M1 U-Net inference service.

        Args:
            batch_images: NumPy array of shape (N, 2, 256, 256) and dtype float32.
            batch_metadata: Sequence of N metadata dictionaries.
            output_dir: Optional directory to store the ZIP response and extracted files.
                        Defaults to a temporary directory.
            extract: Whether to extract the returned ZIP archive automatically.
            session: Optional requests.Session for connection reuse or mocking.

        Returns:
            M1InferenceResult holding output paths, metadata, and status.

        Raises:
            M1ValidationError: If inputs fail contract validation.
            M1InferenceError: If HTTP request fails, returns non-200, or invalid data.
        """
        # 1. Check API key presence without logging
        if not self._api_key:
            raise M1InferenceError(
                "M1 API key is not configured. Set the M1_API_KEY environment variable "
                "or provide api_key to M1Client."
            )

        # 2. Validate input contracts
        self.validate_inputs(batch_images, batch_metadata)

        # 3. Collect original tile IDs
        original_tile_ids: list[str] = [
            str(m.get("tile_id") or f"tile_{idx:04d}")
            for idx, m in enumerate(batch_metadata)
        ]

        # 4. Serialize in-memory payloads
        npy_bytes = self.serialize_tiles_npy(batch_images)
        json_bytes = self.serialize_metadata_json(batch_metadata)

        files = {
            "tiles": ("m2_tiles.npy", npy_bytes, "application/octet-stream"),
            "metadata": ("m2_metadata.json", json_bytes, "application/json"),
        }

        headers = {
            "X-API-Key": self._api_key,
        }

        # 5. Dispatch HTTP POST request
        requester = session or requests
        try:
            response = requester.post(
                self._endpoint_url,
                files=files,
                headers=headers,
                timeout=self._timeout_seconds,
            )
        except requests.exceptions.ConnectionError as exc:
            raise M1InferenceError(
                f"Failed to connect to M1 API at {self._endpoint_url}. "
                f"Ensure the M1 server is running."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise M1InferenceError(
                f"Request to M1 API timed out after {self._timeout_seconds}s."
            ) from exc
        except Exception as exc:
            raise M1InferenceError(f"HTTP request to M1 failed: {exc}") from exc

        # 6. Check response status
        if response.status_code != 200:
            error_body = response.text
            if response.status_code == 401:
                detail = "Authentication failed (401). Verify that M1_API_KEY is correct."
            elif response.status_code == 400:
                detail = f"Input validation rejected by M1 (400): {error_body}"
            elif response.status_code == 500:
                detail = f"M1 server error (500): {error_body}"
            else:
                detail = f"HTTP {response.status_code}: {error_body}"
            raise M1InferenceError(detail, status_code=response.status_code, response_body=error_body)

        # 7. Persist and extract response ZIP
        target_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="m1_client_out_"))
        target_dir.mkdir(parents=True, exist_ok=True)

        zip_path = target_dir / "m1_tiles_result.zip"
        zip_path.write_bytes(response.content)

        extracted_dir: Path | None = None
        predicted_masks: dict[str, Path] = {}
        probabilities: dict[str, Path] = {}
        m1_metadata: dict[str, Any] = {}

        if extract:
            extracted_dir = target_dir / "extracted"
            extracted_dir.mkdir(parents=True, exist_ok=True)

            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(extracted_dir)
            except zipfile.BadZipFile as exc:
                raise M1InferenceError(f"M1 returned an invalid ZIP file: {exc}") from exc

            # Read metadata.json from extracted directory
            meta_file = extracted_dir / "metadata.json"
            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        m1_metadata = json.load(f)
                except Exception as exc:
                    m1_metadata = {"raw_read_error": str(exc)}

            # Map mask files by tile_id (filename stem)
            masks_subdir = extracted_dir / "predicted_masks"
            if masks_subdir.exists():
                for mask_file in masks_subdir.glob("*.tif"):
                    predicted_masks[mask_file.stem] = mask_file

            # Map probability files by tile_id (filename stem)
            prob_subdir = extracted_dir / "probabilities"
            if prob_subdir.exists():
                for prob_file in prob_subdir.glob("*.tif"):
                    probabilities[prob_file.stem] = prob_file

        return M1InferenceResult(
            status_code=response.status_code,
            zip_path=zip_path,
            extracted_dir=extracted_dir,
            metadata=m1_metadata,
            predicted_mask_paths=predicted_masks,
            probability_paths=probabilities,
            tile_ids=original_tile_ids,
        )

    def predict_pipeline_result(
        self,
        result: Sentinel1PipelineResult,
        output_dir: str | Path | None = None,
        extract: bool = True,
        session: requests.Session | None = None,
    ) -> M1InferenceResult:
        """Convenience method to run inference directly on a Sentinel1PipelineResult.

        Args:
            result: Sentinel1PipelineResult returned by run_sentinel1_pipeline().
            output_dir: Optional directory for saving outputs.
            extract: Whether to extract the ZIP archive.
            session: Optional requests.Session.

        Returns:
            M1InferenceResult holding segmentation outputs.
        """
        return self.predict_tiles(
            batch_images=result.batch_images,
            batch_metadata=result.batch_metadata,
            output_dir=output_dir,
            extract=extract,
            session=session,
        )
