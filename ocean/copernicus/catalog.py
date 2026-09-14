"""Copernicus Marine Dataset Catalog and Metadata Definitions.

Defines product configurations, spatial bounding envelopes, temporal coverage
ranges, and selection priority rules for Copernicus hydrodynamic products.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class CopernicusDatasetDescriptor:
    """Metadata descriptor for a Copernicus Marine product and dataset."""

    product_id: str
    dataset_id: str
    title: str
    temporal_coverage_type: str  # "MULTIYEAR" or "ANALYSIS_FORECAST"
    time_min: datetime
    time_max: Optional[datetime]  # None indicates rolling/dynamically updated horizon
    lat_min: float = -80.0
    lat_max: float = 90.0
    lon_min: float = -180.0
    lon_max: float = 180.0
    default_depth: float = 0.49402499198913574
    variables: Tuple[str, ...] = ("uo", "vo")

    def contains_point(self, lat: float, lon: float) -> bool:
        """Check if target coordinates fall within the spatial bounding box."""
        # Normalize lon to [-180, 180]
        norm_lon = ((lon + 180.0) % 360.0) - 180.0
        return (self.lat_min <= lat <= self.lat_max) and (self.lon_min <= norm_lon <= self.lon_max)

    def contains_window(self, start_time: datetime, end_time: datetime) -> bool:
        """Check if the requested temporal window falls completely within dataset temporal bounds."""
        s = start_time.astimezone(timezone.utc) if start_time.tzinfo else start_time.replace(tzinfo=timezone.utc)
        e = end_time.astimezone(timezone.utc) if end_time.tzinfo else end_time.replace(tzinfo=timezone.utc)

        t_min = self.time_min.astimezone(timezone.utc) if self.time_min.tzinfo else self.time_min.replace(tzinfo=timezone.utc)
        if s < t_min:
            return False

        if self.time_max is not None:
            t_max = self.time_max.astimezone(timezone.utc) if self.time_max.tzinfo else self.time_max.replace(tzinfo=timezone.utc)
            if e > t_max:
                return False

        return True


# Multi-year physics reanalysis (Daily mean surface currents)
COPERNICUS_MULTIYEAR_DAILY = CopernicusDatasetDescriptor(
    product_id="GLOBAL_MULTIYEAR_PHY_001_030",
    dataset_id="cmems_mod_glo_phy_my_0.083deg_P1D-m",
    title="Global Ocean Physics Reanalysis (Multiyear 1993 - mid-2026)",
    temporal_coverage_type="MULTIYEAR",
    time_min=datetime(1993, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    time_max=datetime(2026, 6, 23, 0, 0, 0, tzinfo=timezone.utc),
    lat_min=-80.0,
    lat_max=90.0,
    lon_min=-180.0,
    lon_max=180.0,
)

# Analysis and Forecast physics (Daily mean surface currents)
COPERNICUS_ANALYSISFORECAST_DAILY = CopernicusDatasetDescriptor(
    product_id="GLOBAL_ANALYSISFORECAST_PHY_001_024",
    dataset_id="cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m",
    title="Global Ocean Physics Analysis and Forecast (Daily Currents)",
    temporal_coverage_type="ANALYSIS_FORECAST",
    time_min=datetime(2022, 6, 1, 0, 0, 0, tzinfo=timezone.utc),
    time_max=None,  # Rolling horizon extending to forecast window (~now + 10 days)
    lat_min=-80.0,
    lat_max=90.0,
    lon_min=-180.0,
    lon_max=180.0,
)

# Analysis and Forecast physics (Hourly mean surface currents)
COPERNICUS_ANALYSISFORECAST_HOURLY = CopernicusDatasetDescriptor(
    product_id="GLOBAL_ANALYSISFORECAST_PHY_001_024",
    dataset_id="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
    title="Global Ocean Physics Analysis and Forecast (Hourly Currents)",
    temporal_coverage_type="ANALYSIS_FORECAST",
    time_min=datetime(2022, 6, 1, 0, 0, 0, tzinfo=timezone.utc),
    time_max=None,  # Rolling horizon
    lat_min=-80.0,
    lat_max=90.0,
    lon_min=-180.0,
    lon_max=180.0,
)

SUPPORTED_COPERNICUS_DATASETS: List[CopernicusDatasetDescriptor] = [
    COPERNICUS_MULTIYEAR_DAILY,
    COPERNICUS_ANALYSISFORECAST_DAILY,
    COPERNICUS_ANALYSISFORECAST_HOURLY,
]
