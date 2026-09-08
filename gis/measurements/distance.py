"""Geodesic distance and perimeter calculations for GIS geometries.

Uses the Haversine great-circle formula over the WGS84 authalic Earth sphere
to provide physically accurate distances and perimeters in meters and kilometers.
"""

from __future__ import annotations

import math
from typing import Sequence, Tuple, Union

from gis.geometry.models import (
    Coordinate,
    LinearRing,
    LineString,
    MultiPolygon,
    OilSpillGeometry,
    Polygon,
)
from gis.measurements.exceptions import CalculationError

# WGS84 Authalic Earth Radius in meters (radius of sphere with equal surface area)
EARTH_RADIUS_METERS: float = 6371008.8


def _extract_coord(coord: Coordinate | Sequence[float]) -> Tuple[float, float]:
    """Extract (lon, lat) floats from Coordinate or sequence."""
    if isinstance(coord, Coordinate):
        return (coord.x, coord.y)
    if isinstance(coord, (tuple, list)):
        if len(coord) < 2:
            raise CalculationError(f"Coordinate sequence must have at least 2 values, got {coord}.")
        return (float(coord[0]), float(coord[1]))
    raise CalculationError(f"Unsupported coordinate type: {type(coord)}.")


def haversine_distance(
    coord1: Coordinate | Sequence[float],
    coord2: Coordinate | Sequence[float],
) -> float:
    """Calculate the Great-Circle distance between two coordinates in meters.

    Args:
        coord1: First point (lon, lat) or Coordinate.
        coord2: Second point (lon, lat) or Coordinate.

    Returns:
        Great-circle distance in meters.
    """
    lon1, lat1 = _extract_coord(coord1)
    lon2, lat2 = _extract_coord(coord2)

    # Identical coordinates check
    if math.isclose(lon1, lon2, abs_tol=1e-11) and math.isclose(lat1, lat2, abs_tol=1e-11):
        return 0.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    # Numerical safeguard against precision overflow
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return EARTH_RADIUS_METERS * c


def calculate_path_length(
    line: LineString | Sequence[Coordinate | Sequence[float]],
    in_km: bool = False,
) -> float:
    """Calculate the total geodesic length of a LineString or coordinate path.

    Args:
        line: LineString instance or sequence of coordinates.
        in_km: If True, return length in kilometers; otherwise in meters.

    Returns:
        Total path length.
    """
    if isinstance(line, LineString):
        coords = line.coordinates
    elif isinstance(line, (list, tuple)):
        coords = line
    else:
        raise CalculationError(f"Expected LineString or sequence of coordinates, got {type(line)}.")

    if len(coords) < 2:
        return 0.0

    total_length = 0.0
    for i in range(len(coords) - 1):
        total_length += haversine_distance(coords[i], coords[i + 1])

    return total_length / 1000.0 if in_km else total_length


def calculate_ring_perimeter(
    ring: LinearRing | Sequence[Coordinate | Sequence[float]],
    in_km: bool = False,
) -> float:
    """Calculate the geodesic perimeter of a closed ring in meters or kilometers.

    Args:
        ring: LinearRing or sequence of coordinates.
        in_km: If True, returns value in kilometers.

    Returns:
        Ring perimeter.
    """
    if isinstance(ring, LinearRing):
        coords = ring.coordinates
    elif isinstance(ring, (list, tuple)):
        coords = ring
    else:
        raise CalculationError(f"Expected LinearRing or coordinate sequence, got {type(ring)}.")

    if len(coords) < 4:
        return 0.0

    total_dist = 0.0
    for i in range(len(coords) - 1):
        total_dist += haversine_distance(coords[i], coords[i + 1])

    return total_dist / 1000.0 if in_km else total_dist


def calculate_perimeter(
    geom: LinearRing | Polygon | MultiPolygon | OilSpillGeometry,
    include_holes: bool = False,
    in_km: bool = False,
) -> float:
    """Calculate the geodesic perimeter of any polygon or oil spill geometry.

    Args:
        geom: LinearRing, Polygon, MultiPolygon, or OilSpillGeometry.
        include_holes: If True, adds the perimeters of interior rings (holes).
        in_km: If True, returns perimeter in kilometers.

    Returns:
        Perimeter in meters (or kilometers if in_km is True).
    """
    if isinstance(geom, OilSpillGeometry):
        geom = geom.geometry

    if isinstance(geom, LinearRing):
        return calculate_ring_perimeter(geom, in_km=in_km)

    if isinstance(geom, Polygon):
        total = calculate_ring_perimeter(geom.exterior, in_km=False)
        if include_holes:
            for hole in geom.interiors:
                total += calculate_ring_perimeter(hole, in_km=False)
        return total / 1000.0 if in_km else total

    if isinstance(geom, MultiPolygon):
        total = 0.0
        for poly in geom.polygons:
            total += calculate_perimeter(poly, include_holes=include_holes, in_km=False)
        return total / 1000.0 if in_km else total

    raise CalculationError(f"Cannot calculate perimeter for object of type {type(geom)}.")
