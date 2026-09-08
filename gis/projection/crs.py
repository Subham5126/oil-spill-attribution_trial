"""Coordinate Reference System (CRS) representations and utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional, Union

from gis.projection.exceptions import CRSError


@dataclass(frozen=True)
class CRS:
    """Represents a Coordinate Reference System."""

    epsg: int
    name: str
    proj_type: str  # 'geographic' or 'projected'
    unit: str  # 'degree' or 'metre'
    zone: Optional[int] = None
    hemisphere: Optional[str] = None  # 'N' or 'S'

    def __post_init__(self) -> None:
        if self.proj_type not in ("geographic", "projected"):
            raise CRSError(f"Invalid proj_type: {self.proj_type}. Must be 'geographic' or 'projected'.")
        if self.unit not in ("degree", "metre", "meter"):
            raise CRSError(f"Invalid unit: {self.unit}. Must be 'degree' or 'metre'.")
        if self.hemisphere is not None:
            hemi = self.hemisphere.strip().upper()
            if hemi not in ("N", "S"):
                raise CRSError(f"Invalid hemisphere: {self.hemisphere}. Must be 'N' or 'S'.")
            object.__setattr__(self, "hemisphere", hemi)

    @property
    def is_geographic(self) -> bool:
        """Return True if this CRS is geographic (angular units)."""
        return self.proj_type == "geographic"

    @property
    def is_projected(self) -> bool:
        """Return True if this CRS is projected (planar units)."""
        return self.proj_type == "projected"

    @property
    def is_utm(self) -> bool:
        """Return True if this CRS represents a UTM projection."""
        return self.zone is not None

    @property
    def epsg_str(self) -> str:
        """Return standard EPSG authority string (e.g. 'EPSG:4326')."""
        return f"EPSG:{self.epsg}"

    @classmethod
    def wgs84(cls) -> CRS:
        """Standard WGS 84 geographic coordinate system (EPSG:4326)."""
        return cls(
            epsg=4326,
            name="WGS 84",
            proj_type="geographic",
            unit="degree",
        )

    @classmethod
    def web_mercator(cls) -> CRS:
        """WGS 84 / Pseudo-Mercator / Web Mercator (EPSG:3857)."""
        return cls(
            epsg=3857,
            name="WGS 84 / Pseudo-Mercator",
            proj_type="projected",
            unit="metre",
        )

    @classmethod
    def utm(cls, zone: int, hemisphere: str = "N") -> CRS:
        """Construct a Universal Transverse Mercator (UTM) CRS."""
        if not (1 <= zone <= 60):
            raise CRSError(f"UTM zone must be between 1 and 60, got {zone}")

        hemi = str(hemisphere).strip().upper()
        if hemi not in ("N", "S"):
            raise CRSError(f"UTM hemisphere must be 'N' (North) or 'S' (South), got '{hemisphere}'")

        epsg_code = (32600 + zone) if hemi == "N" else (32700 + zone)
        name = f"WGS 84 / UTM zone {zone}{hemi}"

        return cls(
            epsg=epsg_code,
            name=name,
            proj_type="projected",
            unit="metre",
            zone=zone,
            hemisphere=hemi,
        )

    @classmethod
    def from_epsg(cls, epsg: Union[int, str, CRS]) -> CRS:
        """Create a CRS instance from an EPSG integer, string, or existing CRS object."""
        if isinstance(epsg, CRS):
            return epsg

        if isinstance(epsg, str):
            clean = epsg.strip().upper()
            if clean in ("WGS84", "WGS 84", "CRS84", "OGC:CRS84", "URN:OGC:DEF:CRS:OGC:1.3:CRS84"):
                return cls.wgs84()

            match = re.search(r"(\d+)", clean)
            if not match:
                raise CRSError(f"Cannot parse EPSG code from string: '{epsg}'")
            code = int(match.group(1))
        elif isinstance(epsg, (int, float)):
            code = int(epsg)
        else:
            raise CRSError(f"Expected int, str, or CRS instance, got {type(epsg)}")

        if code == 4326:
            return cls.wgs84()
        if code == 3857:
            return cls.web_mercator()
        if 32601 <= code <= 32660:
            zone = code - 32600
            return cls.utm(zone=zone, hemisphere="N")
        if 32701 <= code <= 32760:
            zone = code - 32700
            return cls.utm(zone=zone, hemisphere="S")

        raise CRSError(f"Unsupported EPSG code: {code}")

    @classmethod
    def from_string(cls, crs_str: str) -> CRS:
        """Alias for from_epsg to parse CRS from string identifiers."""
        return cls.from_epsg(crs_str)

    def __str__(self) -> str:
        return self.epsg_str

    def __repr__(self) -> str:
        return f"CRS(epsg={self.epsg}, name='{self.name}')"


def get_utm_zone(longitude: float, latitude: float) -> int:
    """Calculate the standard UTM zone number (1..60) for a given longitude and latitude.

    Standard UTM zones are 6 degrees wide, numbered 1 to 60 starting at 180°W.
    """
    # Normalize longitude into [-180.0, 180.0)
    lon = float(longitude)
    if lon == 180.0:
        return 60

    if not (-180.0 <= lon < 180.0):
        lon = ((lon + 180.0) % 360.0) - 180.0

    zone = int((lon + 180.0) / 6.0) + 1
    if zone > 60:
        zone = 60
    if zone < 1:
        zone = 1
    return zone


def get_utm_epsg(longitude: float, latitude: float) -> int:
    """Determine the EPSG code for the optimal UTM zone at the given coordinate."""
    zone = get_utm_zone(longitude, latitude)
    if latitude >= 0.0:
        return 32600 + zone
    return 32700 + zone


def get_utm_crs_for_geometry(geom: Any) -> CRS:
    """Auto-detect optimal UTM CRS for any GIS geometry, bounding box, or coordinate."""
    from gis.geometry.models import (
        BoundingBox,
        Coordinate,
        LinearRing,
        LineString,
        MultiPolygon,
        OilSpillGeometry,
        Point,
        Polygon,
    )

    if isinstance(geom, Point):
        lon, lat = geom.x, geom.y
    elif isinstance(geom, Coordinate):
        lon, lat = geom.x, geom.y
    elif isinstance(geom, OilSpillGeometry):
        return get_utm_crs_for_geometry(geom.geometry)
    elif isinstance(geom, (Polygon, MultiPolygon, LineString, LinearRing)):
        from gis.measurements.centroid import calculate_spill_centroid
        centroid = calculate_spill_centroid(geom)
        lon, lat = centroid.x, centroid.y
    elif isinstance(geom, BoundingBox):
        lon = (geom.min_x + geom.max_x) / 2.0
        lat = (geom.min_y + geom.max_y) / 2.0
    else:
        raise CRSError(f"Unsupported geometry type for UTM selection: {type(geom)}")

    zone = get_utm_zone(lon, lat)
    hemisphere = "N" if lat >= 0.0 else "S"
    return CRS.utm(zone=zone, hemisphere=hemisphere)
