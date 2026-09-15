"""OilTrace Database Module.

Configures SQLAlchemy engine, session factory, PostGIS connection, and FastAPI database dependency.
Handles missing/offline PostgreSQL gracefully with fallback options.
"""

from __future__ import annotations

from typing import Generator, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import StaticPool

from backend.core.config import settings
from backend.core.logging import logger

Base = declarative_base()

_engine = None
_SessionLocal = None
_db_available: bool = False


def _create_tables(engine):
    try:
        import backend.models.investigation
        import backend.models.spill
        import backend.models.drift
        import backend.models.origin
        import backend.models.attribution
        import backend.models.report
        import backend.models.vessel
        import backend.models.profile
        import backend.models.notification
        import backend.models.artifact
        import backend.models.settings
        Base.metadata.create_all(bind=engine)

        # Non-destructive SQLite schema migration for newly added columns
        with engine.connect() as conn:
            cols = [c[1] for c in conn.execute(text("PRAGMA table_info(investigations)")).fetchall()]
            if cols:
                if "is_deleted" not in cols:
                    conn.execute(text("ALTER TABLE investigations ADD COLUMN is_deleted BOOLEAN DEFAULT 0"))
                if "deleted_at" not in cols:
                    conn.execute(text("ALTER TABLE investigations ADD COLUMN deleted_at DATETIME"))
                if "is_archived" not in cols:
                    conn.execute(text("ALTER TABLE investigations ADD COLUMN is_archived BOOLEAN DEFAULT 0"))
                if "is_starred" not in cols:
                    conn.execute(text("ALTER TABLE investigations ADD COLUMN is_starred BOOLEAN DEFAULT 0"))
                if "parent_investigation_id" not in cols:
                    conn.execute(text("ALTER TABLE investigations ADD COLUMN parent_investigation_id VARCHAR(64)"))
                if "activity_log_json" not in cols:
                    conn.execute(text("ALTER TABLE investigations ADD COLUMN activity_log_json JSON DEFAULT '[]'"))
                if "artifacts_json" not in cols:
                    conn.execute(text("ALTER TABLE investigations ADD COLUMN artifacts_json JSON DEFAULT '{}'"))
                if "sar_acquisition_time" not in cols:
                    conn.execute(text("ALTER TABLE investigations ADD COLUMN sar_acquisition_time DATETIME"))
                if "sar_acquisition_time_source" not in cols:
                    conn.execute(text("ALTER TABLE investigations ADD COLUMN sar_acquisition_time_source VARCHAR(64)"))
                if "sar_acquisition_time_verified" not in cols:
                    conn.execute(text("ALTER TABLE investigations ADD COLUMN sar_acquisition_time_verified BOOLEAN DEFAULT 0"))

            profile_cols = [c[1] for c in conn.execute(text("PRAGMA table_info(user_profiles)")).fetchall()]
            if profile_cols:
                if "department" not in profile_cols:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN department VARCHAR(128) DEFAULT 'Maritime Environmental Enforcement Division'"))
                if "specialization" not in profile_cols:
                    conn.execute(text("ALTER TABLE user_profiles ADD COLUMN specialization VARCHAR(128) DEFAULT 'SAR Detection & Hydrodynamic Drift Reconstruction'"))
            conn.commit()
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")


def _init_engine():
    global _engine, _SessionLocal, _db_available

    db_url = settings.DATABASE_URL
    if not db_url:
        logger.warning("DATABASE_URL is not set. Database persistence will be in fallback/demo mode.")
        _db_available = False
        return None, None

    try:
        # If postgresql:// or postgresql+psycopg:// is supplied
        # Ensure proper driver specification if generic postgresql:// was passed
        if db_url.startswith("postgresql://"):
            try:
                import psycopg
                db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
            except ImportError:
                pass

        connect_args = {}
        if "sqlite" in db_url:
            connect_args["check_same_thread"] = False
        elif "postgresql" in db_url:
            connect_args["connect_timeout"] = 1

        engine = create_engine(
            db_url,
            pool_pre_ping=True,
            echo=settings.DB_ECHO,
            connect_args=connect_args,
        )

        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _engine = engine
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        _create_tables(engine)
        _db_available = True
        logger.info(f"Connected successfully to database. Tables initialized.")
        return _engine, _SessionLocal
    except Exception as exc:
        logger.warning(f"Could not connect to database {db_url} ({exc}). Falling back to local SQLite database.")
        try:
            sqlite_path = settings.REPO_ROOT / "data" / "oiltrace.db"
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            sqlite_url = f"sqlite:///{sqlite_path}"
            engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            _engine = engine
            _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            _create_tables(engine)
            _db_available = True
            logger.info(f"Connected successfully to local SQLite database at {sqlite_path}. Tables initialized.")
            return _engine, _SessionLocal
        except Exception as e2:
            logger.error(f"SQLite fallback failed: {e2}")
            _db_available = False
            return None, None


# Attempt initial connection
_engine, _SessionLocal = _init_engine()


def get_engine():
    """Return the active SQLAlchemy engine, attempting initialization if needed."""
    global _engine, _SessionLocal
    if _engine is None and settings.DATABASE_URL:
        _init_engine()
    return _engine


def get_db() -> Generator[Optional[Session], None, None]:
    """FastAPI dependency for yielding database sessions."""
    global _SessionLocal
    if _SessionLocal is None:
        if settings.DATABASE_URL:
            _init_engine()

    if _SessionLocal is None:
        # Yield None so services know to use demo/memory provider
        yield None
        return

    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Optional[Session]:
    """Get a direct database session for CLI or background contexts."""
    global _SessionLocal
    if _SessionLocal is None:
        _init_engine()
    return _SessionLocal() if _SessionLocal else None


def check_db_health() -> str:
    """Check database liveness for health endpoint."""
    engine = get_engine()
    if engine is None:
        return "unavailable"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "unavailable"
