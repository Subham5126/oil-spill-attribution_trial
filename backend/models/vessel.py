"""Vessel ORM Model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, Index, Integer, JSON, String
from backend.core.database import Base
from backend.models.base import TimestampMixin


class VesselModel(Base, TimestampMixin):
    """Maritime vessel static registry information."""

    __tablename__ = "vessels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mmsi = Column(BigInteger, unique=True, nullable=False, index=True)
    imo = Column(String(32), nullable=True, index=True)
    vessel_name = Column(String(128), nullable=False, index=True)
    flag = Column(String(64), nullable=True)
    vessel_type = Column(String(64), nullable=True)
    call_sign = Column(String(32), nullable=True)
    length_m = Column(Integer, nullable=True)
    width_m = Column(Integer, nullable=True)
    draft_m = Column(Integer, nullable=True)
    metadata_json = Column(JSON, default=dict)

    __table_args__ = (
        Index("idx_vessel_mmsi_imo", "mmsi", "imo"),
    )
