"""Password hashing utilities for OILTRACE.

Uses the bcrypt library directly (passlib 1.7.4 has a known incompatibility
with bcrypt >= 4.0.0 which removed the __about__ module).
"""

from __future__ import annotations

import bcrypt as _bcrypt


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*.

    bcrypt automatically generates a random salt per call.
    """
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*, False otherwise.

    bcrypt.checkpw performs a constant-time comparison to prevent timing attacks.
    """
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False
