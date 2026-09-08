"""Domain-specific exceptions for the GIS Measurement module.

Provides structured error handling for geodetic distance, area, perimeter,
and centroid calculation failures.
"""

from gis.geometry.exceptions import GeometryError


class MeasurementError(GeometryError):
    """Base exception for all measurement-related errors."""


class CalculationError(MeasurementError):
    """Raised when numerical or geometric issues prevent valid measurement computation."""
