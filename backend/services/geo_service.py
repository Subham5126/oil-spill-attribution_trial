"""Sentinel-1 GeoTIFF Inspection & M3 Geometry Vectorization Service.

Lightweight utilities strictly avoiding PyTorch / TorchVision / CUDA imports.
Safe to import in backend.main.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import rasterio
from rasterio.features import shapes

from gis.geometry.models import (
    BoundingBox,
    Coordinate,
    MultiPolygon as GisMultiPolygon,
    OilSpillGeometry,
    Polygon as GisPolygon,
)
from gis.measurements.models import measure_oil_spill


def inspect_sentinel1_tiff(tiff_path: Path) -> Dict[str, Any]:
    """Inspect and extract authoritative geospatial metadata from a Sentinel-1 GeoTIFF."""
    tiff_path = Path(tiff_path)
    if not tiff_path.exists():
        raise FileNotFoundError(f"Input TIFF not found at: {tiff_path}")

    with rasterio.open(tiff_path) as src:
        raw_image = src.read()
        profile = src.profile.copy()
        bounds = src.bounds
        crs_str = str(src.crs) if src.crs else "EPSG:4326"
        transform_tuple = tuple(src.transform)[:6]
        width, height = src.width, src.height
        bands_count = src.count
        tags = src.tags()
        res_x, res_y = src.res

    timestamp_candidates = [
        tags.get("TIFFTAG_DATETIME"),
        tags.get("ACQUISITION_DATETIME"),
        tags.get("ACQUISITION_START_TIME"),
        tags.get("TIMESTAMP"),
        tags.get("DATE_TIME"),
    ]
    acquisition_timestamp = next((t for t in timestamp_candidates if t), None)

    has_georef = (
        crs_str is not None
        and not (bounds.left == 0.0 and bounds.bottom == 0.0 and bounds.right == float(width))
    )

    stats = []
    for b in range(bands_count):
        band_data = raw_image[b]
        valid_mask = np.isfinite(band_data)
        if np.any(valid_mask):
            stats.append({
                "band": b + 1,
                "min": float(np.min(band_data[valid_mask])),
                "max": float(np.max(band_data[valid_mask])),
                "mean": float(np.mean(band_data[valid_mask])),
                "nan_count": int(np.isnan(band_data).sum()),
                "inf_count": int(np.isinf(band_data).sum()),
            })
        else:
            stats.append({
                "band": b + 1,
                "min": 0.0,
                "max": 0.0,
                "mean": 0.0,
                "nan_count": int(band_data.size),
                "inf_count": 0,
            })

    return {
        "file_name": tiff_path.name,
        "absolute_path": str(tiff_path.resolve()),
        "relative_path": str(tiff_path),
        "width": width,
        "height": height,
        "bands_count": bands_count,
        "dtype": str(raw_image.dtype),
        "crs": crs_str,
        "transform": transform_tuple,
        "bounds": {
            "left": float(bounds.left),
            "bottom": float(bounds.bottom),
            "right": float(bounds.right),
            "top": float(bounds.top),
        },
        "resolution": (float(res_x), float(res_y)),
        "has_georeferencing": has_georef,
        "acquisition_timestamp": acquisition_timestamp,
        "tags": tags,
        "band_statistics": stats,
        "raw_image": raw_image,
        "profile": profile,
    }


def run_m3_geometry(
    binary_mask: np.ndarray,
    transform: Tuple[float, float, float, float, float, float],
    crs_str: str,
    spill_id: str,
    observation_time: Optional[datetime],
    max_prob: float,
) -> Tuple[OilSpillGeometry, Any, List[Dict[str, Any]]]:
    """Execute real M3 GIS polygonization and geodesic measurements."""
    affine_transform = rasterio.transform.Affine(*transform)
    mask_shapes = list(shapes(binary_mask, mask=(binary_mask == 1), transform=affine_transform))

    if not mask_shapes:
        raise ValueError("No oil spill polygon shapes extracted from binary mask.")

    polys = []
    for geom_dict, val in mask_shapes:
        if val == 1 and geom_dict.get("type") == "Polygon" and geom_dict.get("coordinates"):
            exterior = [(float(pt[0]), float(pt[1])) for pt in geom_dict["coordinates"][0]]
            if len(exterior) >= 4:
                x = [p[0] for p in exterior]
                y = [p[1] for p in exterior]
                approx_area = 0.5 * abs(sum(x[i] * y[i + 1] - x[i + 1] * y[i] for i in range(len(exterior) - 1)))
                holes = []
                for hole_coords in geom_dict.get("coordinates")[1:]:
                    if len(hole_coords) >= 4:
                        holes.append([(float(pt[0]), float(pt[1])) for pt in hole_coords])
                polys.append((approx_area, exterior, holes))

    if not polys:
        raise ValueError("No valid polygon rings extracted from mask shapes.")

    polys.sort(key=lambda item: item[0], reverse=True)

    max_area = polys[0][0]
    min_area_thresh = max(1e-9, max_area * 0.005)
    valid_polys: List[GisPolygon] = []
    for p in polys[:20]:
        if p[0] >= min_area_thresh or len(valid_polys) == 0:
            try:
                valid_polys.append(GisPolygon(exterior=p[1], interiors=p[2] if p[2] else None, crs=crs_str))
            except Exception:
                valid_polys.append(GisPolygon(exterior=p[1], crs=crs_str))

    if len(valid_polys) == 1:
        chosen_geom: GisPolygon | GisMultiPolygon = valid_polys[0]
    else:
        chosen_geom = GisMultiPolygon(valid_polys, crs=crs_str)

    slick_geom = OilSpillGeometry(
        spill_id=spill_id,
        geometry=chosen_geom,
        detection_timestamp=observation_time or datetime.now(timezone.utc),
        source_sensor="Sentinel-1 SAR C-Band (IW)",
        confidence=max_prob,
        crs=crs_str,
    )
    measurement = measure_oil_spill(slick_geom)
    return slick_geom, measurement, mask_shapes

