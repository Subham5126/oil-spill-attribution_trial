"""Core geospatial geometry models and oil spill geometric representations.

Defines Coordinate, BoundingBox, Point, LineString, LinearRing, Polygon,
MultiPolygon, and OilSpillGeometry with built-in validation and CRS tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, List, Sequence, Tuple, Union

from gis.geometry.exceptions import (
    EmptyGeometryError,
    InvalidCoordinateError,
    InvalidGeometryError,
)
from gis.geometry.validation import (
    signed_ring_area,
    validate_coordinate_values,
    validate_crs,
    validate_line_coordinates,
    validate_linear_ring,
    validate_polygon_rings,
    validate_timestamp_utc,
)


@dataclass(frozen=True)
class Coordinate:
    """Represents a single geospatial coordinate position.

    In geographic systems (WGS84 / EPSG:4326):
    - x corresponds to Longitude [-180.0, 180.0]
    - y corresponds to Latitude [-90.0, 90.0]
    - z corresponds to optional altitude/elevation
    """

    x: float
    y: float
    z: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))
        if self.z is not None:
            object.__setattr__(self, "z", float(self.z))

    @property
    def lon(self) -> float:
        """Alias for X coordinate (longitude in geographic CRS)."""
        return self.x

    @property
    def lat(self) -> float:
        """Alias for Y coordinate (latitude in geographic CRS)."""
        return self.y

    def to_tuple(self) -> Tuple[float, ...]:
        """Convert coordinate to a tuple."""
        if self.z is not None:
            return (self.x, self.y, self.z)
        return (self.x, self.y)

    @classmethod
    def from_tuple(cls, coords: Sequence[float]) -> "Coordinate":
        """Create a Coordinate instance from a tuple or list."""
        if len(coords) < 2:
            raise InvalidCoordinateError(f"Coordinate tuple must have at least 2 values, got {coords}.")
        z = coords[2] if len(coords) > 2 else None
        return cls(x=coords[0], y=coords[1], z=z)


@dataclass(frozen=True)
class BoundingBox:
    """2D minimum bounding box (envelope) in (min_x, min_y, max_x, max_y) order."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self) -> None:
        if self.min_x > self.max_x:
            raise InvalidGeometryError(f"min_x ({self.min_x}) cannot exceed max_x ({self.max_x}).")
        if self.min_y > self.max_y:
            raise InvalidGeometryError(f"min_y ({self.min_y}) cannot exceed max_y ({self.max_y}).")

    @property
    def width(self) -> float:
        """Span in X dimension."""
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        """Span in Y dimension."""
        return self.max_y - self.min_y

    @property
    def center(self) -> Tuple[float, float]:
        """Center coordinate (center_x, center_y)."""
        return ((self.min_x + self.max_x) / 2.0, (self.min_y + self.max_y) / 2.0)

    def to_tuple(self) -> Tuple[float, float, float, float]:
        """Return (min_x, min_y, max_x, max_y)."""
        return (self.min_x, self.min_y, self.max_x, self.max_y)


def _compute_bounds(coords: Sequence[Coordinate]) -> BoundingBox:
    """Compute bounding box for a sequence of coordinates."""
    if not coords:
        raise EmptyGeometryError("Cannot compute bounds for empty coordinates.")
    min_x = min(c.x for c in coords)
    max_x = max(c.x for c in coords)
    min_y = min(c.y for c in coords)
    max_y = max(c.y for c in coords)
    return BoundingBox(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)


class Point:
    """Geospatial 2D/3D Point."""

    def __init__(
        self,
        x_or_coord: float | Coordinate | Sequence[float],
        y: float | None = None,
        z: float | None = None,
        crs: str = "EPSG:4326",
        validate: bool = True,
    ) -> None:
        self.crs = validate_crs(crs)

        if isinstance(x_or_coord, Coordinate):
            self._coord = x_or_coord
        elif isinstance(x_or_coord, (list, tuple)):
            self._coord = Coordinate.from_tuple(x_or_coord)
        elif isinstance(x_or_coord, (int, float)) and y is not None:
            self._coord = Coordinate(x=float(x_or_coord), y=float(y), z=float(z) if z is not None else None)
        else:
            raise InvalidCoordinateError(f"Invalid coordinate parameters: {x_or_coord}, {y}")

        if validate:
            validate_coordinate_values(self._coord.x, self._coord.y, self._coord.z, crs=self.crs)

    @property
    def coordinate(self) -> Coordinate:
        return self._coord

    @property
    def x(self) -> float:
        return self._coord.x

    @property
    def y(self) -> float:
        return self._coord.y

    @property
    def z(self) -> float | None:
        return self._coord.z

    @property
    def lon(self) -> float:
        return self._coord.lon

    @property
    def lat(self) -> float:
        return self._coord.lat

    @property
    def bounds(self) -> BoundingBox:
        return BoundingBox(self.x, self.y, self.x, self.y)

    def to_tuple(self) -> Tuple[float, ...]:
        return self._coord.to_tuple()

    def __repr__(self) -> str:
        return f"Point(x={self.x}, y={self.y}{f', z={self.z}' if self.z is not None else ''}, crs='{self.crs}')"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Point):
            return False
        return self._coord == other._coord and self.crs == other.crs


class LineString:
    """Geospatial LineString consisting of two or more coordinates."""

    def __init__(
        self,
        coordinates: Sequence[Coordinate | Sequence[float]],
        crs: str = "EPSG:4326",
        validate: bool = True,
    ) -> None:
        self.crs = validate_crs(crs)
        parsed: List[Coordinate] = []
        for pt in coordinates:
            if isinstance(pt, Coordinate):
                parsed.append(pt)
            elif isinstance(pt, (tuple, list)):
                parsed.append(Coordinate.from_tuple(pt))
            else:
                raise InvalidCoordinateError(f"Invalid point item in LineString: {type(pt)}")

        if validate:
            raw_tuples = [p.to_tuple() for p in parsed]
            validate_line_coordinates(raw_tuples, crs=self.crs)

        self._coordinates = tuple(parsed)

    @property
    def coordinates(self) -> Tuple[Coordinate, ...]:
        return self._coordinates

    @property
    def bounds(self) -> BoundingBox:
        return _compute_bounds(self._coordinates)

    def to_tuples(self) -> List[Tuple[float, ...]]:
        return [c.to_tuple() for c in self._coordinates]

    def __len__(self) -> int:
        return len(self._coordinates)

    def __repr__(self) -> str:
        return f"LineString(points={len(self._coordinates)}, crs='{self.crs}')"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, LineString):
            return False
        return self._coordinates == other._coordinates and self.crs == other.crs


class LinearRing:
    """Closed sequence of 4 or more coordinates forming a polygon boundary."""

    def __init__(
        self,
        coordinates: Sequence[Coordinate | Sequence[float]],
        crs: str = "EPSG:4326",
        validate: bool = True,
    ) -> None:
        self.crs = validate_crs(crs)
        parsed: List[Coordinate] = []
        for pt in coordinates:
            if isinstance(pt, Coordinate):
                parsed.append(pt)
            elif isinstance(pt, (tuple, list)):
                parsed.append(Coordinate.from_tuple(pt))
            else:
                raise InvalidCoordinateError(f"Invalid point item in LinearRing: {type(pt)}")

        raw_tuples = [p.to_tuple() for p in parsed]
        if validate:
            validate_linear_ring(raw_tuples, crs=self.crs)

        self._coordinates = tuple(parsed)
        self._signed_area = signed_ring_area(raw_tuples)

    @property
    def coordinates(self) -> Tuple[Coordinate, ...]:
        return self._coordinates

    @property
    def bounds(self) -> BoundingBox:
        return _compute_bounds(self._coordinates)

    @property
    def signed_area(self) -> float:
        """Signed planar area using Shoelace formula."""
        return self._signed_area

    @property
    def is_ccw(self) -> bool:
        """True if counterclockwise winding order (positive signed area)."""
        return self._signed_area > 0

    def to_tuples(self) -> List[Tuple[float, ...]]:
        return [c.to_tuple() for c in self._coordinates]

    def __len__(self) -> int:
        return len(self._coordinates)

    def __repr__(self) -> str:
        return f"LinearRing(points={len(self._coordinates)}, is_ccw={self.is_ccw}, crs='{self.crs}')"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, LinearRing):
            return False
        return self._coordinates == other._coordinates and self.crs == other.crs


class Polygon:
    """Geospatial Polygon with an exterior boundary and optional interior rings (holes)."""

    def __init__(
        self,
        exterior: LinearRing | Sequence[Coordinate | Sequence[float]],
        interiors: Sequence[LinearRing | Sequence[Coordinate | Sequence[float]]] | None = None,
        crs: str = "EPSG:4326",
        validate: bool = True,
    ) -> None:
        self.crs = validate_crs(crs)

        if isinstance(exterior, LinearRing):
            self._exterior = exterior
        else:
            self._exterior = LinearRing(exterior, crs=self.crs, validate=validate)

        parsed_interiors: List[LinearRing] = []
        if interiors:
            for hole in interiors:
                if isinstance(hole, LinearRing):
                    parsed_interiors.append(hole)
                else:
                    parsed_interiors.append(LinearRing(hole, crs=self.crs, validate=validate))

        self._interiors = tuple(parsed_interiors)

        if validate:
            validate_polygon_rings(
                self._exterior.to_tuples(),
                [h.to_tuples() for h in self._interiors] if self._interiors else None,
                crs=self.crs,
            )

    @property
    def exterior(self) -> LinearRing:
        """Exterior boundary ring."""
        return self._exterior

    @property
    def interiors(self) -> Tuple[LinearRing, ...]:
        """Interior rings (holes)."""
        return self._interiors

    @property
    def bounds(self) -> BoundingBox:
        return self._exterior.bounds

    def to_coordinates_list(self) -> List[List[Tuple[float, ...]]]:
        """Return list of rings formatted as standard GeoJSON polygon coordinate hierarchy."""
        rings = [self._exterior.to_tuples()]
        for hole in self._interiors:
            rings.append(hole.to_tuples())
        return rings

    def __repr__(self) -> str:
        holes_str = f", holes={len(self._interiors)}" if self._interiors else ""
        return f"Polygon(exterior_points={len(self._exterior)}{holes_str}, crs='{self.crs}')"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Polygon):
            return False
        return (
            self._exterior == other._exterior
            and self._interiors == other._interiors
            and self.crs == other.crs
        )


class MultiPolygon:
    """Collection of one or more distinct Polygon geometries."""

    def __init__(
        self,
        polygons: Sequence[Polygon | Sequence[Any]],
        crs: str = "EPSG:4326",
        validate: bool = True,
    ) -> None:
        self.crs = validate_crs(crs)

        if not polygons:
            raise EmptyGeometryError("MultiPolygon must contain at least one Polygon.")

        parsed_polys: List[Polygon] = []
        for p in polygons:
            if isinstance(p, Polygon):
                parsed_polys.append(p)
            elif isinstance(p, (tuple, list)):
                # Handles GeoJSON [[[ring1]], [[ring2]]] representation
                exterior = p[0]
                interiors = p[1:] if len(p) > 1 else None
                parsed_polys.append(Polygon(exterior, interiors=interiors, crs=self.crs, validate=validate))
            else:
                raise InvalidGeometryError(f"Expected Polygon instance, got {type(p)}.")

        self._polygons = tuple(parsed_polys)

    @property
    def polygons(self) -> Tuple[Polygon, ...]:
        return self._polygons

    @property
    def bounds(self) -> BoundingBox:
        all_coords: List[Coordinate] = []
        for poly in self._polygons:
            all_coords.extend(poly.exterior.coordinates)
        return _compute_bounds(all_coords)

    def to_coordinates_list(self) -> List[List[List[Tuple[float, ...]]]]:
        """Return list of polygons formatted for GeoJSON MultiPolygon."""
        return [p.to_coordinates_list() for p in self._polygons]

    def __len__(self) -> int:
        return len(self._polygons)

    def __iter__(self) -> Iterable[Polygon]:
        return iter(self._polygons)

    def __getitem__(self, idx: int) -> Polygon:
        return self._polygons[idx]

    def __repr__(self) -> str:
        return f"MultiPolygon(polygons={len(self._polygons)}, crs='{self.crs}')"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, MultiPolygon):
            return False
        return self._polygons == other._polygons and self.crs == other.crs


class OilSpillGeometry:
    """Domain model representing a detected oil spill area with geospatial geometry and metadata.

    Encapsulates:
    - Unique spill identifier
    - Geometric boundary (Polygon or MultiPolygon)
    - UTC detection timestamp
    - Source sensor information (e.g. Sentinel-1 SAR)
    - Detection confidence (0.0 to 1.0)
    - Coordinate Reference System
    """

    def __init__(
        self,
        spill_id: str,
        geometry: Polygon | MultiPolygon,
        detection_timestamp: datetime,
        source_sensor: str = "Sentinel-1",
        confidence: float = 1.0,
        crs: str = "EPSG:4326",
        properties: dict[str, Any] | None = None,
        validate: bool = True,
    ) -> None:
        if not spill_id or not isinstance(spill_id, str):
            raise ValueError("spill_id must be a non-empty string.")

        if not isinstance(geometry, (Polygon, MultiPolygon)):
            raise InvalidGeometryError(
                f"Oil spill geometry must be a Polygon or MultiPolygon, got {type(geometry)}."
            )

        if validate:
            validate_timestamp_utc(detection_timestamp)
            if not (0.0 <= confidence <= 1.0):
                raise ValueError(f"Confidence score must be between 0.0 and 1.0, got {confidence}.")

        self.spill_id = spill_id.strip()
        self.geometry = geometry
        self.detection_timestamp = detection_timestamp
        self.source_sensor = source_sensor
        self.confidence = float(confidence)
        self.crs = validate_crs(crs)
        self.properties = properties.copy() if properties else {}

    @property
    def bounds(self) -> BoundingBox:
        """Envelope bounding box of the oil spill."""
        return self.geometry.bounds

    def to_feature_dict(self) -> dict[str, Any]:
        """Convert spill geometry and metadata to a standard GeoJSON Feature dictionary."""
        from gis.geometry.geojson import to_geojson

        return {
            "type": "Feature",
            "id": self.spill_id,
            "geometry": to_geojson(self.geometry),
            "properties": {
                "spill_id": self.spill_id,
                "detection_timestamp": self.detection_timestamp.isoformat(),
                "source_sensor": self.source_sensor,
                "confidence": self.confidence,
                "crs": self.crs,
                **self.properties,
            },
        }

    def __repr__(self) -> str:
        return (
            f"OilSpillGeometry(id='{self.spill_id}', type='{type(self.geometry).__name__}', "
            f"timestamp='{self.detection_timestamp.isoformat()}', confidence={self.confidence})"
        )
