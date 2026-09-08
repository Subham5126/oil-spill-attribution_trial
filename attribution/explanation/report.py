"""Report compilation and high-level explain_attribution entry point (ATTR-03).

Provides the primary user-facing function `explain_attribution` to synthesize
candidate explanations, comparative assessments, and incident reports from ATTR-02 results.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

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
from attribution.models import AttributedCandidate, AttributionResult, OriginMetadata


def explain_attribution(
    result: AttributionResult,
    top_n: int = 5,
    include_provenance: bool = True,
    custom_disclaimer: Optional[str] = None,
) -> AttributionExplanationReport:
    """Generate explainable candidate dossiers, narratives, and an incident report from ATTR-02 results.

    Consumes existing ATTR-02 attribution results without recalculating any mathematical
    scores or altering the established ranking order.

    Args:
        result: AttributionResult from ATTR-02 scoring engine.
        top_n: Number of top-ranked candidates to receive full detailed natural-language
            narratives and comparative notes (default: 5). Candidates outside top_n
            receive standardized concise summaries.
        include_provenance: Whether to include detailed telemetry composition,
            interpolation ratios, and fix provenance in data quality notes (default: True).
        custom_disclaimer: Optional string overriding the standard scientific non-causation disclaimer.

    Returns:
        AttributionExplanationReport: Immutable report container with JSON, Markdown,
            and DataFrame export capabilities.

    Raises:
        TypeError: If result is not an AttributionResult instance.
        ValueError: If top_n is negative.
    """
    if not isinstance(result, AttributionResult):
        raise TypeError(
            f"result must be an AttributionResult instance, got {type(result)}. "
            "Ensure you pass the output of ATTR-02 score_candidates() / attribute_vessels()."
        )

    if isinstance(top_n, bool) or not isinstance(top_n, (int, np.integer)):
        try:
            top_n = int(top_n)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"top_n must be a non-negative integer, got {top_n}") from exc
    if top_n < 0:
        raise ValueError(f"top_n must be a non-negative integer, got {top_n}")

    # Resolve disclaimer
    if custom_disclaimer is not None and str(custom_disclaimer).strip():
        disclaimer = str(custom_disclaimer).strip()
    else:
        disclaimer = DEFAULT_ATTRIBUTION_DISCLAIMER

    origin = result.origin_metadata
    cfg = result.config_summary or {}
    max_dist_km = float(cfg.get("max_distance_km", 25.0))
    max_time_diff_sec = float(cfg.get("max_time_diff_seconds", 7200.0))

    candidate_explanations: List[CandidateExplanation] = []
    ranked = result.ranked_candidates
    cand_count = len(ranked)

    # Process each candidate preserving exact ATTR-02 ranking order
    for idx, cand in enumerate(ranked):
        next_cand = ranked[idx + 1] if idx + 1 < cand_count else None

        # 1. Determine Confidence Tier with Safety Override
        tier = determine_confidence_tier(
            overall_score=cand.score.overall_score,
            min_distance_km=cand.evidence.min_distance_km,
            time_diff_seconds=cand.evidence.time_difference_seconds,
            max_distance_km=max_dist_km,
            max_time_diff_seconds=max_time_diff_sec,
        )

        # 2. Synthesize Evidence Factors
        supp, contra, quality = synthesize_candidate_factors(
            candidate=cand,
            origin=origin,
            config_summary=cfg,
        )

        if not include_provenance:
            quality = []

        # 3. Top-N Narrative vs Standardized Summary
        if idx < top_n:
            narrative = generate_vessel_narrative(
                candidate=cand,
                origin=origin,
                confidence_tier=tier,
                config_summary=cfg,
            )
            comparative = generate_comparative_note(
                candidate=cand,
                next_candidate=next_cand,
            )
        else:
            vname_str = f", '{cand.vessel.vessel_name}'" if cand.vessel.vessel_name else ""
            narrative = (
                f"Rank #{cand.rank} (MMSI: {cand.vessel.mmsi}{vname_str}): analytical score "
                f"{cand.score.overall_score:.4f} ({tier}). Peripheral candidate outside top {top_n} "
                f"detailed narrative review."
            )
            comparative = None

        candidate_explanations.append(
            CandidateExplanation(
                mmsi=cand.vessel.mmsi,
                rank=cand.rank,
                overall_score=cand.score.overall_score,
                confidence_tier=tier,
                summary_narrative=narrative,
                vessel_name=cand.vessel.vessel_name,
                vessel_type=cand.vessel.vessel_type,
                key_supporting_factors=tuple(supp),
                key_contradicting_factors=tuple(contra),
                data_quality_notes=tuple(quality),
                comparative_note=comparative,
            )
        )

    incident_summary = generate_incident_summary(result=result, top_n=top_n)

    top_summary = (
        candidate_explanations[0].summary_narrative
        if candidate_explanations
        else None
    )

    metadata: Dict[str, Any] = {
        "top_n": top_n,
        "include_provenance": include_provenance,
        "total_input_observations": result.report.total_input_observations,
        "total_candidates_evaluated": cand_count,
        "evaluation_timestamp": result.report.evaluation_timestamp,
        "config_summary": cfg,
    }

    return AttributionExplanationReport(
        incident_summary=incident_summary,
        origin_summary=origin.to_dict(),
        candidate_explanations=tuple(candidate_explanations),
        disclaimer=disclaimer,
        top_candidate_summary=top_summary,
        metadata=metadata,
    )
