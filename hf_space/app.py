"""OilTrace Hugging Face Space — M2 + M1 + M3 Inference Application."""

from __future__ import annotations

import io
import os
from pathlib import Path
import tempfile
from typing import Any, Dict

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
import rasterio

from inference.adapters import (
    M1SegmentationModel,
    extract_geotiff_metadata,
    vectorize_mask_to_geojson,
)

app = FastAPI(
    title="OilTrace ML Inference Service",
    description="Dedicated Hugging Face Space for Sentinel-1 M2 Preprocessing, M1 U-Net Segmentation, and M3 Vectorization.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL_DIR = Path(__file__).resolve().parent / "model"
MODEL_PATH = MODEL_DIR / "unet_best.pth"
if not MODEL_PATH.exists():
    # Fallback to repository root when run locally
    repo_model = Path(__file__).resolve().parent.parent / "unet_best.pth"
    if repo_model.exists():
        MODEL_PATH = repo_model

_model_instance: M1SegmentationModel | None = None


def get_model() -> M1SegmentationModel:
    """Lazy load U-Net model instance."""
    global _model_instance
    if _model_instance is None:
        if not MODEL_PATH.exists():
            raise RuntimeError(f"Model checkpoint not found at: {MODEL_PATH}")
        _model_instance = M1SegmentationModel(MODEL_PATH)
    return _model_instance


@app.get("/")
def root():
    return {
        "service": "OilTrace ML Inference Engine (M2+M1+M3)",
        "status": "ONLINE",
        "model_loaded": MODEL_PATH.exists(),
        "endpoints": {
            "health": "/health",
            "predict": "POST /predict",
        },
    }


@app.get("/health")
def health():
    return {
        "status": "HEALTHY",
        "checkpoint_exists": MODEL_PATH.exists(),
        "checkpoint_path": str(MODEL_PATH.name),
        "source": "HUGGINGFACE_SPACE",
    }


@app.post("/predict")
async def predict_spill(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Execute M2 preprocessing + M1 U-Net inference + M3 GIS geometry on an uploaded Sentinel-1 GeoTIFF."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")

    filename = file.filename.lower()
    if not (filename.endswith(".tif") or filename.endswith(".tiff")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Please upload a Sentinel-1 GeoTIFF (.tif or .tiff).",
        )

    # Save to temporary file safely
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
        while chunk := await file.read(1024 * 1024):
            tmp.write(chunk)

    try:
        # 1. Inspect and extract metadata with rasterio
        with rasterio.open(tmp_path) as src:
            image_metadata = extract_geotiff_metadata(src)
            raw_image = src.read()

        if raw_image.shape[0] < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Sentinel-1 SAR input requires at least 2 dual-polarization bands (VV, VH). Got {raw_image.shape[0]}.",
            )

        # 2. Run M1 U-Net segmentation
        model = get_model()
        binary_mask, prob_map, oil_pixels, max_conf, mean_conf = model.predict(raw_image)

        # 3. Run M3 Vectorization & Geodesic Geometry
        spill_geojson = vectorize_mask_to_geojson(
            binary_mask=binary_mask,
            transform=image_metadata["transform"],
            crs_str=image_metadata["crs"],
        )

        acq_time = image_metadata.get("acquisition_time")

        return {
            "success": True,
            "source": "HUGGINGFACE_ML",
            "image_metadata": {
                "filename": file.filename,
                "crs": image_metadata["crs"],
                "bounds": image_metadata["bounds"],
                "centroid": image_metadata["centroid"],
                "width": image_metadata["width"],
                "height": image_metadata["height"],
                "bands_count": image_metadata["bands_count"],
            },
            "acquisition_time": acq_time,
            "timestamp_required": acq_time is None,
            "segmentation": {
                "oil_pixels": oil_pixels,
                "total_pixels": int(raw_image.shape[1] * raw_image.shape[2]),
                "oil_coverage_pct": round((oil_pixels / (raw_image.shape[1] * raw_image.shape[2])) * 100.0, 4),
                "max_confidence": round(max_conf, 4),
                "mean_confidence": round(mean_conf, 4),
            },
            "spill_geometry": {
                "area_km2": spill_geojson["area_km2"],
                "centroid": spill_geojson["centroid"],
                "bbox": spill_geojson["bbox"],
                "geojson": spill_geojson,
            },
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ML Inference pipeline failed: {str(exc)}",
        )
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass

