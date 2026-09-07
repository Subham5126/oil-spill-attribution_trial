"""GIS Geometry component for the Oil Spill Attribution System.

Provides geospatial geometry primitives (Point, LineString, LinearRing,
Polygon, MultiPolygon), specialized OilSpillGeometry, validation routines,
and RFC 7946 GeoJSON serialization.
"""

from gis.geometry.exceptions import (
    CRSValidationError,
    EmptyGeometryError,
    GeometryError,
    InvalidCoordinateError,
    InvalidGeometryError,
    SelfIntersectionError,
)
from gis.geometry.geojson import from_geojson, from_shapely, to_geojson, to_shapely
from gis.geometry.models import (
    BoundingBox,
    Coordinate,
    LineString,
    LinearRing,
    MultiPolygon,
    OilSpillGeometry,
    Point,
    Polygon,
)
from gis.geometry.validation import (
    is_wgs84,
    point_in_polygon,
    signed_ring_area,
    validate_coordinate_values,
    validate_crs,
    validate_line_coordinates,
    validate_linear_ring,
    validate_polygon_rings,
    validate_timestamp_utc,
)

__all__ = [
    # Models
    "Coordinate",
    "BoundingBox",
    "Point",
    "LineString",
    "LinearRing",
    "Polygon",
    "MultiPolygon",
    "OilSpillGeometry",
    # Validation
    "validate_coordinate_values",
    "validate_crs",
    "validate_line_coordinates",
    "validate_linear_ring",
    "validate_polygon_rings",
    "validate_timestamp_utc",
    "signed_ring_area",
    "point_in_polygon",
    "is_wgs84",
    # GeoJSON & Interop
    "to_geojson",
    "from_geojson",
    "to_shapely",
    "from_shapely",
    # Exceptions
    "GeometryError",
    "InvalidCoordinateError",
    "InvalidGeometryError",
    "EmptyGeometryError",
    "SelfIntersectionError",
    "CRSValidationError",
]
