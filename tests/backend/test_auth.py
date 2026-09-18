"""Comprehensive Authentication & Employee Account Provisioning Test Suite for OILTRACE.

Covers all 20 required automated tests from Section 21:
1. TECH_ADMIN creates employee without password
2. Employee creation sets status PENDING_ACTIVATION
3. Employee creation generates activation token hash
4. Raw token not stored in database
5. Raw token not returned in API response
6. Activation email triggered
7. Unactivated employee cannot login
8. Valid activation token allows employee to set password
9. Account status changes to ACTIVE upon activation
10. Activation token cannot be reused
11. Expired activation token is rejected
12. Invalid activation token is rejected
13. Password policy enforced during activation
14. Employee can login after activation using set password
15. Resend invitation invalidates previous token and issues new token
16. Non-TECH_ADMIN cannot create employees
17. TECH_ADMIN can trigger password reset email
18. Password reset token allows employee to set new password
19. Password reset token cannot be reused
20. Expired password reset token is rejected

Also retains RBAC, brute force lockout, and password policy unit tests.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth.hashing import hash_password
from backend.auth.password_policy import validate_password
from backend.core.config import settings
from backend.core.database import get_db
from backend.main import app
from backend.models import Base, User
from backend.models.user import AccountStatus

TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_session():
    """Provide a fresh in-memory SQLite session for each test."""
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(scope="function")
def client(db_session):
    """TestClient with DB dependency overridden to use in-memory SQLite."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


def _make_user(
    db_session,
    email: str = "analyst@coast.gov",
    password: str | None = "C0astGuard!Secure99",
    role: str = "ANALYST",
    employee_id: str = "EMP-001",
    is_active: bool = True,
    account_status: str = AccountStatus.ACTIVE.value,
) -> User:
    user = User(
        official_email=email,
        employee_id=employee_id,
        full_name="Test User",
        role=role,
        department="Marine Patrol",
        password_hash=hash_password(password) if password else None,
        is_active=is_active,
        account_status=account_status,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login(client, identifier: str, password: str):
    return client.post(
        "/api/auth/login",
        json={"identifier": identifier, "password": password},
    )


# ──────────────────────────────────────────────────────────────────────────────
# Section 21 Specification Tests (1 - 20)
# ──────────────────────────────────────────────────────────────────────────────

class TestSection21InvitationAndActivationFlow:
    # 1. TECH_ADMIN creates employee without password
    def test_01_tech_admin_creates_employee_without_password(self, client, db_session):
        _make_user(db_session, email="tech@oiltrace.gov", employee_id="TECH-001", role="TECH_ADMIN")
        _login(client, "tech@oiltrace.gov", "C0astGuard!Secure99")

        with patch("backend.api.auth.send_account_activation_email") as mock_email:
            res = client.post(
                "/api/auth/users",
                json={
                    "employee_id": "EMP-201",
                    "official_email": "ops201@oiltrace.gov",
                    "full_name": "Surveillance Operator",
                    "department": "Radar Ops",
                    "role": "OPERATOR",
                },
            )
            assert res.status_code == 201
            data = res.json()
            assert data["employee_id"] == "EMP-201"
            assert data["official_email"] == "ops201@oiltrace.gov"
            assert data["role"] == "OPERATOR"
            assert "temporary_password" not in data

    # 2. Employee creation sets status PENDING_ACTIVATION
    def test_02_employee_creation_sets_status_pending_activation(self, client, db_session):
        _make_user(db_session, email="tech@oiltrace.gov", employee_id="TECH-001", role="TECH_ADMIN")
        _login(client, "tech@oiltrace.gov", "C0astGuard!Secure99")

        with patch("backend.api.auth.send_account_activation_email"):
            res = client.post(
                "/api/auth/users",
                json={
                    "employee_id": "EMP-202",
                    "official_email": "ops202@oiltrace.gov",
                    "full_name": "Pending Officer",
                    "role": "ANALYST",
                },
            )
            assert res.status_code == 201
            assert res.json()["account_status"] == AccountStatus.PENDING_ACTIVATION.value

            db_user = db_session.query(User).filter(User.employee_id == "EMP-202").first()
            assert db_user.account_status == AccountStatus.PENDING_ACTIVATION.value
            assert db_user.password_hash is None

    # 3. Employee creation generates activation token hash
    def test_03_employee_creation_generates_activation_token_hash(self, client, db_session):
        _make_user(db_session, email="tech@oiltrace.gov", employee_id="TECH-001", role="TECH_ADMIN")
        _login(client, "tech@oiltrace.gov", "C0astGuard!Secure99")

        with patch("backend.api.auth.send_account_activation_email") as mock_email:
            res = client.post(
                "/api/auth/users",
                json={
                    "employee_id": "EMP-203",
                    "official_email": "ops203@oiltrace.gov",
                    "full_name": "Token Officer",
                    "role": "ANALYST",
                },
            )
            assert res.status_code == 201
            db_user = db_session.query(User).filter(User.employee_id == "EMP-203").first()
            assert db_user.activation_token_hash is not None
            assert len(db_user.activation_token_hash) == 64  # SHA-256 hex string
            assert db_user.activation_token_expires_at is not None

    # 4. Raw token not stored in database
    def test_04_raw_token_not_stored_in_database(self, client, db_session):
        _make_user(db_session, email="tech@oiltrace.gov", employee_id="TECH-001", role="TECH_ADMIN")
        _login(client, "tech@oiltrace.gov", "C0astGuard!Secure99")

        captured_token = None

        def capture_send(*args, **kwargs):
            nonlocal captured_token
            captured_token = kwargs.get("raw_token") or (args[2] if len(args) > 2 else None)

        with patch("backend.api.auth.send_account_activation_email", side_effect=capture_send):
            client.post(
                "/api/auth/users",
                json={
                    "employee_id": "EMP-204",
                    "official_email": "ops204@oiltrace.gov",
                    "full_name": "Secure Officer",
                    "role": "ANALYST",
                },
            )

        assert captured_token is not None
        db_user = db_session.query(User).filter(User.employee_id == "EMP-204").first()
        # Raw token must NOT equal the token hash in DB
        assert db_user.activation_token_hash != captured_token
        # It must match the SHA-256 of the captured raw token
        expected_hash = hashlib.sha256(captured_token.encode("utf-8")).hexdigest()
        assert db_user.activation_token_hash == expected_hash

    # 5. Raw token not returned in API response
    def test_05_raw_token_not_returned_in_api_response(self, client, db_session):
        _make_user(db_session, email="tech@oiltrace.gov", employee_id="TECH-001", role="TECH_ADMIN")
        _login(client, "tech@oiltrace.gov", "C0astGuard!Secure99")

        with patch("backend.api.auth.send_account_activation_email") as mock_email:
            res = client.post(
                "/api/auth/users",
                json={
                    "employee_id": "EMP-205",
                    "official_email": "ops205@oiltrace.gov",
                    "full_name": "Leak Check",
                    "role": "VIEWER",
                },
            )
            assert res.status_code == 201
            raw_response_text = res.text
            raw_token = mock_email.call_args.kwargs.get("raw_token") or mock_email.call_args[0][2]
            assert raw_token not in raw_response_text
            assert "activation_token" not in res.json()
            assert "activation_token_hash" not in res.json()

    # 6. Activation email triggered
    def test_06_activation_email_triggered(self, client, db_session):
        _make_user(db_session, email="tech@oiltrace.gov", employee_id="TECH-001", role="TECH_ADMIN")
        _login(client, "tech@oiltrace.gov", "C0astGuard!Secure99")

        with patch("backend.api.auth.send_account_activation_email") as mock_email:
            res = client.post(
                "/api/auth/users",
                json={
                    "employee_id": "EMP-206",
                    "official_email": "ops206@oiltrace.gov",
                    "full_name": "Email Target",
                    "role": "OPERATOR",
                },
            )
            assert res.status_code == 201
            mock_email.assert_called_once()
            args, kwargs = mock_email.call_args
            to_email = kwargs.get("to_email") or args[0]
            full_name = kwargs.get("full_name") or args[1]
            raw_token = kwargs.get("raw_token") or args[2]
            assert to_email == "ops206@oiltrace.gov"
            assert full_name == "Email Target"
            assert len(raw_token) > 20  # raw token string

    # 7. Unactivated employee cannot login
    def test_07_unactivated_employee_cannot_login(self, client, db_session):
        _make_user(
            db_session,
            email="pending@oiltrace.gov",
            employee_id="PND-001",
            password=None,
            account_status=AccountStatus.PENDING_ACTIVATION.value,
        )
        res = _login(client, "PND-001", "SomePassword123!")
        assert res.status_code == 401
        assert "pending activation" in res.json()["detail"].lower()

    # 8. Valid activation token allows employee to set password
    def test_08_valid_activation_token_allows_employee_to_set_password(self, client, db_session):
        _make_user(db_session, email="tech@oiltrace.gov", employee_id="TECH-001", role="TECH_ADMIN")
        _login(client, "tech@oiltrace.gov", "C0astGuard!Secure99")

        captured_token = None

        def capture_send(*args, **kwargs):
            nonlocal captured_token
            captured_token = kwargs.get("raw_token") or (args[2] if len(args) > 2 else None)

        with patch("backend.api.auth.send_account_activation_email", side_effect=capture_send):
            client.post(
                "/api/auth/users",
                json={
                    "employee_id": "EMP-208",
                    "official_email": "ops208@oiltrace.gov",
                    "full_name": "Activate Me",
                    "role": "ANALYST",
                },
            )

        # Verify token endpoint
        verify_res = client.get(f"/api/auth/verify-activation-token?token={captured_token}")
        assert verify_res.status_code == 200
        assert verify_res.json()["employee_id"] == "EMP-208"

        # Activate
        activate_res = client.post(
            "/api/auth/activate",
            json={"token": captured_token, "new_password": "MySecretPass#2026!"},
        )
        assert activate_res.status_code == 200
        assert "activated successfully" in activate_res.json()["detail"].lower()

    # 9. Account status changes to ACTIVE upon activation
    def test_09_account_status_changes_to_active_upon_activation(self, client, db_session):
        raw_token = "valid_test_token_09_random_secure"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        user = User(
            employee_id="EMP-209",
            official_email="ops209@oiltrace.gov",
            full_name="Status Check",
            role="ANALYST",
            account_status=AccountStatus.PENDING_ACTIVATION.value,
            activation_token_hash=token_hash,
            activation_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            is_active=False,
        )
        db_session.add(user)
        db_session.commit()

        res = client.post(
            "/api/auth/activate",
            json={"token": raw_token, "new_password": "MySecretPass#2026!"},
        )
        assert res.status_code == 200

        db_session.refresh(user)
        assert user.account_status == AccountStatus.ACTIVE.value
        assert user.is_active is True
        assert user.password_hash is not None
        assert user.activation_used_at is not None

    # 10. Activation token cannot be reused
    def test_10_activation_token_cannot_be_reused(self, client, db_session):
        raw_token = "valid_test_token_10_random_secure"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        user = User(
            employee_id="EMP-210",
            official_email="ops210@oiltrace.gov",
            full_name="Single Use",
            role="ANALYST",
            account_status=AccountStatus.PENDING_ACTIVATION.value,
            activation_token_hash=token_hash,
            activation_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            is_active=False,
        )
        db_session.add(user)
        db_session.commit()

        # First use succeeds
        res1 = client.post(
            "/api/auth/activate",
            json={"token": raw_token, "new_password": "FirstPassword#2026!"},
        )
        assert res1.status_code == 200

        # Second use with same token fails
        res2 = client.post(
            "/api/auth/activate",
            json={"token": raw_token, "new_password": "SecondPassword#2026!"},
        )
        assert res2.status_code == 400
        assert "invalid" in res2.json()["detail"].lower() or "expired" in res2.json()["detail"].lower()

    # 11. Expired activation token is rejected
    def test_11_expired_activation_token_is_rejected(self, client, db_session):
        raw_token = "expired_token_11_random_secure"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        user = User(
            employee_id="EMP-211",
            official_email="ops211@oiltrace.gov",
            full_name="Expired User",
            role="ANALYST",
            account_status=AccountStatus.PENDING_ACTIVATION.value,
            activation_token_hash=token_hash,
            activation_token_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            is_active=False,
        )
        db_session.add(user)
        db_session.commit()

        # Verification endpoint rejects
        res_verify = client.get(f"/api/auth/verify-activation-token?token={raw_token}")
        assert res_verify.status_code == 400

        # Activation rejects
        res_act = client.post(
            "/api/auth/activate",
            json={"token": raw_token, "new_password": "ValidPassword#2026!"},
        )
        assert res_act.status_code == 400
        assert "expired" in res_act.json()["detail"].lower() or "invalid" in res_act.json()["detail"].lower()

    # 12. Invalid activation token is rejected
    def test_12_invalid_activation_token_is_rejected(self, client, db_session):
        res = client.post(
            "/api/auth/activate",
            json={"token": "non_existent_token_12345", "new_password": "ValidPassword#2026!"},
        )
        assert res.status_code == 400
        assert "invalid" in res.json()["detail"].lower() or "expired" in res.json()["detail"].lower()

    # 13. Password policy enforced during activation
    def test_13_password_policy_enforced_during_activation(self, client, db_session):
        raw_token = "policy_token_13_random_secure"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        user = User(
            employee_id="EMP-213",
            official_email="ops213@oiltrace.gov",
            full_name="Policy User",
            role="ANALYST",
            account_status=AccountStatus.PENDING_ACTIVATION.value,
            activation_token_hash=token_hash,
            activation_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            is_active=False,
        )
        db_session.add(user)
        db_session.commit()

        # Weak password (too short, no symbols)
        res = client.post(
            "/api/auth/activate",
            json={"token": raw_token, "new_password": "weak"},
        )
        assert res.status_code == 400
        assert "password" in res.json()["detail"].lower()

    # 14. Employee can login after activation using set password
    def test_14_employee_can_login_after_activation_using_set_password(self, client, db_session):
        raw_token = "login_token_14_random_secure"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        user = User(
            employee_id="EMP-214",
            official_email="ops214@oiltrace.gov",
            full_name="Login User",
            role="ANALYST",
            account_status=AccountStatus.PENDING_ACTIVATION.value,
            activation_token_hash=token_hash,
            activation_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            is_active=False,
        )
        db_session.add(user)
        db_session.commit()

        # Activate with password
        client.post(
            "/api/auth/activate",
            json={"token": raw_token, "new_password": "MyChosenSecret#2026!"},
        )

        # Login with employee_id
        res1 = _login(client, "EMP-214", "MyChosenSecret#2026!")
        assert res1.status_code == 200
        assert res1.json()["account_status"] == AccountStatus.ACTIVE.value

        # Login with official_email
        res2 = _login(client, "ops214@oiltrace.gov", "MyChosenSecret#2026!")
        assert res2.status_code == 200

    # 15. Resend invitation invalidates previous token and issues new token
    def test_15_resend_invitation_invalidates_previous_token(self, client, db_session):
        _make_user(db_session, email="tech@oiltrace.gov", employee_id="TECH-001", role="TECH_ADMIN")
        _login(client, "tech@oiltrace.gov", "C0astGuard!Secure99")

        first_token = None
        second_token = None

        def capture_first(*args, **kwargs):
            nonlocal first_token
            first_token = kwargs.get("raw_token") or (args[2] if len(args) > 2 else None)

        with patch("backend.api.auth.send_account_activation_email", side_effect=capture_first):
            res_create = client.post(
                "/api/auth/users",
                json={
                    "employee_id": "EMP-215",
                    "official_email": "ops215@oiltrace.gov",
                    "full_name": "Resend User",
                    "role": "ANALYST",
                },
            )
            user_id = res_create.json()["id"]

        assert first_token is not None

        # Advance last_invitation_sent_at past the 30s cooldown window
        user = db_session.query(User).filter(User.id == user_id).first()
        user.last_invitation_sent_at = datetime.now(timezone.utc) - timedelta(seconds=35)
        db_session.commit()

        def capture_second(*args, **kwargs):
            nonlocal second_token
            second_token = kwargs.get("raw_token") or (args[2] if len(args) > 2 else None)

        with patch("backend.api.auth.send_account_activation_email", side_effect=capture_second):
            res_resend = client.post(f"/api/auth/users/{user_id}/resend-invitation")
            assert res_resend.status_code == 200

        assert second_token is not None
        assert first_token != second_token

        # First token must now be invalid
        res_old = client.post(
            "/api/auth/activate",
            json={"token": first_token, "new_password": "ValidPassword#2026!"},
        )
        assert res_old.status_code == 400

        # Second token succeeds
        res_new = client.post(
            "/api/auth/activate",
            json={"token": second_token, "new_password": "ValidPassword#2026!"},
        )
        assert res_new.status_code == 200

    # 16. Non-TECH_ADMIN cannot create employees
    def test_16_non_tech_admin_cannot_create_employees(self, client, db_session):
        for role in ["ADMIN", "ANALYST", "OPERATOR", "VIEWER"]:
            emp_id = f"EMP-{role}"
            email = f"{role.lower()}@oiltrace.gov"
            _make_user(db_session, email=email, employee_id=emp_id, role=role)
            _login(client, emp_id, "C0astGuard!Secure99")

            res = client.post(
                "/api/auth/users",
                json={
                    "employee_id": f"TEST-{role}",
                    "official_email": f"test_{role.lower()}@oiltrace.gov",
                    "full_name": "Unauthorized Attempt",
                    "role": "VIEWER",
                },
            )
            assert res.status_code == 403

    # 17. TECH_ADMIN can trigger password reset email
    def test_17_tech_admin_can_trigger_password_reset_email(self, client, db_session):
        _make_user(db_session, email="tech@oiltrace.gov", employee_id="TECH-001", role="TECH_ADMIN")
        target = _make_user(db_session, email="target17@oiltrace.gov", employee_id="EMP-217", role="ANALYST")
        _login(client, "tech@oiltrace.gov", "C0astGuard!Secure99")

        with patch("backend.api.auth.send_password_reset_email") as mock_reset_email:
            res = client.post(f"/api/auth/users/{target.id}/reset-password")
            assert res.status_code == 200
            assert "password reset" in res.json()["detail"].lower()
            mock_reset_email.assert_called_once()
            to_email = mock_reset_email.call_args.kwargs.get("to_email") or mock_reset_email.call_args[0][0]
            assert to_email == "target17@oiltrace.gov"

            db_session.refresh(target)
            assert target.reset_token_hash is not None
            assert target.reset_token_expires_at is not None

    # 18. Password reset token allows employee to set new password
    def test_18_password_reset_token_allows_employee_to_set_new_password(self, client, db_session):
        _make_user(db_session, email="tech@oiltrace.gov", employee_id="TECH-001", role="TECH_ADMIN")
        target = _make_user(
            db_session,
            email="target18@oiltrace.gov",
            employee_id="EMP-218",
            role="ANALYST",
            password="OldOriginalPassword#2026!",
        )
        _login(client, "tech@oiltrace.gov", "C0astGuard!Secure99")

        captured_reset_token = None

        def capture_reset(*args, **kwargs):
            nonlocal captured_reset_token
            captured_reset_token = kwargs.get("raw_token") or (args[2] if len(args) > 2 else None)

        with patch("backend.api.auth.send_password_reset_email", side_effect=capture_reset):
            client.post(f"/api/auth/users/{target.id}/reset-password")

        # Verify endpoint
        v_res = client.get(f"/api/auth/verify-reset-token?token={captured_reset_token}")
        assert v_res.status_code == 200
        assert v_res.json()["employee_id"] == "EMP-218"

        # Complete reset
        res = client.post(
            "/api/auth/reset-password",
            json={"token": captured_reset_token, "new_password": "NewBrandPassword#2026!"},
        )
        assert res.status_code == 200

        # Old password fails
        old_login = _login(client, "EMP-218", "OldOriginalPassword#2026!")
        assert old_login.status_code == 401

        # New password succeeds
        new_login = _login(client, "EMP-218", "NewBrandPassword#2026!")
        assert new_login.status_code == 200

    # 19. Password reset token cannot be reused
    def test_19_password_reset_token_cannot_be_reused(self, client, db_session):
        raw_reset_token = "single_use_reset_token_19"
        reset_hash = hashlib.sha256(raw_reset_token.encode("utf-8")).hexdigest()
        user = _make_user(db_session, email="target19@oiltrace.gov", employee_id="EMP-219")
        user.reset_token_hash = reset_hash
        user.reset_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        db_session.commit()

        # First reset succeeds
        res1 = client.post(
            "/api/auth/reset-password",
            json={"token": raw_reset_token, "new_password": "FirstReset#2026!"},
        )
        assert res1.status_code == 200

        # Second reset with same token fails
        res2 = client.post(
            "/api/auth/reset-password",
            json={"token": raw_reset_token, "new_password": "SecondReset#2026!"},
        )
        assert res2.status_code == 400
        assert "invalid" in res2.json()["detail"].lower() or "expired" in res2.json()["detail"].lower()

    # 20. Expired password reset token is rejected
    def test_20_expired_password_reset_token_is_rejected(self, client, db_session):
        raw_reset_token = "expired_reset_token_20"
        reset_hash = hashlib.sha256(raw_reset_token.encode("utf-8")).hexdigest()
        user = _make_user(db_session, email="target20@oiltrace.gov", employee_id="EMP-220")
        user.reset_token_hash = reset_hash
        user.reset_token_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()

        res_verify = client.get(f"/api/auth/verify-reset-token?token={raw_reset_token}")
        assert res_verify.status_code == 400

        res_reset = client.post(
            "/api/auth/reset-password",
            json={"token": raw_reset_token, "new_password": "ValidNewPassword#2026!"},
        )
        assert res_reset.status_code == 400
        assert "expired" in res_reset.json()["detail"].lower() or "invalid" in res_reset.json()["detail"].lower()


# ──────────────────────────────────────────────────────────────────────────────
# Existing Governance & RBAC Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestGovernanceAndSecurity:
    def test_duplicate_employee_id_rejected(self, client, db_session):
        _make_user(db_session, email="tech@oiltrace.gov", employee_id="TECH-001", role="TECH_ADMIN")
        _make_user(db_session, email="existing@oiltrace.gov", employee_id="EMP-DUP", role="ANALYST")
        _login(client, "tech@oiltrace.gov", "C0astGuard!Secure99")

        res = client.post(
            "/api/auth/users",
            json={
                "employee_id": "EMP-DUP",
                "official_email": "newunique@oiltrace.gov",
                "full_name": "Duplicate ID Tester",
                "role": "ANALYST",
            },
        )
        assert res.status_code == 409
        assert "employee id" in res.json()["detail"].lower()

    def test_duplicate_official_email_rejected(self, client, db_session):
        _make_user(db_session, email="tech@oiltrace.gov", employee_id="TECH-001", role="TECH_ADMIN")
        _make_user(db_session, email="existing@oiltrace.gov", employee_id="EMP-UNIQUE", role="ANALYST")
        _login(client, "tech@oiltrace.gov", "C0astGuard!Secure99")

        res = client.post(
            "/api/auth/users",
            json={
                "employee_id": "EMP-NEW",
                "official_email": "existing@oiltrace.gov",
                "full_name": "Duplicate Email Tester",
                "role": "ANALYST",
            },
        )
        assert res.status_code == 409
        assert "email" in res.json()["detail"].lower()

    def test_tech_admin_can_deactivate_employee(self, client, db_session):
        _make_user(db_session, email="tech@oiltrace.gov", employee_id="TECH-001", role="TECH_ADMIN")
        target = _make_user(db_session, email="target@oiltrace.gov", employee_id="TGT-001", role="ANALYST")
        _login(client, "tech@oiltrace.gov", "C0astGuard!Secure99")

        res = client.post(f"/api/auth/users/{target.id}/deactivate")
        assert res.status_code == 200
        db_session.refresh(target)
        assert target.is_active is False
        assert target.account_status == AccountStatus.DEACTIVATED.value

    def test_deactivated_employee_loses_login_access(self, client, db_session):
        _make_user(db_session, email="tech@oiltrace.gov", employee_id="TECH-001", role="TECH_ADMIN")
        target = _make_user(db_session, email="target2@oiltrace.gov", employee_id="TGT-002", password="ValidPass#2026!")
        _login(client, "tech@oiltrace.gov", "C0astGuard!Secure99")

        # Deactivate
        client.post(f"/api/auth/users/{target.id}/deactivate")

        # Attempt login
        login_res = _login(client, "TGT-002", "ValidPass#2026!")
        assert login_res.status_code == 401
        assert "inactive" in login_res.json()["detail"].lower() or "deactivated" in login_res.json()["detail"].lower()

    def test_tech_admin_cannot_arbitrarily_create_tech_admin(self, client, db_session):
        _make_user(db_session, email="tech@oiltrace.gov", employee_id="TECH-001", role="TECH_ADMIN")
        _login(client, "tech@oiltrace.gov", "C0astGuard!Secure99")

        res = client.post(
            "/api/auth/users",
            json={
                "employee_id": "TECH-002",
                "official_email": "tech2@oiltrace.gov",
                "full_name": "Second Tech Admin",
                "role": "TECH_ADMIN",
            },
        )
        assert res.status_code == 403
        assert "restricted" in res.json()["detail"].lower() or "cannot be assigned" in res.json()["detail"].lower()

    def test_unauthenticated_cannot_access_employee_management(self, client, db_session):
        res = client.get("/api/auth/users")
        assert res.status_code == 401

        res_post = client.post(
            "/api/auth/users",
            json={
                "employee_id": "EMP-999",
                "official_email": "anon@oiltrace.gov",
                "full_name": "Anon",
                "role": "VIEWER",
            },
        )
        assert res_post.status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# Core Session & Password Policy Unit Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionAndPolicy:
    def test_logout_clears_cookies(self, client, db_session):
        _make_user(db_session, email="logoutuser@oiltrace.gov", employee_id="LOG-001")
        _login(client, "LOG-001", "C0astGuard!Secure99")
        res = client.post("/api/auth/logout")
        assert res.status_code == 200
        me_res = client.get("/api/auth/me")
        assert me_res.status_code == 401

    def test_brute_force_lockout(self, client, db_session):
        _make_user(db_session, email="lockuser@oiltrace.gov", employee_id="LCK-001")
        max_attempts = settings.MAX_LOGIN_ATTEMPTS

        for i in range(max_attempts):
            res = _login(client, "LCK-001", "WrongPassword!99")
            if i < max_attempts - 1:
                assert res.status_code == 401

        res = _login(client, "LCK-001", "WrongPassword!99")
        assert res.status_code == 429
        assert "locked" in res.json()["detail"].lower()

    def test_password_policy_strength(self):
        with pytest.raises(ValueError, match="12 characters"):
            validate_password("Short!1A", "user@coast.gov")

        with pytest.raises(ValueError, match="uppercase"):
            validate_password("alllowercase!99", "user@coast.gov")

        with pytest.raises(ValueError, match="lowercase"):
            validate_password("ALLUPPERCASE!99", "user@coast.gov")

        with pytest.raises(ValueError, match="digit"):
            validate_password("NoDigitHere!XYZ", "user@coast.gov")

        with pytest.raises(ValueError, match="special character"):
            validate_password("NoSymbolHere1234", "user@coast.gov")

        # Policy accepted
        validate_password("C0astGuard!Secure99", "ops@coast.gov")
