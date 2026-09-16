"""OilTrace Repositories Package."""

from backend.repositories.investigations import InvestigationRepository
from backend.repositories.spills import SpillRepository
from backend.repositories.drift import DriftRepository
from backend.repositories.vessels import VesselRepository
from backend.repositories.attribution import AttributionRepository

__all__ = [
    "InvestigationRepository",
    "SpillRepository",
    "DriftRepository",
    "VesselRepository",
    "AttributionRepository",
]
