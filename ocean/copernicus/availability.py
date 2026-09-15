"""Copernicus Marine Availability Service.

Provides a unified availability evaluation for Copernicus CMEMS hydrodynamic datasets,
bridging M4 ocean drift simulation, System Status diagnostic endpoints, and Datasets inventory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.core.config import settings
from backend.core.logging import logger
from ocean.copernicus.cache import OceanDataCache, CachedDatasetMetadata
from ocean.copernicus.client import SUPPORTED_COPERNICUS_DATASETS


class CopernicusStatus(str, Enum):
    """Standardized Copernicus CMEMS availability statuses."""
    READY = "READY"
    CACHE_AVAILABLE = "CACHE_AVAILABLE"
    REMOTE_CONFIGURED = "REMOTE_CONFIGURED"
    REMOTE_REACHABLE = "REMOTE_REACHABLE"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NO_COMPATIBLE_DATA = "NO_COMPATIBLE_DATA"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    NETWORK_ERROR = "NETWORK_ERROR"


@dataclass
class CopernicusAvailabilityResult:
    """Diagnostic and operational status of Copernicus Marine data."""
    status: CopernicusStatus
    message: str
    is_cached: bool = False
    matched_file: Optional[str] = None
    dataset_name: Optional[str] = None
    temporal_range: Optional[Tuple[datetime, datetime]] = None
    spatial_bounds: Optional[Dict[str, float]] = None
    total_indexed_files: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


class CopernicusAvailabilityService:
    """Unified service to evaluate CMEMS cache and remote availability."""

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        sample_dir: Optional[Path] = None,
    ):
        self.cache_dir = cache_dir or (settings.DATA_DIR / "cache" / "ocean")
        self.sample_dir = sample_dir or (settings.REPO_ROOT / "data" / "sample" / "copernicus")
        self.cache = OceanDataCache(self.cache_dir, self.sample_dir)

    def get_dataset_inventory(self) -> List[Dict[str, Any]]:
        """Return full diagnostic inventory of all indexed NetCDF files."""
        inventory: List[Dict[str, Any]] = []
        for meta in self.cache._index:
            try:
                size_mb = round(meta.path.stat().st_size / (1024 * 1024), 2)
            except Exception:
                size_mb = 0.0

            # Determine product family from metadata / path
            fname = meta.path.name.lower()
            if "my" in fname or (meta.time_max and meta.time_max.year < 2024):
                product = "GLOBAL_MULTIYEAR_PHY_001_030 (Reanalysis)"
            else:
                product = "GLOBAL_ANALYSISFORECAST_PHY_001_024 (Analysis/Forecast)"

            inventory.append({
                "filename": meta.path.name,
                "path": str(meta.path),
                "size_mb": size_mb,
                "lat_min": meta.lat_min,
                "lat_max": meta.lat_max,
                "lon_min": meta.lon_min,
                "lon_max": meta.lon_max,
                "time_min": meta.time_min.isoformat() if meta.time_min else None,
                "time_max": meta.time_max.isoformat() if meta.time_max else None,
                "variables": list(meta.variables),
                "product": product,
            })
        return inventory

    def check_availability(
        self,
        obs_time: Optional[datetime] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        duration_hours: float = 4.0,
        simulate_error: Optional[str] = None,
    ) -> CopernicusAvailabilityResult:
        """Evaluate availability either globally or for a specific observation context.

        Args:
            obs_time: SAR observation timestamp (UTC). Never defaults to now() for historical runs.
            lat: Centroid latitude.
            lon: Centroid longitude.
            duration_hours: Drift duration.
            simulate_error: Test-hook for verifying specific failure states.
        """
        # Test hook for error simulation
        if simulate_error:
            err_upper = simulate_error.upper()
            if err_upper in CopernicusStatus.__members__:
                status = CopernicusStatus(err_upper)
                return CopernicusAvailabilityResult(
                    status=status,
                    message=f"Simulated state: {err_upper}",
                    is_cached=False,
                    total_indexed_files=len(self.cache._index),
                )

        # 1. Global (unscoped) check for System Status
        if lat is None or lon is None or obs_time is None:
            indexed_count = len(self.cache._index)
            username = getattr(settings, "COPERNICUS_USERNAME", "")
            password = getattr(settings, "COPERNICUS_PASSWORD", "")
            has_credentials = bool(username and password and len(username) > 2)

            if indexed_count > 0:
                sample_names = [m.path.name for m in self.cache._index[:3]]
                return CopernicusAvailabilityResult(
                    status=CopernicusStatus.CACHE_AVAILABLE,
                    message=f"Local cache operational with {indexed_count} NetCDF grid files ({', '.join(sample_names)}).",
                    is_cached=True,
                    total_indexed_files=indexed_count,
                    details={
                        "credentials_configured": has_credentials,
                        "indexed_count": indexed_count,
                    },
                )
            elif has_credentials:
                return CopernicusAvailabilityResult(
                    status=CopernicusStatus.REMOTE_CONFIGURED,
                    message="Copernicus CMEMS credentials configured; live download service active.",
                    is_cached=False,
                    total_indexed_files=0,
                    details={"credentials_configured": True},
                )
            else:
                return CopernicusAvailabilityResult(
                    status=CopernicusStatus.NOT_CONFIGURED,
                    message="No local NetCDF grids and Copernicus credentials not configured.",
                    is_cached=False,
                    total_indexed_files=0,
                )

        # 2. Contextual check for a specific investigation / coordinates / observation time
        # Physical coordinate bounds
        if not (-80.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return CopernicusAvailabilityResult(
                status=CopernicusStatus.NO_COMPATIBLE_DATA,
                message=f"Coordinates ({lat:.4f}N, {lon:.4f}E) fall outside Copernicus global marine domain [-80, 90].",
                is_cached=False,
                total_indexed_files=len(self.cache._index),
            )

        # Ensure UTC timezone
        if obs_time.tzinfo is None:
            obs_time = obs_time.replace(tzinfo=timezone.utc)
        else:
            obs_time = obs_time.astimezone(timezone.utc)

        start_time = obs_time - timedelta(hours=duration_hours)
        end_time = obs_time + timedelta(hours=2.0)

        # Reanalysis temporal coverage lower bound
        reanalysis_min = datetime(1993, 1, 1, tzinfo=timezone.utc)
        if start_time < reanalysis_min:
            return CopernicusAvailabilityResult(
                status=CopernicusStatus.NO_COMPATIBLE_DATA,
                message=f"Observation time {obs_time.isoformat()} precedes Copernicus CMEMS reanalysis baseline (1993-01-01).",
                is_cached=False,
                total_indexed_files=len(self.cache._index),
            )

        # Check local cache index first
        matched_meta: Optional[CachedDatasetMetadata] = None
        for meta in self.cache._index:
            if meta.contains(
                lat - 0.2, lat + 0.2,
                lon - 0.2, lon + 0.2,
                start_time, end_time
            ):
                matched_meta = meta
                break

        if matched_meta:
            return CopernicusAvailabilityResult(
                status=CopernicusStatus.READY,
                message=f"Hydrodynamic current grid ready in local cache: {matched_meta.path.name}",
                is_cached=True,
                matched_file=matched_meta.path.name,
                temporal_range=(matched_meta.time_min, matched_meta.time_max),
                spatial_bounds={
                    "lat_min": matched_meta.lat_min,
                    "lat_max": matched_meta.lat_max,
                    "lon_min": matched_meta.lon_min,
                    "lon_max": matched_meta.lon_max,
                },
                total_indexed_files=len(self.cache._index),
                details={
                    "file_path": str(matched_meta.path),
                    "variables": list(matched_meta.variables),
                },
            )

        # If not cached, check remote credentials
        username = getattr(settings, "COPERNICUS_USERNAME", "")
        password = getattr(settings, "COPERNICUS_PASSWORD", "")
        if username and password and len(username) > 2:
            return CopernicusAvailabilityResult(
                status=CopernicusStatus.REMOTE_CONFIGURED,
                message=f"Dataset not in local cache; CMEMS remote fetch configured for ({lat:.2f}N, {lon:.2f}E).",
                is_cached=False,
                total_indexed_files=len(self.cache._index),
                details={"target_window": f"{start_time.isoformat()} to {end_time.isoformat()}"},
            )

        return CopernicusAvailabilityResult(
            status=CopernicusStatus.NOT_CONFIGURED,
            message=f"No local cache for ({lat:.2f}N, {lon:.2f}E) at {obs_time.date()} and CMEMS credentials not configured.",
            is_cached=False,
            total_indexed_files=len(self.cache._index),
        )


# Global singleton instance
_availability_service: Optional[CopernicusAvailabilityService] = None


def get_copernicus_availability_service() -> CopernicusAvailabilityService:
    """Return the global CopernicusAvailabilityService singleton."""
    global _availability_service
    if _availability_service is None:
        _availability_service = CopernicusAvailabilityService()
    return _availability_service
