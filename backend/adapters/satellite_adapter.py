"""Satellite Acquisition & Preprocessing Adapter (Member 2 Contract).

Defines the normalized satellite observation contract and adapter interface.
Tomorrow Member 2's Sentinel-1 acquisition and preprocessing pipeline will plug in here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class SatelliteObservation:
    """Normalized satellite observation metadata and raster reference."""

    product_id: str
    sensor: str = "Sentinel-1 SAR C-Band (IW)"
    acquisition_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    polarization: str = "VV+VH"
    crs: str = "EPSG:4326"
    raster_path: Optional[Path] = None
    bounds: Optional[Tuple[float, float, float, float]] = None  # (min_lon, min_lat, max_lon, max_lat)
    resolution_meters: float = 10.0
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "sensor": self.sensor,
            "acquisition_timestamp": self.acquisition_timestamp.isoformat(),
            "polarization": self.polarization,
            "crs": self.crs,
            "raster_path": str(self.raster_path) if self.raster_path else None,
            "bounds": list(self.bounds) if self.bounds else None,
            "resolution_meters": self.resolution_meters,
            "properties": self.properties,
        }


class SatelliteAdapterInterface(ABC):
    """Abstract interface to be implemented by Member 2 satellite pipeline."""

    @abstractmethod
    def acquire(self, product_id: str, **kwargs) -> SatelliteObservation:
        """Acquire or locate raw/preprocessed satellite product."""
        pass

    @abstractmethod
    def preprocess(self, observation: SatelliteObservation, **kwargs) -> Path:
        """Execute radiometric calibration, speckle filtering, and terrain correction."""
        pass

    @abstractmethod
    def get_observation_metadata(self, product_id: str) -> SatelliteObservation:
        """Retrieve observation metadata without re-downloading."""
        pass


class DemoSatelliteAdapter(SatelliteAdapterInterface):
    """Placeholder adapter for demo execution before Member 2 integrates."""

    def acquire(self, product_id: str, **kwargs) -> SatelliteObservation:
        return SatelliteObservation(
            product_id=product_id or "S1B_IW_GRDH_1SDV_20250101T050000",
            sensor="Sentinel-1 SAR C-Band (IW)",
            acquisition_timestamp=datetime(2025, 1, 1, 5, 0, 0, tzinfo=timezone.utc),
            polarization="VV+VH",
            crs="EPSG:4326",
            bounds=(72.46, 18.51, 72.51, 18.54),
            properties={
                "mission": "Sentinel-1B",
                "orbit_pass": "DESCENDING",
                "relative_orbit": 42,
            },
        )

    def preprocess(self, observation: SatelliteObservation, **kwargs) -> Path:
        return Path("/tmp/mock_preprocessed_s1.tif")

    def get_observation_metadata(self, product_id: str) -> SatelliteObservation:
        return self.acquire(product_id)
