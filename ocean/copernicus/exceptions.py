"""Copernicus Marine Data Subsystem Exceptions.

Defines granular exception classes and error codes for spatial, temporal,
authentication, network, and dataset validation errors.
"""

from __future__ import annotations
from typing import Optional


class CopernicusError(Exception):
    """Base exception for all Copernicus ocean data operations."""

    def __init__(self, message: str, code: str = "COPERNICUS_ERROR", details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class SpatialUnavailableError(CopernicusError):
    """Raised when coordinates fall outside supported global ocean spatial extent."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="SPATIAL_UNAVAILABLE", details=details)

    @property
    def latitude(self) -> Optional[float]:
        return self.details.get("latitude") if self.details.get("latitude") is not None else self.details.get("lat")

    @property
    def longitude(self) -> Optional[float]:
        return self.details.get("longitude") if self.details.get("longitude") is not None else self.details.get("lon")


class TemporalUnavailableError(CopernicusError):
    """Raised when observation date falls outside available product timelines."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="TEMPORAL_UNAVAILABLE", details=details)

    @property
    def required_start(self) -> Optional[str]:
        return self.details.get("required_start")

    @property
    def required_end(self) -> Optional[str]:
        return self.details.get("required_end")

    @property
    def dataset_start(self) -> Optional[str]:
        return self.details.get("dataset_start")

    @property
    def dataset_end(self) -> Optional[str]:
        return self.details.get("dataset_end")


class InsufficientTimeWindowError(CopernicusError):
    """Raised when partial temporal coverage exists but does not span the full drift simulation window."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="INSUFFICIENT_TIME_WINDOW", details=details)


class DatasetNotFoundError(CopernicusError):
    """Raised when requested Copernicus product or dataset identifier is not found in catalogue."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="DATASET_NOT_FOUND", details=details)


class DownloadFailedError(CopernicusError):
    """Raised when subset download from Copernicus Marine service fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="DOWNLOAD_FAILED", details=details)


class AuthenticationFailedError(CopernicusError):
    """Raised when Copernicus Marine authentication or credentials fail."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="AUTHENTICATION_FAILED", details=details)


class NetworkError(CopernicusError):
    """Raised on connection timeout, DNS failure, or remote service unavailability."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="NETWORK_ERROR", details=details)


class InvalidNetCDFError(CopernicusError):
    """Raised when downloaded NetCDF fails CF conventions, dimension, or velocity checks."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="INVALID_NETCDF", details=details)


class SarAcquisitionTimeUnavailableError(CopernicusError):
    """Raised when Sentinel-1 SAR acquisition timestamp could not be resolved."""

    def __init__(
        self,
        message: str = "Cannot run ocean drift reconstruction because the Sentinel-1 acquisition timestamp could not be resolved.",
        details: Optional[dict] = None,
    ):
        super().__init__(message, code="SAR_ACQUISITION_TIME_UNAVAILABLE", details=details)
