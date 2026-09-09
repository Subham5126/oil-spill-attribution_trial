"""Investigations Repository."""

from __future__ import annotations

from typing import List, Optional
from sqlalchemy.orm import Session
from backend.models.investigation import InvestigationModel


class InvestigationRepository:
    """Database repository for InvestigationModel entities."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def get_by_id(self, investigation_id: str) -> Optional[InvestigationModel]:
        if self.db is None:
            return None
        return self.db.query(InvestigationModel).filter(
            InvestigationModel.investigation_id == investigation_id
        ).first()

    def list_all(self, limit: int = 100, offset: int = 0) -> List[InvestigationModel]:
        if self.db is None:
            return []
        return self.db.query(InvestigationModel).order_by(
            InvestigationModel.created_at.desc()
        ).offset(offset).limit(limit).all()

    def create(self, inv: InvestigationModel) -> InvestigationModel:
        if self.db is not None:
            self.db.add(inv)
            self.db.commit()
            self.db.refresh(inv)
        return inv

    def update_status(self, investigation_id: str, status: str, message: Optional[str] = None) -> Optional[InvestigationModel]:
        if self.db is None:
            return None
        record = self.get_by_id(investigation_id)
        if record:
            record.status = status
            if message and record.metadata_json is not None:
                meta = dict(record.metadata_json)
                meta["latest_status_message"] = message
                record.metadata_json = meta
            self.db.commit()
            self.db.refresh(record)
        return record
