"""ERA5 10-m wind data loading utilities."""

from .loader import WindDataError, load_wind

__all__ = ["WindDataError", "load_wind"]
