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
        _db_available = True
        logger.info(f"Connected successfully to database.")
        return _engine, _SessionLocal
    except Exception as exc:
        logger.warning(f"Could not connect to database ({exc}). Running in offline/demo fallback mode.")
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
