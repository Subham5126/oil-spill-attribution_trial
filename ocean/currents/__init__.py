"""Copernicus Marine surface-current data loading utilities."""

from .loader import CurrentDataError, load_currents

__all__ = ["CurrentDataError", "load_currents"]
