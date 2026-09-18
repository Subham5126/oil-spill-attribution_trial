"""Unit and integration tests for database configuration, URL normalization,
production safety enforcement, and health check database reporting.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings, normalize_database_url
import backend.core.database as db_mod
from backend.main import app


class TestDatabaseUrlNormalization:
    """Test suite for normalize_database_url function."""

    def test_normalize_postgres_scheme(self):
        url = "postgres://oiltrace:secret@postgres.railway.internal:5432/railway"
        expected = "postgresql+psycopg://oiltrace:secret@postgres.railway.internal:5432/railway"
        assert normalize_database_url(url) == expected

    def test_normalize_postgresql_scheme(self):
        url = "postgresql://oiltrace:secret@postgres.railway.internal:5432/railway"
        expected = "postgresql+psycopg://oiltrace:secret@postgres.railway.internal:5432/railway"
        assert normalize_database_url(url) == expected

    def test_normalize_postgresql_with_psycopg_already_set(self):
        url = "postgresql+psycopg://oiltrace:secret@postgres.railway.internal:5432/railway"
        assert normalize_database_url(url) == url

    def test_normalize_sqlite_url(self):
        url = "sqlite:///data/oiltrace.db"
        assert normalize_database_url(url) == url

    def test_normalize_empty_or_none(self):
        assert normalize_database_url(None) == ""
        assert normalize_database_url("") == ""
        assert normalize_database_url("   ") == ""


class TestProductionDatabaseSafety:
    """Verify that production environments enforce PostgreSQL and reject SQLite."""

    def test_production_environment_rejects_sqlite_engine_init(self):
        """When APP_ENV=production and DATABASE_URL is SQLite, _init_engine must raise RuntimeError."""
        mock_settings = Settings(
            APP_ENV="production",
            DATABASE_URL="sqlite:///data/oiltrace.db"
        )
        with patch("backend.core.database.settings", mock_settings):
            with pytest.raises(RuntimeError) as exc_info:
                db_mod._init_engine()
            assert "Production environment" in str(exc_info.value)
            assert "SQLite is strictly prohibited" in str(exc_info.value)

    def test_production_environment_rejects_missing_database_url(self):
        """When APP_ENV=production and DATABASE_URL is empty, _init_engine must raise RuntimeError."""
        mock_settings = Settings(
            APP_ENV="production",
            DATABASE_URL=""
        )
        with patch("backend.core.database.settings", mock_settings):
            with pytest.raises(RuntimeError) as exc_info:
                db_mod._init_engine()
            assert "Production environment" in str(exc_info.value)
            assert "requires a valid PostgreSQL DATABASE_URL" in str(exc_info.value)


    def test_is_production_and_is_postgres_properties(self):
        prod_settings = Settings(
            APP_ENV="production",
            DATABASE_URL="postgresql://user:pass@host:5432/db"
        )
        assert prod_settings.is_production is True
        assert prod_settings.is_postgres is True

        dev_settings = Settings(
            APP_ENV="development",
            DATABASE_URL="sqlite:///data/oiltrace.db"
        )
        assert dev_settings.is_production is False
        assert dev_settings.is_postgres is False


class TestDatabaseHealthCheck:
    """Verify /api/health reports database status without exposing credentials."""

    def test_health_check_database_connected(self):
        client = TestClient(app)
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        assert data.get("database") == "connected"
        # Confirm no credentials or connection string exposed in health response
        assert "password" not in str(data).lower()
        assert "secret" not in str(data).lower()
        assert "railway" not in str(data).lower()

    def test_health_check_database_unavailable(self):
        client = TestClient(app)
        with patch("backend.api.health.check_db_health", return_value="error"):
            response = client.get("/api/health")
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == "degraded"
            assert data.get("database") == "unavailable"
