"""OilTrace Scientific & Data Adapters Package."""

from backend.adapters.satellite_adapter import (
    SatelliteObservation,
    SatelliteAdapterInterface,
    DemoSatelliteAdapter,
)
from backend.adapters.ai_adapter import (
    SegmentationResult,
    AIAdapterInterface,
    DemoAIAdapter,
)
from backend.adapters.gis_adapter import GISAdapter
from backend.adapters.ocean_adapter import OceanAdapter
from backend.adapters.drift_adapter import DriftAdapter
from backend.adapters.ais_adapter import AISAdapter
from backend.adapters.attribution_adapter import AttributionAdapter
from backend.adapters.demo_adapter import DemoDataProvider, demo_provider

__all__ = [
    "SatelliteObservation",
    "SatelliteAdapterInterface",
    "DemoSatelliteAdapter",
    "SegmentationResult",
    "AIAdapterInterface",
    "DemoAIAdapter",
    "GISAdapter",
    "OceanAdapter",
    "DriftAdapter",
    "AISAdapter",
    "AttributionAdapter",
    "DemoDataProvider",
    "demo_provider",
]
