"""Forward and inverse coordinate projection transformations and geometry reprojection."""

from __future__ import annotations

import math
from typing import Any, Tuple, Union

from gis.geometry.models import BoundingBox, LineString, MultiPolygon, Point, Polygon
from gis.projection.crs import CRS
from gis.projection.exceptions import OutOfRangeError, ProjectionError

# WGS 84 Ellipsoid parameters
WGS84_A = 6378137.0  # semi-major axis (meters)
WGS84_F = 1.0 / 298.257223563  # flattening
WGS84_B = WGS84_A * (1.0 - WGS84_F)  # semi-minor axis
WGS84_E2 = 2.0 * WGS84_F - WGS84_F * WGS84_F  # eccentricity squared
WGS84_E_PRIME2 = WGS84_E2 / (1.0 - WGS84_E2)  # second eccentricity squared

UTM_K0 = 0.9996  # UTM scale factor on central meridian
UTM_FALSE_EASTING = 500000.0  # False Easting (meters)
UTM_FALSE_NORTHING_SOUTH = 10000000.0  # False Northing in Southern Hemisphere (meters)

WEB_MERCATOR_MAX_LAT = 85.0511287798066


def wgs84_to_utm(
    longitude: float,
    latitude: float,
    zone: int,
    hemisphere: str = "N",
) -> Tuple[float, float]:
    """Convert WGS84 geographic coordinates (lon, lat in degrees) to UTM Easting and Northing (meters).

    Uses high-precision Transverse Mercator series expansion.
    """
    if not (-80.0 <= latitude <= 84.0):
        raise OutOfRangeError(f"Latitude {latitude} is outside standard UTM limits (-80 to +84 degrees).")

    hemi = hemisphere.upper()
    if hemi not in ("N", "S"):
        raise ProjectionError(f"Hemisphere must be 'N' or 'S', got '{hemisphere}'")

    lat_rad = math.radians(latitude)
    lon_rad = math.radians(longitude)

    # Central meridian of the zone
    lon0 = (zone * 6.0) - 183.0
    lon0_rad = math.radians(lon0)

    delta_lon = lon_rad - lon0_rad

    sin_lat = math.sin(lat_rad)
    cos_lat = math.cos(lat_rad)
    tan_lat = math.tan(lat_rad)

    # Radius of curvature in the prime vertical
    N = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    T = tan_lat * tan_lat
    C = WGS84_E_PRIME2 * cos_lat * cos_lat
    A = cos_lat * delta_lon

    # Meridian distance M
    M = WGS84_A * (
        (1.0 - WGS84_E2 / 4.0 - 3.0 * WGS84_E2 * WGS84_E2 / 64.0 - 5.0 * WGS84_E2**3 / 256.0) * lat_rad
        - (3.0 * WGS84_E2 / 8.0 + 3.0 * WGS84_E2 * WGS84_E2 / 32.0 + 45.0 * WGS84_E2**3 / 1024.0) * math.sin(2.0 * lat_rad)
        + (15.0 * WGS84_E2 * WGS84_E2 / 256.0 + 45.0 * WGS84_E2**3 / 1024.0) * math.sin(4.0 * lat_rad)
        - (35.0 * WGS84_E2**3 / 3072.0) * math.sin(6.0 * lat_rad)
    )

    # Easting
    easting = UTM_K0 * N * (
        A
        + (1.0 - T + C) * (A**3) / 6.0
        + (5.0 - 18.0 * T + T * T + 72.0 * C - 58.0 * WGS84_E_PRIME2) * (A**5) / 120.0
    ) + UTM_FALSE_EASTING

    # Northing
    northing = UTM_K0 * (
        M
        + N
        * tan_lat
        * (
            (A * A) / 2.0
            + (5.0 - T + 9.0 * C + 4.0 * C * C) * (A**4) / 24.0
            + (61.0 - 58.0 * T + T * T + 600.0 * C - 330.0 * WGS84_E_PRIME2) * (A**6) / 720.0
        )
    )

    if hemi == "S":
        northing += UTM_FALSE_NORTHING_SOUTH

    return easting, northing


def utm_to_wgs84(
    easting: float,
    northing: float,
    zone: int,
    hemisphere: str = "N",
) -> Tuple[float, float]:
    """Convert UTM Easting and Northing (meters) to WGS84 geographic coordinates (lon, lat in degrees)."""
    hemi = hemisphere.upper()
    if hemi not in ("N", "S"):
        raise ProjectionError(f"Hemisphere must be 'N' or 'S', got '{hemisphere}'")

    x = easting - UTM_FALSE_EASTING
    y = northing
    if hemi == "S":
        y -= UTM_FALSE_NORTHING_SOUTH

    e1 = (1.0 - math.sqrt(1.0 - WGS84_E2)) / (1.0 + math.sqrt(1.0 - WGS84_E2))

    M = y / UTM_K0
    mu = M / (
        WGS84_A * (1.0 - WGS84_E2 / 4.0 - 3.0 * WGS84_E2 * WGS84_E2 / 64.0 - 5.0 * WGS84_E2**3 / 256.0)
    )

    # Footprint latitude
    phi1_rad = (
        mu
        + (3.0 * e1 / 2.0 - 27.0 * e1**3 / 32.0) * math.sin(2.0 * mu)
        + (21.0 * e1**2 / 16.0 - 55.0 * e1**4 / 32.0) * math.sin(4.0 * mu)
        + (151.0 * e1**3 / 96.0) * math.sin(6.0 * mu)
        + (1097.0 * e1**4 / 512.0) * math.sin(8.0 * mu)
    )

    sin_phi1 = math.sin(phi1_rad)
    cos_phi1 = math.cos(phi1_rad)
    tan_phi1 = math.tan(phi1_rad)

    N1 = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_phi1 * sin_phi1)
    T1 = tan_phi1 * tan_phi1
    C1 = WGS84_E_PRIME2 * cos_phi1 * cos_phi1
    R1 = WGS84_A * (1.0 - WGS84_E2) / ((1.0 - WGS84_E2 * sin_phi1 * sin_phi1) ** 1.5)
    D = x / (N1 * UTM_K0)

    # Latitude
    lat_rad = phi1_rad - (N1 * tan_phi1 / R1) * (
        (D * D) / 2.0
        - (5.0 + 3.0 * T1 + 10.0 * C1 - 4.0 * C1 * C1 - 9.0 * WGS84_E_PRIME2) * (D**4) / 24.0
        + (61.0 + 90.0 * T1 + 298.0 * C1 + 45.0 * T1 * T1 - 252.0 * WGS84_E_PRIME2 - 3.0 * C1 * C1)
        * (D**6)
        / 720.0
    )

    # Longitude
    lon_rad = (
        D
        - (1.0 + 2.0 * T1 + C1) * (D**3) / 6.0
        + (5.0 - 2.0 * C1 + 28.0 * T1 - 3.0 * C1 * C1 + 8.0 * WGS84_E_PRIME2 + 24.0 * T1 * T1)
        * (D**5)
        / 120.0
    ) / cos_phi1

    lon0 = (zone * 6.0) - 183.0
    lon0_rad = math.radians(lon0)

    lon_deg = math.degrees(lon0_rad + lon_rad)
    lat_deg = math.degrees(lat_rad)

    # Normalize longitude to [-180, 180]
    lon_deg = ((lon_deg + 180.0) % 360.0) - 180.0

    return lon_deg, lat_deg


def wgs84_to_web_mercator(longitude: float, latitude: float) -> Tuple[float, float]:
    """Convert WGS84 coordinates to EPSG:3857 Web Mercator (meters)."""
    if not (-WEB_MERCATOR_MAX_LAT <= latitude <= WEB_MERCATOR_MAX_LAT):
        raise OutOfRangeError(
            f"Latitude {latitude} exceeds Web Mercator valid range (±{WEB_MERCATOR_MAX_LAT}°)."
        )

    x = WGS84_A * math.radians(longitude)
    lat_rad = math.radians(latitude)
    y = WGS84_A * math.log(math.tan(math.pi / 4.0 + lat_rad / 2.0))
    return x, y


def web_mercator_to_wgs84(x: float, y: float) -> Tuple[float, float]:
    """Convert EPSG:3857 Web Mercator (meters) to WGS84 coordinates (degrees)."""
    lon_deg = math.degrees(x / WGS84_A)
    lat_deg = math.degrees(2.0 * math.atan(math.exp(y / WGS84_A)) - math.pi / 2.0)

    # Normalize longitude to [-180, 180]
    lon_deg = ((lon_deg + 180.0) % 360.0) - 180.0
    return lon_deg, lat_deg


def transform_point(point: Point, source_crs: CRS, target_crs: CRS) -> Point:
    """Transform a Point from source_crs to target_crs."""
    target_crs_str = f"EPSG:{target_crs.epsg}"

    if source_crs.epsg == target_crs.epsg:
        return Point(point.x, point.y, crs=target_crs_str)

    # Convert source -> WGS84 first if needed
    if source_crs.epsg == 4326:
        lon, lat = point.x, point.y
    elif source_crs.epsg == 3857:
        lon, lat = web_mercator_to_wgs84(point.x, point.y)
    elif source_crs.is_utm:
        lon, lat = utm_to_wgs84(point.x, point.y, zone=source_crs.zone, hemisphere=source_crs.hemisphere or "N")
    else:
        raise ProjectionError(f"Unsupported source CRS: {source_crs}")

    # Convert WGS84 -> target
    if target_crs.epsg == 4326:
        return Point(lon, lat, crs=target_crs_str)
    elif target_crs.epsg == 3857:
        tx, ty = wgs84_to_web_mercator(lon, lat)
        return Point(tx, ty, crs=target_crs_str)
    elif target_crs.is_utm:
        tx, ty = wgs84_to_utm(lon, lat, zone=target_crs.zone, hemisphere=target_crs.hemisphere or "N")
        return Point(tx, ty, crs=target_crs_str)
    else:
        raise ProjectionError(f"Unsupported target CRS: {target_crs}")


def reproject_geometry(
    geometry: Union[Point, LineString, Polygon, MultiPolygon, BoundingBox],
    source_crs: CRS,
    target_crs: CRS,
) -> Any:
    """Reproject any GIS geometry instance from source_crs to target_crs."""
    source_crs_str = f"EPSG:{source_crs.epsg}"
    target_crs_str = f"EPSG:{target_crs.epsg}"

    if source_crs.epsg == target_crs.epsg:
        return geometry

    if isinstance(geometry, Point):
        return transform_point(geometry, source_crs, target_crs)

    elif isinstance(geometry, LineString):
        new_coords = [
            transform_point(Point(pt.x, pt.y, crs=source_crs_str), source_crs, target_crs)
            for pt in geometry.coordinates
        ]
        return LineString(coordinates=new_coords, crs=target_crs_str)

    elif isinstance(geometry, Polygon):
        new_exterior = [
            transform_point(Point(pt.x, pt.y, crs=source_crs_str), source_crs, target_crs)
            for pt in geometry.exterior.coordinates
        ]
        new_interiors = [
            [
                transform_point(Point(pt.x, pt.y, crs=source_crs_str), source_crs, target_crs)
                for pt in interior.coordinates
            ]
            for interior in geometry.interiors
        ]
        return Polygon(exterior=new_exterior, interiors=new_interiors, crs=target_crs_str)

    elif isinstance(geometry, MultiPolygon):
        new_polygons = [
            reproject_geometry(poly, source_crs, target_crs)
            for poly in geometry.polygons
        ]
        return MultiPolygon(polygons=new_polygons, crs=target_crs_str)

    elif isinstance(geometry, BoundingBox):
        corners = [
            Point(geometry.min_x, geometry.min_y, crs=source_crs_str),
            Point(geometry.max_x, geometry.min_y, crs=source_crs_str),
            Point(geometry.max_x, geometry.max_y, crs=source_crs_str),
            Point(geometry.min_x, geometry.max_y, crs=source_crs_str),
        ]
        transformed_corners = [
            transform_point(c, source_crs, target_crs) for c in corners
        ]
        xs = [c.x for c in transformed_corners]
        ys = [c.y for c in transformed_corners]
        return BoundingBox(
            min_x=min(xs),
            min_y=min(ys),
            max_x=max(xs),
            max_y=max(ys),
        )

    else:
        raise ProjectionError(f"Unsupported geometry type for reprojection: {type(geometry)}")
