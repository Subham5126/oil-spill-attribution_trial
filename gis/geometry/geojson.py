"""GeoJSON (RFC 7946) serialization, deserialization, and Shapely interoperability.

Provides standards-compliant conversion between domain geometry models,
GeoJSON Feature / Geometry dictionaries, and optional Shapely objects.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Union

from gis.geometry.exceptions import InvalidGeometryError
from gis.geometry.models import (
    LineString,
    LinearRing,
    MultiPolygon,
    OilSpillGeometry,
    Point,
    Polygon,
)

GeometryType = Union[Point, LineString, LinearRing, Polygon, MultiPolygon, OilSpillGeometry]


def to_geojson(geom: GeometryType) -> Dict[str, Any]:
    """Serialize a geometry or oil spill domain object to a standard GeoJSON dictionary.

    Args:
        geom: Point, LineString, LinearRing, Polygon, MultiPolygon, or OilSpillGeometry.

    Returns:
        RFC 7946 compliant GeoJSON geometry or feature dictionary.

    Raises:
        InvalidGeometryError: If an unsupported geometry type is provided.
    """
    if isinstance(geom, Point):
        return {
            "type": "Point",
            "coordinates": list(geom.to_tuple()),
        }

    if isinstance(geom, (LineString, LinearRing)):
        return {
            "type": "LineString",
            "coordinates": [list(pt) for pt in geom.to_tuples()],
        }

    if isinstance(geom, Polygon):
        return {
            "type": "Polygon",
            "coordinates": [
                [list(pt) for pt in ring] for ring in geom.to_coordinates_list()
            ],
        }

    if isinstance(geom, MultiPolygon):
        return {
            "type": "MultiPolygon",
            "coordinates": [
                [[list(pt) for pt in ring] for ring in poly_rings]
                for poly_rings in geom.to_coordinates_list()
            ],
        }

    if isinstance(geom, OilSpillGeometry):
        return geom.to_feature_dict()

    raise InvalidGeometryError(f"Cannot serialize object of type {type(geom)} to GeoJSON.")


def from_geojson(
    data: Dict[str, Any],
    crs: str = "EPSG:4326",
    validate: bool = True,
) -> GeometryType:
    """Deserialize a GeoJSON geometry or feature dictionary into domain geometry models.

    Args:
        data: GeoJSON dictionary (Geometry or Feature).
        crs: Coordinate Reference System (defaults to EPSG:4326 per RFC 7946).
        validate: Whether to run full geometric validation.

    Returns:
        Point, LineString, Polygon, MultiPolygon, or OilSpillGeometry instance.

    Raises:
        InvalidGeometryError: If GeoJSON structure is invalid or unsupported.
    """
    if not isinstance(data, dict):
        raise InvalidGeometryError(f"GeoJSON must be a dictionary, got {type(data)}.")

    obj_type = data.get("type")
    if not obj_type:
        raise InvalidGeometryError("GeoJSON object missing required 'type' member.")

    if obj_type == "Feature":
        geom_dict = data.get("geometry")
        if not geom_dict:
            raise InvalidGeometryError("GeoJSON Feature missing 'geometry' object.")

        base_geom = from_geojson(geom_dict, crs=crs, validate=validate)
        properties = data.get("properties", {}) or {}
        feature_id = data.get("id") or properties.get("spill_id")

        # If it represents an Oil Spill feature with timestamps and ID
        if feature_id and "detection_timestamp" in properties:
            if not isinstance(base_geom, (Polygon, MultiPolygon)):
                raise InvalidGeometryError(
                    f"Oil spill feature must have Polygon or MultiPolygon geometry, got {type(base_geom)}."
                )

            ts_str = properties["detection_timestamp"]
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            sensor = properties.get("source_sensor", "Sentinel-1")
            confidence = float(properties.get("confidence", 1.0))
            prop_copy = {
                k: v
                for k, v in properties.items()
                if k not in {"spill_id", "detection_timestamp", "source_sensor", "confidence", "crs"}
            }
            return OilSpillGeometry(
                spill_id=str(feature_id),
                geometry=base_geom,
                detection_timestamp=ts,
                source_sensor=sensor,
                confidence=confidence,
                crs=properties.get("crs", crs),
                properties=prop_copy,
                validate=validate,
            )

        return base_geom

    coords = data.get("coordinates")
    if coords is None:
        raise InvalidGeometryError(f"GeoJSON {obj_type} missing 'coordinates' member.")

    if obj_type == "Point":
        return Point(coords, crs=crs, validate=validate)

    if obj_type == "LineString":
        return LineString(coords, crs=crs, validate=validate)

    if obj_type == "Polygon":
        exterior = coords[0]
        interiors = coords[1:] if len(coords) > 1 else None
        return Polygon(exterior=exterior, interiors=interiors, crs=crs, validate=validate)

    if obj_type == "MultiPolygon":
        return MultiPolygon(polygons=coords, crs=crs, validate=validate)

    raise InvalidGeometryError(f"Unsupported GeoJSON geometry type: '{obj_type}'.")


def to_shapely(geom: GeometryType) -> Any:
    """Convert domain geometry object to a Shapely geometry if Shapely is installed.

    Args:
        geom: Domain geometry object.

    Returns:
        Shapely geometry instance.

    Raises:
        ImportError: If Shapely is not installed.
    """
    try:
        from shapely.geometry import shape
    except ImportError as err:
        raise ImportError(
            "Shapely is not installed. Install shapely to convert to Shapely geometry objects."
        ) from err

    geojson_dict = to_geojson(geom)
    # If Feature, extract underlying geometry
    if geojson_dict.get("type") == "Feature":
        geojson_dict = geojson_dict["geometry"]

    return shape(geojson_dict)


def from_shapely(
    shapely_geom: Any,
    crs: str = "EPSG:4326",
    validate: bool = True,
) -> GeometryType:
    """Convert a Shapely geometry instance to a domain geometry model.

    Args:
        shapely_geom: Shapely geometry (Point, LineString, Polygon, MultiPolygon).
        crs: Coordinate Reference System.
        validate: Whether to validate geometry.

    Returns:
        Domain geometry instance.

    Raises:
        ImportError: If Shapely is not installed.
    """
    try:
        from shapely.geometry import mapping
    except ImportError as err:
        raise ImportError(
            "Shapely is not installed. Install shapely to convert from Shapely geometry objects."
        ) from err

    geojson_dict = mapping(shapely_geom)
    return from_geojson(geojson_dict, crs=crs, validate=validate)
