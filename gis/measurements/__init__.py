"""GIS Measurement module for the Oil Spill Attribution System.

Provides geodesic area, perimeter, distance, centroid, and shape metrics
for oil spills, vessel trajectories, and spatial features.
"""

from gis.measurements.area import (
    calculate_multipolygon_area,
    calculate_polygon_area,
    calculate_ring_geodesic_area,
    calculate_spill_area,
)
from gis.measurements.centroid import (
    calculate_linestring_centroid,
    calculate_multipolygon_centroid,
    calculate_polygon_centroid,
    calculate_ring_centroid,
    calculate_spill_centroid,
)
from gis.measurements.distance import (
    EARTH_RADIUS_METERS,
    calculate_path_length,
    calculate_perimeter,
    calculate_ring_perimeter,
    haversine_distance,
)
from gis.measurements.exceptions import CalculationError, MeasurementError
from gis.measurements.models import (
    SpillMeasurement,
    calculate_bounding_dimensions,
    calculate_compactness,
    measure_oil_spill,
)

__all__ = [
    # Distance & Perimeter
    "EARTH_RADIUS_METERS",
    "haversine_distance",
    "calculate_path_length",
    "calculate_ring_perimeter",
    "calculate_perimeter",
    # Area
    "calculate_ring_geodesic_area",
    "calculate_polygon_area",
    "calculate_multipolygon_area",
    "calculate_spill_area",
    # Centroid
    "calculate_ring_centroid",
    "calculate_polygon_centroid",
    "calculate_multipolygon_centroid",
    "calculate_linestring_centroid",
    "calculate_spill_centroid",
    # Models & Summary
    "SpillMeasurement",
    "calculate_compactness",
    "calculate_bounding_dimensions",
    "measure_oil_spill",
    # Exceptions
    "MeasurementError",
    "CalculationError",
]
