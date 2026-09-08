"""Exceptions for GIS Projection module."""


class ProjectionError(Exception):
    """Base exception for coordinate projection and transformation errors."""


class CRSError(ProjectionError):
    """Exception raised when an invalid or unsupported CRS is encountered."""


class OutOfRangeError(ProjectionError):
    """Exception raised when coordinates fall outside the valid domain of a projection."""
