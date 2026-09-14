"""Copernicus Marine Data Access Client.

Provides intelligent spatial/temporal dataset routing, automated subsetting via
copernicusmarine, granular error classification, and cache reuse.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple
import pandas as pd

from backend.core.config import settings
from backend.core.logging import logger
from ocean.copernicus.catalog import (
    CopernicusDatasetDescriptor,
    COPERNICUS_MULTIYEAR_DAILY,
    COPERNICUS_ANALYSISFORECAST_DAILY,
    SUPPORTED_COPERNICUS_DATASETS,
)
from ocean.copernicus.cache import OceanDataCache
from ocean.copernicus.exceptions import (
    AuthenticationFailedError,
    CopernicusError,
    DownloadFailedError,
    InsufficientTimeWindowError,
    InvalidNetCDFError,
    NetworkError,
    SpatialUnavailableError,
    TemporalUnavailableError,
)
from ocean.currents.loader import load_currents, CurrentDataError


@dataclass
class CopernicusAcquisitionResult:
    """Result container for Copernicus currents dataset acquisition."""

    file_path: Optional[Path]
    dataset: Optional[CopernicusDatasetDescriptor]
    status: str  # "COMPLETED" or error code (e.g. "TEMPORAL_UNAVAILABLE", "SPATIAL_UNAVAILABLE")
    message: str
    is_cached: bool = False
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class CopernicusClient:
    """Intelligent client for querying, selecting, and downloading Copernicus Marine datasets."""

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        sample_dir: Optional[Path] = None,
    ):
        self.cache_dir = cache_dir or (settings.DATA_DIR / "cache" / "ocean")
        self.sample_dir = sample_dir or (settings.REPO_ROOT / "data" / "sample" / "copernicus")
        self.cache = OceanDataCache(self.cache_dir, self.sample_dir)

    def select_dataset(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        end_time: datetime,
    ) -> CopernicusDatasetDescriptor:
        """Select the optimal Copernicus dataset based on spatial and temporal coverage.

        Historical observations covered by the multi-year reanalysis are routed to
        GLOBAL_MULTIYEAR_PHY_001_030 (cmems_mod_glo_phy_my_0.083deg_P1D-m).
        Recent observations beyond reanalysis coverage are routed to
        GLOBAL_ANALYSISFORECAST_PHY_001_024 (cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m).

        Raises:
            SpatialUnavailableError: If coordinates fall outside the global grid.
            TemporalUnavailableError: If the window is before 1993 or beyond forecast range.
            InsufficientTimeWindowError: If window cannot be fulfilled.
        """
        # 1. Spatial validation
        spatial_match = any(ds.contains_point(lat, lon) for ds in SUPPORTED_COPERNICUS_DATASETS)
        if not spatial_match or not (-80.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            logger.warning(f"[OCEAN] Spatial compatibility: FAIL for coordinates ({lat:.4f}°N, {lon:.4f}°E)")
            raise SpatialUnavailableError(
                f"Coordinates ({lat:.4f}°N, {lon:.4f}°E) fall outside Copernicus oceanic spatial extent [-80°S to 90°N].",
                details={
                    "lat": lat,
                    "lon": lon,
                    "required_start": start_time.isoformat() if hasattr(start_time, "isoformat") else str(start_time),
                    "required_end": end_time.isoformat() if hasattr(end_time, "isoformat") else str(end_time),
                    "reason": f"Coordinates ({lat:.4f}°N, {lon:.4f}°E) fall outside Copernicus oceanic spatial extent [-80°S to 90°N].",
                },
            )

        # Ensure UTC timezone
        t_start = start_time.astimezone(timezone.utc) if start_time.tzinfo else start_time.replace(tzinfo=timezone.utc)
        t_end = end_time.astimezone(timezone.utc) if end_time.tzinfo else end_time.replace(tzinfo=timezone.utc)

        if t_end < t_start:
            raise InsufficientTimeWindowError(
                f"Requested end time ({t_end.isoformat()}) is before start time ({t_start.isoformat()})."
            )

        # Multi-year cutoff
        my_desc = COPERNICUS_MULTIYEAR_DAILY
        anfc_desc = COPERNICUS_ANALYSISFORECAST_DAILY

        # Earliest boundary (1993-01-01)
        if t_start < my_desc.time_min:
            logger.warning(
                f"[OCEAN] Temporal compatibility: FAIL ({t_start.strftime('%Y-%m-%d')} precedes archive start {my_desc.time_min.strftime('%Y-%m-%d')})"
            )
            raise TemporalUnavailableError(
                f"Observation start time ({t_start.strftime('%Y-%m-%d')}) precedes Copernicus reanalysis archive beginning ({my_desc.time_min.strftime('%Y-%m-%d')}).",
                details={
                    "required_start": t_start.isoformat(),
                    "required_end": t_end.isoformat(),
                    "dataset_start": my_desc.time_min.isoformat(),
                    "dataset_end": my_desc.time_max.isoformat() if my_desc.time_max else "N/A",
                    "reason": f"Observation start time ({t_start.strftime('%Y-%m-%d')}) precedes Copernicus reanalysis archive beginning ({my_desc.time_min.strftime('%Y-%m-%d')}).",
                },
            )

        # Check if entire window falls within Multiyear reanalysis (1993-01-01 to 2026-06-23)
        if my_desc.time_max is not None and t_end <= my_desc.time_max:
            logger.info(f"[OCEAN] Candidate dataset: {my_desc.product_id}")
            logger.info(
                f"[OCEAN] Dataset coverage: {my_desc.time_min.strftime('%Y-%m-%d')} -> "
                f"{my_desc.time_max.strftime('%Y-%m-%d')}"
            )
            logger.info("[OCEAN] Temporal compatibility: PASS")
            logger.info("[OCEAN] Spatial compatibility: PASS")
            logger.info(f"[OCEAN] Using dataset: {my_desc.dataset_id}")
            return my_desc

        # If observation extends beyond multiyear coverage, evaluate Analysis/Forecast product
        if t_start >= anfc_desc.time_min:
            now_utc = datetime.now(timezone.utc)
            max_forecast_horizon = now_utc + timedelta(days=10)

            # If the user-requested window is far in the future beyond forecast horizon
            if t_start > max_forecast_horizon:
                logger.warning(
                    f"[OCEAN] Temporal compatibility: FAIL ({t_start.strftime('%Y-%m-%d')} exceeds forecast horizon {max_forecast_horizon.strftime('%Y-%m-%d')})"
                )
                raise TemporalUnavailableError(
                    f"Observation date ({t_start.strftime('%Y-%m-%d')}) exceeds available Copernicus analysis/forecast horizon (~{max_forecast_horizon.strftime('%Y-%m-%d')}).",
                    details={
                        "required_start": t_start.isoformat(),
                        "required_end": t_end.isoformat(),
                        "dataset_start": anfc_desc.time_min.isoformat(),
                        "dataset_end": max_forecast_horizon.isoformat(),
                        "reason": f"Observation date ({t_start.strftime('%Y-%m-%d')}) exceeds available Copernicus analysis/forecast horizon (~{max_forecast_horizon.strftime('%Y-%m-%d')}).",
                    },
                )

            logger.info(f"[OCEAN] Candidate dataset: {anfc_desc.product_id}")
            logger.info(
                f"[OCEAN] Dataset coverage: {anfc_desc.time_min.strftime('%Y-%m-%d')} -> "
                f"{max_forecast_horizon.strftime('%Y-%m-%d')} (Rolling Forecast)"
            )
            logger.info("[OCEAN] Temporal compatibility: PASS")
            logger.info("[OCEAN] Spatial compatibility: PASS")
            logger.info(f"[OCEAN] Using dataset: {anfc_desc.dataset_id}")
            return anfc_desc

        raise InsufficientTimeWindowError(
            f"Required ocean drift window ({t_start.strftime('%Y-%m-%d')} to {t_end.strftime('%Y-%m-%d')}) "
            f"cannot be satisfied by a single Copernicus product.",
            details={
                "required_start": t_start.isoformat(),
                "required_end": t_end.isoformat(),
                "reason": "Requested window spans disjoint product coverage horizons.",
            },
        )

    def acquire_currents(
        self,
        lat: float,
        lon: float,
        obs_time: datetime,
        hindcast_hours: int = 72,
        forecast_hours: int = 24,
        buffer_deg: float = 0.75,
    ) -> CopernicusAcquisitionResult:
        """Acquire surface ocean currents covering the spatial AOI and simulation window."""
        t_obs = obs_time.astimezone(timezone.utc) if obs_time.tzinfo else obs_time.replace(tzinfo=timezone.utc)
        start_time = t_obs - timedelta(hours=hindcast_hours)
        end_time = t_obs + timedelta(hours=forecast_hours)

        logger.info(f"[OCEAN] SAR reference time: {t_obs.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        logger.info(
            f"[OCEAN] Required window: {start_time.strftime('%Y-%m-%dT%H:%M:%SZ')} -> "
            f"{end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )

        lat_min = round(max(-80.0, lat - buffer_deg), 3)
        lat_max = round(min(90.0, lat + buffer_deg), 3)
        lon_min = round(max(-180.0, lon - buffer_deg), 3)
        lon_max = round(min(180.0, lon + buffer_deg), 3)

        # 1. Check local cache / sample datasets first
        cached_file = self.cache.find_cached_dataset(
            lat_min=lat_min,
            lat_max=lat_max,
            lon_min=lon_min,
            lon_max=lon_max,
            time_min=start_time,
            time_max=end_time,
        )

        if cached_file is not None and cached_file.exists():
            try:
                # Validate with load_currents
                load_currents(cached_file, select_surface=True)
                dataset_desc = None
                try:
                    dataset_desc = self.select_dataset(lat, lon, start_time, end_time)
                except Exception:
                    pass

                logger.info(f"[OCEAN] Using dataset: {cached_file.name} (Verified Cached Subset)")
                logger.info("[OCEAN] Temporal compatibility: PASS")
                logger.info("[OCEAN] Spatial compatibility: PASS")

                return CopernicusAcquisitionResult(
                    file_path=cached_file,
                    dataset=dataset_desc,
                    status="COMPLETED",
                    message=f"Reusing cached Copernicus currents ({cached_file.name})",
                    is_cached=True,
                    start_time=start_time,
                    end_time=end_time,
                )
            except Exception as e:
                logger.warning(f"Cached file {cached_file.name} failed validation: {e}")

        # 2. Select appropriate dataset based on space & time
        try:
            dataset_desc = self.select_dataset(lat, lon, start_time, end_time)
        except CopernicusError as err:
            logger.warning(f"Copernicus dataset selection blocked: {err}")
            return CopernicusAcquisitionResult(
                file_path=None,
                dataset=None,
                status=err.code,
                message=err.message,
                start_time=start_time,
                end_time=end_time,
            )
        except Exception as e:
            logger.error(f"Unexpected error during dataset selection: {e}")
            return CopernicusAcquisitionResult(
                file_path=None,
                dataset=None,
                status="DATASET_SELECTION_FAILED",
                message=str(e),
                start_time=start_time,
                end_time=end_time,
            )

        # 3. Download subset via copernicusmarine
        out_filename = self.cache.generate_cache_filename(
            dataset_id=dataset_desc.dataset_id,
            lat_min=lat_min,
            lat_max=lat_max,
            lon_min=lon_min,
            lon_max=lon_max,
            time_min=start_time,
            time_max=end_time,
        )
        dest_path = self.cache_dir / out_filename

        try:
            import copernicusmarine
        except ImportError:
            return CopernicusAcquisitionResult(
                file_path=None,
                dataset=dataset_desc,
                status="CLIENT_NOT_INSTALLED",
                message="copernicusmarine Python SDK is not installed in runtime environment.",
                start_time=start_time,
                end_time=end_time,
            )

        CoordinatesOutOfDatasetBounds = getattr(copernicusmarine, "CoordinatesOutOfDatasetBounds", Exception)
        CouldNotConnectToAuthenticationSystem = getattr(copernicusmarine, "CouldNotConnectToAuthenticationSystem", Exception)
        CredentialsCannotBeNone = getattr(copernicusmarine, "CredentialsCannotBeNone", Exception)
        DatasetNotFound = getattr(copernicusmarine, "DatasetNotFound", Exception)
        InvalidUsernameOrPassword = getattr(copernicusmarine, "InvalidUsernameOrPassword", Exception)

        logger.info(
            f"Downloading Copernicus currents subset: {dataset_desc.dataset_id} "
            f"[lat: {lat_min}..{lat_max}, lon: {lon_min}..{lon_max}, "
            f"time: {start_time.isoformat()}..{end_time.isoformat()}] -> {out_filename}"
        )

        try:
            copernicusmarine.subset(
                dataset_id=dataset_desc.dataset_id,
                variables=list(dataset_desc.variables),
                minimum_longitude=lon_min,
                maximum_longitude=lon_max,
                minimum_latitude=lat_min,
                maximum_latitude=lat_max,
                start_datetime=start_time.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%dT00:00:00"),
                end_datetime=(end_time + timedelta(days=1)).replace(hour=23, minute=59, second=59).strftime("%Y-%m-%dT23:59:59"),
                minimum_depth=dataset_desc.default_depth,
                maximum_depth=dataset_desc.default_depth,
                output_directory=str(self.cache_dir),
                output_filename=out_filename,
                overwrite=True,
            )
        except (CouldNotConnectToAuthenticationSystem, InvalidUsernameOrPassword, CredentialsCannotBeNone) as auth_err:
            logger.error(f"Copernicus Marine authentication failure: {auth_err}")
            return CopernicusAcquisitionResult(
                file_path=None,
                dataset=dataset_desc,
                status="AUTHENTICATION_FAILED",
                message=f"Copernicus Marine authentication failed: {auth_err}",
                start_time=start_time,
                end_time=end_time,
            )
        except CoordinatesOutOfDatasetBounds as bounds_err:
            logger.error(f"Coordinates out of bounds for {dataset_desc.dataset_id}: {bounds_err}")
            return CopernicusAcquisitionResult(
                file_path=None,
                dataset=dataset_desc,
                status="COORDINATES_OUT_OF_BOUNDS",
                message=f"Copernicus Marine coordinate bounds error: {bounds_err}",
                start_time=start_time,
                end_time=end_time,
            )
        except DatasetNotFound as ds_err:
            logger.error(f"Dataset not found: {ds_err}")
            return CopernicusAcquisitionResult(
                file_path=None,
                dataset=dataset_desc,
                status="DATASET_NOT_FOUND",
                message=f"Copernicus dataset '{dataset_desc.dataset_id}' not found in catalogue.",
                start_time=start_time,
                end_time=end_time,
            )
        except Exception as dl_err:
            err_str = str(dl_err).lower()
            if "connection" in err_str or "timeout" in err_str or "network" in err_str:
                status = "NETWORK_ERROR"
            else:
                status = "DOWNLOAD_FAILED"
            logger.error(f"Copernicus Marine download failed [{status}]: {dl_err}")
            return CopernicusAcquisitionResult(
                file_path=None,
                dataset=dataset_desc,
                status=status,
                message=f"Copernicus subset download failed: {dl_err}",
                start_time=start_time,
                end_time=end_time,
            )

        if not dest_path.exists():
            return CopernicusAcquisitionResult(
                file_path=None,
                dataset=dataset_desc,
                status="DOWNLOAD_FAILED",
                message=f"Downloaded file {out_filename} was not found on disk after download.",
                start_time=start_time,
                end_time=end_time,
            )

        # 4. Validate downloaded NetCDF
        try:
            load_currents(dest_path, select_surface=True)
            self.cache.reindex()
            return CopernicusAcquisitionResult(
                file_path=dest_path,
                dataset=dataset_desc,
                status="COMPLETED",
                message=f"Acquired and validated Copernicus currents ({dataset_desc.dataset_id})",
                is_cached=False,
                start_time=start_time,
                end_time=end_time,
            )
        except Exception as val_err:
            logger.error(f"Downloaded NetCDF failed validation: {val_err}")
            try:
                dest_path.unlink(missing_ok=True)
            except Exception:
                pass
            return CopernicusAcquisitionResult(
                file_path=None,
                dataset=dataset_desc,
                status="INVALID_NETCDF",
                message=f"Downloaded Copernicus NetCDF failed validation: {val_err}",
                start_time=start_time,
                end_time=end_time,
            )
