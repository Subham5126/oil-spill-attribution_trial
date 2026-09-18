"""FastAPI dependency injectors for authentication and authorization.

Usage in route handlers::

    from backend.auth.dependencies import require_auth, require_role

    @router.get("/protected")
    async def protected(current_user: User = Depends(require_auth)):
        ...

    @router.delete("/admin-only")
    async def admin_only(current_user: User = Depends(require_role("ADMIN"))):
        ...
"""

from __future__ import annotations

from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.auth.tokens import AuthError, decode_token
from backend.core.database import get_db
from backend.models.user import User

_COOKIE_NAME = "oiltrace_access_token"

_401 = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication required. Please sign in.",
)

_403 = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="You do not have permission to access this resource.",
)


def _get_user_from_token(token: str, db: Session) -> User:
    """Decode *token* and return the corresponding User from the database."""
    try:
        payload = decode_token(token)
    except AuthError:
        raise _401

    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise _401

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise _401

    user: User | None = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise _401

    return user


async def get_current_user(
    oiltrace_access_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate the current user from the HTTP-only access cookie.

    Raises HTTP 401 if the cookie is missing, the token is invalid/expired,
    or the user does not exist / is deactivated.
    """
    if not oiltrace_access_token:
        raise _401

    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable.",
        )

    return _get_user_from_token(oiltrace_access_token, db)


async def get_current_user_optional(
    oiltrace_access_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user but returns None instead of raising on missing auth."""
    if not oiltrace_access_token or db is None:
        return None
    try:
        return _get_user_from_token(oiltrace_access_token, db)
    except HTTPException:
        return None


# Convenience alias used as: Depends(require_auth)
require_auth = Depends(get_current_user)


def require_role(*roles: str):
    """Return a FastAPI dependency that restricts access to specified roles.

    Example::

        @router.get("/admin/users")
        async def list_users(
            current_user: User = Depends(require_role("ADMIN")),
        ):
            ...
    """
    allowed = set(roles)

    async def _check_role(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in allowed:
            raise _403
        return current_user

    return _check_role


# Convenience dependency for TECH_ADMIN only endpoints
require_tech_admin = require_role("TECH_ADMIN")

