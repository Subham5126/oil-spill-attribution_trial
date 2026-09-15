"""Scientific Vessel Attribution Confidence Scoring Service.

Computes normalized 0-100 attribution confidence scores, 5-tier confidence levels
(VERY HIGH, HIGH, MODERATE, LOW, VERY LOW), and factor-level explainability
grounded in spatial, temporal, drift, kinematics, vessel particulars, and AIS quality.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union


def get_vessel_type_relevance(vessel_type: Optional[Union[str, int]]) -> Optional[float]:
    """Assess vessel type relevance for marine hydrocarbon discharge."""
    if vessel_type is None:
        return None

    vt_str = str(vessel_type).upper()

    # AIS numerical type code ranges
    # 80-89: Tankers
    # 70-79: Cargo
    # 52: Tugs
    # 30: Fishing
    # 60-69: Passenger
    try:
        code = int(vessel_type)
        if 80 <= code <= 89:
            return 1.0  # Tanker
        if 70 <= code <= 79:
            return 0.85  # Cargo
        if code == 52 or 50 <= code <= 59:
            return 0.60  # Tug / Special craft
        if code == 30 or 31 <= code <= 39:
            return 0.45  # Fishing
        if 60 <= code <= 69:
            return 0.35  # Passenger
        if 36 <= code <= 37:
            return 0.20  # Pleasure / Sailing
    except (ValueError, TypeError):
        pass

    if any(k in vt_str for k in ["TANKER", "CRUDE", "OIL", "CHEMICAL", "BUNKER"]):
        return 1.0
    if any(k in vt_str for k in ["CARGO", "CONTAINER", "BULK", "FREIGHTER", "CARRIER"]):
        return 0.85
    if any(k in vt_str for k in ["TUG", "OFFSHORE", "SUPPLY", "DREDGER", "SERVICE"]):
        return 0.60
    if any(k in vt_str for k in ["FISH", "TRAWLER"]):
        return 0.45
    if any(k in vt_str for k in ["PASSENGER", "FERRY", "CRUISE"]):
        return 0.35
    if any(k in vt_str for k in ["PLEASURE", "YACHT", "SAIL"]):
        return 0.20

    return 0.50


def resolve_confidence_level(score: float) -> str:
    """Map 0-100 confidence score to canonical 5-tier classification."""
    if score >= 90.0:
        return "VERY HIGH"
    if score >= 75.0:
        return "HIGH"
    if score >= 50.0:
        return "MODERATE"
    if score >= 25.0:
        return "LOW"
    return "VERY LOW"


def get_active_calibration_weights(db: Optional[Any] = None) -> Tuple[str, Dict[str, float]]:
    """Retrieve active calibration version and weights from database, with robust fallback."""
    default_weights = {
        "spatial_proximity": 0.35,
        "temporal_overlap": 0.25,
        "drift_consistency": 0.15,
        "track_consistency": 0.10,
        "vessel_type_relevance": 0.08,
        "ais_quality": 0.07,
    }
    if db is not None:
        try:
            from backend.models.settings import AttributionCalibrationModel
            active = db.query(AttributionCalibrationModel).filter_by(is_active=True).first()
            if active:
                return active.version, active.to_weights_dict()
        except Exception:
            pass
    return "CALIB-v1-DEFAULT", default_weights


def compute_vessel_confidence(
    spatial_score: Optional[float] = None,
    temporal_score: Optional[float] = None,
    trajectory_score: Optional[float] = None,
    behaviour_score: Optional[float] = None,
    overall_score: Optional[float] = None,
    min_distance_km: Optional[float] = None,
    time_difference_minutes: Optional[float] = None,
    vessel_type: Optional[Union[str, int]] = None,
    transit_speed_knots: Optional[float] = None,
    ais_gap_count: int = 0,
    max_gap_minutes: float = 0.0,
    total_observations: Optional[int] = None,
    origin_uncertainty_radius_km: Optional[float] = None,
    weights: Optional[Dict[str, float]] = None,
    calibration_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Derive evidence-grounded Attribution Confidence Score (0-100) and factor breakdown.

    Normalizes across available evidence without penalizing missing non-critical telemetry.
    """
    factors: Dict[str, Optional[float]] = {}
    supporting: List[str] = []
    limitations: List[str] = []

    # 1. Spatial Proximity Factor
    if spatial_score is not None and 0.0 <= spatial_score <= 1.0:
        factors["spatial_proximity"] = round(float(spatial_score), 4)
    elif min_distance_km is not None:
        radius = origin_uncertainty_radius_km or 2.5
        if min_distance_km <= radius:
            factors["spatial_proximity"] = 1.0
        else:
            factors["spatial_proximity"] = max(0.05, round(1.0 - (min_distance_km - radius) / 35.0, 4))
    else:
        factors["spatial_proximity"] = None
        limitations.append("Spatial distance metric not available")

    if min_distance_km is not None:
        if min_distance_km <= 2.0:
            supporting.append(f"Passed within {min_distance_km:.2f} km of probable discharge origin")
        elif min_distance_km <= 5.0:
            supporting.append(f"Operating in close proximity ({min_distance_km:.2f} km) to estimated release zone")
        elif min_distance_km > 15.0:
            limitations.append(f"Vessel remained distant ({min_distance_km:.2f} km) from estimated discharge origin")

    # 2. Temporal Overlap Factor
    if temporal_score is not None and 0.0 <= temporal_score <= 1.0:
        factors["temporal_overlap"] = round(float(temporal_score), 4)
    elif time_difference_minutes is not None:
        abs_dt = abs(time_difference_minutes)
        if abs_dt <= 30.0:
            factors["temporal_overlap"] = 1.0
        else:
            factors["temporal_overlap"] = max(0.05, round(1.0 - (abs_dt - 30.0) / 240.0, 4))
    else:
        factors["temporal_overlap"] = None
        limitations.append("Temporal arrival offset not available")

    if time_difference_minutes is not None:
        abs_dt = abs(time_difference_minutes)
        if abs_dt <= 30.0:
            supporting.append(f"Timing closely aligned (within {abs_dt:.0f} min) of estimated release window")
        elif abs_dt <= 90.0:
            supporting.append(f"Presence recorded within {abs_dt / 60.0:.1f} hours of estimated release")
        elif abs_dt > 180.0:
            limitations.append(f"Approach occurred {abs_dt / 60.0:.1f} hours away from estimated release")

    # 3. Drift Consistency Factor
    if trajectory_score is not None and 0.0 <= trajectory_score <= 1.0:
        factors["drift_consistency"] = round(float(trajectory_score), 4)
        if trajectory_score >= 0.75:
            supporting.append("Course and track strongly compatible with hydrodynamic drift corridor")
        elif trajectory_score < 0.3:
            limitations.append("Vessel track poorly aligned with hydrodynamic drift vector")
    else:
        factors["drift_consistency"] = None
        limitations.append("Hydrodynamic trajectory alignment not computed")

    # 4. Track / Behaviour Consistency Factor
    if behaviour_score is not None and 0.0 <= behaviour_score <= 1.0:
        factors["track_consistency"] = round(float(behaviour_score), 4)
    else:
        factors["track_consistency"] = None

    if transit_speed_knots is not None and transit_speed_knots > 0:
        if 4.0 <= transit_speed_knots <= 18.0:
            supporting.append(f"Normal transit speed maintained ({transit_speed_knots:.1f} knots)")
        elif transit_speed_knots < 3.0:
            supporting.append(f"Low speed or loitering detected ({transit_speed_knots:.1f} knots)")

    # 5. Vessel Type Relevance
    vt_relevance = get_vessel_type_relevance(vessel_type)
    factors["vessel_type_relevance"] = vt_relevance
    if vt_relevance is not None:
        if vt_relevance >= 0.85:
            supporting.append("Vessel category (Tanker / Cargo) carries significant fuel or liquid cargo")
        elif vt_relevance <= 0.40:
            limitations.append("Vessel category carries lower characteristic discharge potential")
    else:
        limitations.append("Vessel type unverified in static AIS records")

    # 6. AIS Quality & Continuity
    if total_observations is not None or ais_gap_count > 0:
        if ais_gap_count == 0 and (total_observations or 0) >= 10:
            factors["ais_quality"] = 1.0
            supporting.append("Continuous unbroken AIS transponder telemetry throughout encounter")
        elif ais_gap_count > 0:
            penalty = min(0.6, max_gap_minutes / 180.0)
            factors["ais_quality"] = round(max(0.2, 1.0 - penalty), 4)
            limitations.append(f"AIS telemetry gap recorded ({max_gap_minutes:.0f} min)")
        else:
            factors["ais_quality"] = 0.70
    else:
        factors["ais_quality"] = 0.85  # Default nominal assumption if count not reported

    # Analytical component weights (use dynamic calibrated weights if supplied)
    base_weights = {
        "spatial_proximity": 0.35,
        "temporal_overlap": 0.25,
        "drift_consistency": 0.15,
        "track_consistency": 0.10,
        "vessel_type_relevance": 0.08,
        "ais_quality": 0.07,
    }
    active_weights = weights or base_weights

    # Normalize weights across available (non-None) factors
    valid_factors = {k: v for k, v in factors.items() if v is not None}
    weight_sum = sum(active_weights.get(k, 0.0) for k in valid_factors)

    if weight_sum > 0:
        composite_ratio = sum(valid_factors[k] * active_weights.get(k, 0.0) for k in valid_factors) / weight_sum
    elif overall_score is not None:
        composite_ratio = float(overall_score)
    else:
        composite_ratio = 0.0

    # If explicit overall score was provided, blend harmoniously (70% factor composite + 30% overall)
    if overall_score is not None and 0.0 <= overall_score <= 1.0:
        final_ratio = 0.70 * composite_ratio + 0.30 * float(overall_score)
    else:
        final_ratio = composite_ratio

    final_score = round(max(0.0, min(100.0, final_ratio * 100.0)), 1)
    level = resolve_confidence_level(final_score)

    return {
        "confidence_score": final_score,
        "confidence_level": level,
        "calibration_version": calibration_version or "CALIB-v1-DEFAULT",
        "weights_used": {k: round(active_weights.get(k, 0.0), 4) for k in valid_factors},
        "confidence_factors": {
            "spatial_proximity": factors.get("spatial_proximity"),
            "temporal_overlap": factors.get("temporal_overlap"),
            "drift_consistency": factors.get("drift_consistency"),
            "track_consistency": factors.get("track_consistency"),
            "vessel_type_relevance": factors.get("vessel_type_relevance"),
            "ais_quality": factors.get("ais_quality"),
            "supporting": supporting,
            "limitations": limitations,
        },
    }
