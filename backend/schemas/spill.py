"""Spill Schemas matching Member 3 GIS and frontend interfaces."""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel
from backend.schemas.common import BoundingBox, GeoPoint


class AreaMeasurement(BaseModel):
    sq_meters: float
    sq_kilometers: float


class PerimeterMeasurement(BaseModel):
    meters: float
    kilometers: float


class ShapeCharacteristics(BaseModel):
    aspect_ratio: float
    compactness: float


class SpillMetadataSchema(BaseModel):
    spill_id: str
    sensor: str
    source_sensor: Optional[str] = None
    detection_timestamp: str
    observation_time: Optional[str] = None
    confidence: float
    crs: str = "EPSG:4326"
    properties: Optional[Dict[str, Any]] = None


class GisMeasurementSchema(BaseModel):
    spill_id: str
    crs: str = "EPSG:4326"
    area: AreaMeasurement
    perimeter: PerimeterMeasurement
    centroid: GeoPoint
    bounding_box: BoundingBox
    shape_characteristics: ShapeCharacteristics


class SpillGeometryResponse(BaseModel):
    spill_id: str
    investigation_id: str
    sensor: str
    confidence: float
    detection_timestamp: str
    crs: str = "EPSG:4326"
    geojson_geometry: Dict[str, Any]
    measurements: GisMeasurementSchema
