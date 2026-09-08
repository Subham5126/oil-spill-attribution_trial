"""Geospatial geometry and coordinate validation logic.

Enforces topological integrity, coordinate bounds, CRS consistency,
and GeoJSON (RFC 7946) standard compliance.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Sequence, Tuple, Union

from gis.geometry.exceptions import (
    CRSValidationError,
    EmptyGeometryError,
    InvalidCoordinateError,
    InvalidGeometryError,
    SelfIntersectionError,
)

# Standard geographic CRS identifiers representing WGS 84
WGS84_CRS_IDENTIFIERS = {
    "EPSG:4326",
    "urn:ogc:def:crs:OGC:1.3:CRS84",
    "urn:ogc:def:crs:EPSG::4326",
    "WGS84",
    "WGS 84",
}


def validate_coordinate_values(
    x: float,
    y: float,
    z: float | None = None,
    crs: str = "EPSG:4326",
) -> None:
    """Validate numeric and spatial validity of a single coordinate point.

    In geographic systems (WGS84 / EPSG:4326):
    - x corresponds to Longitude: [-180.0, 180.0]
    - y corresponds to Latitude: [-90.0, 90.0]

    Args:
        x: X coordinate or Longitude.
        y: Y coordinate or Latitude.
        z: Optional Z coordinate or elevation.
        crs: Coordinate Reference System identifier.

    Raises:
        InvalidCoordinateError: If coordinates are non-finite or outside range.
    """
    if not (isinstance(x, (int, float)) and isinstance(y, (int, float))):
        raise InvalidCoordinateError(f"Coordinates must be numeric, got x={type(x)}, y={type(y)}.")

    if not (math.isfinite(x) and math.isfinite(y)):
        raise InvalidCoordinateError(f"Coordinates must be finite numbers, got ({x}, {y}).")

    if z is not None:
        if not isinstance(z, (int, float)):
            raise InvalidCoordinateError(f"Elevation/Z must be numeric, got {type(z)}.")
        if not math.isfinite(z):
            raise InvalidCoordinateError(f"Elevation/Z must be a finite number, got {z}.")

    # Geographic boundary check for standard WGS84
    if is_wgs84(crs):
        if not (-180.0 <= x <= 180.0):
            raise InvalidCoordinateError(
                f"Longitude {x} is out of bounds [-180.0, 180.0] in CRS {crs}."
            )
        if not (-90.0 <= y <= 90.0):
            raise InvalidCoordinateError(
                f"Latitude {y} is out of bounds [-90.0, 90.0] in CRS {crs}."
            )


def is_wgs84(crs: str) -> bool:
    """Check if the given CRS string represents WGS 84 geographic coordinates."""
    if not crs or not isinstance(crs, str):
        return False
    return crs.strip().upper() in {ident.upper() for ident in WGS84_CRS_IDENTIFIERS}


def validate_crs(crs: str) -> str:
    """Validate CRS string format.

    Args:
        crs: CRS identifier (e.g. 'EPSG:4326').

    Returns:
        Normalized CRS string.

    Raises:
        CRSValidationError: If CRS identifier is missing or empty.
    """
    if not crs or not isinstance(crs, str) or not crs.strip():
        raise CRSValidationError("CRS must be a non-empty string identifier (e.g. 'EPSG:4326').")
    return crs.strip()


def validate_line_coordinates(coords: Sequence[Tuple[float, ...]], crs: str = "EPSG:4326") -> None:
    """Validate coordinate sequence for a LineString.

    Must contain at least two coordinate positions.

    Args:
        coords: Sequence of coordinate tuples.
        crs: Coordinate Reference System.

    Raises:
        EmptyGeometryError: If sequence is empty.
        InvalidGeometryError: If sequence contains fewer than 2 points.
        InvalidCoordinateError: If any coordinate is invalid.
    """
    if coords is None or len(coords) == 0:
        raise EmptyGeometryError("LineString coordinates cannot be empty.")
    if len(coords) < 2:
        raise InvalidGeometryError(
            f"LineString requires at least 2 coordinate points, got {len(coords)}."
        )

    for pt in coords:
        validate_coordinate_values(pt[0], pt[1], pt[2] if len(pt) > 2 else None, crs=crs)


def signed_ring_area(coords: Sequence[Tuple[float, ...]]) -> float:
    """Calculate the signed planar area of a coordinate ring using the Shoelace formula.

    Positive area indicates counterclockwise (CCW) winding.
    Negative area indicates clockwise (CW) winding.

    Args:
        coords: Sequence of (x, y) coordinates representing a closed ring.

    Returns:
        Signed planar area.
    """
    n = len(coords)
    if n < 4:
        return 0.0
    area = 0.0
    for i in range(n - 1):
        x1, y1 = coords[i][0], coords[i][1]
        x2, y2 = coords[i + 1][0], coords[i + 1][1]
        area += (x1 * y2) - (x2 * y1)
    return area / 2.0


def validate_linear_ring(coords: Sequence[Tuple[float, ...]], crs: str = "EPSG:4326") -> None:
    """Validate a LinearRing (polygon boundary).

    Requirements:
    - At least 4 points (including the repeated closing point).
    - First point must match the last point (closed).
    - At least 3 distinct points (non-collapsed, non-zero area).
    - No self-intersections among non-adjacent segments.

    Args:
        coords: Sequence of coordinates.
        crs: Coordinate Reference System.

    Raises:
        EmptyGeometryError: If sequence is empty.
        InvalidGeometryError: If ring is unclosed, has < 4 points, or zero area.
        SelfIntersectionError: If boundary intersects itself.
    """
    if coords is None or len(coords) == 0:
        raise EmptyGeometryError("Linear ring coordinates cannot be empty.")
    if len(coords) < 4:
        raise InvalidGeometryError(
            f"LinearRing requires at least 4 coordinate positions (got {len(coords)})."
        )

    # Validate each coordinate position
    for pt in coords:
        validate_coordinate_values(pt[0], pt[1], pt[2] if len(pt) > 2 else None, crs=crs)

    # Check closure (first point equals last point)
    first_pt = (coords[0][0], coords[0][1])
    last_pt = (coords[-1][0], coords[-1][1])
    if not math.isclose(first_pt[0], last_pt[0], abs_tol=1e-9) or not math.isclose(
        first_pt[1], last_pt[1], abs_tol=1e-9
    ):
        raise InvalidGeometryError(
            f"LinearRing must be closed: first point {first_pt} does not match last point {last_pt}."
        )

    # Check distinct vertices count
    distinct = {(round(pt[0], 9), round(pt[1], 9)) for pt in coords[:-1]}
    if len(distinct) < 3:
        raise InvalidGeometryError(
            f"LinearRing must contain at least 3 distinct vertices, found {len(distinct)}."
        )

    # Check self-intersection
    check_ring_self_intersection(coords)

    # Check non-zero area
    area = signed_ring_area(coords)
    if math.isclose(area, 0.0, abs_tol=1e-12):
        raise InvalidGeometryError("LinearRing has zero area or collinear vertices.")



def check_ring_self_intersection(coords: Sequence[Tuple[float, ...]]) -> None:
    """Check whether a ring self-intersects.

    Raises:
        SelfIntersectionError: If non-adjacent segments intersect.
    """
    n = len(coords) - 1  # number of segments
    segments = [(coords[i], coords[i + 1]) for i in range(n)]

    for i in range(n):
        seg1_a, seg1_b = segments[i]
        for j in range(i + 1, n):
            # Adjacent segments share a vertex; skip immediate neighbors and wraparound
            if j == i + 1 or (i == 0 and j == n - 1):
                continue

            seg2_a, seg2_b = segments[j]
            if segments_intersect(seg1_a, seg1_b, seg2_a, seg2_b):
                raise SelfIntersectionError(
                    f"Ring self-intersects between segment {i} ({seg1_a[:2]}->{seg1_b[:2]}) "
                    f"and segment {j} ({seg2_a[:2]}->{seg2_b[:2]})."
                )


def _orientation(p: Tuple[float, ...], q: Tuple[float, ...], r: Tuple[float, ...]) -> int:
    """Find orientation of ordered triplet (p, q, r).

    Returns:
        0 -> Collinear
        1 -> Clockwise
        2 -> Counterclockwise
    """
    val = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
    if math.isclose(val, 0.0, abs_tol=1e-12):
        return 0
    return 1 if val > 0 else 2


def _on_segment(p: Tuple[float, ...], q: Tuple[float, ...], r: Tuple[float, ...]) -> bool:
    """Check if point q lies on segment pr."""
    return (
        min(p[0], r[0]) - 1e-12 <= q[0] <= max(p[0], r[0]) + 1e-12
        and min(p[1], r[1]) - 1e-12 <= q[1] <= max(p[1], r[1]) + 1e-12
    )


def segments_intersect(
    p1: Tuple[float, ...],
    q1: Tuple[float, ...],
    p2: Tuple[float, ...],
    q2: Tuple[float, ...],
) -> bool:
    """Determine whether 2D line segment p1-q1 intersects segment p2-q2."""
    # Bounding box quick check
    if (
        max(p1[0], q1[0]) < min(p2[0], q2[0]) - 1e-12
        or min(p1[0], q1[0]) > max(p2[0], q2[0]) + 1e-12
        or max(p1[1], q1[1]) < min(p2[1], q2[1]) - 1e-12
        or min(p1[1], q1[1]) > max(p2[1], q2[1]) + 1e-12
    ):
        return False

    o1 = _orientation(p1, q1, p2)
    o2 = _orientation(p1, q1, q2)
    o3 = _orientation(p2, q2, p1)
    o4 = _orientation(p2, q2, q1)

    # General case
    if o1 != o2 and o3 != o4:
        return True

    # Special Cases (collinear segments)
    if o1 == 0 and _on_segment(p1, p2, q1):
        return True
    if o2 == 0 and _on_segment(p1, q2, q1):
        return True
    if o3 == 0 and _on_segment(p2, p1, q2):
        return True
    if o4 == 0 and _on_segment(p2, q1, q2):
        return True

    return False


def point_in_polygon(
    pt: Tuple[float, ...],
    polygon_ring: Sequence[Tuple[float, ...]],
) -> bool:
    """Test if a 2D point lies inside a polygon ring using ray-casting.

    Args:
        pt: Coordinate (x, y).
        polygon_ring: Sequence of (x, y) coordinates forming a closed ring.

    Returns:
        True if inside or on boundary, False otherwise.
    """
    x, y = pt[0], pt[1]
    inside = False
    n = len(polygon_ring)
    for i in range(n - 1):
        xi, yi = polygon_ring[i][0], polygon_ring[i][1]
        xj, yj = polygon_ring[i + 1][0], polygon_ring[i + 1][1]

        # Check if point is directly on segment
        if _on_segment((xi, yi), (x, y), (xj, yj)) and math.isclose(
            (yj - yi) * (x - xi), (y - yi) * (xj - xi), abs_tol=1e-9
        ):
            return True

        intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-18) + xi)
        if intersect:
            inside = not inside
    return inside


def validate_polygon_rings(
    exterior: Sequence[Tuple[float, ...]],
    interiors: Sequence[Sequence[Tuple[float, ...]]] | None = None,
    crs: str = "EPSG:4326",
) -> None:
    """Validate exterior and interior boundary rings of a polygon.

    Args:
        exterior: Coordinates of the exterior boundary.
        interiors: Optional sequence of interior ring (hole) coordinates.
        crs: Coordinate Reference System.

    Raises:
        InvalidGeometryError: If exterior or hole rings violate containment or overlap rules.
    """
    validate_linear_ring(exterior, crs=crs)

    if interiors:
        for idx, hole in enumerate(interiors):
            validate_linear_ring(hole, crs=crs)

            # Check that hole vertices are contained within the exterior ring
            for pt in hole[:-1]:
                if not point_in_polygon(pt, exterior):
                    raise InvalidGeometryError(
                        f"Hole {idx} vertex {pt[:2]} is outside the exterior boundary."
                    )


def validate_timestamp_utc(ts: datetime) -> None:
    """Validate that a datetime timestamp is timezone-aware and set to UTC.

    Adheres to ARCHITECTURE.md Section 29 (Time Handling).

    Args:
        ts: Datetime object.

    Raises:
        ValueError: If timestamp is naive (no timezone) or not UTC.
    """
    if not isinstance(ts, datetime):
        raise TypeError(f"Detection timestamp must be a datetime object, got {type(ts)}.")

    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        raise ValueError(
            f"Timestamp {ts} must be timezone-aware (UTC). Naive datetimes are prohibited."
        )
