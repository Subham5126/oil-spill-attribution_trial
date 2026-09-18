"""Bootstrap CLI — create the first OILTRACE administrator account.

Usage
-----
    python -m backend.scripts.create_admin

This script is interactive. It prompts for email, employee ID (optional),
full name, and password (with confirmation). It will refuse to create an
admin if one already exists unless --force is passed.

Run this once after the database migration on a fresh deployment.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# Ensure the repository root is on sys.path when run as __main__
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first OILTRACE admin user.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Create a new admin even if one already exists.",
    )
    args = parser.parse_args()

    # Deferred imports so the module can be imported without side effects
    from backend.core.database import SessionLocal
    from backend.auth.hashing import hash_password
    from backend.auth.password_policy import validate_password
    from backend.models.user import User

    if SessionLocal is None:
        print("ERROR: Database session factory is not available. Check DATABASE_URL.", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        # Check for existing admins
        existing_admin = db.query(User).filter(User.role == "ADMIN", User.is_active == True).first()
        if existing_admin and not args.force:
            print(
                f"An admin user already exists: {existing_admin.email}\n"
                "Use --force to create an additional admin."
            )
            sys.exit(0)

        print("=" * 60)
        print("OILTRACE — Create Administrator Account")
        print("=" * 60)

        # Collect inputs
        email = input("Official email address: ").strip().lower()
        if not email or "@" not in email:
            print("ERROR: Invalid email address.", file=sys.stderr)
            sys.exit(1)

        # Check uniqueness
        if db.query(User).filter(User.email == email).first():
            print(f"ERROR: A user with email '{email}' already exists.", file=sys.stderr)
            sys.exit(1)

        employee_id_raw = input("Employee ID (optional, press Enter to skip): ").strip()
        employee_id = employee_id_raw if employee_id_raw else None

        if employee_id and db.query(User).filter(User.employee_id == employee_id).first():
            print(f"ERROR: Employee ID '{employee_id}' is already in use.", file=sys.stderr)
            sys.exit(1)

        full_name = input("Full name: ").strip()
        if not full_name:
            print("ERROR: Full name cannot be empty.", file=sys.stderr)
            sys.exit(1)

        department = input("Department (optional, press Enter to skip): ").strip() or None

        # Password (hidden input with confirmation)
        print("\nPassword requirements: min 12 chars, uppercase, lowercase, digit, symbol.")
        while True:
            password = getpass.getpass("Password: ")
            confirm = getpass.getpass("Confirm password: ")

            if password != confirm:
                print("ERROR: Passwords do not match. Try again.")
                continue

            try:
                validate_password(password, email)
            except ValueError as exc:
                print(f"ERROR: {exc} Try again.")
                continue

            break

        # Create the user
        user = User(
            email=email,
            employee_id=employee_id,
            full_name=full_name,
            role="ADMIN",
            department=department,
            password_hash=hash_password(password),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        print("\n" + "=" * 60)
        print(f"Admin created successfully.")
        print(f"  ID:          {user.id}")
        print(f"  Email:       {user.email}")
        if user.employee_id:
            print(f"  Employee ID: {user.employee_id}")
        print(f"  Name:        {user.full_name}")
        print(f"  Role:        {user.role}")
        print("=" * 60)
        print("\nYou can now sign in at the OILTRACE login page.")

    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
