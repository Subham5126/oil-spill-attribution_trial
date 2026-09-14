"""Notification ORM Model.

Persists real investigation lifecycle alerts, pipeline status transitions,
and forensic readiness events with idempotency and read/unread status.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, JSON, String, Text
from backend.core.database import Base
from backend.models.base import TimestampMixin


class NotificationModel(Base, TimestampMixin):
    """Notification record tracking an operational alert or event."""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_key = Column(String(128), unique=True, nullable=False, index=True)
    notification_type = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    investigation_id = Column(String(64), nullable=True, index=True)
    status = Column(String(32), nullable=True)
    link_path = Column(String(255), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    metadata_json = Column(JSON, default=dict)

    __table_args__ = (
        Index("idx_notifications_read_created", "is_read", "created_at"),
        Index("idx_notifications_inv_type", "investigation_id", "notification_type"),
    )
