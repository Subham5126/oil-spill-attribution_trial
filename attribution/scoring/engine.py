"""Attribution Scoring Engine.

Orchestrates multi-criteria evidence scoring, adaptive weight re-normalization,
deterministic 4-tier ranking, and explainable evidence generation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from attribution.models import (
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
from attribution.scoring.config import AttributionScoringConfig
from attribution.scoring.spatial import calculate_spatial_score, find_closest_approach
from attribution.scoring.temporal import calculate_temporal_score, resolve_time_of_closest_approach
from attribution.scoring.trajectory import (
    analyze_ais_gaps,
    calculate_trajectory_score,
    calculate_behaviour_score,
    determine_vessel_direction,
)


def _generate_evidence_factors(
    vessel: CandidateVessel,
    min_dist_km: float,
    origin_radius_km: float,
    time_diff_sec: float,
    vessel_dir_deg: Optional[float],
    explicit_drift_deg: Optional[float],
    traj_score: Optional[float],
    mean_speed: Optional[float],
    gap_count: int,
    max_gap_min: float,
    interpolated_ratio: float,
    cpa_is_interp: bool,
) -> Tuple[List[str], List[str], Optional[str], Optional[str], Optional[str]]:
    """Generate deterministic, reproducible supporting and contradicting factors."""
    supporting: List[str] = []
    contradicting: List[str] = []

    # 1. Spatial proximity evidence
    if min_dist_km <= origin_radius_km:
        spatial_notes = (
            f"Closest approach of {min_dist_km:.2f} km entered the release origin "
            f"uncertainty zone ({origin_radius_km:.1f} km)"
        )
        supporting.append(spatial_notes)
    elif min_dist_km <= 5.0:
        spatial_notes = f"Passed within {min_dist_km:.2f} km of release origin"
        supporting.append(spatial_notes)
    else:
        spatial_notes = f"Closest approach occurred at {min_dist_km:.2f} km from release origin"
        if min_dist_km > 15.0:
            contradicting.append(f"Remained distant from release origin ({min_dist_km:.2f} km)")

    # 2. Temporal compatibility evidence
    time_min = time_diff_sec / 60.0
    if time_diff_sec <= 1800.0:
        temporal_notes = f"Timing coincided within {time_min:.1f} minutes of estimated release time"
        supporting.append(temporal_notes)
    else:
        time_hours = time_diff_sec / 3600.0
        temporal_notes = f"Closest approach offset by {time_hours:.1f} hours from estimated release time"
        if time_diff_sec > 3600.0:
            contradicting.append(f"Closest approach occurred {time_hours:.1f} hours away from estimated release time")

    # 3. Trajectory & Direction evidence
    if explicit_drift_deg is not None and vessel_dir_deg is not None and traj_score is not None:
        if traj_score >= 0.80:
            supporting.append(
                f"Course over ground ({vessel_dir_deg:.1f}°) strongly aligned with explicit drift vector ({explicit_drift_deg:.1f}°)"
            )
        elif traj_score <= 0.20:
            contradicting.append("Vessel trajectory opposed the explicit drift vector")

    # 4. Telemetry continuity & gaps (strictly neutral language)
    if gap_count == 0 and vessel.total_observations >= 10:
        supporting.append("Continuous unbroken AIS telemetry throughout encounter")
    elif gap_count >= 1:
        gap_msg = f"AIS telemetry gap of {max_gap_min:.1f} minutes occurred during observation period"
        contradicting.append(gap_msg)

    # 5. Speed evidence
    speed_notes: Optional[str] = None
    if mean_speed is not None:
        speed_notes = f"Mean transit speed {mean_speed:.1f} knots"
        if mean_speed < 0.5:
            contradicting.append("Vessel was stationary or drifting during observation window")

    # 6. Interpolation provenance (uncertainty factor, never treated as misconduct)
    if interpolated_ratio > 0.50:
        contradicting.append(f"Trajectory reconstruction relied heavily on interpolation ({interpolated_ratio:.1%})")

    # 7. Vessel Context
    vtype_str = str(vessel.vessel_type or "Unknown")
    relevance_str = "Standard commercial vessel"
    if any(k in vtype_str.lower() for k in ["tanker", "crude", "oil", "product", "chemical"]):
        relevance_str = f"High carrying capacity ({vtype_str})"
        supporting.append(f"Vessel type '{vtype_str}' indicates hydrocarbon carrying capacity")
    elif any(k in vtype_str.lower() for k in ["cargo", "container", "bulk"]):
        relevance_str = f"Moderate carrying capacity ({vtype_str})"

    return supporting, contradicting, spatial_notes, temporal_notes, speed_notes


def score_candidates(
    data: Union[pd.DataFrame, Any],
    origin_data: Union[OriginMetadata, Any],
    config: Optional[AttributionScoringConfig] = None,
) -> AttributionResult:
    """Evaluate and rank candidate vessels using multi-criteria attribution scoring.

    Follows the approved ATTR-02 specification:
    - Piecewise-linear spatial decay with uncertainty plateau.
    - Piecewise-linear temporal decay with acceptable window plateau.
    - Directional trajectory alignment using EXPLICIT drift vectors only (never inferred from spill_obs).
    - Deterministic 3-tier speed handling (observed -> derived -> neutral 0.70).
    - Neutral telemetry continuity and gap analysis.
    - Adaptive weight re-normalization when sub-scores are unavailable.
    - Complete 4-tier deterministic ranking:
        1. overall_score DESC
        2. spatial_score DESC (None treated as -1.0 for sort only)
        3. temporal_score DESC (None treated as -1.0 for sort only)
        4. MMSI ASC
    - Preserves None values in stored VesselScore objects.

    Args:
        data: Filtered AIS observations (DataFrame or filter result).
        origin_data: Spill release origin metadata (OriginMetadata or dict).
        config: Optional AttributionScoringConfig.

    Returns:
        AttributionResult: Deterministic ranked result container.
    """
    # 1. Validate inputs
    df_validated = validate_ais_observations(data)
    origin_meta = validate_origin_metadata(origin_data)

    if config is None:
        config = AttributionScoringConfig()

    execution_notes: List[str] = []

    # Handle zero candidates edge-case
    if df_validated.empty:
        report = AttributionReport(
            total_input_observations=0,
            total_candidate_vessels=0,
            evaluation_timestamp=pd.Timestamp.now(tz="UTC").isoformat(),
            origin_timestamp=origin_meta.timestamp.isoformat(),
            origin_center=(origin_meta.latitude, origin_meta.longitude),
            origin_radius_km=origin_meta.radius_km,
            execution_notes=["Input observation dataset is empty. Zero candidate vessels evaluated."],
        )
        return AttributionResult(
            ranked_candidates=[],
            origin_metadata=origin_meta,
            report=report,
            config_summary=config.to_dict(),
        )

    # 2. Extract CandidateVessel baseline metadata
    candidate_vessels_list = extract_candidate_vessels(df_validated)
    vessels_by_mmsi = {v.mmsi: v for v in candidate_vessels_list}

    # 3. Check for explicit drift direction (CRITICAL: NEVER infer from spill_observation)
    explicit_drift_deg: Optional[float] = None
    if isinstance(origin_meta.source_info, dict):
        raw_drift = origin_meta.source_info.get("drift_direction_deg")
        if raw_drift is None:
            raw_drift = origin_meta.source_info.get("explicit_drift_direction_deg")
        if raw_drift is not None and isinstance(raw_drift, (int, float, np.integer, np.floating)) and np.isfinite(raw_drift):
            explicit_drift_deg = float(raw_drift) % 360.0

    unattributed_list: List[AttributedCandidate] = []

    # 4. Score each candidate vessel
    for mmsi, df_vessel in df_validated.groupby("mmsi"):
        mmsi_int = int(mmsi)
        vessel_obj = vessels_by_mmsi[mmsi_int]

        # A. Spatial Scoring
        min_dist_km, cpa_row, is_cpa_interp = find_closest_approach(
            df_vessel=df_vessel,
            origin_lat=origin_meta.latitude,
            origin_lon=origin_meta.longitude,
            origin_timestamp=origin_meta.timestamp,
        )
        spatial_score = calculate_spatial_score(
            min_distance_km=min_dist_km,
            origin_radius_km=origin_meta.radius_km,
            max_distance_km=config.max_distance_km,
            decay_method=config.spatial_decay,
        )

        # B. Temporal Scoring
        t_cpa, time_diff_sec, _ = resolve_time_of_closest_approach(
            df_vessel=df_vessel,
            origin_timestamp=origin_meta.timestamp,
            origin_lat=origin_meta.latitude,
            origin_lon=origin_meta.longitude,
        )
        temporal_score = calculate_temporal_score(
            time_diff_seconds=time_diff_sec,
            acceptable_window_seconds=config.acceptable_window_seconds,
            max_time_diff_seconds=config.max_time_diff_seconds,
            decay_method=config.temporal_decay,
        )

        # C. Trajectory Scoring
        vessel_dir_deg = determine_vessel_direction(df_vessel, cpa_timestamp=t_cpa)
        track_intersects_origin = bool(min_dist_km <= origin_meta.radius_km)
        trajectory_score = calculate_trajectory_score(
            vessel_direction_deg=vessel_dir_deg,
            explicit_drift_direction_deg=explicit_drift_deg,
            trajectory_intersects_origin=track_intersects_origin,
            spatial_score=spatial_score,
        )

        # D. Behaviour Scoring
        behaviour_score = calculate_behaviour_score(
            df_vessel=df_vessel,
            origin_radius_km=origin_meta.radius_km,
            config=config,
        )

        # E. Adaptive Weight Re-Normalization
        active_scores = [
            (config.spatial_weight, spatial_score),
            (config.temporal_weight, temporal_score),
            (config.trajectory_weight, trajectory_score),
            (config.behaviour_weight, behaviour_score),
        ]

        active_sum = sum(w for w, s in active_scores if s is not None)
        if active_sum > 0.0:
            overall_score = sum((w / active_sum) * s for w, s in active_scores if s is not None)
            overall_score = float(max(0.0, min(1.0, overall_score)))
        else:
            overall_score = 0.0

        vessel_score = VesselScore(
            spatial_score=spatial_score,
            temporal_score=temporal_score,
            trajectory_score=trajectory_score,
            behaviour_score=behaviour_score,
            overall_score=round(overall_score, 4),
        )

        # F. Assemble AttributionEvidence
        gap_count, _, max_gap_min = analyze_ais_gaps(
            df_vessel=df_vessel,
            origin_radius_km=origin_meta.radius_km,
            gap_threshold_seconds=config.gap_threshold_seconds,
        )

        interp_ratio = (
            float(vessel_obj.interpolated_observations) / float(vessel_obj.total_observations)
            if vessel_obj.total_observations > 0
            else 0.0
        )

        (
            supp_factors,
            contra_factors,
            spat_notes,
            temp_notes,
            speed_notes,
        ) = _generate_evidence_factors(
            vessel=vessel_obj,
            min_dist_km=min_dist_km,
            origin_radius_km=origin_meta.radius_km,
            time_diff_sec=time_diff_sec,
            vessel_dir_deg=vessel_dir_deg,
            explicit_drift_deg=explicit_drift_deg,
            traj_score=trajectory_score,
            mean_speed=vessel_obj.mean_sog_knots,
            gap_count=gap_count,
            max_gap_min=max_gap_min,
            interpolated_ratio=interp_ratio,
            cpa_is_interp=is_cpa_interp,
        )

        evidence = AttributionEvidence(
            min_distance_km=min_dist_km,
            time_of_closest_approach=t_cpa,
            time_difference_seconds=time_diff_sec,
            spatial_proximity_notes=spat_notes,
            temporal_alignment_notes=temp_notes,
            trajectory_consistency_score=trajectory_score,
            movement_direction_deg=vessel_dir_deg,
            heading_drift_alignment_deg=explicit_drift_deg,
            mean_speed_knots=vessel_obj.mean_sog_knots,
            speed_consistency_notes=speed_notes,
            telemetry_continuity=1.0 if gap_count == 0 else 0.5,
            ais_gap_count=gap_count,
            interpolated_ratio=interp_ratio,
            vessel_type_relevance=str(vessel_obj.vessel_type or "Unknown"),
            supporting_factors=supp_factors,
            contradicting_factors=contra_factors,
            evidence_metadata={
                "closest_approach_is_interpolated": is_cpa_interp,
                "explicit_drift_used": explicit_drift_deg is not None,
            },
        )

        # Temporary rank placeholder
        unattributed_list.append(
            AttributedCandidate(
                rank=1,
                vessel=vessel_obj,
                score=vessel_score,
                evidence=evidence,
            )
        )

    # 5. Complete 4-tier Deterministic Ranking
    # 1. overall_score DESC
    # 2. spatial_score DESC (None treated as -1.0 for comparison only)
    # 3. temporal_score DESC (None treated as -1.0 for comparison only)
    # 4. MMSI ASC
    def _rank_key(cand: AttributedCandidate) -> Tuple[float, float, float, int]:
        s = cand.score
        spat_val = float(s.spatial_score) if s.spatial_score is not None else -1.0
        temp_val = float(s.temporal_score) if s.temporal_score is not None else -1.0
        return (-float(s.overall_score), -spat_val, -temp_val, int(cand.vessel.mmsi))

    sorted_candidates = sorted(unattributed_list, key=_rank_key)

    # Assign sequential 1-based ranks
    ranked_candidates: List[AttributedCandidate] = []
    for rank_idx, cand in enumerate(sorted_candidates, start=1):
        ranked_candidates.append(
            AttributedCandidate(
                rank=rank_idx,
                vessel=cand.vessel,
                score=cand.score,  # Stored score preserves None!
                evidence=cand.evidence,
            )
        )

    # 6. Audit report
    report = AttributionReport(
        total_input_observations=len(df_validated),
        total_candidate_vessels=len(ranked_candidates),
        evaluation_timestamp=pd.Timestamp.now(tz="UTC").isoformat(),
        origin_timestamp=origin_meta.timestamp.isoformat(),
        origin_center=(origin_meta.latitude, origin_meta.longitude),
        origin_radius_km=origin_meta.radius_km,
        execution_notes=execution_notes,
    )

    return AttributionResult(
        ranked_candidates=ranked_candidates,
        origin_metadata=origin_meta,
        report=report,
        config_summary=config.to_dict(),
    )


# Canonical public alias
attribute_vessels = score_candidates
