"""Hugging Face Inference Adapters for M2, M1, and M3.

Encapsulates:
- M2: Sentinel-1 dual-polarization preprocessing and tiling
- M1: PyTorch U-Net deep learning segmentation
- M3: Vectorization and WGS-84 geodesic measurements
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import rasterio
from rasterio.features import shapes
import torch
import torch.nn as nn
import segmentation_models_pytorch as smp


def extract_geotiff_metadata(src: rasterio.io.DatasetReader) -> Dict[str, Any]:
    """Extract authoritative geospatial metadata from open rasterio reader."""
    bounds = src.bounds
    crs_str = str(src.crs) if src.crs else "EPSG:4326"
    width, height = src.width, src.height
    count = src.count
    transform = tuple(src.transform)[:6]
    tags = src.tags()

    timestamp_candidates = [
        tags.get("TIFFTAG_DATETIME"),
        tags.get("ACQUISITION_DATETIME"),
        tags.get("ACQUISITION_START_TIME"),
        tags.get("TIMESTAMP"),
        tags.get("DATE_TIME"),
    ]
    acq_time = next((t for t in timestamp_candidates if t), None)

    return {
        "width": width,
        "height": height,
        "bands_count": count,
        "crs": crs_str,
        "transform": transform,
        "bounds": {
            "left": float(bounds.left),
            "bottom": float(bounds.bottom),
            "right": float(bounds.right),
            "top": float(bounds.top),
        },
        "centroid": {
            "lat": float((bounds.bottom + bounds.top) / 2.0),
            "lon": float((bounds.left + bounds.right) / 2.0),
        },
        "acquisition_time": acq_time,
        "tags": tags,
    }


class M1SegmentationModel:
    """Wrapper for PyTorch U-Net segmentation inference."""

    def __init__(self, model_path: Path, device: Optional[str] = None):
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model checkpoint not found at: {self.model_path}")

        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        self.model = smp.Unet(
            encoder_name="resnet34",
            encoder_weights=None,
            in_channels=2,
            classes=1,
        )
        checkpoint = torch.load(self.model_path, map_location=self.device)
        if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
            self.model.load_state_dict(checkpoint["state_dict"])
        elif isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
            self.model.load_state_dict(checkpoint["model_state_dict"])
        elif isinstance(checkpoint, dict):
            self.model.load_state_dict(checkpoint)
        elif isinstance(checkpoint, nn.Module):
            self.model = checkpoint
        else:
            raise ValueError(f"Unrecognized checkpoint format: {type(checkpoint)}")

        self.model.to(self.device)
        self.model.eval()

    def predict(
        self,
        image: np.ndarray,
        tile_size: int = 512,
        threshold: float = 0.5,
    ) -> Tuple[np.ndarray, np.ndarray, int, float, float]:
        """Perform tiled sliding-window inference with percentile normalization."""
        if not np.all(np.isfinite(image)):
            image = np.nan_to_num(image, nan=-25.0, posinf=0.0, neginf=-50.0)

        c, height, width = image.shape
        if c < 2:
            raise ValueError(f"Sentinel-1 requires at least 2 bands (VV, VH), received {c}.")

        # Take first two bands
        bands = image[:2].astype(np.float32)

        # Percentile normalize per-band across scene
        norm_bands = np.zeros_like(bands, dtype=np.float32)
        for b in range(2):
            v = bands[b]
            p2, p98 = np.percentile(v, (2, 98))
            if p98 > p2:
                norm_bands[b] = np.clip((v - p2) / (p98 - p2), 0.0, 1.0)
            else:
                norm_bands[b] = 0.0

        prob_map = np.zeros((height, width), dtype=np.float32)
        count_map = np.zeros((height, width), dtype=np.float32)

        with torch.no_grad():
            for y in range(0, height, tile_size):
                for x in range(0, width, tile_size):
                    y2 = min(y + tile_size, height)
                    x2 = min(x + tile_size, width)
                    patch = norm_bands[:, y:y2, x:x2]

                    oh, ow = patch.shape[1], patch.shape[2]
                    pad_h = tile_size - oh
                    pad_w = tile_size - ow

                    if pad_h > 0 or pad_w > 0:
                        patch = np.pad(patch, ((0, 0), (0, pad_h), (0, pad_w)), mode="edge")

                    tensor = torch.from_numpy(patch).unsqueeze(0).to(self.device)
                    logits = self.model(tensor)
                    probs = torch.sigmoid(logits)[0, 0].cpu().numpy()
                    unpadded = probs[:oh, :ow]

                    prob_map[y:y2, x:x2] += unpadded
                    count_map[y:y2, x:x2] += 1.0

        prob_map /= np.maximum(count_map, 1.0)
        binary_mask = (prob_map >= threshold).astype(np.uint8)

        oil_pixels = int(np.sum(binary_mask))
        max_conf = float(np.max(prob_map)) if prob_map.size > 0 else 0.0
        mean_conf = float(np.mean(prob_map[binary_mask == 1])) if oil_pixels > 0 else 0.0

        return binary_mask, prob_map, oil_pixels, max_conf, mean_conf


def vectorize_mask_to_geojson(
    binary_mask: np.ndarray,
    transform: Tuple[float, float, float, float, float, float],
    crs_str: str,
) -> Dict[str, Any]:
    """M3: Vectorize binary oil mask to GeoJSON Polygon/MultiPolygon and compute WGS-84 area."""
    if np.sum(binary_mask) == 0:
        return {
            "type": "FeatureCollection",
            "features": [],
            "area_km2": 0.0,
            "centroid": {"lat": 0.0, "lon": 0.0},
            "bbox": {"min_lon": 0.0, "min_lat": 0.0, "max_lon": 0.0, "max_lat": 0.0},
        }

    affine = rasterio.transform.Affine(*transform)
    extracted = list(shapes(binary_mask, mask=(binary_mask == 1), transform=affine))

    polys = []
    total_area_deg2 = 0.0
    all_lons = []
    all_lats = []

    for geom_dict, val in extracted:
        if val == 1 and geom_dict.get("type") == "Polygon" and geom_dict.get("coordinates"):
            coords = geom_dict["coordinates"]
            exterior = coords[0]
            if len(exterior) >= 4:
                xs = [p[0] for p in exterior]
                ys = [p[1] for p in exterior]
                ring_area = 0.5 * abs(sum(xs[i] * ys[i + 1] - xs[i + 1] * ys[i] for i in range(len(exterior) - 1)))
                if ring_area > 0:
                    polys.append(coords)
                    total_area_deg2 += ring_area
                    all_lons.extend(xs)
                    all_lats.extend(ys)

    if not polys or not all_lons:
        return {
            "type": "FeatureCollection",
            "features": [],
            "area_km2": 0.0,
            "centroid": {"lat": 0.0, "lon": 0.0},
            "bbox": {"min_lon": 0.0, "min_lat": 0.0, "max_lon": 0.0, "max_lat": 0.0},
        }

    min_lon, max_lon = min(all_lons), max(all_lons)
    min_lat, max_lat = min(all_lats), max(all_lats)
    centroid_lon = float(sum(all_lons) / len(all_lons))
    centroid_lat = float(sum(all_lats) / len(all_lats))

    # Geodesic area calculation
    c_lat_rad = math.radians(centroid_lat)
    km_per_deg_lat = 111.139
    km_per_deg_lon = 111.139 * math.cos(c_lat_rad)
    area_km2 = float(total_area_deg2 * km_per_deg_lat * km_per_deg_lon)

    if len(polys) == 1:
        geometry = {"type": "Polygon", "coordinates": polys[0]}
    else:
        geometry = {"type": "MultiPolygon", "coordinates": polys}

    feature = {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "area_km2": round(area_km2, 4),
            "centroid_lat": round(centroid_lat, 6),
            "centroid_lon": round(centroid_lon, 6),
            "crs": crs_str,
        },
    }

    return {
        "type": "FeatureCollection",
        "features": [feature],
        "area_km2": round(area_km2, 4),
        "centroid": {"lat": round(centroid_lat, 6), "lon": round(centroid_lon, 6)},
        "bbox": {
            "min_lon": round(min_lon, 6),
            "min_lat": round(min_lat, 6),
            "max_lon": round(max_lon, 6),
            "max_lat": round(max_lat, 6),
        },
    }

