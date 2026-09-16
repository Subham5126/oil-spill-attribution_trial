"""OilTrace Base Model and Utilities.

Defines the declarative base, timestamps, and PostGIS Geometry type helpers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.types import TypeDecorator, Text
from backend.core.database import Base


def utc_now() -> datetime:
    """Return current UTC datetime with timezone."""
    return datetime.now(timezone.utc)


# Check if GeoAlchemy2 Geometry can be used
try:
    from geoalchemy2 import Geometry
    HAS_GEOALCHEMY = True
except ImportError:
    HAS_GEOALCHEMY = False
    Geometry = None


class SafeGeometry(TypeDecorator):
    """Custom type that uses GeoAlchemy2 Geometry on PostGIS/PostgreSQL, but falls back to Text on SQLite."""

    impl = Text
    cache_ok = True

    def __init__(self, geometry_type: str = "GEOMETRY", srid: int = 4326, **kwargs):
        self.geometry_type = geometry_type
        self.srid = srid
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and HAS_GEOALCHEMY:
            return dialect.type_descriptor(Geometry(geometry_type=self.geometry_type, srid=self.srid))
        return dialect.type_descriptor(Text())


class TimestampMixin:
    """Mixin for models requiring created_at and updated_at timestamps."""

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
