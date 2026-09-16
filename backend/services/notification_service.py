"""Notification Service.

Manages investigation alerts, operational lifecycle transitions,
and read/unread states backed by the NotificationModel database table.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from backend.core.logging import logger
from backend.models.investigation import InvestigationModel
from backend.models.notification import NotificationModel


class NotificationService:
    """Service for managing system alerts and investigation notifications."""

    @staticmethod
    def sync_notifications_from_investigations(db: Session) -> None:
        """Lightweight reconciliation that ensures real notifications exist for all investigations."""
        try:
            investigations = (
                db.query(InvestigationModel)
                .filter(InvestigationModel.is_deleted.is_(False))
                .order_by(InvestigationModel.created_at.desc())
                .limit(50)
                .all()
            )

            for inv in investigations:
                inv_id = inv.investigation_id
                title = inv.title or f"Incident {inv_id}"

                # 1. Created Notification
                create_key = f"{inv_id}:CREATED"
                existing_create = (
                    db.query(NotificationModel.id)
                    .filter(NotificationModel.event_key == create_key)
                    .first()
                )
                if not existing_create:
                    notif = NotificationModel(
                        event_key=create_key,
                        notification_type="NEW_INVESTIGATION",
                        title="New Investigation",
                        message=f"{title} ({inv_id})",
                        investigation_id=inv_id,
                        status=inv.status,
                        link_path=f"/investigations/{inv_id}",
                        is_read=False,
                        created_at=inv.created_at or datetime.now(timezone.utc),
                    )
                    db.add(notif)

                # 2. Status-specific Notification
                status_lower = (inv.status or "").lower()
                if status_lower == "completed":
                    comp_key = f"{inv_id}:COMPLETED"
                    existing_comp = (
                        db.query(NotificationModel.id)
                        .filter(NotificationModel.event_key == comp_key)
                        .first()
                    )
                    if not existing_comp:
                        notif = NotificationModel(
                            event_key=comp_key,
                            notification_type="INVESTIGATION_COMPLETED",
                            title="Investigation Completed",
                            message=f"{title} — Forensic report ready",
                            investigation_id=inv_id,
                            status="Completed",
                            link_path=f"/reports/{inv_id}",
                            is_read=False,
                            created_at=inv.updated_at or datetime.now(timezone.utc),
                        )
                        db.add(notif)
                elif status_lower == "failed":
                    fail_key = f"{inv_id}:FAILED"
                    existing_fail = (
                        db.query(NotificationModel.id)
                        .filter(NotificationModel.event_key == fail_key)
                        .first()
                    )
                    if not existing_fail:
                        notif = NotificationModel(
                            event_key=fail_key,
                            notification_type="INVESTIGATION_FAILED",
                            title="Investigation Failed",
                            message=f"{title} — Pipeline execution failed",
                            investigation_id=inv_id,
                            status="Failed",
                            link_path=f"/investigations/{inv_id}",
                            is_read=False,
                            created_at=inv.updated_at or datetime.now(timezone.utc),
                        )
                        db.add(notif)
                elif status_lower == "blocked":
                    block_key = f"{inv_id}:BLOCKED"
                    existing_block = (
                        db.query(NotificationModel.id)
                        .filter(NotificationModel.event_key == block_key)
                        .first()
                    )
                    if not existing_block:
                        notif = NotificationModel(
                            event_key=block_key,
                            notification_type="INVESTIGATION_BLOCKED",
                            title="Pipeline Blocked",
                            message=f"{title} — Ocean/AIS data unavailable",
                            investigation_id=inv_id,
                            status="Blocked",
                            link_path=f"/investigations/{inv_id}",
                            is_read=False,
                            created_at=inv.updated_at or datetime.now(timezone.utc),
                        )
                        db.add(notif)

            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error syncing notifications from investigations: {e}")

    @staticmethod
    def create_notification(
        db: Session,
        notification_type: str,
        title: str,
        message: str,
        investigation_id: Optional[str] = None,
        status: Optional[str] = None,
        link_path: Optional[str] = None,
        event_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[NotificationModel]:
        """Create an event notification with idempotency support."""
        try:
            if not event_key:
                now_ts = int(datetime.now(timezone.utc).timestamp())
                event_key = f"{investigation_id or 'sys'}:{notification_type}:{now_ts}"

            existing = (
                db.query(NotificationModel)
                .filter(NotificationModel.event_key == event_key)
                .first()
            )
            if existing:
                return existing

            notif = NotificationModel(
                event_key=event_key,
                notification_type=notification_type,
                title=title,
                message=message,
                investigation_id=investigation_id,
                status=status,
                link_path=link_path or (f"/investigations/{investigation_id}" if investigation_id else "/dashboard"),
                is_read=False,
                metadata_json=metadata or {},
                created_at=datetime.now(timezone.utc),
            )
            db.add(notif)
            db.commit()
            db.refresh(notif)
            logger.info(f"Created notification [{notification_type}] for investigation {investigation_id}")
            return notif
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create notification: {e}")
            return None

    @staticmethod
    def list_notifications(
        db: Session,
        limit: int = 50,
        unread_only: bool = False,
    ) -> Dict[str, Any]:
        """Retrieve recent notifications along with current unread count."""
        try:
            NotificationService.sync_notifications_from_investigations(db)

            q = db.query(NotificationModel)
            if unread_only:
                q = q.filter(NotificationModel.is_read.is_(False))

            items = q.order_by(desc(NotificationModel.created_at)).limit(limit).all()
            unread_count = (
                db.query(func.count(NotificationModel.id))
                .filter(NotificationModel.is_read.is_(False))
                .scalar()
                or 0
            )

            serialized_items = []
            for item in items:
                serialized_items.append({
                    "id": item.id,
                    "event_key": item.event_key,
                    "notification_type": item.notification_type,
                    "title": item.title,
                    "message": item.message,
                    "investigation_id": item.investigation_id,
                    "status": item.status,
                    "link_path": item.link_path,
                    "is_read": item.is_read,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                })

            return {
                "items": serialized_items,
                "unread_count": unread_count,
            }
        except Exception as e:
            logger.error(f"Failed to list notifications: {e}")
            return {"items": [], "unread_count": 0}

    @staticmethod
    def mark_as_read(db: Session, notification_id: int) -> bool:
        """Mark an individual notification as read."""
        try:
            notif = db.query(NotificationModel).filter(NotificationModel.id == notification_id).first()
            if notif:
                notif.is_read = True
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to mark notification {notification_id} as read: {e}")
            return False

    @staticmethod
    def mark_all_as_read(db: Session) -> int:
        """Mark all unread notifications as read."""
        try:
            updated = (
                db.query(NotificationModel)
                .filter(NotificationModel.is_read.is_(False))
                .update({"is_read": True}, synchronize_session=False)
            )
            db.commit()
            return updated
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to mark all notifications as read: {e}")
            return 0

    @staticmethod
    def get_unread_count(db: Session) -> int:
        """Get the count of unread notifications."""
        try:
            return (
                db.query(func.count(NotificationModel.id))
                .filter(NotificationModel.is_read.is_(False))
                .scalar()
                or 0
            )
        except Exception as e:
            logger.error(f"Failed to count unread notifications: {e}")
            return 0
