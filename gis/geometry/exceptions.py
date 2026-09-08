"""Domain-specific exceptions for the GIS Geometry module.

Provides clear, structured error reporting for coordinate and geometry validation
failures as required by the system architecture.
"""


class GeometryError(Exception):
    """Base exception for all geometry-related errors in the GIS module."""


class InvalidCoordinateError(GeometryError):
    """Raised when coordinate values are invalid, out of geographic bounds, or non-finite."""


class InvalidGeometryError(GeometryError):
    """Raised when a geometric object violates topological or structural rules."""


class EmptyGeometryError(InvalidGeometryError):
    """Raised when an operation is attempted on an empty geometry or coordinate sequence."""


class SelfIntersectionError(InvalidGeometryError):
    """Raised when a polygon boundary ring intersects itself."""


class CRSValidationError(GeometryError):
    """Raised when a Coordinate Reference System (CRS) is invalid or malformed."""
