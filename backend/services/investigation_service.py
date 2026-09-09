"""Investigation Service Module."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.adapters.demo_adapter import demo_provider
from backend.core.config import settings
from backend.core.exceptions import InvestigationNotFoundError
from backend.core.logging import logger
from backend.models.investigation import InvestigationModel
from backend.repositories.investigations import InvestigationRepository
from backend.schemas.investigation import (
    InvestigationCreate,
    InvestigationResponse,
    InvestigationStatusResponse,
)


class InvestigationService:
    """Service coordinating investigation lifecycle and querying."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self.repo = InvestigationRepository(db)

    def list_investigations(self) -> List[Dict[str, Any]]:
        """List all investigations, falling back to demo records if DB is empty or unavailable."""
        db_records = self.repo.list_all()
        if db_records:
            results = []
            for r in db_records:
                results.append({
                    "id": r.investigation_id,
                    "title": r.title,
                    "status": r.status,
                    "priority": r.priority,
                    "region": r.region,
                    "coordinates": {
                        "latitude": r.centroid_lat or 18.523598,
                        "longitude": r.centroid_lon or 72.481513,
                    },
                    "spill_area_km2": r.spill_area_km2 or 3.9275,
                    "detection_time": r.observation_timestamp.isoformat() if r.observation_timestamp else "2025-01-01T05:00:00 UTC",
                    "suspect_vessel": r.suspect_vessel,
                    "match_confidence": r.match_confidence,
                    "evidence_nodes_count": r.evidence_nodes_count,
                    "sar_epoch": r.sar_epoch or "05:00Z",
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                })
            return results

        # Fall back to demo investigations
        return demo_provider.get_demo_investigations()

    def get_investigation(self, investigation_id: str) -> Dict[str, Any]:
        """Fetch investigation by public identifier."""
        record = self.repo.get_by_id(investigation_id)
        if record:
            return {
                "id": record.investigation_id,
                "title": record.title,
                "status": record.status,
                "priority": record.priority,
                "region": record.region,
                "coordinates": {
                    "latitude": record.centroid_lat or 18.523598,
                    "longitude": record.centroid_lon or 72.481513,
                },
                "spill_area_km2": record.spill_area_km2 or 3.9275,
                "detection_time": record.observation_timestamp.isoformat() if record.observation_timestamp else "2025-01-01T05:00:00 UTC",
                "suspect_vessel": record.suspect_vessel,
                "match_confidence": record.match_confidence,
                "evidence_nodes_count": record.evidence_nodes_count,
                "sar_epoch": record.sar_epoch or "05:00Z",
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }

        # Check demo dataset
        for inv in demo_provider.get_demo_investigations():
            if inv["id"] == investigation_id:
                return inv

        raise InvestigationNotFoundError(
            f"Investigation '{investigation_id}' not found",
            stage="INVESTIGATION_LOOKUP",
        )

    def create_investigation(self, payload: InvestigationCreate) -> Dict[str, Any]:
        """Create and persist a new investigation entity."""
        inv_id = f"SAR-{datetime.now(timezone.utc).strftime('%Y%m%d')}-IND-{int(datetime.now().timestamp()) % 10000:04d}"
        coord = payload.coordinates or None
        lat = coord.latitude if coord else 18.5236
        lon = coord.longitude if coord else 72.4815

        inv = InvestigationModel(
            investigation_id=inv_id,
            title=payload.name,
            status="Active",
            priority=payload.priority,
            region=payload.region,
            observation_timestamp=payload.observation_timestamp or datetime.now(timezone.utc),
            centroid_lat=lat,
            centroid_lon=lon,
            spill_area_km2=0.0,
            metadata_json=payload.metadata,
        )
        self.repo.create(inv)

        return {
            "id": inv_id,
            "title": payload.name,
            "status": "Active",
            "priority": payload.priority,
            "region": payload.region,
            "coordinates": {"latitude": lat, "longitude": lon},
            "spill_area_km2": 0.0,
            "detection_time": inv.observation_timestamp.isoformat(),
            "evidence_nodes_count": 0,
            "sar_epoch": inv.observation_timestamp.strftime("%H:%MZ"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_investigation_status(self, investigation_id: str) -> Dict[str, Any]:
        """Retrieve execution and lifecycle status of an investigation."""
        inv = self.get_investigation(investigation_id)
        return {
            "investigation_id": investigation_id,
            "status": inv.get("status", "Active"),
            "stage": "COMPLETED" if inv.get("status") in ("Completed", "Active") else "PROCESSING",
            "progress_percentage": 100 if inv.get("status") in ("Completed", "Active") else 50,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "message": f"Investigation {investigation_id} is {inv.get('status')}",
        }
