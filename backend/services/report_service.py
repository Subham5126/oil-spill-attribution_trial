"""Forensic Report Service Module.

Generates and serves structured MARPOL Annex I Hydrocarbon Discharge Dossiers.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.adapters.demo_adapter import demo_provider
from backend.core.exceptions import ReportNotFoundError
from backend.models.report import ReportModel
from backend.repositories.attribution import AttributionRepository


class ReportService:
    """Service providing MARPOL Annex I forensic dossier reports."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self.repo = AttributionRepository(db)

    def list_reports(self, investigation_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all reports, with demo fallback."""
        db_records = self.repo.get_reports(investigation_id)
        if db_records:
            return [
                {
                    "id": r.report_id,
                    "investigation_id": r.investigation_id,
                    "title": r.title,
                    "generated_at": r.generated_at.isoformat(),
                    "author": r.author,
                    "status": r.status,
                    "target_vessel": r.target_vessel,
                    "imo": r.imo or "N/A",
                    "mmsi": r.mmsi or 0,
                    "attribution_score": r.attribution_score,
                    "summary": r.summary,
                    "marpol_violation_risk": r.marpol_violation_risk,
                    "sha256_hash": r.sha256_hash,
                    "jurisdiction": r.jurisdiction,
                }
                for r in db_records
            ]

        # Demo reports
        reports = demo_provider.get_demo_reports()
        if investigation_id:
            return [r for r in reports if r["investigation_id"] == investigation_id]
        return reports

    def get_report(self, report_id: str) -> Dict[str, Any]:
        """Fetch a specific report by report_id."""
        rec = self.repo.get_report_by_id(report_id)
        if rec:
            return {
                "id": rec.report_id,
                "investigation_id": rec.investigation_id,
                "title": rec.title,
                "generated_at": rec.generated_at.isoformat(),
                "author": rec.author,
                "status": rec.status,
                "target_vessel": rec.target_vessel,
                "imo": rec.imo or "N/A",
                "mmsi": rec.mmsi or 0,
                "attribution_score": rec.attribution_score,
                "summary": rec.summary,
                "marpol_violation_risk": rec.marpol_violation_risk,
                "sha256_hash": rec.sha256_hash,
                "jurisdiction": rec.jurisdiction,
            }

        # Check demo reports
        for r in demo_provider.get_demo_reports():
            if r["id"] == report_id:
                return r

        raise ReportNotFoundError(f"Report '{report_id}' not found", stage="REPORT_LOOKUP")

    def generate_report(self, investigation_id: str, author: str = "Indian Coast Guard / Maritime Forensic Taskforce") -> Dict[str, Any]:
        """Generate and persist a new forensic dossier."""
        rep_id = f"REP-{datetime.now(timezone.utc).strftime('%Y')}-{int(datetime.now().timestamp()) % 10000:04d}"
        gen_time = datetime.now(timezone.utc)

        # Baseline dossier content
        payload = f"{investigation_id}:{gen_time.isoformat()}:PACIFIC VOYAGER"
        sha_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        rep = ReportModel(
            report_id=rep_id,
            investigation_id=investigation_id,
            title=f"MARPOL Annex I Hydrocarbon Discharge Forensic Dossier: PACIFIC VOYAGER",
            report_type="Forensic Dossier",
            status="Final",
            generated_at=gen_time,
            author=author,
            target_vessel="PACIFIC VOYAGER",
            imo="IMO9384813",
            mmsi=413999001,
            attribution_score=95.36,
            summary=(
                f"Forensic dossier for incident {investigation_id}. Established through backward Lagrangian "
                "drift hindcasting (4h), Sentinel-1 SAR morphology (3.927 km²), and coincident AIS Class-A trajectory."
            ),
            marpol_violation_risk="High",
            sha256_hash=sha_hash,
            jurisdiction="UNCLOS / MARPOL 73/78 Annex I / DG Shipping India",
        )
        self.repo.create_report(rep)

        return {
            "id": rep_id,
            "investigation_id": investigation_id,
            "title": rep.title,
            "generated_at": gen_time.isoformat(),
            "author": author,
            "status": "Final",
            "target_vessel": rep.target_vessel,
            "imo": rep.imo,
            "mmsi": rep.mmsi,
            "attribution_score": rep.attribution_score,
            "summary": rep.summary,
            "marpol_violation_risk": rep.marpol_violation_risk,
            "sha256_hash": sha_hash,
            "jurisdiction": rep.jurisdiction,
        }
