"""OilTrace Backend Core Package."""

from backend.core.config import settings
from backend.core.database import Base, get_db, check_db_health, get_engine
from backend.core.logging import logger, PipelineStageLogger
from backend.core.exceptions import (
    OilTraceException,
    InvestigationNotFoundError,
    SpillNotFoundError,
    VesselNotFoundError,
    ReportNotFoundError,
    PipelineExecutionError,
    InvalidRequestError,
)

__all__ = [
    "settings",
    "Base",
    "get_db",
    "check_db_health",
    "get_engine",
    "logger",
    "PipelineStageLogger",
    "OilTraceException",
    "InvestigationNotFoundError",
    "SpillNotFoundError",
    "VesselNotFoundError",
    "ReportNotFoundError",
    "PipelineExecutionError",
    "InvalidRequestError",
]
