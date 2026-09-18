"""Admin user management API router for OILTRACE.

All endpoints require the requesting user to have role=ADMIN.
These endpoints are the only way to create, update, and deactivate users.

Endpoints
---------
GET    /api/admin/users                       — List all users (paginated).
POST   /api/admin/users                       — Create a new user.
GET    /api/admin/users/{user_id}             — Get user detail.
PATCH  /api/admin/users/{user_id}             — Update user fields.
DELETE /api/admin/users/{user_id}             — Deactivate user (soft delete).
POST   /api/admin/users/{user_id}/reset-password — Force-reset a user's password.
GET    /api/admin/audit-log                   — Paginated security audit log.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from backend.auth.dependencies import require_role
from backend.auth.hashing import hash_password
from backend.auth.password_policy import validate_password
from backend.core.database import get_db
from backend.models.audit_log import AuditLog, log_action
from backend.models.user import ROLES, User

router = APIRouter(prefix="/admin", tags=["Admin"])

_admin_only = require_role("ADMIN")


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ──────────────────────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: int
    email: str
    employee_id: Optional[str]
    full_name: str
    role: str
    department: Optional[str]
    is_active: bool
    failed_login_attempts: int
    locked_until: Optional[datetime]
    last_login_at: Optional[datetime]
    last_login_ip: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreateUserRequest(BaseModel):
    email: str
    employee_id: Optional[str] = None
    full_name: str
    role: str = "VIEWER"
    department: Optional[str] = None
    password: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ROLES:
            raise ValueError(f"Role must be one of: {', '.join(ROLES)}")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address.")
        return v


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ROLES:
            raise ValueError(f"Role must be one of: {', '.join(ROLES)}")
        return v


class ResetPasswordRequest(BaseModel):
    new_password: str


class AuditLogOut(BaseModel):
    id: int
    user_id: Optional[int]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    extra: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedUsers(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[UserOut]


class PaginatedAuditLog(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AuditLogOut]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=PaginatedUsers)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_admin: User = _admin_only,
    db: Session = Depends(get_db),
) -> PaginatedUsers:
    """List all users with pagination. ADMIN only."""
    q = db.query(User).order_by(User.id)
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedUsers(total=total, page=page, page_size=page_size, items=items)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    current_admin: User = _admin_only,
    db: Session = Depends(get_db),
) -> UserOut:
    """Create a new organization user. ADMIN only."""
    # Check uniqueness
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists.")

    if body.employee_id:
        emp_existing = db.query(User).filter(User.employee_id == body.employee_id).first()
        if emp_existing:
            raise HTTPException(status_code=409, detail="A user with this employee ID already exists.")

    # Validate password
    try:
        validate_password(body.password, body.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    user = User(
        email=body.email,
        employee_id=body.employee_id,
        full_name=body.full_name,
        role=body.role,
        department=body.department,
        password_hash=hash_password(body.password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    log_action(
        db,
        "USER_CREATED",
        user_id=current_admin.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=_get_client_ip(request),
        extra={"email": body.email, "role": body.role},
    )
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    current_admin: User = _admin_only,
    db: Session = Depends(get_db),
) -> UserOut:
    """Get a specific user by ID. ADMIN only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UpdateUserRequest,
    request: Request,
    current_admin: User = _admin_only,
    db: Session = Depends(get_db),
) -> UserOut:
    """Update user fields (role, department, name, active status). ADMIN only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Prevent admin from deactivating themselves
    if body.is_active is False and user.id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account.")

    changes: dict = {}
    if body.full_name is not None:
        changes["full_name"] = body.full_name
        user.full_name = body.full_name
    if body.role is not None:
        changes["role"] = body.role
        user.role = body.role
    if body.department is not None:
        changes["department"] = body.department
        user.department = body.department
    if body.is_active is not None:
        changes["is_active"] = body.is_active
        user.is_active = body.is_active

    db.add(user)
    log_action(
        db,
        "USER_UPDATED",
        user_id=current_admin.id,
        resource_type="user",
        resource_id=str(user_id),
        ip_address=_get_client_ip(request),
        extra=changes,
    )
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_200_OK)
async def deactivate_user(
    user_id: int,
    request: Request,
    current_admin: User = _admin_only,
    db: Session = Depends(get_db),
) -> dict:
    """Soft-deactivate a user (sets is_active=False). ADMIN only."""
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.is_active = False
    db.add(user)
    log_action(
        db,
        "USER_DEACTIVATED",
        user_id=current_admin.id,
        resource_type="user",
        resource_id=str(user_id),
        ip_address=_get_client_ip(request),
    )
    db.commit()
    return {"detail": f"User {user_id} deactivated."}


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    user_id: int,
    body: ResetPasswordRequest,
    request: Request,
    current_admin: User = _admin_only,
    db: Session = Depends(get_db),
) -> dict:
    """Force-reset a user's password. ADMIN only.

    The new password must still meet policy requirements.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    try:
        validate_password(body.new_password, user.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    user.password_hash = hash_password(body.new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    db.add(user)
    log_action(
        db,
        "PASSWORD_RESET_BY_ADMIN",
        user_id=current_admin.id,
        resource_type="user",
        resource_id=str(user_id),
        ip_address=_get_client_ip(request),
    )
    db.commit()
    return {"detail": f"Password reset for user {user_id}."}


@router.get("/audit-log", response_model=PaginatedAuditLog)
async def get_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_admin: User = _admin_only,
    db: Session = Depends(get_db),
) -> PaginatedAuditLog:
    """Retrieve paginated security audit log. ADMIN only."""
    q = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedAuditLog(total=total, page=page, page_size=page_size, items=items)
