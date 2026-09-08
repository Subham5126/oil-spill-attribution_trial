"""Oil Spill Attribution Module.

Provides evidence-based candidate vessel scoring, multi-criteria attribution,
and explainability for identified marine oil spill events.
"""

from attribution.explanation import (
    DEFAULT_ATTRIBUTION_DISCLAIMER,
    AttributionExplanationReport,
    CandidateExplanation,
    ConfidenceTier,
    determine_confidence_tier,
    explain_attribution,
    generate_comparative_note,
    generate_incident_summary,
    generate_vessel_narrative,
    synthesize_candidate_factors,
)
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
from attribution.scoring import (
    AttributionScoringConfig,
    attribute_vessels,
    score_candidates,
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
    "AttributionScoringConfig",
    "score_candidates",
    "attribute_vessels",
    "CandidateExplanation",
    "AttributionExplanationReport",
    "ConfidenceTier",
    "DEFAULT_ATTRIBUTION_DISCLAIMER",
    "explain_attribution",
    "determine_confidence_tier",
    "synthesize_candidate_factors",
    "generate_vessel_narrative",
    "generate_comparative_note",
    "generate_incident_summary",
]
