"""Attribution Scoring & Explainability Adapter (Member 5 Integration).

Bridges the backend to Member 5 multi-criteria evidence scoring (spatial, temporal,
trajectory, behaviour) and forensic explanation narrative generation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from attribution import (
    AttributionExplanationReport,
    AttributionResult,
    AttributionScoringConfig,
    OriginMetadata,
    explain_attribution,
    score_candidates,
)


class AttributionAdapter:
    """Service adapter interfacing with Member 5 multi-criteria scoring and explanation."""

    @staticmethod
    def score_vessels(
        filtered_ais_data: Any,
        origin_metadata: OriginMetadata,
        config: Optional[AttributionScoringConfig] = None,
    ) -> AttributionResult:
        """Calculate normalized multi-tier scores and rank suspect vessels."""
        return score_candidates(
            data=filtered_ais_data,
            origin_data=origin_metadata,
            config=config,
        )

    @staticmethod
    def generate_explanation(
        attribution_result: AttributionResult,
        top_n: int = 5,
    ) -> AttributionExplanationReport:
        """Generate structured forensic explanation narrative report."""
        return explain_attribution(
            result=attribution_result,
            top_n=top_n,
        )
