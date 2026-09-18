"""Authentication API router for OILTRACE.

Endpoints
---------
POST /api/auth/login    — Authenticate and set HTTP-only cookies.
POST /api/auth/logout   — Clear auth cookies.
GET  /api/auth/me       — Return current user profile.
POST /api/auth/refresh  — Refresh the access token using the refresh cookie.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.auth.hashing import verify_password
from backend.auth.tokens import (
    AuthError,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from backend.core.config import settings
from backend.core.database import get_db
from backend.models.audit_log import log_action
from backend.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])

_ACCESS_COOKIE = "oiltrace_access_token"
_REFRESH_COOKIE = "oiltrace_refresh_token"


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ──────────────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    identifier: str  # email OR employee_id
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    employee_id: str | None
    full_name: str
    role: str
    department: str | None
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────────────────
# Cookie helpers
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
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/login")
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

    # Find user by email or employee_id (case-insensitive)
    from sqlalchemy import func, or_
    user: User | None = (
        db.query(User)
        .filter(
            or_(
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
        # Log attempt without a user_id
        log_action(db, "LOGIN_FAILED_UNKNOWN", ip_address=ip, extra={"identifier": identifier_raw})
        db.commit()
        raise _INVALID

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

    # Inactive user
    if not user.is_active:
        raise _INVALID

    # Verify password
    if not verify_password(body.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
            from datetime import timedelta
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


@router.get("/me")
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
    """Issue a new access token using the refresh cookie.

    The refresh cookie is path-scoped to ``/api/auth/refresh`` so it is only
    sent to this endpoint, not to every API request.
    """
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
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive.")

    # Issue fresh access token only
    from backend.auth.tokens import create_access_token
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
