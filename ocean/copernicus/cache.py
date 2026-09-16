"""Copernicus NetCDF Cache Management & Containment Engine.

Indexes local and sample NetCDF datasets, validates spatial and temporal
containment, and reuses compatible local subsets before issuing network requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import List, Optional, Tuple
import pandas as pd
import xarray as xr

from backend.core.logging import logger


@dataclass
class CachedDatasetMetadata:
    """Indexed metadata for a local NetCDF ocean dataset."""

    path: Path
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    time_min: datetime
    time_max: datetime
    variables: Tuple[str, ...]

    def contains(
        self,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        time_min: datetime,
        time_max: datetime,
        required_vars: Tuple[str, ...] = ("uo", "vo"),
    ) -> bool:
        """Verify spatial, temporal, and variable containment with tolerance."""
        # Variable check
        for v in required_vars:
            if v not in self.variables:
                return False

        # Spatial check (allow grid spacing tolerance of 0.10 deg ~ 1 Copernicus grid cell)
        grid_tol = 0.10
        if (self.lat_min > lat_min + grid_tol) or (self.lat_max < lat_max - grid_tol):
            return False
        if (self.lon_min > lon_min + grid_tol) or (self.lon_max < lon_max - grid_tol):
            return False

        # Temporal check
        t_start = time_min.astimezone(timezone.utc) if time_min.tzinfo else time_min.replace(tzinfo=timezone.utc)
        t_end = time_max.astimezone(timezone.utc) if time_max.tzinfo else time_max.replace(tzinfo=timezone.utc)
        c_start = self.time_min.astimezone(timezone.utc) if self.time_min.tzinfo else self.time_min.replace(tzinfo=timezone.utc)
        c_end = self.time_max.astimezone(timezone.utc) if self.time_max.tzinfo else self.time_max.replace(tzinfo=timezone.utc)

        # Allow 24-hour margin for daily discretization
        margin = pd.Timedelta(hours=24)
        if (c_start > t_start + margin) or (c_end < t_end - margin):
            return False

        return True


class OceanDataCache:
    """Manages indexing and lookup of local Copernicus NetCDF datasets."""

    def __init__(self, cache_dir: Path, sample_dir: Optional[Path] = None):
        self.cache_dir = cache_dir
        self.sample_dir = sample_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._index: List[CachedDatasetMetadata] = []
        self.reindex()

    def reindex(self) -> None:
        """Scan cache and sample directories and build spatial/temporal index."""
        self._index.clear()
        scan_dirs = [self.cache_dir]
        if self.sample_dir and self.sample_dir.exists():
            scan_dirs.append(self.sample_dir)

        seen_paths = set()
        for d in scan_dirs:
            for nc_file in d.glob("*.nc"):
                resolved = nc_file.resolve()
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)

                meta = self._inspect_file(resolved)
                if meta is not None:
                    self._index.append(meta)

    def _inspect_file(self, path: Path) -> Optional[CachedDatasetMetadata]:
        """Inspect a NetCDF file with xarray to extract its bounding coordinates and time range."""
        try:
            with xr.open_dataset(path) as ds:
                lat_var = "latitude" if "latitude" in ds else ("lat" if "lat" in ds else None)
                lon_var = "longitude" if "longitude" in ds else ("lon" if "lon" in ds else None)
                time_var = "time" if "time" in ds else None

                if not (lat_var and lon_var and time_var):
                    return None

                lat_min = float(ds[lat_var].min().values)
                lat_max = float(ds[lat_var].max().values)
                lon_min = float(ds[lon_var].min().values)
                lon_max = float(ds[lon_var].max().values)

                # Normalize lon range if [0, 360]
                if lon_max > 180.0 and lon_min >= 0.0:
                    lon_min = ((lon_min + 180.0) % 360.0) - 180.0
                    lon_max = ((lon_max + 180.0) % 360.0) - 180.0
                    if lon_min > lon_max:
                        lon_min, lon_max = lon_max, lon_min

                raw_tmin = ds[time_var].min().values
                raw_tmax = ds[time_var].max().values
                t_min = pd.Timestamp(raw_tmin).tz_localize(timezone.utc) if pd.Timestamp(raw_tmin).tz is None else pd.Timestamp(raw_tmin).tz_convert(timezone.utc)
                t_max = pd.Timestamp(raw_tmax).tz_localize(timezone.utc) if pd.Timestamp(raw_tmax).tz is None else pd.Timestamp(raw_tmax).tz_convert(timezone.utc)

                variables = tuple(str(v) for v in ds.data_vars)

                return CachedDatasetMetadata(
                    path=path,
                    lat_min=lat_min,
                    lat_max=lat_max,
                    lon_min=lon_min,
                    lon_max=lon_max,
                    time_min=t_min.to_pydatetime(),
                    time_max=t_max.to_pydatetime(),
                    variables=variables,
                )
        except Exception as e:
            logger.debug(f"Failed to inspect NetCDF file {path.name}: {e}")
            return None

    def find_cached_dataset(
        self,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        time_min: datetime,
        time_max: datetime,
        required_vars: Tuple[str, ...] = ("uo", "vo"),
    ) -> Optional[Path]:
        """Find an existing NetCDF that encloses the spatial extent and time window."""
        # First check indexed entries
        for meta in self._index:
            if meta.contains(lat_min, lat_max, lon_min, lon_max, time_min, time_max, required_vars):
                logger.info(f"Reusing cached Copernicus NetCDF: {meta.path.name}")
                return meta.path

        # If not found in index, perform a fresh reindex and check once more
        self.reindex()
        for meta in self._index:
            if meta.contains(lat_min, lat_max, lon_min, lon_max, time_min, time_max, required_vars):
                logger.info(f"Reusing newly indexed Copernicus NetCDF: {meta.path.name}")
                return meta.path

        return None

    def generate_cache_filename(
        self,
        dataset_id: str,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        time_min: datetime,
        time_max: datetime,
    ) -> str:
        """Create a deterministic cache filename for a subset."""
        t_start_str = time_min.strftime("%Y%m%d")
        t_end_str = time_max.strftime("%Y%m%d")
        clean_ds_id = dataset_id.replace("-", "_").replace(".", "_")
        return f"{clean_ds_id}_{lat_min:.2f}_{lat_max:.2f}_{lon_min:.2f}_{lon_max:.2f}_{t_start_str}_{t_end_str}.nc"
