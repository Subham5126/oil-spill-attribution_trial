"""OilTrace Models Package."""

from backend.models.base import Base, SafeGeometry, TimestampMixin
from backend.models.investigation import InvestigationModel
from backend.models.spill import SpillDetectionModel
from backend.models.drift import DriftRunModel
from backend.models.origin import OriginCandidateModel
from backend.models.vessel import VesselModel
from backend.models.ais import AISTrackModel
from backend.models.attribution import AttributionResultModel
from backend.models.report import ReportModel

__all__ = [
    "Base",
    "SafeGeometry",
    "TimestampMixin",
    "InvestigationModel",
    "SpillDetectionModel",
    "DriftRunModel",
    "OriginCandidateModel",
    "VesselModel",
    "AISTrackModel",
    "AttributionResultModel",
    "ReportModel",
]
