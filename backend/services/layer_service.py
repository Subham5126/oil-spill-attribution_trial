"""GIS Layer & GeoJSON Export Service.

Assembles and serves multi-layer WGS84 GeoJSON FeatureCollections for the MapLibre frontend:
- Observed spill polygon & bounding box
- Forward forecast & backward hindcast particle dispersion cones
- Probable origin point & 95% spatial dispersion ellipse
- Candidate vessel trajectories and primary suspect tracks
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from backend.adapters.demo_adapter import demo_provider
from backend.repositories.investigations import InvestigationRepository
from backend.repositories.spills import SpillRepository


class LayerService:
    """Service providing GIS layers in GeoJSON format."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self.inv_repo = InvestigationRepository(db)
        self.spill_repo = SpillRepository(db)

    def get_latest_layers_geojson(self) -> Dict[str, Any]:
        """Fetch the latest GIS GeoJSON FeatureCollection."""
        return demo_provider.load_latest_layers_geojson()

    def get_layers_for_investigation(self, investigation_id: str) -> Dict[str, Any]:
        """Fetch GeoJSON layers for a specific investigation."""
        # Check demo provider match
        layers = demo_provider.load_latest_layers_geojson()
        features = layers.get("features", [])

        # Filter features if tagged with investigation_id, or return complete set
        matching_features = [
            f for f in features if f.get("properties", {}).get("spill_id") == investigation_id
        ]
        if matching_features:
            return {
                "type": "FeatureCollection",
                "crs": layers.get("crs"),
                "features": matching_features,
            }

        return layers
