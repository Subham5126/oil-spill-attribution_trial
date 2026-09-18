"""Password policy enforcement for OILTRACE.

Validates that passwords meet the required strength criteria before
being stored or accepted as a valid credential change.
"""

from __future__ import annotations

import re


_MIN_LENGTH = 12
_UPPER = re.compile(r"[A-Z]")
_LOWER = re.compile(r"[a-z]")
_DIGIT = re.compile(r"\d")
_SYMBOL = re.compile(r"[!@#$%^&*()\-_=+\[\]{}|;:',.<>?/`~\"\\]")


def validate_password(password: str, user_identifier: str = "") -> None:
    """Validate that *password* meets the OILTRACE password policy.

    Args:
        password: The plaintext password to validate.
        user_identifier: The user's email or employee ID (used to prevent
            passwords that contain the identifier).

    Raises:
        ValueError: If the password does not meet policy requirements.
    """
    errors: list[str] = []

    if len(password) < _MIN_LENGTH:
        errors.append(f"Password must be at least {_MIN_LENGTH} characters long.")

    if not _UPPER.search(password):
        errors.append("Password must contain at least one uppercase letter.")

    if not _LOWER.search(password):
        errors.append("Password must contain at least one lowercase letter.")

    if not _DIGIT.search(password):
        errors.append("Password must contain at least one digit.")

    if not _SYMBOL.search(password):
        errors.append("Password must contain at least one special character.")

    # Prevent trivially guessable passwords based on the user identifier
    if user_identifier:
        # Check the local part of an email address
        identifier_lower = user_identifier.lower().split("@")[0]
        if identifier_lower and len(identifier_lower) >= 4:
            if identifier_lower in password.lower():
                errors.append("Password must not contain your email address or employee ID.")

    if errors:
        raise ValueError(" ".join(errors))
