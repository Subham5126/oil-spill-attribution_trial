"""Audit log model for OILTRACE.

Records security-relevant events such as logins, logouts, user creation,
role changes, and access to sensitive endpoints.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import Session

from backend.core.database import Base


class AuditLog(Base):
    """Security and access audit log entry."""

    __tablename__ = "audit_logs"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: Optional[int] = Column(Integer, nullable=True, index=True)
    action: str = Column(String(64), nullable=False)
    resource_type: Optional[str] = Column(String(64), nullable=True)
    resource_id: Optional[str] = Column(String(64), nullable=True)
    ip_address: Optional[str] = Column(String(64), nullable=True)
    user_agent: Optional[str] = Column(String(512), nullable=True)
    extra: Optional[str] = Column(Text, nullable=True)  # JSON blob
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} action={self.action!r} user_id={self.user_id}>"


def log_action(
    db: Session,
    action: str,
    user_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """Append an audit entry and flush (does NOT commit — caller owns the transaction).

    Args:
        db: Active SQLAlchemy session.
        action: Short action name, e.g. ``"LOGIN_SUCCESS"``, ``"USER_CREATED"``.
        user_id: ID of the acting user, or None for unauthenticated events.
        resource_type: e.g. ``"user"``, ``"investigation"``.
        resource_id: String ID of the affected resource.
        ip_address: Client IP from request.
        user_agent: Client user-agent header.
        extra: Arbitrary extra context serialized to JSON.
    """
    if db is None:
        return
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        user_agent=user_agent,
        extra=json.dumps(extra) if extra else None,
    )
    db.add(entry)
    db.flush()
