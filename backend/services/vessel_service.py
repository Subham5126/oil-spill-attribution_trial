"""Vessel Service Module."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.adapters.demo_adapter import demo_provider
from backend.core.exceptions import VesselNotFoundError
from backend.repositories.vessels import VesselRepository


class VesselService:
    """Service providing vessel registries and kinematic tracks."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self.repo = VesselRepository(db)

    def list_vessels(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """List vessels, falling back to candidates from demo result."""
        db_vessels = self.repo.list_vessels(limit=limit, offset=offset)
        if db_vessels:
            return [
                {
                    "mmsi": v.mmsi,
                    "imo": v.imo,
                    "vessel_name": v.vessel_name,
                    "flag": v.flag,
                    "vessel_type": v.vessel_type,
                    "call_sign": v.call_sign,
                    "length_m": v.length_m,
                    "width_m": v.width_m,
                    "draft_m": v.draft_m,
                }
                for v in db_vessels
            ]

        # Extract vessels from demo data
        demo_res = demo_provider.load_latest_result()
        candidates = demo_res.get("candidate_vessels", [])
        return [
            {
                "mmsi": c.get("mmsi"),
                "imo": c.get("imo"),
                "vessel_name": c.get("vessel_name"),
                "flag": "Panama" if c.get("mmsi") == 413999001 else "Liberia",
                "vessel_type": "Tanker" if c.get("vessel_type") == 80 else "Cargo",
                "call_sign": "VRBM8" if c.get("mmsi") == 413999001 else "LAHP7",
                "length_m": 274 if c.get("mmsi") == 413999001 else 189,
                "width_m": 48 if c.get("mmsi") == 413999001 else 30,
                "draft_m": 15 if c.get("mmsi") == 413999001 else 10,
            }
            for c in candidates
        ]

    def get_vessel(self, mmsi: int) -> Dict[str, Any]:
        """Fetch a single vessel by MMSI."""
        v = self.repo.get_by_mmsi(mmsi)
        if v:
            return {
                "mmsi": v.mmsi,
                "imo": v.imo,
                "vessel_name": v.vessel_name,
                "flag": v.flag,
                "vessel_type": v.vessel_type,
                "call_sign": v.call_sign,
                "length_m": v.length_m,
                "width_m": v.width_m,
                "draft_m": v.draft_m,
            }

        # Check demo dataset
        for v in self.list_vessels():
            if v["mmsi"] == mmsi:
                return v

        raise VesselNotFoundError(f"Vessel with MMSI {mmsi} not found", stage="VESSEL_LOOKUP")
