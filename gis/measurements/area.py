"""Geodesic and planar surface area calculations for GIS geometries.

Calculates spherical surface area in square meters (m²) and square kilometers (km²)
using the Chamberlain-Duquette spherical excess line-integral algorithm over the
WGS84 authalic Earth sphere.
"""

from __future__ import annotations

import math
from typing import Sequence, Tuple, Union

from gis.geometry.models import (
    Coordinate,
    LinearRing,
    MultiPolygon,
    OilSpillGeometry,
    Polygon,
)
from gis.geometry.validation import signed_ring_area
from gis.measurements.distance import EARTH_RADIUS_METERS, _extract_coord
from gis.measurements.exceptions import CalculationError


def calculate_ring_geodesic_area(
    ring: LinearRing | Sequence[Coordinate | Sequence[float]],
) -> float:
    """Calculate the geodesic surface area of a closed coordinate ring in square meters.

    Uses the Chamberlain-Duquette spherical excess formula on the WGS84 authalic sphere.

    Args:
        ring: LinearRing or sequence of closed coordinates.

    Returns:
        Surface area in square meters (m²). Always non-negative.
    """
    if isinstance(ring, LinearRing):
        coords = ring.coordinates
    elif isinstance(ring, (list, tuple)):
        coords = ring
    else:
        raise CalculationError(f"Expected LinearRing or sequence of coordinates, got {type(ring)}.")

    n = len(coords)
    if n < 4:
        return 0.0

    total_sum = 0.0
    for i in range(n - 1):
        lon1, lat1 = _extract_coord(coords[i])
        lon2, lat2 = _extract_coord(coords[i + 1])

        lambda1 = math.radians(lon1)
        lambda2 = math.radians(lon2)
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)

        # Chamberlin-Duquette line integral
        total_sum += (lambda2 - lambda1) * (2.0 + math.sin(phi1) + math.sin(phi2))

    area_sq_m = abs(total_sum * (EARTH_RADIUS_METERS**2) / 2.0)
    return area_sq_m


def calculate_polygon_area(
    polygon: Polygon,
    in_sq_km: bool = False,
) -> float:
    """Calculate the net geodesic area of a Polygon (exterior minus holes).

    Args:
        polygon: Polygon instance.
        in_sq_km: If True, returns area in square kilometers (km²); otherwise m².

    Returns:
        Net surface area.

    Raises:
        CalculationError: If hole areas exceed exterior area.
    """
    if not isinstance(polygon, Polygon):
        raise CalculationError(f"Expected Polygon, got {type(polygon)}.")

    exterior_area = calculate_ring_geodesic_area(polygon.exterior)
    holes_area = 0.0

    for hole in polygon.interiors:
        holes_area += calculate_ring_geodesic_area(hole)

    net_area = exterior_area - holes_area
    if net_area < 0.0:
        raise CalculationError(
            f"Calculated negative polygon area ({net_area} m²): hole areas exceed exterior boundary."
        )

    return net_area / 1_000_000.0 if in_sq_km else net_area


def calculate_multipolygon_area(
    multipolygon: MultiPolygon,
    in_sq_km: bool = False,
) -> float:
    """Calculate the total surface area of a MultiPolygon by summing constituent polygons.

    Args:
        multipolygon: MultiPolygon instance.
        in_sq_km: If True, returns area in square kilometers.

    Returns:
        Total surface area in m² or km².
    """
    if not isinstance(multipolygon, MultiPolygon):
        raise CalculationError(f"Expected MultiPolygon, got {type(multipolygon)}.")

    total_area = sum(calculate_polygon_area(poly, in_sq_km=False) for poly in multipolygon.polygons)
    return total_area / 1_000_000.0 if in_sq_km else total_area


def calculate_spill_area(
    spill: OilSpillGeometry | Polygon | MultiPolygon,
    in_sq_km: bool = False,
) -> float:
    """Calculate the surface area of an oil spill geometry.

    Args:
        spill: OilSpillGeometry, Polygon, or MultiPolygon.
        in_sq_km: If True, returns area in km².

    Returns:
        Surface area.
    """
    if isinstance(spill, OilSpillGeometry):
        geom = spill.geometry
    else:
        geom = spill

    if isinstance(geom, Polygon):
        return calculate_polygon_area(geom, in_sq_km=in_sq_km)
    if isinstance(geom, MultiPolygon):
        return calculate_multipolygon_area(geom, in_sq_km=in_sq_km)

    raise CalculationError(f"Cannot calculate spill area for object of type {type(spill)}.")
