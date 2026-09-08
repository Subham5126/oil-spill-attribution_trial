"""Centroid and center of mass calculations for geospatial geometries.

Implements true 2D polygon moment algorithms and area-weighted multi-polygon
centroids, returning Point instances from gis.geometry.
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
    Point,
    Polygon,
)
from gis.geometry.validation import signed_ring_area
from gis.measurements.distance import haversine_distance
from gis.measurements.exceptions import CalculationError


def calculate_ring_centroid(
    ring: LinearRing | Sequence[Coordinate | Sequence[float]],
    crs: str = "EPSG:4326",
) -> Tuple[float, float, float]:
    """Calculate the 2D planar centroid and absolute area of a single ring.

    Uses standard second-order polygon moments.

    Args:
        ring: LinearRing or sequence of coordinates.
        crs: Coordinate Reference System.

    Returns:
        Tuple of (centroid_x, centroid_y, abs_area).

    Raises:
        CalculationError: If ring has zero area or collinear points.
    """
    if isinstance(ring, LinearRing):
        coords = ring.coordinates
        crs = ring.crs
    elif isinstance(ring, (list, tuple)):
        coords = ring
    else:
        raise CalculationError(f"Expected LinearRing or sequence of coordinates, got {type(ring)}.")

    n = len(coords)
    if n < 4:
        raise CalculationError(f"Cannot calculate centroid of ring with {n} points.")

    signed_area_val = 0.0
    cx_accum = 0.0
    cy_accum = 0.0

    for i in range(n - 1):
        x0 = coords[i].x if isinstance(coords[i], Coordinate) else float(coords[i][0])
        y0 = coords[i].y if isinstance(coords[i], Coordinate) else float(coords[i][1])
        x1 = coords[i + 1].x if isinstance(coords[i + 1], Coordinate) else float(coords[i + 1][0])
        y1 = coords[i + 1].y if isinstance(coords[i + 1], Coordinate) else float(coords[i + 1][1])

        cross = (x0 * y1) - (x1 * y0)
        signed_area_val += cross
        cx_accum += (x0 + x1) * cross
        cy_accum += (y0 + y1) * cross

    signed_area_val = signed_area_val / 2.0
    if math.isclose(signed_area_val, 0.0, abs_tol=1e-14):
        # Fallback to mean of distinct vertices for degenerate ring
        pts = coords[:-1]
        mean_x = sum(p.x if isinstance(p, Coordinate) else float(p[0]) for p in pts) / len(pts)
        mean_y = sum(p.y if isinstance(p, Coordinate) else float(p[1]) for p in pts) / len(pts)
        return (mean_x, mean_y, 0.0)

    factor = 6.0 * signed_area_val
    cx = cx_accum / factor
    cy = cy_accum / factor

    return (cx, cy, abs(signed_area_val))


def calculate_polygon_centroid(polygon: Polygon) -> Point:
    """Calculate the true center of mass of a Polygon, taking holes into account.

    Args:
        polygon: Polygon instance.

    Returns:
        Point instance representing the centroid.
    """
    if not isinstance(polygon, Polygon):
        raise CalculationError(f"Expected Polygon, got {type(polygon)}.")

    ext_cx, ext_cy, ext_area = calculate_ring_centroid(polygon.exterior, crs=polygon.crs)

    if not polygon.interiors:
        return Point(ext_cx, ext_cy, crs=polygon.crs)

    # If holes exist, subtract their moments
    total_moment_x = ext_cx * ext_area
    total_moment_y = ext_cy * ext_area
    net_area = ext_area

    for hole in polygon.interiors:
        h_cx, h_cy, h_area = calculate_ring_centroid(hole, crs=polygon.crs)
        total_moment_x -= h_cx * h_area
        total_moment_y -= h_cy * h_area
        net_area -= h_area

    if math.isclose(net_area, 0.0, abs_tol=1e-14) or net_area < 0:
        return Point(ext_cx, ext_cy, crs=polygon.crs)

    return Point(total_moment_x / net_area, total_moment_y / net_area, crs=polygon.crs)



def calculate_multipolygon_centroid(multipolygon: MultiPolygon) -> Point:
    """Calculate the area-weighted centroid of a MultiPolygon.

    Args:
        multipolygon: MultiPolygon instance.

    Returns:
        Point representing the composite center of mass.
    """
    if not isinstance(multipolygon, MultiPolygon):
        raise CalculationError(f"Expected MultiPolygon, got {type(multipolygon)}.")

    total_weight_x = 0.0
    total_weight_y = 0.0
    total_area = 0.0

    for poly in multipolygon.polygons:
        poly_centroid = calculate_polygon_centroid(poly)
        _, _, poly_area = calculate_ring_centroid(poly.exterior, crs=poly.crs)

        total_weight_x += poly_centroid.x * poly_area
        total_weight_y += poly_centroid.y * poly_area
        total_area += poly_area

    if math.isclose(total_area, 0.0, abs_tol=1e-14):
        # Fallback to mean of centers
        center_x = sum(p.bounds.center[0] for p in multipolygon.polygons) / len(multipolygon)
        center_y = sum(p.bounds.center[1] for p in multipolygon.polygons) / len(multipolygon)
        return Point(center_x, center_y, crs=multipolygon.crs)

    return Point(
        total_weight_x / total_area,
        total_weight_y / total_area,
        crs=multipolygon.crs,
    )


def calculate_linestring_centroid(line: LineString) -> Point:
    """Calculate length-weighted centroid of a LineString.

    Args:
        line: LineString instance.

    Returns:
        Point at the length-weighted center of the path.
    """
    if not isinstance(line, LineString):
        raise CalculationError(f"Expected LineString, got {type(line)}.")

    coords = line.coordinates
    if len(coords) == 0:
        raise CalculationError("Cannot calculate centroid of empty LineString.")
    if len(coords) == 1:
        return Point(coords[0].x, coords[0].y, crs=line.crs)

    total_len = 0.0
    weighted_x = 0.0
    weighted_y = 0.0

    for i in range(len(coords) - 1):
        seg_len = haversine_distance(coords[i], coords[i + 1])
        mid_x = (coords[i].x + coords[i + 1].x) / 2.0
        mid_y = (coords[i].y + coords[i + 1].y) / 2.0

        weighted_x += mid_x * seg_len
        weighted_y += mid_y * seg_len
        total_len += seg_len

    if math.isclose(total_len, 0.0, abs_tol=1e-12):
        return Point(coords[0].x, coords[0].y, crs=line.crs)

    return Point(weighted_x / total_len, weighted_y / total_len, crs=line.crs)



def calculate_spill_centroid(
    spill: OilSpillGeometry | Polygon | MultiPolygon | Point,
) -> Point:
    """Calculate the centroid of an oil spill or geometry.

    Args:
        spill: OilSpillGeometry, Polygon, MultiPolygon, or Point.

    Returns:
        Point instance.
    """
    if isinstance(spill, OilSpillGeometry):
        geom = spill.geometry
    else:
        geom = spill

    if isinstance(geom, Point):
        return geom
    if isinstance(geom, Polygon):
        return calculate_polygon_centroid(geom)
    if isinstance(geom, MultiPolygon):
        return calculate_multipolygon_centroid(geom)
    if isinstance(geom, LineString):
        return calculate_linestring_centroid(geom)

    raise CalculationError(f"Cannot calculate centroid for object of type {type(spill)}.")
