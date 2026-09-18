"""User model for OILTRACE authentication and RBAC.

This is a separate model from UserProfileModel (display profile).
The User model is the authoritative source for authentication
credentials and role-based access control.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from backend.models.base import Base, TimestampMixin

# Valid roles — ordered from most to least privileged
ROLES = ("ADMIN", "ANALYST", "OPERATOR", "VIEWER")


class User(Base, TimestampMixin):
    """Authenticated organization user.

    Columns
    -------
    employee_id
        Optional short org-issued identifier (e.g. ``EMP-0042``).
        Can be used as the login identifier in addition to ``email``.
    email
        Official organization email. Primary login identifier.
    role
        One of ADMIN / ANALYST / OPERATOR / VIEWER.
    is_active
        Set to False to deactivate without deleting (soft delete).
    failed_login_attempts
        Incremented on each failed login. Reset on success.
    locked_until
        Brute-force lockout expiry. None if not locked.
    """

    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    employee_id: Optional[str] = Column(String(32), unique=True, nullable=True, index=True)
    email: str = Column(String(255), unique=True, nullable=False, index=True)
    full_name: str = Column(String(255), nullable=False)
    role: str = Column(String(32), nullable=False, default="VIEWER")
    department: Optional[str] = Column(String(128), nullable=True)
    password_hash: str = Column(String(255), nullable=False)
    is_active: bool = Column(Boolean, nullable=False, default=True)
    failed_login_attempts: int = Column(Integer, nullable=False, default=0)
    locked_until: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    last_login_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    last_login_ip: Optional[str] = Column(String(64), nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"
