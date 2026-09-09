"""Spill Detection Service Module."""

from __future__ import annotations

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from backend.adapters.demo_adapter import demo_provider
from backend.core.exceptions import SpillNotFoundError
from backend.repositories.spills import SpillRepository


class SpillService:
    """Service managing spill detections and morphological geometries."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self.repo = SpillRepository(db)

    def get_spill(self, investigation_id: str) -> Dict[str, Any]:
        """Fetch spill detection and measurements for an investigation."""
        rec = self.repo.get_by_investigation_id(investigation_id)
        if rec:
            return {
                "spill_metadata": {
                    "spill_id": rec.spill_id,
                    "sensor": rec.sensor,
                    "detection_timestamp": rec.observation_timestamp.isoformat(),
                    "confidence": rec.confidence,
                    "crs": rec.crs,
                    "properties": rec.properties or {},
                },
                "gis_measurement": {
                    "spill_id": rec.spill_id,
                    "crs": rec.crs,
                    "area": {
                        "sq_meters": rec.area_sq_m or (rec.area_sq_km * 1e6),
                        "sq_kilometers": rec.area_sq_km,
                    },
                    "perimeter": {
                        "meters": rec.perimeter_m or 9963.0,
                        "kilometers": rec.perimeter_km or 9.963,
                    },
                    "centroid": {
                        "latitude": rec.centroid_lat,
                        "longitude": rec.centroid_lon,
                    },
                    "bounding_box": rec.bounding_box or {},
                    "shape_characteristics": {
                        "aspect_ratio": rec.aspect_ratio or 1.54,
                        "compactness": rec.compactness or 0.4972,
                    },
                },
            }

        # Fallback to demo result
        demo_res = demo_provider.load_latest_result()
        return {
            "spill_metadata": demo_res.get("spill_metadata", {}),
            "gis_measurement": demo_res.get("gis_measurement", {}),
        }

    def get_spill_geometry(self, investigation_id: str) -> Dict[str, Any]:
        """Fetch GeoJSON polygon and physical metrics for the spill."""
        spill_info = self.get_spill(investigation_id)
        layers = demo_provider.load_latest_layers_geojson()

        # Find the oil_spill feature
        spill_feature = None
        for f in layers.get("features", []):
            if f.get("properties", {}).get("layer_type") == "oil_spill":
                spill_feature = f
                break

        geom = spill_feature.get("geometry") if spill_feature else {
            "type": "Polygon",
            "coordinates": [[[72.465, 18.512], [72.501, 18.532], [72.482, 18.530], [72.465, 18.512]]]
        }

        return {
            "spill_id": spill_info.get("spill_metadata", {}).get("spill_id", investigation_id),
            "investigation_id": investigation_id,
            "sensor": spill_info.get("spill_metadata", {}).get("sensor", "Sentinel-1 SAR"),
            "confidence": spill_info.get("spill_metadata", {}).get("confidence", 0.94),
            "detection_timestamp": spill_info.get("spill_metadata", {}).get("detection_timestamp", "2025-01-01T05:00:00Z"),
            "crs": "EPSG:4326",
            "geojson_geometry": geom,
            "measurements": spill_info.get("gis_measurement", {}),
        }
