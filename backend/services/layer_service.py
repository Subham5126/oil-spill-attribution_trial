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
from backend.models.investigation import InvestigationModel
from backend.repositories.investigations import InvestigationRepository
from backend.repositories.spills import SpillRepository


class LayerService:
    """Service providing GIS layers in GeoJSON format."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self.inv_repo = InvestigationRepository(db)
        self.spill_repo = SpillRepository(db)

    def get_latest_layers_geojson(self, mode: Optional[str] = None) -> Dict[str, Any]:
        """Fetch the latest GIS GeoJSON FeatureCollection from database or return empty collection."""
        if mode == "demo":
            return demo_provider.load_latest_layers_geojson(mode=mode)

        if self.db:
            # Query non-deleted investigations with geojson_layers
            active_invs = (
                self.db.query(InvestigationModel)
                .filter(InvestigationModel.geojson_layers.isnot(None))
                .filter(InvestigationModel.is_deleted == False)
                .order_by(InvestigationModel.created_at.desc())
                .all()
            )
            if active_invs:
                # If only 1 investigation, return its layers directly
                if len(active_invs) == 1:
                    return active_invs[0].geojson_layers

                # If multiple investigations, combine all their real features for global surveillance overview
                combined_features = []
                for inv in active_invs:
                    if inv.geojson_layers and "features" in inv.geojson_layers:
                        for f in inv.geojson_layers["features"]:
                            feat = dict(f)
                            props = dict(feat.get("properties") or {})
                            props["investigation_id"] = inv.investigation_id
                            props["incident_title"] = inv.title
                            props["region"] = inv.region
                            feat["properties"] = props
                            combined_features.append(feat)
                return {"type": "FeatureCollection", "features": combined_features}

            # If there are NO non-deleted investigations in the database, return empty collection
            total_count = self.db.query(InvestigationModel).filter(InvestigationModel.is_deleted == False).count()
            if total_count == 0:
                return {"type": "FeatureCollection", "features": []}

        return {"type": "FeatureCollection", "features": []}

    def get_layers_for_investigation(self, investigation_id: str) -> Dict[str, Any]:
        """Fetch GeoJSON layers for a specific investigation."""
        if self.db:
            from backend.services.pipeline_service import PipelineService
            ps = PipelineService(self.db)
            return ps.get_layers_geojson(investigation_id)

        return {"type": "FeatureCollection", "features": []}

