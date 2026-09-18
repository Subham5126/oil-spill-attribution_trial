"""Authentication and Employee Provisioning API router for OILTRACE.

Endpoints
---------
Authentication:
POST /api/auth/login            — Authenticate with email/employee-ID + password.
POST /api/auth/logout           — Clear auth cookies.
GET  /api/auth/me               — Return current user profile.
POST /api/auth/refresh          — Refresh access token using refresh cookie.
POST /api/auth/change-password  — Self-service password change for authenticated users.

Activation & Password Reset (Zero Admin Passwords):
GET  /api/auth/verify-activation-token — Verify token and get employee details (read-only).
POST /api/auth/activate                — Activate account and set personal password.
GET  /api/auth/verify-reset-token      — Verify password reset token.
POST /api/auth/reset-password          — Complete password reset using token.

TECH_ADMIN Employee Provisioning & Management:
GET    /api/auth/users                       — List all employees (paginated).
POST   /api/auth/users                       — Provision a new employee (sends email invitation).
GET    /api/auth/users/{user_id}             — Retrieve employee details.
PATCH  /api/auth/users/{user_id}             — Update employee details (role, department, name).
POST   /api/auth/users/{user_id}/activate    — Re-activate employee account.
POST   /api/auth/users/{user_id}/deactivate  — Soft-deactivate employee account.
POST   /api/auth/users/{user_id}/resend-invitation — Invalidate previous token and resend invitation email.
POST   /api/auth/users/{user_id}/reset-password    — Trigger password reset email to employee.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user, require_role, require_tech_admin
from backend.auth.hashing import hash_password, verify_password
from backend.auth.password_policy import validate_password
from backend.auth.tokens import (
    AuthError,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from backend.core.config import settings
from backend.core.database import get_db
from backend.models.audit_log import log_action
from backend.models.user import (
    PROVISIONABLE_ROLES,
    ROLES,
    STATUS_ACTIVE,
    STATUS_DEACTIVATED,
    STATUS_PENDING_ACTIVATION,
    User,
)
from backend.services.email_service import (
    email_service,
    send_account_activation_email,
    send_activation_email,
    send_password_reset_email,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

_ACCESS_COOKIE = "oiltrace_access_token"
_REFRESH_COOKIE = "oiltrace_refresh_token"


def _hash_token(token: str) -> str:
    """Hash raw token with SHA-256 for secure database lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ──────────────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    identifier: str  # email OR employee_id
    password: str


class UserOut(BaseModel):
    id: int
    employee_id: str
    official_email: str
    email: str
    full_name: str
    role: str
    department: Optional[str] = None
    account_status: str = STATUS_PENDING_ACTIVATION
    is_active: bool = False
    must_change_password: bool = False
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CreateEmployeeRequest(BaseModel):
    employee_id: str
    official_email: str
    full_name: str
    department: Optional[str] = None
    role: str = "VIEWER"

    @field_validator("employee_id")
    @classmethod
    def validate_emp_id(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) < 2:
            raise ValueError("Employee ID must be at least 2 characters long.")
        return v

    @field_validator("official_email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid official organization email address.")
        return v

    @field_validator("role")
    @classmethod
    def validate_role_field(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ROLES:
            raise ValueError(f"Role must be one of: {', '.join(ROLES)}")
        return v


class UpdateEmployeeRequest(BaseModel):
    full_name: Optional[str] = None
    department: Optional[str] = None
    role: Optional[str] = None

    @field_validator("role")
    @classmethod
    def validate_role_field(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip().upper()
            if v not in ROLES:
                raise ValueError(f"Role must be one of: {', '.join(ROLES)}")
        return v


class ActivateAccountRequest(BaseModel):
    token: str
    new_password: str


class TokenVerificationResponse(BaseModel):
    employee_id: str
    official_email: str
    full_name: str
    department: Optional[str] = None
    role: str


class CompletePasswordResetRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class PaginatedUsers(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[UserOut]


# ──────────────────────────────────────────────────────────────────────────────
# Cookie & Client IP helpers
# ──────────────────────────────────────────────────────────────────────────────

def _set_auth_cookies(response: Response, user: User) -> None:
    """Write both access and refresh tokens as HTTP-only cookies."""
    payload = {"sub": str(user.id), "role": user.role}
    access_token = create_access_token(payload)
    refresh_token = create_refresh_token(payload)

    cookie_kwargs = {
        "httponly": True,
        "samesite": settings.COOKIE_SAMESITE,
        "secure": settings.COOKIE_SECURE,
    }

    response.set_cookie(
        key=_ACCESS_COOKIE,
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **cookie_kwargs,
    )
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/auth/refresh",
        **cookie_kwargs,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(_ACCESS_COOKIE)
    response.delete_cookie(_REFRESH_COOKIE, path="/api/auth/refresh")


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# Authentication Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=UserOut)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> UserOut:
    """Authenticate with email/employee-ID + password.

    Sets HTTP-only access and refresh token cookies on success.
    Returns the authenticated user's profile (no token values in body).
    """
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable.")

    identifier_raw = body.identifier.strip()
    identifier_lower = identifier_raw.lower()

    # Find user by official_email, email synonym, or employee_id (case-insensitive)
    user: User | None = (
        db.query(User)
        .filter(
            or_(
                func.lower(User.official_email) == identifier_lower,
                func.lower(User.email) == identifier_lower,
                func.lower(User.employee_id) == identifier_lower,
                User.employee_id == identifier_raw,
            )
        )
        .first()
    )

    ip = _get_client_ip(request)
    ua = request.headers.get("user-agent", "")[:512]
    now = datetime.now(timezone.utc)

    # Generic failure message — never reveal whether email/ID exists
    _INVALID = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials. Please check your identifier and password.",
    )

    if user is None:
        log_action(db, "LOGIN_FAILED_UNKNOWN", ip_address=ip, extra={"identifier": identifier_raw})
        db.commit()
        raise _INVALID

    # Check pending activation status
    if user.account_status == STATUS_PENDING_ACTIVATION:
        log_action(db, "LOGIN_BLOCKED_PENDING", user_id=user.id, ip_address=ip)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account pending activation. Please check your email to set your password.",
        )

    # Inactive / Deactivated check
    if not user.is_active or user.account_status == STATUS_DEACTIVATED:
        log_action(db, "LOGIN_FAILED_INACTIVE", user_id=user.id, ip_address=ip)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account inactive. Contact your Technology Administrator.",
        )

    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account has no password set. Please use your activation email link.",
        )

    # Brute-force lockout check
    if user.locked_until:
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            remaining_secs = int((locked_until - now).total_seconds())
            log_action(db, "LOGIN_BLOCKED_LOCKOUT", user_id=user.id, ip_address=ip)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account locked. Try again in {remaining_secs // 60} min {remaining_secs % 60} sec.",
            )

    # Verify password
    if not verify_password(body.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            log_action(
                db,
                "LOGIN_LOCKOUT_TRIGGERED",
                user_id=user.id,
                ip_address=ip,
                extra={"attempts": user.failed_login_attempts},
            )
        else:
            log_action(
                db,
                "LOGIN_FAILED_BAD_PASSWORD",
                user_id=user.id,
                ip_address=ip,
                extra={"attempts": user.failed_login_attempts},
            )
        db.add(user)
        db.commit()
        raise _INVALID

    # ── Success ───────────────────────────────────────────────────────────────
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    user.last_login_ip = ip
    db.add(user)
    log_action(db, "LOGIN_SUCCESS", user_id=user.id, ip_address=ip, user_agent=ua)
    db.commit()

    _set_auth_cookies(response, user)
    return UserOut.model_validate(user)


@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Clear auth cookies and record the logout event."""
    ip = _get_client_ip(request)
    if db is not None:
        log_action(db, "LOGOUT", user_id=current_user.id, ip_address=ip)
        db.commit()
    _clear_auth_cookies(response)
    return {"detail": "Logged out successfully."}


@router.get("/me", response_model=UserOut)
async def me(
    current_user: User = Depends(get_current_user),
) -> UserOut:
    """Return the profile of the currently authenticated user."""
    return UserOut.model_validate(current_user)


@router.post("/refresh")
async def refresh_token(
    response: Response,
    oiltrace_refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Issue a new access token using the refresh cookie."""
    if not oiltrace_refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing.")

    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable.")

    try:
        payload = decode_refresh_token(oiltrace_refresh_token)
    except AuthError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")

    user_id_str = payload.get("sub")
    try:
        user_id = int(user_id_str)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid refresh token payload.")

    user: User | None = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active or user.account_status != STATUS_ACTIVE:
        raise HTTPException(status_code=401, detail="User not found or inactive.")

    new_access = create_access_token({"sub": str(user.id), "role": user.role})
    response.set_cookie(
        key=_ACCESS_COOKIE,
        value=new_access,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
        secure=settings.COOKIE_SECURE,
    )
    return {"detail": "Access token refreshed."}


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Self-service password change for currently authenticated employee."""
    if not current_user.password_hash or not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    try:
        validate_password(body.new_password, current_user.official_email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    current_user.password_hash = hash_password(body.new_password)
    current_user.must_change_password = False
    current_user.failed_login_attempts = 0
    current_user.locked_until = None
    db.add(current_user)
    log_action(
        db,
        "PASSWORD_CHANGED",
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(current_user.id),
        ip_address=_get_client_ip(request),
    )
    db.commit()
    return {"detail": "Password changed successfully."}


# ──────────────────────────────────────────────────────────────────────────────
# Public Activation & Password Reset Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/verify-activation-token", response_model=TokenVerificationResponse)
async def verify_activation_token(
    token: str = Query(..., min_length=16),
    db: Session = Depends(get_db),
) -> TokenVerificationResponse:
    """Verify single-use activation token and return employee identity for read-only display."""
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable.")

    token_hash = _hash_token(token)
    user = db.query(User).filter(User.activation_token_hash == token_hash).first()
    now = datetime.now(timezone.utc)

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired activation link.")

    if user.account_status != STATUS_PENDING_ACTIVATION or user.activation_used_at is not None:
        raise HTTPException(status_code=400, detail="This activation link has already been used.")

    if user.activation_token_expires_at:
        exp = user.activation_token_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            raise HTTPException(
                status_code=400,
                detail="Activation link has expired. Please contact your Technology Administrator.",
            )

    return TokenVerificationResponse(
        employee_id=user.employee_id,
        official_email=user.official_email,
        full_name=user.full_name,
        department=user.department,
        role=user.role,
    )


@router.post("/activate")
async def activate_account(
    body: ActivateAccountRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Activate account and set personal password via one-time token."""
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable.")

    token_hash = _hash_token(body.token)
    user = db.query(User).filter(User.activation_token_hash == token_hash).first()
    now = datetime.now(timezone.utc)

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired activation link.")

    if user.account_status != STATUS_PENDING_ACTIVATION or user.activation_used_at is not None:
        raise HTTPException(status_code=400, detail="This activation link has already been used.")

    if user.activation_token_expires_at:
        exp = user.activation_token_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            raise HTTPException(
                status_code=400,
                detail="Activation link has expired. Please contact your Technology Administrator.",
            )

    try:
        validate_password(body.new_password, user.official_email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    user.password_hash = hash_password(body.new_password)
    user.account_status = STATUS_ACTIVE
    user.is_active = True
    user.activation_used_at = now
    user.activation_token_hash = None
    user.activation_token_expires_at = None
    user.must_change_password = False
    user.failed_login_attempts = 0
    user.locked_until = None
    db.add(user)
    log_action(
        db,
        "USER_ACTIVATED",
        user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=_get_client_ip(request),
    )
    db.commit()
    return {"detail": "Account activated successfully. You may now sign in with your password."}


@router.get("/verify-reset-token", response_model=TokenVerificationResponse)
async def verify_reset_token(
    token: str = Query(..., min_length=16),
    db: Session = Depends(get_db),
) -> TokenVerificationResponse:
    """Verify single-use password reset token."""
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable.")

    token_hash = _hash_token(token)
    user = db.query(User).filter(User.reset_token_hash == token_hash).first()
    now = datetime.now(timezone.utc)

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset link.")

    if user.reset_token_expires_at:
        exp = user.reset_token_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            raise HTTPException(
                status_code=400,
                detail="Password reset link has expired. Please request a new reset from your Technology Administrator.",
            )

    return TokenVerificationResponse(
        employee_id=user.employee_id,
        official_email=user.official_email,
        full_name=user.full_name,
        department=user.department,
        role=user.role,
    )


@router.post("/reset-password")
async def complete_password_reset(
    body: CompletePasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Complete password reset using single-use reset token."""
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable.")

    token_hash = _hash_token(body.token)
    user = db.query(User).filter(User.reset_token_hash == token_hash).first()
    now = datetime.now(timezone.utc)

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset link.")

    if user.reset_token_expires_at:
        exp = user.reset_token_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            raise HTTPException(
                status_code=400,
                detail="Password reset link has expired. Please request a new reset.",
            )

    try:
        validate_password(body.new_password, user.official_email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    user.password_hash = hash_password(body.new_password)
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    user.must_change_password = False
    user.failed_login_attempts = 0
    user.locked_until = None
    db.add(user)
    log_action(
        db,
        "PASSWORD_RESET_COMPLETED",
        user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=_get_client_ip(request),
    )
    db.commit()
    return {"detail": "Your password has been successfully reset. You may now sign in."}


# ──────────────────────────────────────────────────────────────────────────────
# TECH_ADMIN Employee Provisioning & Management Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=PaginatedUsers)
async def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_admin: User = Depends(require_tech_admin),
    db: Session = Depends(get_db),
) -> PaginatedUsers:
    """List all employees with pagination. TECH_ADMIN only."""
    q = db.query(User).order_by(User.id)
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedUsers(total=total, page=page, page_size=page_size, items=items)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_employee(
    body: CreateEmployeeRequest,
    request: Request,
    current_admin: User = Depends(require_tech_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    """Provision a new employee account and send invitation email. TECH_ADMIN only.

    NO password fields are accepted. The employee will set their own password
    through a cryptographically secure one-time activation link sent to their email.
    """
    allow_tech_admin_creation = os.getenv("ALLOW_TECH_ADMIN_CREATION", "false").lower() in ("true", "1")
    if body.role == "TECH_ADMIN" and not allow_tech_admin_creation:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="TECH_ADMIN role cannot be assigned through employee provisioning. Use bootstrap CLI.",
        )

    # Check email uniqueness
    email_clean = body.official_email.strip().lower()
    existing_email = db.query(User).filter(
        or_(func.lower(User.official_email) == email_clean, func.lower(User.email) == email_clean)
    ).first()
    if existing_email:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this official email already exists.")

    # Check employee_id uniqueness
    emp_id_clean = body.employee_id.strip()
    existing_emp = db.query(User).filter(
        func.lower(User.employee_id) == emp_id_clean.lower()
    ).first()
    if existing_emp:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this employee ID already exists.")

    # Generate cryptographically secure single-use activation token
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=settings.INVITATION_EXPIRE_HOURS)

    user = User(
        employee_id=emp_id_clean,
        official_email=email_clean,
        full_name=body.full_name.strip(),
        role=body.role,
        department=body.department.strip() if body.department else None,
        password_hash=None,  # No password until employee activates
        is_active=False,     # Inactive until activation
        account_status=STATUS_PENDING_ACTIVATION,
        activation_token_hash=token_hash,
        activation_token_expires_at=expires_at,
        last_invitation_sent_at=now,
    )
    db.add(user)
    db.flush()

    # Dispatch activation invitation email
    send_account_activation_email(
        to_email=user.official_email,
        full_name=user.full_name,
        employee_id=user.employee_id,
        department=user.department,
        role=user.role,
        raw_token=raw_token,
    )

    log_action(
        db,
        "USER_CREATED",
        user_id=current_admin.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=_get_client_ip(request),
        extra={"employee_id": emp_id_clean, "official_email": email_clean, "role": body.role},
    )
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/users/{user_id}", response_model=UserOut)
async def get_employee(
    user_id: int,
    current_admin: User = Depends(require_tech_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    """Get employee details by ID. TECH_ADMIN only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Employee not found.")
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_employee(
    user_id: int,
    body: UpdateEmployeeRequest,
    request: Request,
    current_admin: User = Depends(require_tech_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    """Update employee fields (full_name, department, role). TECH_ADMIN only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Employee not found.")

    allow_tech_admin_creation = os.getenv("ALLOW_TECH_ADMIN_CREATION", "false").lower() in ("true", "1")
    if body.role == "TECH_ADMIN" and not allow_tech_admin_creation:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Elevating to TECH_ADMIN role is restricted by security policy.",
        )

    changes: dict = {}
    if body.full_name is not None:
        changes["full_name"] = body.full_name
        user.full_name = body.full_name.strip()
    if body.department is not None:
        changes["department"] = body.department.strip() if body.department else None
        user.department = changes["department"]
    if body.role is not None and body.role != user.role:
        changes["old_role"] = user.role
        changes["new_role"] = body.role
        user.role = body.role
        log_action(
            db,
            "ROLE_CHANGED",
            user_id=current_admin.id,
            resource_type="user",
            resource_id=str(user.id),
            ip_address=_get_client_ip(request),
            extra=changes,
        )

    db.add(user)
    log_action(
        db,
        "USER_UPDATED",
        user_id=current_admin.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=_get_client_ip(request),
        extra=changes,
    )
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/activate")
async def activate_employee_admin(
    user_id: int,
    request: Request,
    current_admin: User = Depends(require_tech_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Re-activate an employee account. TECH_ADMIN only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Employee not found.")

    if not user.password_hash:
        raise HTTPException(
            status_code=400,
            detail="Cannot activate an employee who has not completed initial password setup. Use Resend Invitation.",
        )

    user.account_status = STATUS_ACTIVE
    user.is_active = True
    user.failed_login_attempts = 0
    user.locked_until = None
    db.add(user)
    log_action(
        db,
        "USER_ACTIVATED",
        user_id=current_admin.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=_get_client_ip(request),
    )
    db.commit()
    return {"detail": f"Employee {user.employee_id} activated."}


@router.post("/users/{user_id}/deactivate")
async def deactivate_employee_admin(
    user_id: int,
    request: Request,
    current_admin: User = Depends(require_tech_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Soft-deactivate an employee account. TECH_ADMIN only."""
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Employee not found.")

    user.account_status = STATUS_DEACTIVATED
    user.is_active = False
    db.add(user)
    log_action(
        db,
        "USER_DEACTIVATED",
        user_id=current_admin.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=_get_client_ip(request),
    )
    db.commit()
    return {"detail": f"Employee {user.employee_id} deactivated."}


@router.post("/users/{user_id}/resend-invitation")
async def resend_invitation(
    user_id: int,
    request: Request,
    current_admin: User = Depends(require_tech_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Resend account activation email with a fresh single-use token. TECH_ADMIN only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Employee not found.")

    if user.account_status != STATUS_PENDING_ACTIVATION:
        raise HTTPException(
            status_code=400,
            detail=f"Employee is not pending activation (current status: {user.account_status}).",
        )

    now = datetime.now(timezone.utc)
    # Rate limit: 30 seconds cooldown
    if user.last_invitation_sent_at:
        last_sent = user.last_invitation_sent_at
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        if (now - last_sent).total_seconds() < 30:
            raise HTTPException(
                status_code=429,
                detail="Please wait at least 30 seconds before resending an invitation.",
            )

    # Invalidate previous token and generate new one
    raw_token = secrets.token_urlsafe(32)
    user.activation_token_hash = _hash_token(raw_token)
    user.activation_token_expires_at = now + timedelta(hours=settings.INVITATION_EXPIRE_HOURS)
    user.last_invitation_sent_at = now
    db.add(user)

    send_account_activation_email(
        to_email=user.official_email,
        full_name=user.full_name,
        employee_id=user.employee_id,
        department=user.department,
        role=user.role,
        raw_token=raw_token,
    )

    log_action(
        db,
        "INVITATION_RESENT",
        user_id=current_admin.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=_get_client_ip(request),
    )
    db.commit()
    return {"detail": f"Activation invitation re-sent to {user.official_email}."}


@router.post("/users/{user_id}/reset-password")
async def trigger_password_reset(
    user_id: int,
    request: Request,
    current_admin: User = Depends(require_tech_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Send a secure password reset email to the employee. TECH_ADMIN only.

    TECH_ADMIN never enters or views the employee's new password.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Employee not found.")

    if user.account_status == STATUS_PENDING_ACTIVATION:
        raise HTTPException(
            status_code=400,
            detail="Employee has not yet activated their account. Use [Resend Invitation] instead.",
        )

    now = datetime.now(timezone.utc)
    raw_token = secrets.token_urlsafe(32)
    user.reset_token_hash = _hash_token(raw_token)
    user.reset_token_expires_at = now + timedelta(hours=settings.RESET_PASSWORD_EXPIRE_HOURS)
    db.add(user)

    send_password_reset_email(
        to_email=user.official_email,
        full_name=user.full_name,
        employee_id=user.employee_id,
        raw_token=raw_token,
    )

    log_action(
        db,
        "PASSWORD_RESET_REQUESTED",
        user_id=current_admin.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=_get_client_ip(request),
    )
    db.commit()
    return {"detail": f"Password reset instructions have been sent to {user.official_email}."}
