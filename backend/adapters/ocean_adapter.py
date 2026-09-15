"""Ocean & Meteorological Data Ingestion Adapter (Member 4 Integration).

Bridges the backend to Copernicus Marine ocean current and wind dataset loaders.
Dynamically searches local NetCDF datasets to match geographic bounds and dates.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import pandas as pd
import xarray as xr

from backend.core.config import settings
from backend.core.logging import logger
from ocean.copernicus import CopernicusClient, CopernicusAcquisitionResult
from ocean.currents import load_currents
from ocean.wind import load_wind


class OceanAdapter:
    """Service adapter interfacing with Copernicus Marine and ERA5 data loaders."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or settings.OCEAN_DATA_DIR
        self.copernicus_dir = settings.REPO_ROOT / "data" / "sample" / "copernicus"
        self.era5_dir = settings.REPO_ROOT / "data" / "sample" / "era5"
        self.cache_dir = settings.DATA_DIR / "cache" / "ocean"
        self.client = CopernicusClient(cache_dir=self.cache_dir, sample_dir=self.copernicus_dir)

    def acquire_ocean_currents(
        self,
        lat: float,
        lon: float,
        obs_time: datetime,
        hindcast_hours: int = 72,
        forecast_hours: int = 24,
        buffer_deg: float = 0.75,
    ) -> CopernicusAcquisitionResult:
        """Acquire verified ocean currents NetCDF for the requested coordinates and temporal window."""
        return self.client.acquire_currents(
            lat=lat,
            lon=lon,
            obs_time=obs_time,
            hindcast_hours=hindcast_hours,
            forecast_hours=forecast_hours,
            buffer_deg=buffer_deg,
        )

    def find_matching_currents(
        self, lat: float, lon: float, obs_time: Optional[datetime] = None
    ) -> Optional[Path]:
        """Dynamically search available NetCDF files to find one covering the target coordinates and time."""
        if obs_time is not None:
            res = self.acquire_ocean_currents(lat, lon, obs_time)
            if res.status == "COMPLETED" and res.file_path:
                return res.file_path

        # Fallback local search in sample directory with space and time checks
        if not self.copernicus_dir.exists():
            return None

        candidates = list(self.copernicus_dir.glob("*.nc"))
        candidates.sort(key=lambda p: 0 if "current_test" not in p.name else 1)

        for nc_path in candidates:
            try:
                with xr.open_dataset(nc_path) as ds:
                    lat_var = "latitude" if "latitude" in ds else "lat"
                    lon_var = "longitude" if "longitude" in ds else "lon"

                    if lat_var in ds and lon_var in ds:
                        min_lat = float(ds[lat_var].min())
                        max_lat = float(ds[lat_var].max())
                        min_lon = float(ds[lon_var].min())
                        max_lon = float(ds[lon_var].max())

                        if (min_lat - 0.1 <= lat <= max_lat + 0.1) and (min_lon - 0.1 <= lon <= max_lon + 0.1):
                            if obs_time is not None and "time" in ds:
                                t_min = pd.Timestamp(ds["time"].min().values)
                                t_max = pd.Timestamp(ds["time"].max().values)
                                obs_ts = pd.Timestamp(obs_time)
                                if obs_ts.tzinfo:
                                    obs_ts = obs_ts.tz_convert(None)
                                if obs_ts < t_min - pd.Timedelta(days=1) or obs_ts > t_max + pd.Timedelta(days=1):
                                    continue
                            logger.info(
                                f"Matched Copernicus dataset {nc_path.name} for ({lat:.4f}, {lon:.4f}) "
                                f"[Bounds: lat ({min_lat:.2f}, {max_lat:.2f}), lon ({min_lon:.2f}, {max_lon:.2f})]"
                            )
                            return nc_path
            except Exception as e:
                logger.debug(f"Could not inspect NetCDF {nc_path}: {e}")
                continue

        return None

    def get_currents_path(self, obs_time: Optional[datetime] = None) -> Path:
        """Resolve currents NetCDF file path with temporal matching."""
        if obs_time is not None:
            # Check which sample file matches the observation time
            for candidate in [
                self.copernicus_dir / "persian_gulf_current_2017.nc",
                self.copernicus_dir / "red_sea_current_2019.nc",
                self.copernicus_dir / "current_test.nc",
            ]:
                if candidate.exists():
                    try:
                        with xr.open_dataset(candidate) as ds:
                            if "time" in ds:
                                t_min = pd.Timestamp(ds["time"].min().values)
                                t_max = pd.Timestamp(ds["time"].max().values)
                                obs_ts = pd.Timestamp(obs_time)
                                if obs_ts.tzinfo:
                                    obs_ts = obs_ts.tz_convert(None)
                                if t_min <= obs_ts <= t_max:
                                    return candidate
                    except Exception:
                        pass

        for candidate in [
            self.copernicus_dir / "persian_gulf_current_2017.nc",
            self.copernicus_dir / "red_sea_current_2019.nc",
            self.copernicus_dir / "current_test.nc",
        ]:
            if candidate.exists():
                return candidate

        raise FileNotFoundError(f"No Copernicus currents NetCDF file found in {self.copernicus_dir}")

    def get_wind_path(self) -> Optional[Path]:
        """Resolve wind NetCDF file path if available."""
        for candidate in [
            self.era5_dir / "wind_test.nc",
            self.data_dir / "era5" / "wind_test.nc",
        ]:
            if candidate.exists():
                return candidate
        return None

    def load_environmental_datasets(
        self, nc_path: Optional[Path] = None, obs_time: Optional[datetime] = None
    ) -> Tuple[xr.Dataset, Optional[xr.Dataset]]:
        """Load Copernicus currents and optional ERA5 wind xarray Datasets."""
        curr_path = nc_path or self.get_currents_path(obs_time=obs_time)
        logger.info(f"Loading ocean currents from {curr_path}")
        curr_ds = load_currents(curr_path, select_surface=True)

        wind_path = self.get_wind_path()
        wind_ds = None
        if wind_path and wind_path.exists():
            try:
                wind_ds = load_wind(wind_path)
            except Exception as e:
                logger.warning(f"Could not load wind dataset from {wind_path}: {e}")

        if wind_ds is None:
            # Construct neutral atmospheric forcing dataset matching currents grid
            u_dim = curr_ds["uo"].dims if "uo" in curr_ds else list(curr_ds.dims.keys())
            wind_ds = xr.Dataset(
                {
                    "u10": (u_dim, np.zeros_like(curr_ds["uo"].values if "uo" in curr_ds else 0.0), {"units": "m/s"}),
                    "v10": (u_dim, np.zeros_like(curr_ds["vo"].values if "vo" in curr_ds else 0.0), {"units": "m/s"}),
                },
                coords=curr_ds.coords,
            )

        return curr_ds, wind_ds
