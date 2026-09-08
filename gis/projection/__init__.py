"""GIS Projection module for Coordinate Reference Systems and reprojection."""

from gis.projection.crs import (
    CRS,
    get_utm_crs_for_geometry,
    get_utm_epsg,
    get_utm_zone,
)
from gis.projection.exceptions import (
    CRSError,
    OutOfRangeError,
    ProjectionError,
)
from gis.projection.transformer import (
    reproject_geometry,
    transform_point,
    utm_to_wgs84,
    web_mercator_to_wgs84,
    wgs84_to_utm,
    wgs84_to_web_mercator,
)

__all__ = [
    # CRS and helpers
    "CRS",
    "get_utm_zone",
    "get_utm_epsg",
    "get_utm_crs_for_geometry",
    # Transformers
    "wgs84_to_utm",
    "utm_to_wgs84",
    "wgs84_to_web_mercator",
    "web_mercator_to_wgs84",
    "transform_point",
    "reproject_geometry",
    # Exceptions
    "ProjectionError",
    "CRSError",
    "OutOfRangeError",
]
