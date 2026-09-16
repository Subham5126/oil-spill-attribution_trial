"""Vessels & AIS Tracks Repository."""

from __future__ import annotations

from typing import List, Optional
from sqlalchemy.orm import Session
from backend.models.vessel import VesselModel
from backend.models.ais import AISTrackModel


class VesselRepository:
    """Database repository for VesselModel and AISTrackModel entities."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def get_by_mmsi(self, mmsi: int) -> Optional[VesselModel]:
        if self.db is None:
            return None
        return self.db.query(VesselModel).filter(VesselModel.mmsi == mmsi).first()

    def list_vessels(self, limit: int = 50, offset: int = 0) -> List[VesselModel]:
        if self.db is None:
            return []
        return self.db.query(VesselModel).offset(offset).limit(limit).all()

    def create(self, vessel: VesselModel) -> VesselModel:
        if self.db is not None:
            self.db.add(vessel)
            self.db.commit()
            self.db.refresh(vessel)
        return vessel

    def get_ais_tracks(self, investigation_id: str, mmsi: Optional[int] = None) -> List[AISTrackModel]:
        if self.db is None:
            return []
        query = self.db.query(AISTrackModel).filter(AISTrackModel.investigation_id == investigation_id)
        if mmsi is not None:
            query = query.filter(AISTrackModel.mmsi == mmsi)
        return query.order_by(AISTrackModel.timestamp.asc()).all()

    def bulk_create_tracks(self, tracks: List[AISTrackModel]) -> None:
        if self.db is not None and tracks:
            self.db.bulk_save_objects(tracks)
            self.db.commit()
