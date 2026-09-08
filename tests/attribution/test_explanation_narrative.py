"""Unit tests for Natural Language Narrative and Comparative Note generation (ATTR-03)."""

import pandas as pd
import pytest

from attribution.explanation.models import ConfidenceTier
from attribution.explanation.narrative import (
    generate_comparative_note,
    generate_incident_summary,
    generate_vessel_narrative,
)
from attribution.models import (
    AttributedCandidate,
    AttributionEvidence,
    AttributionReport,
    AttributionResult,
    CandidateVessel,
    OriginMetadata,
    VesselScore,
)


@pytest.fixture
def origin_fixture():
    """Standard origin fixture for narrative testing."""
    return OriginMetadata(
        timestamp=pd.Timestamp("2025-01-08T00:00:00Z"),
        latitude=28.0050,
        longitude=-90.0000,
        radius_km=5.0,
        confidence_level=0.95,
    )


# =============================================================================
# 1. Candidate Narrative Generation Tests
# =============================================================================

def test_narrative_generation_complete_candidate(origin_fixture):
    """Verify narrative synthesis for a complete candidate with full telemetry."""
    vessel = CandidateVessel(
        mmsi=368021480,
        vessel_name="KENDRA JEAN",
        vessel_type="Towing",
        total_observations=50,
        min_distance_km=2.34,
        closest_approach_time=pd.Timestamp("2025-01-08T00:23:24Z"),
        mean_sog_knots=8.2,
    )
    score = VesselScore(
        spatial_score=1.0,
        temporal_score=0.95,
        trajectory_score=0.90,
        behaviour_score=0.85,
        overall_score=0.9970,
    )
    evidence = AttributionEvidence(
        min_distance_km=2.34,
        time_of_closest_approach=pd.Timestamp("2025-01-08T00:23:24Z"),
        time_difference_seconds=1404.0,  # 23.4 min
        mean_speed_knots=8.2,
        ais_gap_count=0,
        evidence_metadata={"closest_approach_is_interpolated": False},
    )
    candidate = AttributedCandidate(rank=1, vessel=vessel, score=score, evidence=evidence)

    narrative = generate_vessel_narrative(
        candidate=candidate,
        origin=origin_fixture,
        confidence_tier=ConfidenceTier.HIGH_CONFIDENCE.value,
    )

    assert "KENDRA JEAN (MMSI: 368021480)" in narrative
    assert "ranked #1 with an analytical attribution score of 0.9970 (HIGH_CONFIDENCE)" in narrative
    assert "closest approach of 2.34 km" in narrative
    assert "uncertainty envelope (radius: 5.00 km)" in narrative
    assert "2025-01-08T00:23:24Z" in narrative
    assert "recorded by a direct broadcast fix" in narrative
    assert "23.4 minutes from the estimated release time" in narrative
    assert "mean transit speed was 8.2 knots" in narrative
    assert "AIS telemetry was continuous throughout the encounter" in narrative
    assert "they do not establish that the vessel caused the spill" in narrative


def test_narrative_generation_sparse_candidate(origin_fixture):
    """Verify narrative synthesis for a sparse candidate with minimal metadata."""
    vessel = CandidateVessel(
        mmsi=987654321,
        total_observations=3,
    )
    score = VesselScore(overall_score=0.15)
    evidence = AttributionEvidence()
    candidate = AttributedCandidate(rank=8, vessel=vessel, score=score, evidence=evidence)

    narrative = generate_vessel_narrative(
        candidate=candidate,
        origin=origin_fixture,
        confidence_tier=ConfidenceTier.NEGLIGIBLE_CORRELATION.value,
    )

    assert "Candidate vessel (MMSI: 987654321)" in narrative
    assert "ranked #8 with an analytical attribution score of 0.1500 (NEGLIGIBLE_CORRELATION)" in narrative
    assert "None" not in narrative
    assert "they do not establish that the vessel caused the spill" in narrative


def test_narrative_interpolated_cpa(origin_fixture):
    """Verify that interpolated CPA fix provenance is explicitly stated."""
    vessel = CandidateVessel(
        mmsi=205123456,
        min_distance_km=4.5,
        closest_approach_time=pd.Timestamp("2025-01-08T00:10:00Z"),
    )
    candidate = AttributedCandidate(
        rank=2,
        vessel=vessel,
        score=VesselScore(overall_score=0.65),
        evidence=AttributionEvidence(
            min_distance_km=4.5,
            time_of_closest_approach=pd.Timestamp("2025-01-08T00:10:00Z"),
            time_difference_seconds=600.0,
            evidence_metadata={"closest_approach_is_interpolated": True},
        ),
    )

    narrative = generate_vessel_narrative(
        candidate=candidate,
        origin=origin_fixture,
        confidence_tier=ConfidenceTier.MODERATE_CONFIDENCE.value,
    )

    assert "derived from an interpolated fix" in narrative


def test_narrative_is_deterministic(origin_fixture):
    """Verify that narrative generation is 100% deterministic."""
    vessel = CandidateVessel(mmsi=123456789, min_distance_km=3.0)
    candidate = AttributedCandidate(
        rank=1,
        vessel=vessel,
        score=VesselScore(overall_score=0.82),
        evidence=AttributionEvidence(min_distance_km=3.0),
    )

    n1 = generate_vessel_narrative(candidate, origin_fixture, "HIGH_CONFIDENCE")
    n2 = generate_vessel_narrative(candidate, origin_fixture, "HIGH_CONFIDENCE")
    assert n1 == n2


# =============================================================================
# 2. Comparative Assessment Tests
# =============================================================================

def test_comparative_note_substantive_distinction():
    """Verify comparative note when Candidate 1 outranks Candidate 2 on spatial & temporal metrics."""
    c1 = AttributedCandidate(
        rank=1,
        vessel=CandidateVessel(mmsi=111111111, vessel_name="VESSEL_ONE", min_distance_km=1.0),
        score=VesselScore(
            spatial_score=1.0,
            temporal_score=0.90,
            overall_score=0.95,
        ),
        evidence=AttributionEvidence(min_distance_km=1.0, time_difference_seconds=120.0),
    )
    c2 = AttributedCandidate(
        rank=2,
        vessel=CandidateVessel(mmsi=222222222, vessel_name="VESSEL_TWO", min_distance_km=8.0),
        score=VesselScore(
            spatial_score=0.50,
            temporal_score=0.60,
            overall_score=0.55,
        ),
        evidence=AttributionEvidence(min_distance_km=8.0, time_difference_seconds=1800.0),
    )

    note = generate_comparative_note(candidate=c1, next_candidate=c2)
    assert note is not None
    assert "VESSEL_TWO" in note
    assert "closer spatial proximity (1.00 km vs 8.00 km)" in note
    assert "closer temporal alignment (2.0 min vs 30.0 min)" in note


def test_comparative_note_exact_tie():
    """Verify comparative note when two candidates have identical sub-scores."""
    c1 = AttributedCandidate(
        rank=1,
        vessel=CandidateVessel(mmsi=100000001, vessel_name="VESSEL_A", min_distance_km=5.0),
        score=VesselScore(
            spatial_score=0.80,
            temporal_score=0.80,
            trajectory_score=0.70,
            behaviour_score=0.70,
            overall_score=0.75,
        ),
        evidence=AttributionEvidence(min_distance_km=5.0, time_difference_seconds=600.0),
    )
    c2 = AttributedCandidate(
        rank=2,
        vessel=CandidateVessel(mmsi=200000002, vessel_name="VESSEL_B", min_distance_km=5.0),
        score=VesselScore(
            spatial_score=0.80,
            temporal_score=0.80,
            trajectory_score=0.70,
            behaviour_score=0.70,
            overall_score=0.75,
        ),
        evidence=AttributionEvidence(min_distance_km=5.0, time_difference_seconds=600.0),
    )

    note = generate_comparative_note(candidate=c1, next_candidate=c2)
    assert note is not None
    assert "deterministic tie-breaking (MMSI ordering)" in note
    assert "scores across all evaluated dimensions are identical" in note


def test_comparative_note_single_rank1():
    """Verify comparative note when Rank 1 has no succeeding candidate."""
    c1 = AttributedCandidate(
        rank=1,
        vessel=CandidateVessel(mmsi=111111111),
        score=VesselScore(overall_score=0.90),
    )
    note = generate_comparative_note(candidate=c1, next_candidate=None)
    assert note == "Rank #1: Highest analytical score among all evaluated candidate vessels."


# =============================================================================
# 3. Incident Summary Tests
# =============================================================================

def test_incident_summary_with_candidates(origin_fixture):
    """Verify incident executive summary with candidate fleet."""
    c1 = AttributedCandidate(rank=1, vessel=CandidateVessel(mmsi=1), score=VesselScore(overall_score=0.85))
    c2 = AttributedCandidate(rank=2, vessel=CandidateVessel(mmsi=2), score=VesselScore(overall_score=0.60))
    c3 = AttributedCandidate(rank=3, vessel=CandidateVessel(mmsi=3), score=VesselScore(overall_score=0.10))

    report = AttributionReport(
        total_input_observations=5000,
        total_candidate_vessels=3,
        evaluation_timestamp="2025-01-08T12:00:00Z",
    )
    result = AttributionResult(
        ranked_candidates=[c1, c2, c3],
        origin_metadata=origin_fixture,
        report=report,
    )

    summary = generate_incident_summary(result=result, top_n=2)
    assert "5,000 AIS observations across 3 candidate vessels" in summary
    assert "1 high-confidence candidate(s)" in summary
    assert "1 moderate-confidence candidate(s)" in summary
    assert "1 low/negligible-correlation candidate(s)" in summary
    assert "top 2 candidates" in summary


def test_incident_summary_zero_candidates(origin_fixture):
    """Verify incident executive summary when zero candidates were found."""
    report = AttributionReport(
        total_input_observations=0,
        total_candidate_vessels=0,
        evaluation_timestamp="2025-01-08T12:00:00Z",
    )
    result = AttributionResult(
        ranked_candidates=[],
        origin_metadata=origin_fixture,
        report=report,
    )

    summary = generate_incident_summary(result=result, top_n=5)
    assert "No candidate vessels met the spatio-temporal filtering criteria" in summary
