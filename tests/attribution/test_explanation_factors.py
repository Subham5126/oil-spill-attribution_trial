"""Unit tests for Factor Synthesis and Confidence Tier Classification (ATTR-03)."""

import pandas as pd
import pytest

from attribution.explanation.factors import (
    determine_confidence_tier,
    synthesize_candidate_factors,
)
from attribution.explanation.models import ConfidenceTier
from attribution.models import (
    AttributedCandidate,
    AttributionEvidence,
    CandidateVessel,
    OriginMetadata,
    VesselScore,
)


# =============================================================================
# 1. Confidence Tier Mapping & Safety Override Tests
# =============================================================================

@pytest.mark.parametrize(
    "score,expected_tier",
    [
        (1.0, "HIGH_CONFIDENCE"),
        (0.85, "HIGH_CONFIDENCE"),
        (0.80, "HIGH_CONFIDENCE"),
        (0.7999, "MODERATE_CONFIDENCE"),
        (0.65, "MODERATE_CONFIDENCE"),
        (0.50, "MODERATE_CONFIDENCE"),
        (0.4999, "LOW_CONFIDENCE"),
        (0.35, "LOW_CONFIDENCE"),
        (0.20, "LOW_CONFIDENCE"),
        (0.1999, "NEGLIGIBLE_CORRELATION"),
        (0.05, "NEGLIGIBLE_CORRELATION"),
        (0.0, "NEGLIGIBLE_CORRELATION"),
    ],
)
def test_confidence_tier_standard_thresholds(score, expected_tier):
    """Verify confidence tier thresholds within nominal boundaries."""
    tier = determine_confidence_tier(
        overall_score=score,
        min_distance_km=5.0,
        time_diff_seconds=300.0,
        max_distance_km=25.0,
        max_time_diff_seconds=7200.0,
    )
    assert tier == expected_tier


def test_confidence_tier_spatial_safety_override():
    """Verify safety override when candidate exceeds maximum spatial distance."""
    # A score of 0.95 would ordinarily be HIGH_CONFIDENCE,
    # but distance of 30 km exceeds max_distance_km (25 km).
    tier = determine_confidence_tier(
        overall_score=0.95,
        min_distance_km=30.0,
        time_diff_seconds=60.0,
        max_distance_km=25.0,
        max_time_diff_seconds=7200.0,
    )
    assert tier == ConfidenceTier.LOW_CONFIDENCE.value


def test_confidence_tier_temporal_safety_override():
    """Verify safety override when candidate exceeds maximum temporal difference."""
    # Score 0.75 would be MODERATE_CONFIDENCE, but time delta of 9000s exceeds max (7200s).
    tier = determine_confidence_tier(
        overall_score=0.75,
        min_distance_km=2.0,
        time_diff_seconds=9000.0,
        max_distance_km=25.0,
        max_time_diff_seconds=7200.0,
    )
    assert tier == ConfidenceTier.LOW_CONFIDENCE.value


def test_confidence_tier_negligible_score_not_elevated_by_override():
    """Verify that a negligible score remains NEGLIGIBLE even when out of bounds."""
    tier = determine_confidence_tier(
        overall_score=0.08,
        min_distance_km=50.0,
        time_diff_seconds=15000.0,
        max_distance_km=25.0,
        max_time_diff_seconds=7200.0,
    )
    assert tier == ConfidenceTier.NEGLIGIBLE_CORRELATION.value


# =============================================================================
# 2. Factor Synthesis & Neutrality Tests
# =============================================================================

@pytest.fixture
def sample_origin():
    """Standard origin fixture for factor testing."""
    return OriginMetadata(
        timestamp=pd.Timestamp("2025-01-08T00:00:00Z"),
        latitude=28.0000,
        longitude=-90.0000,
        radius_km=5.0,
        confidence_level=0.95,
    )


def test_synthesize_factors_tanker_close_encounter(sample_origin):
    """Verify factor synthesis for a close tanker candidate."""
    vessel = CandidateVessel(
        mmsi=205123456,
        vessel_name="PACIFIC TANKER",
        vessel_type="Tanker",
        total_observations=100,
        actual_observations=95,
        interpolated_observations=5,
        min_distance_km=1.2,
        closest_approach_time=pd.Timestamp("2025-01-08T00:02:00Z"),
        mean_sog_knots=12.5,
    )
    score = VesselScore(
        spatial_score=1.0,
        temporal_score=0.98,
        trajectory_score=0.85,
        behaviour_score=0.90,
        overall_score=0.94,
    )
    evidence = AttributionEvidence(
        min_distance_km=1.2,
        time_of_closest_approach=pd.Timestamp("2025-01-08T00:02:00Z"),
        time_difference_seconds=120.0,
        mean_speed_knots=12.5,
        ais_gap_count=0,
        evidence_metadata={"closest_approach_is_interpolated": False},
    )
    candidate = AttributedCandidate(rank=1, vessel=vessel, score=score, evidence=evidence)

    supp, contra, quality = synthesize_candidate_factors(candidate, sample_origin)

    # Supporting factors should note spatial containment, close time, speed, continuous AIS, and tanker type
    supp_text = " ".join(supp)
    assert "uncertainty envelope" in supp_text
    assert "temporal alignment" in supp_text
    assert "transit underway" in supp_text
    assert "Continuous AIS telemetry" in supp_text
    assert "hydrocarbon cargo capacity" in supp_text

    # Contradicting factors should not contain distance contradiction since CPA <= radius
    contra_text = " ".join(contra)
    assert "remained outside" not in contra_text

    # Quality notes should reflect low interpolation ratio and actual broadcast CPA
    qual_text = " ".join(quality)
    assert "verified by a direct broadcast" in qual_text
    assert "100 total fixes" in qual_text


def test_synthesize_factors_distant_tug_with_gaps(sample_origin):
    """Verify factor synthesis for a distant tug with telemetry gaps."""
    vessel = CandidateVessel(
        mmsi=316000000,
        vessel_name="HARBOR TUG",
        vessel_type="Tug",
        total_observations=50,
        actual_observations=20,
        interpolated_observations=30,
        min_distance_km=15.0,
        closest_approach_time=pd.Timestamp("2025-01-08T01:30:00Z"),
        mean_sog_knots=0.2,  # Stationary / drifting
    )
    score = VesselScore(
        spatial_score=0.25,
        temporal_score=0.10,
        trajectory_score=0.20,
        behaviour_score=0.30,
        overall_score=0.21,
    )
    evidence = AttributionEvidence(
        min_distance_km=15.0,
        time_of_closest_approach=pd.Timestamp("2025-01-08T01:30:00Z"),
        time_difference_seconds=5400.0,
        mean_speed_knots=0.2,
        ais_gap_count=2,
        evidence_metadata={"closest_approach_is_interpolated": True},
    )
    candidate = AttributedCandidate(rank=5, vessel=vessel, score=score, evidence=evidence)

    supp, contra, quality = synthesize_candidate_factors(candidate, sample_origin)

    contra_text = " ".join(contra)
    assert "remained outside estimated origin uncertainty radius" in contra_text
    assert "Temporal divergence" in contra_text
    assert "stationary, moored, or drifting" in contra_text
    assert "non-bulk fuel/cargo profile" in contra_text
    assert "Intermittent telemetry coverage" in contra_text

    qual_text = " ".join(quality)
    assert "derived from an interpolated fix" in qual_text
    assert "predominantly on interpolation" in qual_text
    assert "2 telemetry interval(s)" in qual_text


def test_synthesize_factors_strict_neutrality(sample_origin):
    """Verify that synthesized factors strictly exclude prohibited accusatory language."""
    vessel = CandidateVessel(
        mmsi=205123456,
        vessel_name="UNKNOWN_VESSEL",
        total_observations=10,
        min_distance_km=1.0,
    )
    candidate = AttributedCandidate(
        rank=1,
        vessel=vessel,
        score=VesselScore(overall_score=0.88),
        evidence=AttributionEvidence(min_distance_km=1.0, time_difference_seconds=60.0),
    )

    supp, contra, quality = synthesize_candidate_factors(candidate, sample_origin)
    all_text = " ".join(supp + contra + quality).lower()

    # STRICT REQUIREMENT: No accusatory, guilt, or intentional misconduct language
    forbidden_words = [
        "guilty",
        "caused",
        "violator",
        "culprit",
        "malicious",
        "illegal",
        "intentional",
        "evasion",
        "shut down",
    ]
    for word in forbidden_words:
        assert word not in all_text, f"Forbidden word '{word}' found in factor synthesis: {all_text}"
