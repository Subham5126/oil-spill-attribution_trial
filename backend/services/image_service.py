"""Sentinel-1 Image Registry & Discovery Service.

Provides discovery, filtering, and metadata inspection of real Sentinel-1 GeoTIFFs
available in the repository for oil spill investigations.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import settings
from backend.core.logging import logger

INVENTORY_CSV = settings.REPO_ROOT / "reports" / "sentinel1_inventory.csv"
IMAGES_DIR = settings.REPO_ROOT / "01_Train_Val_Oil_Spill_images" / "Oil"


class ImageService:
    """Service providing access to real Sentinel-1 imagery inventory."""

    _cached_inventory: Optional[List[Dict[str, Any]]] = None

    @classmethod
    def list_images(cls, region: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """List available real Sentinel-1 images with geospatial metadata."""
        if cls._cached_inventory is None:
            cls._load_inventory()

        images = cls._cached_inventory or []
        if region:
            reg_lower = region.lower()
            images = [img for img in images if reg_lower in img.get("region_name", "").lower()]

        return images[:limit]

    @classmethod
    def get_image_metadata(cls, image_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve metadata for a specific Sentinel-1 image by ID (e.g. '00052' or '52')."""
        if cls._cached_inventory is None:
            cls._load_inventory()

        norm_id = image_id.strip()
        if norm_id.isdigit():
            norm_id = f"{int(norm_id):05d}"

        for img in cls._cached_inventory or []:
            if img["image_id"] == norm_id or img["filename"] == f"{norm_id}.tif":
                if not img.get("acquisition_time"):
                    from backend.services.temporal_service import resolve_sar_acquisition_time, to_utc_iso
                    coords = (img.get("centroid_lat"), img.get("centroid_lon")) if img.get("centroid_lat") else None
                    dt = resolve_sar_acquisition_time(
                        image_id=norm_id,
                        image_path=img.get("file_path"),
                        coordinates=coords,
                        raise_if_missing=False,
                    )
                    if dt:
                        iso_str = to_utc_iso(dt)
                        img["acquisition_time"] = iso_str
                        img["observation_timestamp"] = iso_str
                return img

        # Fallback: check filesystem directly
        tif_path = IMAGES_DIR / f"{norm_id}.tif"
        if tif_path.exists():
            from backend.services.temporal_service import resolve_sar_acquisition_time, to_utc_iso
            dt = resolve_sar_acquisition_time(
                image_id=norm_id,
                image_path=str(tif_path),
                raise_if_missing=False,
            )
            iso_str = to_utc_iso(dt) if dt else None
            return {
                "image_id": norm_id,
                "filename": f"{norm_id}.tif",
                "file_path": str(tif_path),
                "width": 2048,
                "height": 2048,
                "crs": "EPSG:4326",
                "region_name": "Offshore Waters",
                "acquisition_time": iso_str,
                "observation_timestamp": iso_str,
                "exists_locally": True,
            }

        return None

    @classmethod
    def _load_inventory(cls) -> None:
        """Parse sentinel1_inventory.csv into memory."""
        items: List[Dict[str, Any]] = []

        if INVENTORY_CSV.exists():
            try:
                with open(INVENTORY_CSV, "r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        filename = row.get("filename", "")
                        image_id = Path(filename).stem
                        file_path = row.get("file_path", "")

                        p = Path(file_path)
                        if not p.exists():
                            p = IMAGES_DIR / filename

                        c_lat = float(row.get("centroid_lat") or 0.0)
                        c_lon = float(row.get("centroid_lon") or 0.0)
                        acq_time = row.get("acquisition_time") or None

                        items.append({
                            "image_id": image_id,
                            "filename": filename,
                            "file_path": str(p),
                            "width": int(row.get("width") or 2048),
                            "height": int(row.get("height") or 2048),
                            "num_bands": int(row.get("num_bands") or 2),
                            "crs": row.get("crs") or "EPSG:4326",
                            "min_lon": float(row.get("min_lon") or 0.0),
                            "min_lat": float(row.get("min_lat") or 0.0),
                            "max_lon": float(row.get("max_lon") or 0.0),
                            "max_lat": float(row.get("max_lat") or 0.0),
                            "centroid_lon": c_lon,
                            "centroid_lat": c_lat,
                            "pixel_res_m": float(row.get("pixel_res_m") or 10.0),
                            "acquisition_time": acq_time,
                            "observation_timestamp": acq_time,
                            "satellite": row.get("satellite") or "Sentinel-1",
                            "product_type": row.get("product_type") or "GRD",
                            "polarization": row.get("polarization") or "VV, VH",
                            "region_name": row.get("region_name") or "Offshore Waters",
                            "exists_locally": p.exists(),
                        })
            except Exception as e:
                logger.error(f"Failed to parse inventory CSV: {e}")

        # If CSV was empty or not found, scan directory
        if not items and IMAGES_DIR.exists():
            for f in sorted(IMAGES_DIR.glob("*.tif"))[:50]:
                items.append({
                    "image_id": f.stem,
                    "filename": f.name,
                    "file_path": str(f),
                    "width": 2048,
                    "height": 2048,
                    "num_bands": 2,
                    "crs": "EPSG:4326",
                    "centroid_lon": 0.0,
                    "centroid_lat": 0.0,
                    "region_name": "Offshore Waters",
                    "acquisition_time": None,
                    "exists_locally": True,
                })

        cls._cached_inventory = items
        logger.info(f"Loaded {len(items)} Sentinel-1 imagery records into registry.")
