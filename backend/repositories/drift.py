"""Drift Runs & Origin Candidates Repository."""

from __future__ import annotations

from typing import List, Optional
from sqlalchemy.orm import Session
from backend.models.drift import DriftRunModel
from backend.models.origin import OriginCandidateModel


class DriftRepository:
    """Database repository for DriftRunModel and OriginCandidateModel entities."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def get_latest_drift_run(self, investigation_id: str) -> Optional[DriftRunModel]:
        if self.db is None:
            return None
        return self.db.query(DriftRunModel).filter(
            DriftRunModel.investigation_id == investigation_id
        ).order_by(DriftRunModel.created_at.desc()).first()

    def create_drift_run(self, drift: DriftRunModel) -> DriftRunModel:
        if self.db is not None:
            self.db.add(drift)
            self.db.commit()
            self.db.refresh(drift)
        return drift

    def get_origin_candidates(self, investigation_id: str) -> List[OriginCandidateModel]:
        if self.db is None:
            return []
        return self.db.query(OriginCandidateModel).filter(
            OriginCandidateModel.investigation_id == investigation_id
        ).order_by(OriginCandidateModel.rank.asc()).all()

    def create_origin_candidate(self, candidate: OriginCandidateModel) -> OriginCandidateModel:
        if self.db is not None:
            self.db.add(candidate)
            self.db.commit()
            self.db.refresh(candidate)
        return candidate
