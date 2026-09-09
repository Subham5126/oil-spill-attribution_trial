"""Forensic Report Schemas matching frontend Report interface."""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ReportCreate(BaseModel):
    investigation_id: str
    title: Optional[str] = None
    author: Optional[str] = "Indian Coast Guard / Maritime Forensic Taskforce"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReportResponse(BaseModel):
    """Forensic report matching frontend Report interface."""

    id: str
    investigation_id: str
    title: str
    generated_at: str
    author: str
    status: str = "Final"
    target_vessel: str
    imo: str
    mmsi: int
    attribution_score: float
    summary: str
    marpol_violation_risk: str = "High"
    sha256_hash: str
    jurisdiction: str
