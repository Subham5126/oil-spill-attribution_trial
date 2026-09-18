"""User model for OILTRACE authentication and RBAC.

This is a separate model from UserProfileModel (display profile).
The User model is the authoritative source for authentication
credentials and role-based access control.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import synonym

from backend.models.base import Base, TimestampMixin

# Valid roles — ordered from most to least privileged
ROLES = ("TECH_ADMIN", "ADMIN", "ANALYST", "OPERATOR", "VIEWER")

# Roles that a TECH_ADMIN is permitted to provision by default
PROVISIONABLE_ROLES = ("ADMIN", "ANALYST", "OPERATOR", "VIEWER")

import enum

# Valid account statuses
class AccountStatus(str, enum.Enum):
    PENDING_ACTIVATION = "PENDING_ACTIVATION"
    ACTIVE = "ACTIVE"
    DEACTIVATED = "DEACTIVATED"

STATUS_PENDING_ACTIVATION = AccountStatus.PENDING_ACTIVATION.value
STATUS_ACTIVE = AccountStatus.ACTIVE.value
STATUS_DEACTIVATED = AccountStatus.DEACTIVATED.value
ACCOUNT_STATUSES = (STATUS_PENDING_ACTIVATION, STATUS_ACTIVE, STATUS_DEACTIVATED)


class User(Base, TimestampMixin):
    """Authenticated organization user.

    Columns
    -------
    employee_id
        Organization-issued identifier (e.g. ``EMP-0042``, ``TECH-001``). Unique.
    official_email
        Official organization email. Unique.
    email
        Synonym for official_email for backward compatibility.
    full_name
        Full employee name.
    department
        Department or operating division.
    role
        One of TECH_ADMIN / ADMIN / ANALYST / OPERATOR / VIEWER.
    is_active
        Whether the user is allowed to authenticate. False if deactivated or pending.
    account_status
        One of PENDING_ACTIVATION / ACTIVE / DEACTIVATED.
    password_hash
        bcrypt hash of the password. Nullable while account is pending activation.
    activation_token_hash
        SHA-256 hash of single-use account activation token.
    activation_token_expires_at
        Timestamp when the activation token expires.
    activation_used_at
        Timestamp when the activation token was consumed.
    reset_token_hash
        SHA-256 hash of single-use password reset token.
    reset_token_expires_at
        Timestamp when password reset token expires.
    last_invitation_sent_at
        Timestamp when the last activation email was dispatched.
    must_change_password
        True if employee must update password on next login.
    failed_login_attempts
        Incremented on each failed login. Reset on success.
    locked_until
        Brute-force lockout expiry. None if not locked.
    last_login_at
        Timestamp of last successful login.
    last_login_ip
        IP address from last login.
    """

    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    employee_id: str = Column(String(32), unique=True, nullable=False, index=True)
    official_email: str = Column(String(255), unique=True, nullable=False, index=True)
    full_name: str = Column(String(255), nullable=False)
    role: str = Column(String(32), nullable=False, default="VIEWER")
    department: Optional[str] = Column(String(128), nullable=True)
    password_hash: Optional[str] = Column(String(255), nullable=True)
    is_active: bool = Column(Boolean, nullable=False, default=False)
    account_status: str = Column(String(32), nullable=False, default=STATUS_PENDING_ACTIVATION)
    activation_token_hash: Optional[str] = Column(String(64), nullable=True, index=True)
    activation_token_expires_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    activation_used_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    reset_token_hash: Optional[str] = Column(String(64), nullable=True, index=True)
    reset_token_expires_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    last_invitation_sent_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    must_change_password: bool = Column(Boolean, nullable=False, default=False)
    failed_login_attempts: int = Column(Integer, nullable=False, default=0)
    locked_until: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    last_login_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    last_login_ip: Optional[str] = Column(String(64), nullable=True)

    # Synonym mapping: user.email <-> user.official_email
    email = synonym("official_email")

    def __repr__(self) -> str:
        return f"<User id={self.id} employee_id={self.employee_id!r} official_email={self.official_email!r} role={self.role!r} status={self.account_status!r}>"
