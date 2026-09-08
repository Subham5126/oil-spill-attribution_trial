"""Factor synthesis, evidence categorization, and analytical confidence tier assignment (ATTR-03).

Interprets ATTR-02 quantitative metrics into neutral, factual supporting,
contradicting, and data-quality evidence factors.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from attribution.explanation.models import ConfidenceTier
from attribution.models import AttributedCandidate, OriginMetadata


def determine_confidence_tier(
    overall_score: float,
    min_distance_km: Optional[float] = None,
    time_diff_seconds: Optional[float] = None,
    max_distance_km: float = 25.0,
    max_time_diff_seconds: float = 7200.0,
) -> str:
    """Classify candidate attribution into an analytical confidence tier.

    Follows the approved specification:
    - overall_score >= 0.80: HIGH_CONFIDENCE
    - 0.50 <= overall_score < 0.80: MODERATE_CONFIDENCE
    - 0.20 <= overall_score < 0.50: LOW_CONFIDENCE
    - overall_score < 0.20: NEGLIGIBLE_CORRELATION

    Safety Override:
    If the candidate is beyond ATTR-02's configured maximum spatial distance
    (min_distance_km > max_distance_km) OR beyond the configured maximum temporal
    difference (|time_diff_seconds| > max_time_diff_seconds), its confidence must
    not exceed LOW_CONFIDENCE.

    IMPORTANT:
    These tiers are analytical correlation classifications. They are NOT
    probabilities and do NOT establish legal culpability or causation.
    """
    score = float(max(0.0, min(1.0, overall_score)))

    if score >= 0.80:
        base_tier = ConfidenceTier.HIGH_CONFIDENCE.value
    elif score >= 0.50:
        base_tier = ConfidenceTier.MODERATE_CONFIDENCE.value
    elif score >= 0.20:
        base_tier = ConfidenceTier.LOW_CONFIDENCE.value
    else:
        base_tier = ConfidenceTier.NEGLIGIBLE_CORRELATION.value

    # Safety override check
    exceeds_spatial = (
        min_distance_km is not None
        and np.isfinite(min_distance_km)
        and float(min_distance_km) > float(max_distance_km)
    )
    exceeds_temporal = (
        time_diff_seconds is not None
        and np.isfinite(time_diff_seconds)
        and abs(float(time_diff_seconds)) > float(max_time_diff_seconds)
    )

    if exceeds_spatial or exceeds_temporal:
        if base_tier in (
            ConfidenceTier.HIGH_CONFIDENCE.value,
            ConfidenceTier.MODERATE_CONFIDENCE.value,
        ):
            return ConfidenceTier.LOW_CONFIDENCE.value

    return base_tier


def synthesize_candidate_factors(
    candidate: AttributedCandidate,
    origin: OriginMetadata,
    config_summary: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], List[str], List[str]]:
    """Synthesize neutral, factual evidence factors from ATTR-02 candidate metrics.

    Categorizes evidence into:
    1. Supporting factors: Factual alignments with evaluated spill parameters.
    2. Contradicting / mitigating factors: Factual divergences, gaps, or peripheral metrics.
    3. Data-quality notes: Provenance, interpolation reliance, and telemetry coverage.

    Strict Neutrality Rules:
    - Never uses words indicating guilt, intent, evasion, illegal action, or causation.
    - AIS gaps indicate absent telemetry due to propagation/reception, never intent.
    - Interpolation represents mathematical estimation provenance, not misconduct.
    - Vessel type represents contextual cargo capacity, not direct evidence of release.

    Returns:
        Tuple of (supporting_factors, contradicting_factors, data_quality_notes).
    """
    cfg = config_summary or {}
    max_dist_km = float(cfg.get("max_distance_km", 25.0))
    acceptable_window_sec = float(cfg.get("acceptable_window_seconds", 1800.0))
    gap_threshold_sec = float(cfg.get("gap_threshold_seconds", 1800.0))

    vessel = candidate.vessel
    score = candidate.score
    evidence = candidate.evidence

    supporting: List[str] = []
    contradicting: List[str] = []
    quality_notes: List[str] = []

    # 1. Spatial Proximity Evidence
    d_min = evidence.min_distance_km if evidence.min_distance_km is not None else vessel.min_distance_km
    if d_min is not None and np.isfinite(d_min):
        radius = float(origin.radius_km)
        if radius > 0.0 and d_min <= radius:
            supporting.append(
                f"Trajectory intersected origin uncertainty envelope (CPA: {d_min:.2f} km <= radius: {radius:.2f} km)"
            )
        elif d_min <= max_dist_km:
            supporting.append(f"Closest point of approach was {d_min:.2f} km from estimated origin center")
        else:
            contradicting.append(
                f"Vessel remained beyond configured maximum evaluation distance ({d_min:.2f} km > {max_dist_km:.1f} km)"
            )

        if radius > 0.0 and d_min > radius:
            contradicting.append(
                f"Trajectory remained outside estimated origin uncertainty radius (CPA: {d_min:.2f} km > {radius:.2f} km)"
            )

    # 2. Temporal Alignment Evidence
    dt_sec = evidence.time_difference_seconds
    if dt_sec is not None and np.isfinite(dt_sec):
        abs_dt_sec = abs(float(dt_sec))
        abs_dt_min = abs_dt_sec / 60.0
        if abs_dt_sec <= acceptable_window_sec:
            supporting.append(
                f"Close temporal alignment: CPA occurred within {abs_dt_min:.1f} minutes of estimated release timestamp"
            )
        else:
            contradicting.append(
                f"Temporal divergence: CPA occurred {abs_dt_min:.1f} minutes outside acceptable release window"
            )

    # 3. Trajectory & Directional Consistency
    if score.trajectory_score is not None:
        traj_s = float(score.trajectory_score)
        if traj_s >= 0.70:
            supporting.append(f"Vessel transit geometry aligned with evaluated drift/encounter vector (score: {traj_s:.2f})")
        elif traj_s < 0.40:
            contradicting.append(f"Vessel transit heading diverged from evaluated drift vector (score: {traj_s:.2f})")

    # 4. Kinematic Behaviour Evidence
    mean_sog = evidence.mean_speed_knots if evidence.mean_speed_knots is not None else vessel.mean_sog_knots
    if mean_sog is not None and np.isfinite(mean_sog):
        if mean_sog >= 0.5:
            supporting.append(f"Maintained steady transit underway (mean speed: {mean_sog:.1f} knots)")
        else:
            contradicting.append("Vessel was stationary, moored, or drifting (< 0.5 knots) during encounter window")

    # 5. Telemetry Continuity & AIS Gaps
    gap_count = int(evidence.ais_gap_count)
    if gap_count == 0:
        supporting.append("Continuous AIS telemetry recorded across the evaluation encounter")
    else:
        gap_min = gap_threshold_sec / 60.0
        contradicting.append(f"Intermittent telemetry coverage: {gap_count} transmission interval(s) exceeded {gap_min:.0f} min")

    # 6. Vessel Context
    vtype_raw = str(vessel.vessel_type or "").strip()
    if vtype_raw:
        vtype_lower = vtype_raw.lower()
        if any(k in vtype_lower for k in ["tanker", "crude", "oil", "product", "chemical"]):
            supporting.append(f"Vessel classification '{vtype_raw}' indicates liquid hydrocarbon cargo capacity")
        elif any(k in vtype_lower for k in ["cargo", "container", "bulk", "carrier", "freighter"]):
            supporting.append(f"Commercial cargo vessel class '{vtype_raw}' carries substantial bunker fuel volume")
        elif any(k in vtype_lower for k in ["tug", "towing", "pilot", "passenger", "ferry", "pleasure", "yacht", "fishing"]):
            contradicting.append(f"Vessel classification '{vtype_raw}' has limited or non-bulk fuel/cargo profile")

    # 7. Data Quality and Provenance Notes
    tot_obs = int(vessel.total_observations)
    interp_obs = int(vessel.interpolated_observations)
    if tot_obs > 0:
        interp_ratio = float(interp_obs) / float(tot_obs)
        quality_notes.append(
            f"Observation composition: {tot_obs} total fixes ({vessel.actual_observations} broadcast, {interp_obs} interpolated, {interp_ratio:.1%} interpolation ratio)"
        )
        if interp_ratio > 0.50:
            quality_notes.append(f"Trajectory reconstruction relied predominantly on interpolation ({interp_ratio:.1%})")

    # CPA fix provenance
    is_cpa_interp = evidence.evidence_metadata.get("closest_approach_is_interpolated")
    if is_cpa_interp is True:
        quality_notes.append("Closest point of approach (CPA) was derived from an interpolated fix")
    elif is_cpa_interp is False:
        quality_notes.append("Closest point of approach (CPA) was verified by a direct broadcast AIS observation")

    if gap_count > 0:
        quality_notes.append(f"Encounter contains {gap_count} telemetry interval(s) exceeding {gap_threshold_sec/60:.0f} minutes")

    if mean_sog is None:
        quality_notes.append("Speed Over Ground (SOG) telemetry was missing or invalid in broadcast fixes")

    if evidence.movement_direction_deg is None:
        quality_notes.append("Kinematic course/heading could not be resolved from sparse fixes")

    return supporting, contradicting, quality_notes
