"""ML Inference Service Adapter (Member 1, 2, 3 Integration).

Acts as the client bridge between the lightweight Render FastAPI backend
and the dedicated Hugging Face ML Space running M2 + M1 + M3.

Provides:
1. HTTP client forwarding uploaded TIFF to HF Space POST /predict
2. Lazy local fallback if HF_ML_API_URL is not set AND PyTorch is locally installed
3. Strict isolation: does NOT import torch at module load time!
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

from backend.core.config import settings

logger = logging.getLogger("oiltrace.backend.ml_adapter")


@dataclass
class MLInferenceResult:
    """Standardized output contract for M1-M3 segmentation and geometry."""

    success: bool
    source: str  # "HUGGINGFACE_ML" or "LOCAL_LAZY_ML"
    image_metadata: Dict[str, Any]
    acquisition_time: Optional[str]
    timestamp_required: bool
    oil_pixels: int
    max_confidence: float
    mean_confidence: float
    area_km2: float
    centroid_lat: float
    centroid_lon: float
    bbox: Dict[str, float]
    geojson: Dict[str, Any]
    error_message: Optional[str] = None


class MLAdapter:
    "Adapter to orchestrate M1/M2/M3 inference via remote HF Space or lazy local fallback."

    def __init__(self, endpoint_url: Optional[str] = None, timeout_seconds: float = 120.0):
        self.endpoint_url = endpoint_url or settings.HF_ML_API_URL
        self.timeout_seconds = timeout_seconds

    def predict(self, tiff_path: Path) -> MLInferenceResult:
        """Execute M2+M1+M3 inference on a Sentinel-1 GeoTIFF."""
        tiff_path = Path(tiff_path)
        if not tiff_path.exists():
            raise FileNotFoundError(f"TIFF file not found: {tiff_path}")

        # If remote Hugging Face Space endpoint is configured, use it
        if self.endpoint_url and self.endpoint_url.strip():
            return self._predict_remote(tiff_path)

        # Otherwise fallback to lazy local execution
        return self._predict_local_lazy(tiff_path)

    def _predict_remote(self, tiff_path: Path) -> MLInferenceResult:
        """Call remote Hugging Face Space POST /predict."""
        base = self.endpoint_url.rstrip("/")
        url = f"{base}/predict" if not base.endswith("/predict") else base
        logger.info(f"[ML_ADAPTER] Dispatching inference request to remote HF Space: {url} ({tiff_path.name})")

        with open(tiff_path, "rb") as f:
            files = {"file": (tiff_path.name, f, "image/tiff")}
            try:
                resp = requests.post(url, files=files, timeout=self.timeout_seconds)
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as req_err:
                logger.error(f"[ML_ADAPTER] Remote ML call failed: {req_err}")
                raise RuntimeError(f"Hugging Face ML inference service unavailable: {req_err}") from req_err

        geom = data.get("spill_geometry", {})
        seg = data.get("segmentation", {})
        meta = data.get("image_metadata", {})
        centroid = geom.get("centroid", {})
        bbox = geom.get("bbox", {})

        return MLInferenceResult(
            success=data.get("success", True),
            source=data.get("source", "HUGGINGFACE_ML"),
            image_metadata=meta,
            acquisition_time=data.get("acquisition_time"),
            timestamp_required=data.get("timestamp_required", data.get("acquisition_time") is None),
            oil_pixels=seg.get("oil_pixels", 0),
            max_confidence=seg.get("max_confidence", 0.0),
            mean_confidence=seg.get("mean_confidence", 0.0),
            area_km2=geom.get("area_km2", 0.0),
            centroid_lat=centroid.get("lat", 0.0),
            centroid_lon=centroid.get("lon", 0.0),
            bbox=bbox,
            geojson=geom.get("geojson", {}),
        )

    def _predict_local_lazy(self, tiff_path: Path) -> MLInferenceResult:
        """Lazy local fallback loading torch ONLY on demand when remote HF Space is not set."""
        logger.info(f"[ML_ADAPTER] HF_ML_API_URL not set; executing lazy local ML on {tiff_path.name}")
        try:
            from hf_space.inference.adapters import (
                M1SegmentationModel,
                extract_geotiff_metadata,
                vectorize_mask_to_geojson,
            )
        except ImportError:
            # Fallback path if hf_space not in sys.path
            import sys
            hf_path = str(settings.REPO_ROOT / "hf_space")
            if hf_path not in sys.path:
                sys.path.insert(0, hf_path)
            from inference.adapters import (
                M1SegmentationModel,
                extract_geotiff_metadata,
                vectorize_mask_to_geojson,
            )

        import rasterio

        with rasterio.open(tiff_path) as src:
            image_metadata = extract_geotiff_metadata(src)
            raw_image = src.read()

        model_path = settings.OILTRACE_MODEL_PATH
        model = M1SegmentationModel(model_path)
        binary_mask, prob_map, oil_pixels, max_conf, mean_conf = model.predict(raw_image)

        spill_geojson = vectorize_mask_to_geojson(
            binary_mask=binary_mask,
            transform=image_metadata["transform"],
            crs_str=image_metadata["crs"],
        )

        acq_time = image_metadata.get("acquisition_time")
        centroid = spill_geojson["centroid"]
        bbox = spill_geojson["bbox"]

        return MLInferenceResult(
            success=True,
            source="LOCAL_LAZY_ML",
            image_metadata=image_metadata,
            acquisition_time=acq_time,
            timestamp_required=acq_time is None,
            oil_pixels=oil_pixels,
            max_confidence=round(max_conf, 4),
            mean_confidence=round(mean_conf, 4),
            area_km2=spill_geojson["area_km2"],
            centroid_lat=centroid["lat"],
            centroid_lon=centroid["lon"],
            bbox=bbox,
            geojson=spill_geojson,
        )

