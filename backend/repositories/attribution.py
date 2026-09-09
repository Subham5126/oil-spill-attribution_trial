"""Attribution & Reports Repository."""

from __future__ import annotations

from typing import List, Optional
from sqlalchemy.orm import Session
from backend.models.attribution import AttributionResultModel
from backend.models.report import ReportModel


class AttributionRepository:
    """Database repository for AttributionResultModel and ReportModel entities."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def get_attribution_results(self, investigation_id: str) -> List[AttributionResultModel]:
        if self.db is None:
            return []
        return self.db.query(AttributionResultModel).filter(
            AttributionResultModel.investigation_id == investigation_id
        ).order_by(AttributionResultModel.rank.asc()).all()

    def create_attribution_result(self, result: AttributionResultModel) -> AttributionResultModel:
        if self.db is not None:
            self.db.add(result)
            self.db.commit()
            self.db.refresh(result)
        return result

    def get_reports(self, investigation_id: Optional[str] = None) -> List[ReportModel]:
        if self.db is None:
            return []
        query = self.db.query(ReportModel)
        if investigation_id:
            query = query.filter(ReportModel.investigation_id == investigation_id)
        return query.order_by(ReportModel.generated_at.desc()).all()

    def get_report_by_id(self, report_id: str) -> Optional[ReportModel]:
        if self.db is None:
            return None
        return self.db.query(ReportModel).filter(ReportModel.report_id == report_id).first()

    def create_report(self, report: ReportModel) -> ReportModel:
        if self.db is not None:
            self.db.add(report)
            self.db.commit()
            self.db.refresh(report)
        return report
