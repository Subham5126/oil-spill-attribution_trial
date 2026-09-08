"""Attribution Explanation & Reporting Package (ATTR-03).

Provides explainability dossiers, evidence factor synthesis, natural language
narratives, confidence tier classification, and incident report generation
for marine oil spill vessel attribution.
"""

from attribution.explanation.factors import (
    determine_confidence_tier,
    synthesize_candidate_factors,
)
from attribution.explanation.models import (
    DEFAULT_ATTRIBUTION_DISCLAIMER,
    AttributionExplanationReport,
    CandidateExplanation,
    ConfidenceTier,
)
from attribution.explanation.narrative import (
    generate_comparative_note,
    generate_incident_summary,
    generate_vessel_narrative,
)
from attribution.explanation.report import explain_attribution

__all__ = [
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
