"""OilTrace Services Package.

Services should be imported directly from their respective modules
(e.g. `from backend.services.email_service import get_email_service` or
`from backend.services.pipeline_service import PipelineService`)
to prevent circular imports and heavy eager loading during lightweight application startup.
"""

__all__ = [
    "InvestigationService",
    "PipelineService",
    "DriftService",
    "LayerService",
    "ReportService",
    "SpillService",
    "VesselService",
    "AttributionService",
]
