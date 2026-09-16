"""Forensic Report ORM Model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from backend.core.database import Base
from backend.models.base import TimestampMixin


class ReportModel(Base, TimestampMixin):
    """MARPOL Annex I Forensic Report Record."""

    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(64), unique=True, nullable=False, index=True)
    investigation_id = Column(String(64), ForeignKey("investigations.investigation_id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    report_type = Column(String(64), default="Forensic Dossier", nullable=False)
    status = Column(String(32), default="Final", nullable=False)
    generated_at = Column(DateTime(timezone=True), nullable=False)
    author = Column(String(128), default="Indian Coast Guard / Maritime Forensic Taskforce", nullable=False)
    target_vessel = Column(String(128), nullable=False)
    imo = Column(String(32), nullable=True)
    mmsi = Column(BigInteger, nullable=True)
    attribution_score = Column(Float, nullable=False)
    summary = Column(Text, nullable=False)
    marpol_violation_risk = Column(String(32), default="High", nullable=False)
    sha256_hash = Column(String(64), nullable=False)
    jurisdiction = Column(String(128), default="UNCLOS / MARPOL 73/78 Annex I / DG Shipping India", nullable=False)
    location_path = Column(String(255), nullable=True)
    metadata_json = Column(JSON, default=dict)

    investigation = relationship("InvestigationModel", back_populates="reports")

    __table_args__ = (
        Index("idx_report_inv_generated", "investigation_id", "generated_at"),
    )
