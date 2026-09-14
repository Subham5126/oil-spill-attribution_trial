from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import desc, asc, or_, and_, func
from sqlalchemy.orm import Session
from backend.models.investigation import InvestigationModel


class InvestigationRepository:
    """Database repository for InvestigationModel entities."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def get_by_id(self, investigation_id: str, include_deleted: bool = False) -> Optional[InvestigationModel]:
        if self.db is None:
            return None
        q = self.db.query(InvestigationModel).filter(
            InvestigationModel.investigation_id == investigation_id
        )
        if not include_deleted:
            q = q.filter(InvestigationModel.is_deleted.is_(False))
        return q.first()

    def list_all(
        self,
        search: Optional[str] = None,
        status: Optional[str] = None,
        region: Optional[str] = None,
        starred: Optional[bool] = None,
        archived: Optional[bool] = None,
        include_deleted: bool = False,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> List[InvestigationModel]:
        if self.db is None:
            return []

        q = self.db.query(InvestigationModel)
        if not include_deleted:
            q = q.filter(InvestigationModel.is_deleted.is_(False))
        if archived is not None:
            q = q.filter(InvestigationModel.is_archived.is_(archived))
        if starred is not None:
            q = q.filter(InvestigationModel.is_starred.is_(starred))
        if status and status.lower() != "all":
            q = q.filter(func.lower(InvestigationModel.status) == status.lower())
        if region and region.lower() != "all":
            q = q.filter(InvestigationModel.region.ilike(f"%{region}%"))
        if search and search.strip():
            term = f"%{search.strip()}%"
            q = q.filter(
                or_(
                    InvestigationModel.investigation_id.ilike(term),
                    InvestigationModel.title.ilike(term),
                    InvestigationModel.region.ilike(term),
                    InvestigationModel.image_id.ilike(term),
                    InvestigationModel.suspect_vessel.ilike(term),
                )
            )

        # Sorting
        order_col = getattr(InvestigationModel, sort_by, InvestigationModel.created_at)
        q = q.order_by(desc(order_col) if sort_dir == "desc" else asc(order_col))

        return q.offset(offset).limit(limit).all()

    def list_history(
        self,
        search: Optional[str] = None,
        status: Optional[str] = None,
        region: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> List[InvestigationModel]:
        if self.db is None:
            return []

        q = self.db.query(InvestigationModel).filter(InvestigationModel.is_deleted.is_(False))
        if status and status.lower() != "all":
            q = q.filter(func.lower(InvestigationModel.status) == status.lower())
        if region and region.lower() != "all":
            q = q.filter(InvestigationModel.region.ilike(f"%{region}%"))
        if from_date:
            q = q.filter(InvestigationModel.created_at >= from_date)
        if to_date:
            q = q.filter(InvestigationModel.created_at <= to_date)
        if search and search.strip():
            term = f"%{search.strip()}%"
            q = q.filter(
                or_(
                    InvestigationModel.investigation_id.ilike(term),
                    InvestigationModel.title.ilike(term),
                    InvestigationModel.region.ilike(term),
                    InvestigationModel.image_id.ilike(term),
                )
            )

        order_col = getattr(InvestigationModel, sort_by, InvestigationModel.created_at)
        q = q.order_by(desc(order_col) if sort_dir == "desc" else asc(order_col))
        return q.offset(offset).limit(limit).all()

    def count_summary(self) -> Dict[str, Any]:
        if self.db is None:
            return {
                "total": 0,
                "completed": 0,
                "active": 0,
                "running": 0,
                "failed": 0,
                "total_spill_area_km2": 0.0,
                "candidate_vessels_count": 0,
            }

        base = self.db.query(InvestigationModel).filter(InvestigationModel.is_deleted.is_(False))
        total = base.count()
        completed = base.filter(func.lower(InvestigationModel.status) == "completed").count()
        running = base.filter(
            or_(
                func.lower(InvestigationModel.pipeline_status) == "running",
                func.lower(InvestigationModel.status) == "running",
            )
        ).count()
        failed = base.filter(
            or_(
                func.lower(InvestigationModel.pipeline_status) == "failed",
                func.lower(InvestigationModel.status) == "failed",
            )
        ).count()
        active = base.filter(
            and_(
                func.lower(InvestigationModel.status) != "completed",
                func.lower(InvestigationModel.status) != "failed",
            )
        ).count()

        total_area = (
            self.db.query(func.sum(InvestigationModel.spill_area_km2))
            .filter(InvestigationModel.is_deleted.is_(False))
            .scalar()
            or 0.0
        )

        total_vessels = 0
        records = base.all()
        for r in records:
            if r.result_json and isinstance(r.result_json, dict):
                candidates = r.result_json.get("candidate_vessels") or []
                total_vessels += len(candidates)

        return {
            "total": total,
            "completed": completed,
            "active": active,
            "running": running,
            "failed": failed,
            "total_spill_area_km2": round(float(total_area), 4),
            "candidate_vessels_count": total_vessels,
        }

    def create(self, inv: InvestigationModel) -> InvestigationModel:
        if self.db is not None:
            now = datetime.now(timezone.utc)
            if not inv.activity_log_json:
                inv.activity_log_json = [
                    {
                        "event": "CREATED",
                        "timestamp": now.isoformat(),
                        "details": f"Investigation incident {inv.investigation_id} created.",
                    }
                ]
            self.db.add(inv)
            self.db.commit()
            self.db.refresh(inv)
        return inv

    def update(self, inv: InvestigationModel) -> InvestigationModel:
        if self.db is not None:
            self.db.add(inv)
            self.db.commit()
            self.db.refresh(inv)
        return inv

    def soft_delete(self, investigation_id: str) -> bool:
        rec = self.get_by_id(investigation_id, include_deleted=False)
        if rec and self.db is not None:
            now = datetime.now(timezone.utc)
            rec.is_deleted = True
            rec.deleted_at = now
            self.append_activity(investigation_id, "SOFT_DELETED", "Investigation moved to trash.")
            self.db.commit()
            return True
        return False

    def restore(self, investigation_id: str) -> bool:
        rec = self.get_by_id(investigation_id, include_deleted=True)
        if rec and rec.is_deleted and self.db is not None:
            rec.is_deleted = False
            rec.deleted_at = None
            self.append_activity(investigation_id, "RESTORED", "Investigation restored from trash.")
            self.db.commit()
            return True
        return False

    def hard_delete(self, investigation_id: str) -> bool:
        rec = self.get_by_id(investigation_id, include_deleted=True)
        if rec and self.db is not None:
            self.db.delete(rec)
            self.db.commit()
            return True
        return False

    def toggle_star(self, investigation_id: str, starred: Optional[bool] = None) -> Optional[bool]:
        rec = self.get_by_id(investigation_id)
        if rec and self.db is not None:
            rec.is_starred = not rec.is_starred if starred is None else starred
            self.db.commit()
            return rec.is_starred
        return None

    def toggle_archive(self, investigation_id: str, archived: Optional[bool] = None) -> Optional[bool]:
        rec = self.get_by_id(investigation_id)
        if rec and self.db is not None:
            rec.is_archived = not rec.is_archived if archived is None else archived
            self.append_activity(
                investigation_id,
                "ARCHIVED" if rec.is_archived else "UNARCHIVED",
                "Investigation archive status changed.",
            )
            self.db.commit()
            return rec.is_archived
        return None

    def append_activity(
        self,
        investigation_id: str,
        event: str,
        details: str = "",
        user: str = "Forensic Analyst",
    ):
        rec = self.get_by_id(investigation_id, include_deleted=True)
        if rec and self.db is not None:
            logs = list(rec.activity_log_json or [])
            logs.append({
                "event": event,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": details,
                "user": user,
            })
            rec.activity_log_json = logs
            self.db.commit()
