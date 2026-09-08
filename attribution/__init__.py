"""Oil Spill Attribution Module.

Provides evidence-based candidate vessel scoring, multi-criteria attribution,
and explainability for identified marine oil spill events.
"""

from attribution.models import (
    OPTIONAL_AIS_COLUMNS,
    REQUIRED_AIS_COLUMNS,
    AttributedCandidate,
    AttributionEvidence,
    AttributionReport,
    AttributionResult,
    CandidateVessel,
    OriginMetadata,
    VesselScore,
    extract_candidate_vessels,
    validate_ais_observations,
    validate_origin_metadata,
)

__all__ = [
    "CandidateVessel",
    "AttributionEvidence",
    "VesselScore",
    "AttributedCandidate",
    "OriginMetadata",
    "AttributionReport",
    "AttributionResult",
    "extract_candidate_vessels",
    "validate_ais_observations",
    "validate_origin_metadata",
    "REQUIRED_AIS_COLUMNS",
    "OPTIONAL_AIS_COLUMNS",
]
