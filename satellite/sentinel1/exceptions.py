"""Custom exception classes for Sentinel-1 satellite processing."""


class Sentinel1Error(Exception):
    """Base exception for all Sentinel-1 processing errors."""
    pass


class Sentinel1DataError(Sentinel1Error, ValueError):
    """Raised when a Sentinel-1 file cannot be loaded, is corrupt, or has invalid data format."""
    pass


class Sentinel1MetadataError(Sentinel1DataError):
    """Raised when required Sentinel-1 metadata is missing or invalid."""
    pass
