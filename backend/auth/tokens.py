"""JWT token creation and verification for OILTRACE.

Access tokens expire in ACCESS_TOKEN_EXPIRE_MINUTES (default 30 min).
Refresh tokens expire in REFRESH_TOKEN_EXPIRE_DAYS (default 7 days).

Both tokens are HS256-signed JWTs using settings.SECRET_KEY.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from backend.core.config import settings

_ALGORITHM = "HS256"
_ACCESS_TYPE = "access"
_REFRESH_TYPE = "refresh"


class AuthError(Exception):
    """Raised when token decoding fails or token is invalid."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(data: dict[str, Any]) -> str:
    """Create a short-lived access JWT.

    Args:
        data: Payload claims to embed. ``sub`` should be the user ID as str.

    Returns:
        Encoded JWT string.
    """
    payload = dict(data)
    expire = _utc_now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload.update({"exp": expire, "iat": _utc_now(), "type": _ACCESS_TYPE})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


def create_refresh_token(data: dict[str, Any]) -> str:
    """Create a long-lived refresh JWT.

    Args:
        data: Payload claims. ``sub`` should be the user ID as str.

    Returns:
        Encoded JWT string.
    """
    payload = dict(data)
    expire = _utc_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload.update({"exp": expire, "iat": _utc_now(), "type": _REFRESH_TYPE})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


def decode_token(token: str, expected_type: str = _ACCESS_TYPE) -> dict[str, Any]:
    """Decode and validate a JWT.

    Args:
        token: Encoded JWT string.
        expected_type: ``"access"`` or ``"refresh"`` — checked against the
            ``type`` claim to prevent token substitution attacks.

    Returns:
        Decoded payload dict.

    Raises:
        AuthError: If the token is expired, malformed, or has the wrong type.
    """
    try:
        payload: dict[str, Any] = jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise AuthError(f"Invalid token: {exc}") from exc

    if payload.get("type") != expected_type:
        raise AuthError(f"Expected token type '{expected_type}', got '{payload.get('type')}'")

    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Convenience wrapper for decoding a refresh token."""
    return decode_token(token, expected_type=_REFRESH_TYPE)
