"""GeoJSON Layer Schemas for GIS endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GeoJSONCRSProperties(BaseModel):
    name: str = "urn:ogc:def:crs:OGC:1.3:CRS84"


class GeoJSONCRS(BaseModel):
    type: str = "name"
    properties: GeoJSONCRSProperties = Field(default_factory=GeoJSONCRSProperties)


class GeoJSONFeature(BaseModel):
    type: str = "Feature"
    id: Optional[str] = None
    geometry: Dict[str, Any]
    properties: Dict[str, Any] = Field(default_factory=dict)


class GeoJSONFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    crs: Optional[GeoJSONCRS] = None
    features: List[GeoJSONFeature] = Field(default_factory=list)
