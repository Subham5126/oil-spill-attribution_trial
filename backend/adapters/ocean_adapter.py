"""Ocean & Meteorological Data Ingestion Adapter (Member 4 Integration).

Bridges the backend to Member 4 ocean current and wind dataset loaders.
Supports local NetCDF files and configurable directories without downloading unconfigured sources.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import xarray as xr
from backend.core.config import settings
from backend.core.logging import logger
from ocean.currents import load_currents
from ocean.wind import load_wind


class OceanAdapter:
    """Service adapter interfacing with Member 4 Copernicus and ERA5 data loaders."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or settings.OCEAN_DATA_DIR

    def get_currents_path(self) -> Path:
        """Resolve currents NetCDF file path."""
        candidate = self.data_dir / "copernicus" / "current_test.nc"
        if candidate.exists():
            return candidate
        # Check parent sample dir
        alt = settings.REPO_ROOT / "data" / "sample" / "copernicus" / "current_test.nc"
        if alt.exists():
            return alt
        raise FileNotFoundError(f"Copernicus currents NetCDF file not found in {self.data_dir}")

    def get_wind_path(self) -> Path:
        """Resolve wind NetCDF file path."""
        candidate = self.data_dir / "era5" / "wind_test.nc"
        if candidate.exists():
            return candidate
        alt = settings.REPO_ROOT / "data" / "sample" / "era5" / "wind_test.nc"
        if alt.exists():
            return alt
        raise FileNotFoundError(f"ERA5 wind NetCDF file not found in {self.data_dir}")

    def load_environmental_datasets(self) -> tuple[xr.Dataset, xr.Dataset]:
        """Load Copernicus currents and ERA5 wind xarray Datasets."""
        curr_path = self.get_currents_path()
        wind_path = self.get_wind_path()

        logger.info(f"Loading ocean currents from {curr_path}")
        curr_ds = load_currents(curr_path)

        logger.info(f"Loading wind fields from {wind_path}")
        wind_ds = load_wind(wind_path)

        return curr_ds, wind_ds
