"""Copernicus Marine Data Subsystem.

Provides automated dataset selection based on spatial and temporal coverage,
caching, downloading, and validation for ocean hydrodynamic forcing.
"""

from ocean.copernicus.catalog import (
    CopernicusDatasetDescriptor,
    COPERNICUS_MULTIYEAR_DAILY,
    COPERNICUS_ANALYSISFORECAST_DAILY,
    COPERNICUS_ANALYSISFORECAST_HOURLY,
    SUPPORTED_COPERNICUS_DATASETS,
)
from ocean.copernicus.cache import OceanDataCache, CachedDatasetMetadata
from ocean.copernicus.client import CopernicusClient, CopernicusAcquisitionResult
from ocean.copernicus.exceptions import (
    CopernicusError,
    SpatialUnavailableError,
    TemporalUnavailableError,
    InsufficientTimeWindowError,
    DatasetNotFoundError,
    DownloadFailedError,
    AuthenticationFailedError,
    NetworkError,
    InvalidNetCDFError,
    SarAcquisitionTimeUnavailableError,
)

__all__ = [
    "CopernicusDatasetDescriptor",
    "COPERNICUS_MULTIYEAR_DAILY",
    "COPERNICUS_ANALYSISFORECAST_DAILY",
    "COPERNICUS_ANALYSISFORECAST_HOURLY",
    "SUPPORTED_COPERNICUS_DATASETS",
    "OceanDataCache",
    "CachedDatasetMetadata",
    "CopernicusClient",
    "CopernicusAcquisitionResult",
    "CopernicusError",
    "SpatialUnavailableError",
    "TemporalUnavailableError",
    "InsufficientTimeWindowError",
    "DatasetNotFoundError",
    "DownloadFailedError",
    "AuthenticationFailedError",
    "NetworkError",
    "InvalidNetCDFError",
    "SarAcquisitionTimeUnavailableError",
]
