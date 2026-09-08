"""Measurement models and comprehensive oil spill characterization.

Provides the SpillMeasurement dataclass and the high-level measure_oil_spill
function incorporating physical area, perimeter, centroid, and shape indices.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple, Union

from gis.geometry.models import (
    BoundingBox,
    Coordinate,
    MultiPolygon,
    OilSpillGeometry,
    Point,
    Polygon,
)
from gis.measurements.area import calculate_spill_area
from gis.measurements.centroid import calculate_spill_centroid
from gis.measurements.distance import calculate_perimeter, haversine_distance
from gis.measurements.exceptions import CalculationError


def calculate_compactness(area_sq_m: float, perimeter_m: float) -> float:
    """Calculate the isoperimetric quotient (compactness) of a 2D shape.

    Formula: (4 * pi * Area) / (Perimeter^2)
    - Circle = 1.0
    - Elongated ship wake / narrow spill <= 0.2

    Args:
        area_sq_m: Surface area in square meters.
        perimeter_m: Perimeter in meters.

    Returns:
        Compactness ratio between 0.0 and 1.0.
    """
    if perimeter_m <= 0.0 or area_sq_m <= 0.0:
        return 0.0

    compactness = (4.0 * math.pi * area_sq_m) / (perimeter_m**2)
    # Clip to [0.0, 1.0] to handle small discrete boundary approximations
    return min(1.0, max(0.0, compactness))


def calculate_bounding_dimensions(bbox: BoundingBox) -> Tuple[float, float, float]:
    """Calculate geodesic width, height, and aspect ratio of a BoundingBox in meters.

    Args:
        bbox: BoundingBox (min_x, min_y, max_x, max_y).

    Returns:
        Tuple of (width_meters, height_meters, aspect_ratio).
    """
    mid_y = (bbox.min_y + bbox.max_y) / 2.0
    mid_x = (bbox.min_x + bbox.max_x) / 2.0

    # Width: distance from (min_x, mid_y) to (max_x, mid_y)
    width_m = haversine_distance((bbox.min_x, mid_y), (bbox.max_x, mid_y))

    # Height: distance from (mid_x, min_y) to (mid_x, max_y)
    height_m = haversine_distance((mid_x, bbox.min_y), (mid_x, bbox.max_y))

    # Aspect ratio: max(dimension) / min(dimension)
    min_dim = min(width_m, height_m)
    max_dim = max(width_m, height_m)

    aspect_ratio = (max_dim / min_dim) if min_dim > 1e-6 else 1.0
    return (width_m, height_m, aspect_ratio)


@dataclass(frozen=True)
class SpillMeasurement:
    """Comprehensive physical and geometric measurement report for an oil spill."""

    area_sq_m: float
    area_sq_km: float
    perimeter_m: float
    perimeter_km: float
    centroid: Point
    bounding_box: BoundingBox
    bbox_width_m: float
    bbox_height_m: float
    aspect_ratio: float
    compactness: float
    spill_id: Optional[str] = None
    crs: str = "EPSG:4326"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize measurement results to a JSON-compatible dictionary."""
        return {
            "spill_id": self.spill_id,
            "crs": self.crs,
            "area": {
                "sq_meters": round(self.area_sq_m, 2),
                "sq_kilometers": round(self.area_sq_km, 4),
            },
            "perimeter": {
                "meters": round(self.perimeter_m, 2),
                "kilometers": round(self.perimeter_km, 4),
            },
            "centroid": {
                "longitude": round(self.centroid.lon, 6),
                "latitude": round(self.centroid.lat, 6),
            },
            "bounding_box": {
                "min_lon": self.bounding_box.min_x,
                "min_lat": self.bounding_box.min_y,
                "max_lon": self.bounding_box.max_x,
                "max_lat": self.bounding_box.max_y,
                "width_meters": round(self.bbox_width_m, 2),
                "height_meters": round(self.bbox_height_m, 2),
            },
            "shape_characteristics": {
                "aspect_ratio": round(self.aspect_ratio, 2),
                "compactness": round(self.compactness, 4),
            },
        }


def measure_oil_spill(
    spill: OilSpillGeometry | Polygon | MultiPolygon,
) -> SpillMeasurement:
    """Perform complete physical and geometric measurements on an oil spill.

    Args:
        spill: OilSpillGeometry, Polygon, or MultiPolygon.

    Returns:
        SpillMeasurement dataclass with all computed metrics.
    """
    if isinstance(spill, OilSpillGeometry):
        spill_id = spill.spill_id
        geom = spill.geometry
        crs = spill.crs
    elif isinstance(spill, (Polygon, MultiPolygon)):
        spill_id = None
        geom = spill
        crs = spill.crs
    else:
        raise CalculationError(
            f"Cannot measure object of type {type(spill)}. Expected OilSpillGeometry, Polygon, or MultiPolygon."
        )

    # 1. Physical Area
    area_m2 = calculate_spill_area(geom, in_sq_km=False)
    area_km2 = area_m2 / 1_000_000.0

    # 2. Perimeter (exterior + holes)
    perim_m = calculate_perimeter(geom, include_holes=True, in_km=False)
    perim_km = perim_m / 1000.0

    # 3. Centroid
    centroid = calculate_spill_centroid(geom)

    # 4. Bounding Box & Aspect Ratio
    bbox = geom.bounds
    width_m, height_m, aspect_ratio = calculate_bounding_dimensions(bbox)

    # 5. Compactness
    compactness = calculate_compactness(area_m2, perim_m)

    return SpillMeasurement(
        area_sq_m=area_m2,
        area_sq_km=area_km2,
        perimeter_m=perim_m,
        perimeter_km=perim_km,
        centroid=centroid,
        bounding_box=bbox,
        bbox_width_m=width_m,
        bbox_height_m=height_m,
        aspect_ratio=aspect_ratio,
        compactness=compactness,
        spill_id=spill_id,
        crs=crs,
    )
