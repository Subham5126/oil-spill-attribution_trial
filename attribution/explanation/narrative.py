"""Natural language narrative generation for candidate vessel attribution (ATTR-03).

Generates deterministic, professional, and explainable natural-language narratives,
comparative assessments, and incident executive summaries.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from attribution.explanation.models import ConfidenceTier
from attribution.models import AttributedCandidate, AttributionResult, OriginMetadata


def generate_vessel_narrative(
    candidate: AttributedCandidate,
    origin: OriginMetadata,
    confidence_tier: str,
    config_summary: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a deterministic, professional natural-language narrative for a candidate vessel.

    Constructs a factual paragraph covering:
    - Identity, rank, analytical score, and confidence tier.
    - Reconstructed spatial trajectory and distance relative to origin radius.
    - Temporal encounter timing and delta relative to estimated release time.
    - Provenance of closest approach fix (broadcast vs interpolated).
    - Kinematic transit speed and telemetry continuity/gaps.
    - Explicit closing scientific caveat disclaiming proof of causation.

    Args:
        candidate: The AttributedCandidate to explain.
        origin: OriginMetadata containing estimated spill parameters.
        confidence_tier: Classified analytical confidence tier.
        config_summary: Optional configuration dictionary.

    Returns:
        Structured narrative string.
    """
    vessel = candidate.vessel
    score = candidate.score
    evidence = candidate.evidence
    cfg = config_summary or {}
    gap_threshold_sec = float(cfg.get("gap_threshold_seconds", 1800.0))

    sentences: List[str] = []

    # 1. Vessel identification and ranking
    vname = vessel.vessel_name.strip() if vessel.vessel_name else None
    if vname:
        identity_part = f"{vname} (MMSI: {vessel.mmsi})"
    else:
        identity_part = f"Candidate vessel (MMSI: {vessel.mmsi})"

    vtype = str(vessel.vessel_type or "").strip()
    type_clause = f", reporting as '{vtype}'," if vtype else ""

    sentences.append(
        f"{identity_part}{type_clause} was ranked #{candidate.rank} with an analytical attribution "
        f"score of {score.overall_score:.4f} ({confidence_tier})."
    )

    # 2. Spatial encounter
    d_min = evidence.min_distance_km if evidence.min_distance_km is not None else vessel.min_distance_km
    radius = float(origin.radius_km)
    if d_min is not None and np.isfinite(d_min):
        if radius > 0.0 and d_min <= radius:
            sentences.append(
                f"Its reconstructed trajectory reached a closest approach of {d_min:.2f} km from the estimated "
                f"release origin, within the evaluated uncertainty envelope (radius: {radius:.2f} km)."
            )
        elif radius > 0.0:
            sentences.append(
                f"Its reconstructed trajectory reached a closest approach of {d_min:.2f} km from the estimated "
                f"release origin, remaining outside the uncertainty envelope (radius: {radius:.2f} km)."
            )
        else:
            sentences.append(
                f"Its reconstructed trajectory reached a closest approach of {d_min:.2f} km from the estimated "
                f"release origin."
            )

    # 3. Temporal encounter & CPA provenance
    t_cpa = evidence.time_of_closest_approach or vessel.closest_approach_time
    dt_sec = evidence.time_difference_seconds
    is_cpa_interp = evidence.evidence_metadata.get("closest_approach_is_interpolated")

    if t_cpa is not None and dt_sec is not None and np.isfinite(dt_sec):
        abs_dt_min = abs(float(dt_sec)) / 60.0
        fix_provenance = (
            "derived from an interpolated fix"
            if is_cpa_interp is True
            else "recorded by a direct broadcast fix"
            if is_cpa_interp is False
            else "calculated from vessel trajectory"
        )
        sentences.append(
            f"The closest approach occurred at {t_cpa.strftime('%Y-%m-%dT%H:%M:%SZ')} ({fix_provenance}), "
            f"approximately {abs_dt_min:.1f} minutes from the estimated release time."
        )
    elif t_cpa is not None:
        sentences.append(f"The closest approach occurred at {t_cpa.strftime('%Y-%m-%dT%H:%M:%SZ')}.")

    # 4. Kinematics and Telemetry Continuity
    kinematic_parts: List[str] = []
    mean_sog = evidence.mean_speed_knots if evidence.mean_speed_knots is not None else vessel.mean_sog_knots
    if mean_sog is not None and np.isfinite(mean_sog):
        kinematic_parts.append(f"mean transit speed was {mean_sog:.1f} knots")

    gap_count = int(evidence.ais_gap_count)
    if gap_count == 0:
        kinematic_parts.append("AIS telemetry was continuous throughout the encounter")
    else:
        gap_min = gap_threshold_sec / 60.0
        kinematic_parts.append(f"telemetry contained {gap_count} interval(s) exceeding {gap_min:.0f} minutes")

    if kinematic_parts:
        sentences.append(f"During the observation window, {', and '.join(kinematic_parts)}.")

    # 5. Scientific Non-Causation Caveat
    if confidence_tier == ConfidenceTier.HIGH_CONFIDENCE.value:
        caveat = "These observations indicate strong analytical correlation with the evaluated origin and time window; they do not establish that the vessel caused the spill."
    elif confidence_tier == ConfidenceTier.MODERATE_CONFIDENCE.value:
        caveat = "These observations indicate moderate analytical correlation with the evaluated encounter parameters; they do not establish that the vessel caused the spill."
    elif confidence_tier == ConfidenceTier.LOW_CONFIDENCE.value:
        caveat = "These observations reflect weak analytical correlation with the evaluated encounter window; they do not establish that the vessel caused the spill."
    else:
        caveat = "These observations reflect negligible analytical correlation with the evaluated release origin; they do not establish that the vessel caused the spill."

    sentences.append(caveat)

    return " ".join(sentences)


def generate_comparative_note(
    candidate: AttributedCandidate,
    next_candidate: Optional[AttributedCandidate],
) -> Optional[str]:
    """Generate a deterministic comparative note contrasting a candidate with the next ranked vessel.

    Only states distinctions that are directly substantiated by ATTR-02 scores and evidence.
    If candidates are identical across evaluated score dimensions, explicitly states that
    ordering is determined by deterministic tie-breaking rather than inventing differences.

    Args:
        candidate: Higher-ranked candidate.
        next_candidate: Immediately succeeding candidate (Rank + 1), or None if last rank.

    Returns:
        Comparative statement string, or None if no comparison is applicable.
    """
    if next_candidate is None:
        if candidate.rank == 1:
            return "Rank #1: Highest analytical score among all evaluated candidate vessels."
        return None

    c1 = candidate
    c2 = next_candidate

    s1 = c1.score
    s2 = c2.score
    e1 = c1.evidence
    e2 = c2.evidence

    target_label = (
        f"Candidate #{c2.rank} ({c2.vessel.vessel_name})"
        if c2.vessel.vessel_name
        else f"Candidate #{c2.rank} (MMSI: {c2.vessel.mmsi})"
    )

    # Check for exact score tie across all dimensions
    is_tied = (
        abs(s1.overall_score - s2.overall_score) < 1e-6
        and (s1.spatial_score == s2.spatial_score)
        and (s1.temporal_score == s2.temporal_score)
        and (s1.trajectory_score == s2.trajectory_score)
        and (s1.behaviour_score == s2.behaviour_score)
    )

    if is_tied:
        return (
            f"Ranked above {target_label} based on deterministic tie-breaking (MMSI ordering); "
            f"scores across all evaluated dimensions are identical."
        )

    reasons: List[str] = []

    # 1. Spatial comparison
    spat1 = s1.spatial_score or 0.0
    spat2 = s2.spatial_score or 0.0
    d1 = e1.min_distance_km if e1.min_distance_km is not None else c1.vessel.min_distance_km
    d2 = e2.min_distance_km if e2.min_distance_km is not None else c2.vessel.min_distance_km

    if spat1 > spat2 + 0.01 and d1 is not None and d2 is not None:
        reasons.append(f"closer spatial proximity ({d1:.2f} km vs {d2:.2f} km)")

    # 2. Temporal comparison
    temp1 = s1.temporal_score or 0.0
    temp2 = s2.temporal_score or 0.0
    dt1 = abs(e1.time_difference_seconds) if e1.time_difference_seconds is not None else None
    dt2 = abs(e2.time_difference_seconds) if e2.time_difference_seconds is not None else None

    if temp1 > temp2 + 0.01 and dt1 is not None and dt2 is not None:
        reasons.append(f"closer temporal alignment ({dt1/60:.1f} min vs {dt2/60:.1f} min)")

    # 3. Trajectory / Behaviour comparison
    traj1 = s1.trajectory_score or 0.0
    traj2 = s2.trajectory_score or 0.0
    if traj1 > traj2 + 0.05:
        reasons.append("stronger trajectory alignment")

    beh1 = s1.behaviour_score or 0.0
    beh2 = s2.behaviour_score or 0.0
    if beh1 > beh2 + 0.05:
        reasons.append("more consistent transit behaviour")

    if reasons:
        return f"Ranked above {target_label} primarily due to {', and '.join(reasons)}."

    # General score difference fallback
    diff = s1.overall_score - s2.overall_score
    return f"Ranked above {target_label} due to a higher overall analytical score (+{diff:.4f})."


def generate_incident_summary(
    result: AttributionResult,
    top_n: int = 5,
) -> str:
    """Generate an executive summary of the attribution run and evaluated candidate fleet."""
    tot_obs = int(result.report.total_input_observations)
    tot_cand = int(result.report.total_candidate_vessels)
    origin = result.origin_metadata

    lat_str = f"{origin.latitude:.5f}°"
    lon_str = f"{origin.longitude:.5f}°"
    ts_str = origin.timestamp.strftime("%Y-%m-%d %H:%M:%SZ")
    radius_str = f"{origin.radius_km:.2f} km"

    if tot_cand == 0:
        return (
            f"Evaluated {tot_obs} AIS observation(s) against estimated spill release origin at "
            f"Latitude {lat_str}, Longitude {lon_str} (time: {ts_str}, uncertainty radius: {radius_str}). "
            f"No candidate vessels met the spatio-temporal filtering criteria within the evaluated domain."
        )

    # Count candidates by score tier
    high_count = sum(1 for c in result.ranked_candidates if c.score.overall_score >= 0.80)
    mod_count = sum(1 for c in result.ranked_candidates if 0.50 <= c.score.overall_score < 0.80)
    low_count = sum(1 for c in result.ranked_candidates if c.score.overall_score < 0.50)

    top_n_count = min(top_n, tot_cand)
    summary_parts = [
        f"Evaluated {tot_obs:,} AIS observations across {tot_cand} candidate vessels against estimated spill release "
        f"origin ({lat_str}, {lon_str}) at {ts_str} (uncertainty radius: {radius_str}).",
        f"Analytical evaluation identified {high_count} high-confidence candidate(s), {mod_count} moderate-confidence "
        f"candidate(s), and {low_count} low/negligible-correlation candidate(s).",
    ]

    if top_n_count > 0:
        summary_parts.append(f"Detailed explainability dossiers are provided for the top {top_n_count} candidates.")

    return " ".join(summary_parts)
