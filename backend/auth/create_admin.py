"""Bootstrap CLI — create the initial OILTRACE TECH_ADMIN account.

Usage
-----
    Interactive:
        python -m backend.auth.create_admin

    Non-interactive (flags):
        python -m backend.auth.create_admin --employee-id "TECH-001" --email "techadmin@oiltrace.gov" --name "Technology Administrator" --password "TechAdmin#Secure2026!"

This script creates an organization administrator with role=TECH_ADMIN.
It validates password strength (min 12 chars, uppercase, lowercase, digit, symbol).
It will refuse to create another TECH_ADMIN if one already exists unless --force is passed.
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
    parser = argparse.ArgumentParser(description="Create the initial OILTRACE TECH_ADMIN user.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Create a new TECH_ADMIN even if one already exists.",
    )
    parser.add_argument("--employee-id", type=str, help="Employee ID (e.g. TECH-001).")
    parser.add_argument("--email", type=str, help="Official organization email address.")
    parser.add_argument("--name", type=str, help="Full name of administrator.")
    parser.add_argument("--department", type=str, help="Department or division.")
    parser.add_argument("--password", type=str, help="Account password (min 12 chars, mixed case, digit, symbol).")
    args = parser.parse_args()

    # Deferred imports so the module can be imported without side effects
    from backend.core.database import SessionLocal, _SessionLocal
    from backend.auth.hashing import hash_password
    from backend.auth.password_policy import validate_password
    from backend.models.user import User

    session_factory = SessionLocal or _SessionLocal
    if session_factory is None:
        print("ERROR: Database session factory is not available. Check DATABASE_URL.", file=sys.stderr)
        sys.exit(1)

    db = session_factory()
    try:
        # Check for existing TECH_ADMIN
        existing_tech_admin = db.query(User).filter(User.role == "TECH_ADMIN", User.is_active == True).first()
        if existing_tech_admin and not args.force:
            print(
                f"A TECH_ADMIN user already exists: {existing_tech_admin.official_email} ({existing_tech_admin.employee_id})\n"
                "Use --force to create an additional TECH_ADMIN."
            )
            sys.exit(0)

        # ── Employee ID ───────────────────────────────────────────────────────
        if args.employee_id:
            employee_id = args.employee_id.strip()
        else:
            print("=" * 60)
            print("OILTRACE — Bootstrap Initial TECH_ADMIN Account")
            print("=" * 60)
            employee_id = input("Employee ID (e.g. TECH-001): ").strip()

        if not employee_id:
            print("ERROR: Employee ID cannot be empty.", file=sys.stderr)
            sys.exit(1)

        if db.query(User).filter(User.employee_id == employee_id).first():
            print(f"ERROR: Employee ID '{employee_id}' is already in use.", file=sys.stderr)
            sys.exit(1)

        # ── Email ─────────────────────────────────────────────────────────────
        if args.email:
            email = args.email.strip().lower()
        else:
            email = input("Official organization email: ").strip().lower()

        if not email or "@" not in email:
            print("ERROR: Invalid email address.", file=sys.stderr)
            sys.exit(1)

        if db.query(User).filter((User.official_email == email) | (User.email == email)).first():
            print(f"ERROR: A user with email '{email}' already exists.", file=sys.stderr)
            sys.exit(1)

        # ── Full Name ─────────────────────────────────────────────────────────
        if args.name:
            full_name = args.name.strip()
        else:
            full_name = input("Full name: ").strip()

        if not full_name:
            print("ERROR: Full name cannot be empty.", file=sys.stderr)
            sys.exit(1)

        # ── Department ────────────────────────────────────────────────────────
        if args.department is not None:
            department = args.department.strip() or None
        else:
            department = input("Department (optional, press Enter to skip): ").strip() or "IT & Systems Directorate"

        # ── Password ──────────────────────────────────────────────────────────
        if args.password:
            password = args.password
            try:
                validate_password(password, email)
            except ValueError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                sys.exit(1)
        else:
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

        # Create the TECH_ADMIN user
        user = User(
            employee_id=employee_id,
            official_email=email,
            full_name=full_name,
            role="TECH_ADMIN",
            department=department,
            password_hash=hash_password(password),
            is_active=True,
            account_status="ACTIVE",
            must_change_password=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        print("\n" + "=" * 60)
        print("TECH_ADMIN created successfully.")
        print(f"  ID:          {user.id}")
        print(f"  Employee ID: {user.employee_id}")
        print(f"  Email:       {user.official_email}")
        print(f"  Name:        {user.full_name}")
        print(f"  Role:        {user.role}")
        print(f"  Department:  {user.department}")
        print("=" * 60)
        print("\nYou can now sign in at the OILTRACE login page.")

    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
