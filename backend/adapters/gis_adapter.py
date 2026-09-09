"""GIS Geometry & Measurement Adapter (Member 3 Integration).

Bridges the backend to Member 3 GIS algorithms:
- Polygon validation and coordinates in EPSG:4326
- Centroid, area, perimeter, bounding box, compactness, aspect ratio
- GeoJSON export and layer generation
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from gis.geometry.models import (
    BoundingBox,
    Coordinate,
    LinearRing,
    LineString,
    OilSpillGeometry,
    Polygon as GisPolygon,
)
from gis.measurements.models import SpillMeasurement, measure_oil_spill
from gis.visualization.export import to_map_view_config
from gis.visualization.geojson_layers import (
    combine_feature_collection,
    create_bbox_layer,
    create_drift_cone_layer,
    create_spill_layer,
    create_vessel_track_layer,
)
from integration.contracts.spill_contract import SpillObservation


class GISAdapter:
    """Service adapter interfacing with Member 3 GIS components."""

    @staticmethod
    def measure_spill(spill: Any) -> SpillMeasurement:
        """Calculate authoritative physical measurements using Member 3 geodesics."""
        return measure_oil_spill(spill)

    @staticmethod
    def create_spill_observation(
        spill: Any,
        measurement: Optional[SpillMeasurement] = None,
    ) -> SpillObservation:
        """Create normalized SpillObservation contract from GIS geometry."""
        return SpillObservation.from_oil_spill_geometry(spill, measurement)

    @staticmethod
    def build_feature_collection(
        layers: List[Dict[str, Any]],
        crs_name: str = "urn:ogc:def:crs:OGC:1.3:CRS84",
    ) -> Dict[str, Any]:
        """Combine layer features into standard WGS84 GeoJSON FeatureCollection."""
        return combine_feature_collection(layers, crs_name=crs_name)

    @staticmethod
    def get_map_view_config(feature_collection: Dict[str, Any], default_zoom: int = 11) -> Dict[str, Any]:
        """Derive optimal camera bounding box and center coordinate for map display."""
        return to_map_view_config(feature_collection, default_zoom=default_zoom)
