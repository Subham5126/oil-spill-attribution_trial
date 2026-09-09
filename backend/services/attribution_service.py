"""Attribution Service Module."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.adapters.demo_adapter import demo_provider
from backend.repositories.attribution import AttributionRepository


class AttributionService:
    """Service managing vessel attribution results and ranking."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self.repo = AttributionRepository(db)

    def get_attribution(self, investigation_id: str) -> Dict[str, Any]:
        """Fetch attribution ranking for an investigation."""
        db_records = self.repo.get_attribution_results(investigation_id)
        if db_records:
            ranked = []
            for r in db_records:
                ranked.append({
                    "rank": r.rank,
                    "mmsi": r.mmsi,
                    "vessel_name": r.vessel_name,
                    "imo": r.imo or "N/A",
                    "vessel_type": r.vessel_type or 0,
                    "scores": {
                        "overall": r.overall_score,
                        "spatial": r.spatial_score,
                        "temporal": r.temporal_score,
                        "trajectory": r.trajectory_score,
                        "behaviour": r.behaviour_score,
                    },
                    "metrics": {
                        "min_distance_km": r.min_distance_km,
                        "time_difference_minutes": r.time_difference_minutes,
                        "transit_speed_knots": r.transit_speed_knots or 12.0,
                    },
                    "suspicious_flags": r.suspicious_flags_json or [],
                    "explanation": r.explanation_json or [],
                })
            primary = ranked[0] if ranked else None
            return {
                "investigation_id": investigation_id,
                "primary_suspect": primary,
                "attribution_ranking": ranked,
                "provenance": {"data_source_mode": "REAL"},
            }

        # Demo attribution
        demo_res = demo_provider.load_latest_result()
        return {
            "investigation_id": investigation_id,
            "primary_suspect": demo_res.get("primary_suspect"),
            "attribution_ranking": demo_res.get("attribution_ranking", []),
            "ais_search": demo_res.get("ais_search"),
            "provenance": demo_res.get("provenance", {"data_source_mode": "DEMO"}),
        }
