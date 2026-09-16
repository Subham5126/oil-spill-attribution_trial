"""Spills Repository."""

from __future__ import annotations

from typing import List, Optional
from sqlalchemy.orm import Session
from backend.models.spill import SpillDetectionModel


class SpillRepository:
    """Database repository for SpillDetectionModel entities."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def get_by_investigation_id(self, investigation_id: str) -> Optional[SpillDetectionModel]:
        if self.db is None:
            return None
        return self.db.query(SpillDetectionModel).filter(
            SpillDetectionModel.investigation_id == investigation_id
        ).first()

    def get_by_spill_id(self, spill_id: str) -> Optional[SpillDetectionModel]:
        if self.db is None:
            return None
        return self.db.query(SpillDetectionModel).filter(
            SpillDetectionModel.spill_id == spill_id
        ).first()

    def create(self, spill: SpillDetectionModel) -> SpillDetectionModel:
        if self.db is not None:
            self.db.add(spill)
            self.db.commit()
            self.db.refresh(spill)
        return spill
