"""Attribution Data Models, Contracts, and Validation Layer.

Defines the strongly typed foundation for marine oil spill vessel attribution:
- CandidateVessel: Vessel identity, static metadata, and kinematic trajectory metrics.
- AttributionEvidence: Structured evidence dimensions for explainability (spatial,
  temporal, trajectory, behaviour, and telemetry continuity).
- VesselScore: Quantitative sub-scores and overall analytical ranking index.
- AttributedCandidate: Unified container pairing a candidate vessel, score, evidence, and rank.
- OriginMetadata: Standardized spill release origin envelope and uncertainty representation.
- AttributionReport: Audit metrics and execution summary for attribution runs.
- AttributionResult: Deterministic container holding ranked candidates, origin metadata,
  and audit reporting.
- Input validation and extraction functions for AIS-07 and Member 4 handoffs.

NOTE ON SCORING INTERPRETATION:
In accordance with ARCHITECTURE.md Section 12, vessel scores represent an analytical
ranking or confidence index. They must never be presented as statistical probabilities
of guilt or definitive legal proof of responsibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import math
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

import numpy as np
import pandas as pd

# Canonical geographic bounds (WGS84 EPSG:4326)
LAT_MIN: float = -90.0
LAT_MAX: float = 90.0
LON_MIN: float = -180.0
LON_MAX: float = 180.0

# Canonical AIS schema contracts for Attribution input
REQUIRED_AIS_COLUMNS: Set[str] = {
    "mmsi",
    "timestamp",
    "latitude",
    "longitude",
    "distance_km",
}

OPTIONAL_AIS_COLUMNS: Set[str] = {
    "sog",
    "cog",
    "heading",
    "vessel_name",
    "vessel_type",
    "imo",
    "callsign",
    "length",
    "width",
    "draft",
    "draught",
    "trajectory_segment_id",
    "is_interpolated",
    "interpolation_method",
}


def _validate_utc_timestamp(val: Any, field_name: str) -> pd.Timestamp:
    """Validate that a timestamp is non-null, parseable, and timezone-aware in UTC.

    Raises:
        ValueError: If timestamp is missing, null, NaT, unparseable, or timezone-naive.
    """
    if val is None or isinstance(val, bool):
        raise ValueError(f"{field_name} must be provided and non-null")

    try:
        ts = pd.Timestamp(val)
    except Exception as exc:
        raise ValueError(
            f"Invalid {field_name}: '{val}'. Could not parse datetime: {exc}"
        ) from exc

    if pd.isna(ts) or ts is pd.NaT:
        raise ValueError(f"Invalid {field_name}: value is null or NaT")

    if ts.tzinfo is None:
        raise ValueError(
            f"{field_name} must be timezone-aware (expected UTC), got naive timestamp '{val}'"
        )

    try:
        return ts.tz_convert("UTC")
    except Exception as exc:
        raise ValueError(
            f"Failed to convert {field_name} '{val}' to UTC: {exc}"
        ) from exc



def _is_finite_number(val: Any) -> bool:
    """Check if value is a finite int or float (not bool, not NaN, not Inf)."""
    if val is None or isinstance(val, bool):
        return False
    try:
        f = float(val)
        return bool(np.isfinite(f))
    except (TypeError, ValueError):
        return False


def _validate_score_value(val: Optional[float], field_name: str) -> Optional[float]:
    """Validate that a score is either None or a finite float in [0.0, 1.0]."""
    if val is None:
        return None
    if not _is_finite_number(val):
        raise ValueError(
            f"{field_name} must be a finite number in [0.0, 1.0], got {val}"
        )
    f_val = float(val)
    if not (0.0 <= f_val <= 1.0):
        raise ValueError(
            f"{field_name} must be within [0.0, 1.0], got {f_val}"
        )
    return f_val


@dataclass
class CandidateVessel:
    """Vessel-level representation of an AIS candidate.

    Distinct from row-level AIS observations, CandidateVessel represents a unique
    vessel (identified by MMSI) with static particulars and aggregated track summary.
    """

    mmsi: int
    vessel_name: Optional[str] = None
    vessel_type: Optional[Union[str, int]] = None
    imo: Optional[str] = None
    callsign: Optional[str] = None
    length: Optional[float] = None
    width: Optional[float] = None
    draft: Optional[float] = None
    total_observations: int = 0
    actual_observations: int = 0
    interpolated_observations: int = 0
    min_distance_km: Optional[float] = None
    closest_approach_time: Optional[pd.Timestamp] = None
    first_observed_time: Optional[pd.Timestamp] = None
    last_observed_time: Optional[pd.Timestamp] = None
    mean_sog_knots: Optional[float] = None
    segment_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validate MMSI
        if isinstance(self.mmsi, bool):
            raise ValueError(
                f"mmsi must be a valid positive integer, got boolean {self.mmsi}"
            )

        if isinstance(self.mmsi, (float, np.floating)):
            if not np.isfinite(self.mmsi) or not float(self.mmsi).is_integer():
                raise ValueError(
                    f"mmsi must be a non-fractional integer, got float {self.mmsi}"
                )

        try:
            mmsi_val = int(self.mmsi)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"mmsi must be a valid positive integer, got {self.mmsi}"
            ) from exc

        if isinstance(self.mmsi, str):
            try:
                f_val = float(self.mmsi)
                if not f_val.is_integer():
                    raise ValueError(f"mmsi must be an integer, got '{self.mmsi}'")
            except ValueError as exc:
                raise ValueError(
                    f"mmsi must be an integer, got '{self.mmsi}'"
                ) from exc

        self.mmsi = mmsi_val
        if self.mmsi <= 0:
            raise ValueError(f"mmsi must be a positive integer, got {self.mmsi}")

        # Handle draught alias in metadata if draft is None
        if self.draft is None and "draught" in self.metadata:
            self.draft = self.metadata.pop("draught")

        # Validate dimensional metrics
        for dim_name, dim_val in [
            ("length", self.length),
            ("width", self.width),
            ("draft", self.draft),
        ]:
            if dim_val is not None:
                if not _is_finite_number(dim_val) or float(dim_val) < 0.0:
                    raise ValueError(
                        f"{dim_name} must be a finite non-negative number, got {dim_val}"
                    )
                setattr(self, dim_name, float(dim_val))

        # Validate distance
        if self.min_distance_km is not None:
            if (
                not _is_finite_number(self.min_distance_km)
                or float(self.min_distance_km) < 0.0
            ):
                raise ValueError(
                    f"min_distance_km must be a finite non-negative number, got {self.min_distance_km}"
                )
            self.min_distance_km = float(self.min_distance_km)

        # Validate timestamps if provided
        if self.closest_approach_time is not None:
            self.closest_approach_time = _validate_utc_timestamp(
                self.closest_approach_time, "closest_approach_time"
            )
        if self.first_observed_time is not None:
            self.first_observed_time = _validate_utc_timestamp(
                self.first_observed_time, "first_observed_time"
            )
        if self.last_observed_time is not None:
            self.last_observed_time = _validate_utc_timestamp(
                self.last_observed_time, "last_observed_time"
            )

        # Validate counts as non-negative integers
        for count_name in [
            "total_observations",
            "actual_observations",
            "interpolated_observations",
        ]:
            count_val = getattr(self, count_name)
            if isinstance(count_val, bool) or not isinstance(
                count_val, (int, np.integer)
            ):
                raise ValueError(
                    f"{count_name} must be a non-negative integer, got {type(count_val).__name__} ({count_val})"
                )
            if int(count_val) < 0:
                raise ValueError(f"{count_name} must be non-negative, got {count_val}")
            setattr(self, count_name, int(count_val))

        # Validate mean SOG when supplied as finite and non-negative
        if self.mean_sog_knots is not None:
            if (
                not _is_finite_number(self.mean_sog_knots)
                or float(self.mean_sog_knots) < 0.0
            ):
                raise ValueError(
                    f"mean_sog_knots must be a finite non-negative number, got {self.mean_sog_knots}"
                )
            self.mean_sog_knots = float(self.mean_sog_knots)


    def to_dict(self) -> Dict[str, Any]:
        """Serialize CandidateVessel to a deterministic JSON-serializable dictionary."""
        return {
            "mmsi": int(self.mmsi),
            "vessel_name": str(self.vessel_name) if self.vessel_name is not None else None,
            "vessel_type": self.vessel_type,
            "imo": str(self.imo) if self.imo is not None else None,
            "callsign": str(self.callsign) if self.callsign is not None else None,
            "length": self.length,
            "width": self.width,
            "draft": self.draft,
            "total_observations": int(self.total_observations),
            "actual_observations": int(self.actual_observations),
            "interpolated_observations": int(self.interpolated_observations),
            "min_distance_km": self.min_distance_km,
            "closest_approach_time": (
                self.closest_approach_time.isoformat()
                if self.closest_approach_time is not None
                else None
            ),
            "first_observed_time": (
                self.first_observed_time.isoformat()
                if self.first_observed_time is not None
                else None
            ),
            "last_observed_time": (
                self.last_observed_time.isoformat()
                if self.last_observed_time is not None
                else None
            ),
            "mean_sog_knots": self.mean_sog_knots,
            "segment_ids": sorted(list(self.segment_ids)),
            "metadata": self.metadata,
        }


@dataclass
class AttributionEvidence:
    """Evidence container for vessel attribution explainability.

    Defines the multi-criteria structure representing:
    - Spatial proximity to probable release origin.
    - Temporal compatibility with estimated release time.
    - Trajectory consistency with drift hindcast vector.
    - Kinematic movement direction and speed evidence.
    - AIS telemetry continuity and coverage.
    - Vessel type and operational context evidence.

    NOTE: This is the structure contract only; calculation of evidence values
    is handled by downstream scoring and explanation components.
    """

    min_distance_km: Optional[float] = None
    time_of_closest_approach: Optional[pd.Timestamp] = None
    time_difference_seconds: Optional[float] = None
    spatial_proximity_notes: Optional[str] = None
    temporal_alignment_notes: Optional[str] = None
    trajectory_consistency_score: Optional[float] = None
    movement_direction_deg: Optional[float] = None
    heading_drift_alignment_deg: Optional[float] = None
    mean_speed_knots: Optional[float] = None
    speed_consistency_notes: Optional[str] = None
    telemetry_continuity: Optional[float] = None
    ais_gap_count: int = 0
    interpolated_ratio: Optional[float] = None
    vessel_type_relevance: Optional[str] = None
    supporting_factors: List[str] = field(default_factory=list)
    contradicting_factors: List[str] = field(default_factory=list)
    evidence_metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.min_distance_km is not None:
            if (
                not _is_finite_number(self.min_distance_km)
                or float(self.min_distance_km) < 0.0
            ):
                raise ValueError(
                    f"min_distance_km must be a finite non-negative number, got {self.min_distance_km}"
                )
            self.min_distance_km = float(self.min_distance_km)

        if self.time_of_closest_approach is not None:
            self.time_of_closest_approach = _validate_utc_timestamp(
                self.time_of_closest_approach, "time_of_closest_approach"
            )

        # Validate ratio/score fields if present
        for score_field in [
            "trajectory_consistency_score",
            "telemetry_continuity",
            "interpolated_ratio",
        ]:
            val = getattr(self, score_field)
            if val is not None:
                validated_val = _validate_score_value(val, score_field)
                setattr(self, score_field, validated_val)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize AttributionEvidence to a deterministic dictionary."""
        return {
            "min_distance_km": self.min_distance_km,
            "time_of_closest_approach": (
                self.time_of_closest_approach.isoformat()
                if self.time_of_closest_approach is not None
                else None
            ),
            "time_difference_seconds": self.time_difference_seconds,
            "spatial_proximity_notes": self.spatial_proximity_notes,
            "temporal_alignment_notes": self.temporal_alignment_notes,
            "trajectory_consistency_score": self.trajectory_consistency_score,
            "movement_direction_deg": self.movement_direction_deg,
            "heading_drift_alignment_deg": self.heading_drift_alignment_deg,
            "mean_speed_knots": self.mean_speed_knots,
            "speed_consistency_notes": self.speed_consistency_notes,
            "telemetry_continuity": self.telemetry_continuity,
            "ais_gap_count": int(self.ais_gap_count),
            "interpolated_ratio": self.interpolated_ratio,
            "vessel_type_relevance": self.vessel_type_relevance,
            "supporting_factors": list(self.supporting_factors),
            "contradicting_factors": list(self.contradicting_factors),
            "evidence_metadata": self.evidence_metadata,
        }


@dataclass
class VesselScore:
    """Quantitative attribution score representation for a candidate vessel.

    Attributes:
        spatial_score: Sub-score evaluating spatial proximity to origin [0.0, 1.0].
        temporal_score: Sub-score evaluating temporal alignment with release time [0.0, 1.0].
        trajectory_score: Sub-score evaluating kinematic consistency [0.0, 1.0].
        behaviour_score: Sub-score evaluating speed/heading/operational indicators [0.0, 1.0].
        overall_score: Composite analytical ranking and confidence index [0.0, 1.0].

    IMPORTANT INTERPRETATION RULE:
    overall_score represents an analytical ranking or confidence index. It is NOT a
    statistical probability of guilt and NOT definitive proof of legal responsibility.
    """

    spatial_score: Optional[float] = None
    temporal_score: Optional[float] = None
    trajectory_score: Optional[float] = None
    behaviour_score: Optional[float] = None
    overall_score: float = 0.0

    def __post_init__(self) -> None:
        self.spatial_score = _validate_score_value(self.spatial_score, "spatial_score")
        self.temporal_score = _validate_score_value(self.temporal_score, "temporal_score")
        self.trajectory_score = _validate_score_value(
            self.trajectory_score, "trajectory_score"
        )
        self.behaviour_score = _validate_score_value(
            self.behaviour_score, "behaviour_score"
        )
        self.overall_score = float(
            _validate_score_value(self.overall_score, "overall_score") or 0.0
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize VesselScore to a dictionary."""
        return {
            "spatial_score": self.spatial_score,
            "temporal_score": self.temporal_score,
            "trajectory_score": self.trajectory_score,
            "behaviour_score": self.behaviour_score,
            "overall_score": float(self.overall_score),
        }


@dataclass
class AttributedCandidate:
    """Unified container pairing a candidate vessel, score, evidence, and rank."""

    rank: int
    vessel: CandidateVessel
    score: VesselScore
    evidence: AttributionEvidence = field(default_factory=AttributionEvidence)

    def __post_init__(self) -> None:
        if not isinstance(self.rank, (int, np.integer)) or int(self.rank) < 1:
            raise ValueError(f"rank must be an integer >= 1, got {self.rank}")
        self.rank = int(self.rank)

        if not isinstance(self.vessel, CandidateVessel):
            raise TypeError(
                f"vessel must be a CandidateVessel instance, got {type(self.vessel)}"
            )
        if not isinstance(self.score, VesselScore):
            raise TypeError(
                f"score must be a VesselScore instance, got {type(self.score)}"
            )
        if not isinstance(self.evidence, AttributionEvidence):
            raise TypeError(
                f"evidence must be an AttributionEvidence instance, got {type(self.evidence)}"
            )

    @property
    def mmsi(self) -> int:
        """Convenience property for vessel MMSI."""
        return self.vessel.mmsi

    @property
    def overall_score(self) -> float:
        """Convenience property for overall score."""
        return self.score.overall_score

    def to_dict(self) -> Dict[str, Any]:
        """Serialize candidate to dictionary."""
        return {
            "rank": int(self.rank),
            "vessel": self.vessel.to_dict(),
            "score": self.score.to_dict(),
            "evidence": self.evidence.to_dict(),
        }


@dataclass
class OriginMetadata:
    """Standardized spill release origin envelope from Member 4 / AIS-08."""

    timestamp: pd.Timestamp
    latitude: float
    longitude: float
    radius_km: float = 0.0
    confidence_level: Optional[float] = None
    source_info: Dict[str, Any] = field(default_factory=dict)
    uncertainty: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.timestamp = _validate_utc_timestamp(self.timestamp, "origin timestamp")

        if not _is_finite_number(self.latitude) or not (LAT_MIN <= float(self.latitude) <= LAT_MAX):
            raise ValueError(
                f"Origin latitude must be in [{LAT_MIN}, {LAT_MAX}], got {self.latitude}"
            )
        self.latitude = float(self.latitude)

        if not _is_finite_number(self.longitude) or not (LON_MIN <= float(self.longitude) <= LON_MAX):
            raise ValueError(
                f"Origin longitude must be in [{LON_MIN}, {LON_MAX}], got {self.longitude}"
            )
        self.longitude = float(self.longitude)

        if not _is_finite_number(self.radius_km) or float(self.radius_km) < 0.0:
            raise ValueError(
                f"Origin radius_km must be a non-negative number, got {self.radius_km}"
            )
        self.radius_km = float(self.radius_km)

        if self.confidence_level is not None:
            self.confidence_level = _validate_score_value(
                self.confidence_level, "confidence_level"
            )

    @classmethod
    def from_origin_data(cls, origin_data: Union[OriginMetadata, Dict[str, Any], Any]) -> OriginMetadata:
        """Construct OriginMetadata from polymorphic Member 4 / AIS-08 data contracts."""
        if isinstance(origin_data, OriginMetadata):
            return origin_data

        if hasattr(origin_data, "origin") and hasattr(origin_data, "uncertainty"):
            # AISIntegrationResult object from AIS-08
            origin_dict = getattr(origin_data, "origin", {})
            uncertainty_dict = getattr(origin_data, "uncertainty", {})
        elif isinstance(origin_data, dict):
            origin_dict = origin_data.get("origin", origin_data)
            uncertainty_dict = origin_data.get("uncertainty", {})
        else:
            raise TypeError(
                f"Unsupported origin_data type: {type(origin_data)}. Expected OriginMetadata, AISIntegrationResult, or dict."
            )

        ts = origin_dict.get("timestamp")
        if ts is None:
            # Fallback to spill_observation timestamp if present
            spill_obs = getattr(origin_data, "spill_observation", None)
            if isinstance(spill_obs, dict):
                ts = spill_obs.get("timestamp")
            elif isinstance(origin_data, dict) and "spill_observation" in origin_data:
                ts = origin_data["spill_observation"].get("timestamp")

        if ts is None:
            raise ValueError("origin_data must contain 'timestamp'")

        lat = origin_dict.get("latitude")
        if lat is None:
            lat = origin_dict.get("centroid_latitude")
        if lat is None:
            lat = uncertainty_dict.get("centroid_latitude")
        if lat is None:
            raise ValueError("origin_data must contain 'latitude' or 'centroid_latitude'")

        lon = origin_dict.get("longitude")
        if lon is None:
            lon = origin_dict.get("centroid_longitude")
        if lon is None:
            lon = uncertainty_dict.get("centroid_longitude")
        if lon is None:
            raise ValueError("origin_data must contain 'longitude' or 'centroid_longitude'")

        radius_km = uncertainty_dict.get("radius_km", origin_dict.get("radius_km", 0.0))
        confidence_level = uncertainty_dict.get(
            "confidence_level", origin_dict.get("confidence_level")
        )

        return cls(
            timestamp=ts,
            latitude=float(lat),
            longitude=float(lon),
            radius_km=float(radius_km),
            confidence_level=(
                float(confidence_level) if confidence_level is not None else None
            ),
            source_info=origin_dict,
            uncertainty=uncertainty_dict,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize OriginMetadata to a dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "latitude": float(self.latitude),
            "longitude": float(self.longitude),
            "radius_km": float(self.radius_km),
            "confidence_level": self.confidence_level,
            "source_info": self.source_info,
            "uncertainty": self.uncertainty,
        }


@dataclass(frozen=True)
class AttributionReport:
    """Audit metrics and summary statistics for an attribution evaluation run."""

    total_input_observations: int
    total_candidate_vessels: int
    evaluation_timestamp: str
    origin_timestamp: Optional[str] = None
    origin_center: Optional[Tuple[float, float]] = None
    origin_radius_km: Optional[float] = None
    execution_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize AttributionReport to a dictionary."""
        return {
            "total_input_observations": int(self.total_input_observations),
            "total_candidate_vessels": int(self.total_candidate_vessels),
            "evaluation_timestamp": str(self.evaluation_timestamp),
            "origin_timestamp": self.origin_timestamp,
            "origin_center": self.origin_center,
            "origin_radius_km": self.origin_radius_km,
            "execution_notes": list(self.execution_notes),
        }


@dataclass
class AttributionResult:
    """Top-level result container for vessel attribution evaluation."""

    ranked_candidates: List[AttributedCandidate]
    origin_metadata: OriginMetadata
    report: AttributionReport
    config_summary: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.ranked_candidates, list):
            raise TypeError(
                f"ranked_candidates must be a list, got {type(self.ranked_candidates)}"
            )
        for cand in self.ranked_candidates:
            if not isinstance(cand, AttributedCandidate):
                raise TypeError(
                    f"All items in ranked_candidates must be AttributedCandidate, got {type(cand)}"
                )

    @property
    def candidate_mmsis(self) -> List[int]:
        """Return list of candidate MMSIs in ranked order."""
        return [cand.mmsi for cand in self.ranked_candidates]

    @property
    def top_candidate(self) -> Optional[AttributedCandidate]:
        """Return the highest ranked candidate (rank 1), or None if empty."""
        if not self.ranked_candidates:
            return None
        return min(self.ranked_candidates, key=lambda c: c.rank)

    def get_candidate(self, mmsi: int) -> Optional[AttributedCandidate]:
        """Find an attributed candidate by MMSI."""
        for cand in self.ranked_candidates:
            if cand.mmsi == mmsi:
                return cand
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize AttributionResult to a deterministic dictionary."""
        # Ensure deterministic candidate ordering by rank ascending
        sorted_candidates = sorted(self.ranked_candidates, key=lambda c: (c.rank, c.mmsi))
        return {
            "ranked_candidates": [cand.to_dict() for cand in sorted_candidates],
            "origin_metadata": self.origin_metadata.to_dict(),
            "report": self.report.to_dict(),
            "config_summary": self.config_summary,
        }

    def to_dataframe(self) -> pd.DataFrame:
        """Return a tabular summary DataFrame of ranked vessels."""
        if not self.ranked_candidates:
            cols = [
                "rank",
                "mmsi",
                "vessel_name",
                "vessel_type",
                "overall_score",
                "spatial_score",
                "temporal_score",
                "trajectory_score",
                "behaviour_score",
                "min_distance_km",
                "total_observations",
            ]
            return pd.DataFrame(columns=cols)

        sorted_candidates = sorted(self.ranked_candidates, key=lambda c: (c.rank, c.mmsi))
        rows = []
        for cand in sorted_candidates:
            v = cand.vessel
            s = cand.score
            e = cand.evidence
            rows.append({
                "rank": cand.rank,
                "mmsi": v.mmsi,
                "vessel_name": v.vessel_name,
                "vessel_type": v.vessel_type,
                "overall_score": s.overall_score,
                "spatial_score": s.spatial_score,
                "temporal_score": s.temporal_score,
                "trajectory_score": s.trajectory_score,
                "behaviour_score": s.behaviour_score,
                "min_distance_km": e.min_distance_km if e.min_distance_km is not None else v.min_distance_km,
                "total_observations": v.total_observations,
            })
        return pd.DataFrame(rows)


def validate_ais_observations(data: Union[pd.DataFrame, Any]) -> pd.DataFrame:
    """Validate and extract observation-level AIS data for Attribution processing.

    Accepts:
    - pd.DataFrame directly from AIS-07 filter_temporal()
    - AIS-07 TemporalFilterResult
    - AIS-06 SpatialFilterResult
    - Any object with a callable to_dataframe() or .data DataFrame attribute.

    Validates:
    1. Presence of all required columns: mmsi, timestamp, latitude, longitude, distance_km.
    2. Geographic bounds: latitude in [-90, 90], longitude in [-180, 180].
    3. Proximity bounds: distance_km is finite and non-negative.
    4. Temporal validity: timestamps are non-null, parseable, and timezone-aware UTC.
    5. MMSI validity: positive non-zero integers.
    6. Does not mutate the caller's input data.

    Returns:
        Validated copy of pd.DataFrame.

    Raises:
        TypeError: If input data type cannot be resolved to a DataFrame.
        ValueError: If required columns are missing, values are out of bounds,
            or timestamps are naive/invalid.
    """
    # 1. Polymorphic extraction
    if isinstance(data, pd.DataFrame):
        df = data.copy()
    elif hasattr(data, "to_dataframe") and callable(data.to_dataframe):
        df = data.to_dataframe()
    elif hasattr(data, "data") and isinstance(data.data, pd.DataFrame):
        df = data.data.copy()
    else:
        raise TypeError(
            f"Unsupported data type for attribution input: {type(data)}. "
            "Expected pd.DataFrame, TemporalFilterResult, SpatialFilterResult, or object with to_dataframe()."
        )

    # 2. Check required columns
    missing_cols = REQUIRED_AIS_COLUMNS - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"AIS DataFrame missing required columns for attribution: {sorted(list(missing_cols))}. "
            f"Found columns: {sorted(list(df.columns))}"
        )

    # If empty DataFrame, return empty copy
    if df.empty:
        return df.copy()

    # 3. Validate MMSI
    mmsi_series = df["mmsi"]
    if mmsi_series.isna().any():
        raise ValueError("AIS DataFrame 'mmsi' column contains null or NaN values")

    if mmsi_series.dtype == bool or any(isinstance(v, bool) for v in mmsi_series):
        raise ValueError("AIS DataFrame 'mmsi' column contains boolean values")

    try:
        mmsi_numeric = pd.to_numeric(mmsi_series, errors="raise")
    except Exception as exc:
        raise ValueError(
            f"AIS DataFrame 'mmsi' column contains non-numeric values: {exc}"
        ) from exc

    if not np.isfinite(mmsi_numeric).all():
        raise ValueError("AIS DataFrame 'mmsi' column contains infinite or NaN values")

    # Reject non-integer numeric MMSIs (e.g. 205123456.5) instead of silently truncating
    if not np.all(np.equal(np.mod(mmsi_numeric, 1), 0)):
        raise ValueError(
            "AIS DataFrame 'mmsi' column contains non-integer floating-point values"
        )

    if (mmsi_numeric <= 0).any():
        invalid_mmsis = mmsi_numeric[mmsi_numeric <= 0].tolist()
        raise ValueError(
            f"AIS DataFrame contains non-positive MMSI identifiers: {invalid_mmsis[:5]}"
        )

    mmsi_ints = mmsi_numeric.astype(int)

    # 4. Validate Coordinates
    if df["latitude"].dtype == bool or any(isinstance(v, bool) for v in df["latitude"]):
        raise ValueError("AIS DataFrame 'latitude' column contains boolean values")
    if df["longitude"].dtype == bool or any(isinstance(v, bool) for v in df["longitude"]):
        raise ValueError("AIS DataFrame 'longitude' column contains boolean values")

    try:
        lats = pd.to_numeric(df["latitude"], errors="raise")
    except Exception as exc:
        raise ValueError(
            f"AIS DataFrame 'latitude' contains non-numeric values: {exc}"
        ) from exc

    try:
        lons = pd.to_numeric(df["longitude"], errors="raise")
    except Exception as exc:
        raise ValueError(
            f"AIS DataFrame 'longitude' contains non-numeric values: {exc}"
        ) from exc

    if lats.isna().any() or not np.isfinite(lats).all():
        raise ValueError("AIS DataFrame contains null, NaN, or infinite latitude values")
    if lons.isna().any() or not np.isfinite(lons).all():
        raise ValueError("AIS DataFrame contains null, NaN, or infinite longitude values")

    if (lats < LAT_MIN).any() or (lats > LAT_MAX).any():
        raise ValueError(
            f"AIS DataFrame contains latitudes outside [{LAT_MIN}, {LAT_MAX}]"
        )
    if (lons < LON_MIN).any() or (lons > LON_MAX).any():
        raise ValueError(
            f"AIS DataFrame contains longitudes outside [{LON_MIN}, {LON_MAX}]"
        )

    # 5. Validate distance_km
    if df["distance_km"].dtype == bool or any(isinstance(v, bool) for v in df["distance_km"]):
        raise ValueError("AIS DataFrame 'distance_km' column contains boolean values")

    try:
        dist = pd.to_numeric(df["distance_km"], errors="raise")
    except Exception as exc:
        raise ValueError(
            f"AIS DataFrame 'distance_km' contains non-numeric values: {exc}"
        ) from exc

    if dist.isna().any() or not np.isfinite(dist).all():
        raise ValueError("AIS DataFrame contains null, NaN, or infinite distance_km values")
    if (dist < 0.0).any():
        raise ValueError("AIS DataFrame contains negative distance_km values")

    # 6. Validate Timestamps (must be timezone-aware UTC)
    raw_ts = df["timestamp"]
    if raw_ts.isna().any():
        raise ValueError("AIS DataFrame 'timestamp' column contains null or NaT values")

    # Fast path: already datetime64 with timezone
    if pd.api.types.is_datetime64_any_dtype(raw_ts):
        if getattr(raw_ts.dt, "tz", None) is None:
            raise ValueError(
                "AIS DataFrame 'timestamp' column must be timezone-aware (expected UTC), got naive timestamps"
            )
        try:
            norm_ts = raw_ts.dt.tz_convert("UTC")
        except Exception as exc:
            raise ValueError(f"Failed to convert AIS timestamps to UTC: {exc}") from exc
    else:
        # Check and normalize each timestamp individually to handle mixed offsets or malformed items safely
        norm_list = []
        for idx, val in raw_ts.items():
            if val is None or isinstance(val, bool):
                raise ValueError(
                    f"AIS DataFrame 'timestamp' contains null or boolean value at index {idx}"
                )
            try:
                ts = pd.Timestamp(val)
            except Exception as exc:
                raise ValueError(
                    f"AIS DataFrame 'timestamp' contains unparseable datetime at index {idx}: '{val}' ({exc})"
                ) from exc

            if pd.isna(ts) or ts is pd.NaT:
                raise ValueError(
                    f"AIS DataFrame 'timestamp' contains null or NaT value at index {idx}"
                )

            if ts.tzinfo is None:
                raise ValueError(
                    f"AIS DataFrame 'timestamp' column must be timezone-aware (expected UTC), got naive timestamp '{val}' at index {idx}"
                )

            try:
                norm_list.append(ts.tz_convert("UTC"))
            except Exception as exc:
                raise ValueError(
                    f"Failed to convert timestamp '{val}' at index {idx} to UTC: {exc}"
                ) from exc

        norm_ts = pd.Series(norm_list, index=raw_ts.index, dtype="datetime64[ns, UTC]")

    result_df = df.copy()
    result_df["mmsi"] = mmsi_ints
    result_df["latitude"] = lats.astype(float)
    result_df["longitude"] = lons.astype(float)
    result_df["distance_km"] = dist.astype(float)
    result_df["timestamp"] = norm_ts
    return result_df



def validate_origin_metadata(
    origin_data: Union[OriginMetadata, Dict[str, Any], Any]
) -> OriginMetadata:
    """Validate and normalize spill release origin metadata.

    Accepts:
    - OriginMetadata instance
    - AISIntegrationResult from AIS-08 (adapt_drift_origin_result)
    - Standardized origin_data dictionary from Member 4 handoff

    Returns:
        Validated OriginMetadata instance.
    """
    return OriginMetadata.from_origin_data(origin_data)


def extract_candidate_vessels(data: Union[pd.DataFrame, Any]) -> List[CandidateVessel]:
    """Extract vessel-level CandidateVessel models from observation-level AIS data.

    Aggregates telemetry observations per MMSI into CandidateVessel summaries:
    - Identifiers and static particulars (first non-null values observed).
    - Observation counts (total, actual, interpolated).
    - Proximity metrics (min_distance_km and closest_approach_time).
    - Temporal bounds (first_observed_time, last_observed_time).
    - Kinematic summaries (mean SOG where available).
    - Trajectory segment IDs.

    Args:
        data: Validated pd.DataFrame, TemporalFilterResult, or SpatialFilterResult.

    Returns:
        List of CandidateVessel instances, ordered by min_distance_km ascending
        (closest approach first), with ties broken by MMSI.
    """
    df = validate_ais_observations(data)
    if df.empty:
        return []

    candidates: List[CandidateVessel] = []

    for mmsi, group in df.groupby("mmsi", sort=True):
        mmsi_int = int(mmsi)
        total_obs = len(group)

        has_interp = "is_interpolated" in group.columns
        if has_interp:
            interp_count = int(group["is_interpolated"].sum())
            actual_count = int((~group["is_interpolated"]).sum())
        else:
            interp_count = 0
            actual_count = total_obs

        # Find closest approach
        min_dist = float(group["distance_km"].min())
        min_idx = group["distance_km"].idxmin()
        closest_time = group.loc[min_idx, "timestamp"]
        if not isinstance(closest_time, pd.Timestamp):
            closest_time = pd.Timestamp(closest_time)
        if closest_time.tzinfo is None:
            closest_time = closest_time.tz_localize("UTC")
        else:
            closest_time = closest_time.tz_convert("UTC")

        first_time = group["timestamp"].min()
        last_time = group["timestamp"].max()

        # Mean SOG
        mean_sog = None
        if "sog" in group.columns:
            valid_sog = group["sog"].dropna()
            if not valid_sog.empty:
                mean_sog = float(valid_sog.mean())

        # Segments
        segment_ids: List[str] = []
        if "trajectory_segment_id" in group.columns:
            segment_ids = sorted(
                list(group["trajectory_segment_id"].dropna().astype(str).unique())
            )

        # Static attributes: helper to find first non-null
        def _get_first(col: str) -> Any:
            if col in group.columns:
                valid_vals = group[col].dropna()
                for val in valid_vals:
                    if isinstance(val, str) and val.strip() and val.strip().lower() != "nan":
                        return val.strip()
                    elif not isinstance(val, str) and not pd.isna(val):
                        return val
            return None

        vessel_name = _get_first("vessel_name")
        vessel_type = _get_first("vessel_type")
        imo = _get_first("imo")
        callsign = _get_first("callsign")
        length = _get_first("length")
        width = _get_first("width")
        draft = _get_first("draft")
        if draft is None:
            draft = _get_first("draught")

        vessel = CandidateVessel(
            mmsi=mmsi_int,
            vessel_name=str(vessel_name) if vessel_name is not None else None,
            vessel_type=vessel_type,
            imo=str(imo) if imo is not None else None,
            callsign=str(callsign) if callsign is not None else None,
            length=float(length) if length is not None and _is_finite_number(length) else None,
            width=float(width) if width is not None and _is_finite_number(width) else None,
            draft=float(draft) if draft is not None and _is_finite_number(draft) else None,
            total_observations=total_obs,
            actual_observations=actual_count,
            interpolated_observations=interp_count,
            min_distance_km=min_dist,
            closest_approach_time=closest_time,
            first_observed_time=first_time,
            last_observed_time=last_time,
            mean_sog_knots=mean_sog,
            segment_ids=segment_ids,
        )
        candidates.append(vessel)

    # Deterministic sort: min_distance_km ascending, ties broken by MMSI
    candidates.sort(
        key=lambda v: (
            v.min_distance_km if v.min_distance_km is not None else float("inf"),
            v.mmsi,
        )
    )
    return candidates
