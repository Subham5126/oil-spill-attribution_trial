"""Notifications API Router."""

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=Dict[str, Any])
def list_notifications(
    limit: int = Query(default=50, ge=1, le=100),
    unread_only: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Retrieve system alerts and investigation lifecycle notifications with unread count."""
    return NotificationService.list_notifications(db, limit=limit, unread_only=unread_only)


@router.patch("/{notification_id}/read")
def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
):
    """Mark a specific notification as read."""
    success = NotificationService.mark_as_read(db, notification_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return {"status": "SUCCESS", "id": notification_id, "is_read": True}


@router.post("/mark-all-read")
def mark_all_notifications_as_read(
    db: Session = Depends(get_db),
):
    """Mark all unread notifications as read."""
    count = NotificationService.mark_all_as_read(db)
    return {"status": "SUCCESS", "marked_count": count}


@router.get("/unread-count")
def get_unread_notification_count(
    db: Session = Depends(get_db),
):
    """Retrieve current unread notification count for badge rendering."""
    count = NotificationService.get_unread_count(db)
    return {"unread_count": count}
