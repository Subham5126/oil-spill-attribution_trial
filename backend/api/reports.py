"""Forensic Reports API Router."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.schemas.report import ReportCreate, ReportResponse
from backend.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("", response_model=List[ReportResponse])
def list_reports(
    investigation_id: Optional[str] = Query(None, description="Filter by investigation ID"),
    db: Session = Depends(get_db),
):
    """List forensic reports / MARPOL Annex I violation dossiers."""
    service = ReportService(db)
    return service.list_reports(investigation_id=investigation_id)


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(report_id: str, db: Session = Depends(get_db)):
    """Retrieve a specific forensic report by report ID."""
    service = ReportService(db)
    return service.get_report(report_id)


@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_report(payload: ReportCreate, db: Session = Depends(get_db)):
    """Generate and persist a new forensic report for an investigation."""
    service = ReportService(db)
    return service.generate_report(
        investigation_id=payload.investigation_id,
        author=payload.author or "Indian Coast Guard / Maritime Forensic Taskforce",
    )
