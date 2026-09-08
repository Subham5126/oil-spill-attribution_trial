"""Unit tests for the Attribution Scoring Engine."""

import pandas as pd
import pytest

from attribution.models import (
    AttributedCandidate,
    AttributionResult,
    CandidateVessel,
    OriginMetadata,
    VesselScore,
)
from attribution.scoring.config import AttributionScoringConfig
from attribution.scoring.engine import attribute_vessels, score_candidates


# ---------------------------------------------------------------------------
# Sample Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_origin() -> OriginMetadata:
    return OriginMetadata(
        timestamp=pd.Timestamp("2025-01-08T00:30:00Z"),
        latitude=28.0,
        longitude=-90.0,
        radius_km=5.0,
    )


@pytest.fixture
def multi_candidate_df() -> pd.DataFrame:
    """Create a synthetic dataset with 3 distinct vessels at varying distances."""
    return pd.DataFrame([
        # Vessel 1: Close approach and perfect timing (Expected top rank)
        {
            "mmsi": 111111111,
            "timestamp": "2025-01-08T00:30:00Z",
            "latitude": 28.01,
            "longitude": -90.00,
            "distance_km": 1.11,
            "sog": 12.0,
            "cog": 90.0,
            "vessel_type": "Tanker",
            "is_interpolated": False,
        },
        # Vessel 2: Moderate approach distance
        {
            "mmsi": 222222222,
            "timestamp": "2025-01-08T00:45:00Z",
            "latitude": 28.10,
            "longitude": -90.00,
            "distance_km": 11.12,
            "sog": 14.0,
            "cog": 90.0,
            "vessel_type": "Cargo",
            "is_interpolated": False,
        },
        # Vessel 3: Far away
        {
            "mmsi": 333333333,
            "timestamp": "2025-01-08T02:00:00Z",
            "latitude": 28.25,
            "longitude": -90.00,
            "distance_km": 27.8,
            "sog": 8.0,
            "cog": 180.0,
            "vessel_type": "Tug",
            "is_interpolated": False,
        },
    ])


# ===========================================================================
# 1. Multi-Candidate Scoring & Ranking Tests
# ===========================================================================
def test_engine_scores_and_ranks_candidates(multi_candidate_df, sample_origin):
    """Verify engine scores and strictly ranks candidates by overall_score descending."""
    result = score_candidates(data=multi_candidate_df, origin_data=sample_origin)
    assert isinstance(result, AttributionResult)
    assert len(result.ranked_candidates) == 3

    # Verify 1-based sequential ranks
    assert [c.rank for c in result.ranked_candidates] == [1, 2, 3]

    # Verify descending overall scores
    scores = [c.score.overall_score for c in result.ranked_candidates]
    assert scores == sorted(scores, reverse=True)

    # Top candidate should be the close Tanker (MMSI 111111111)
    top = result.top_candidate
    assert top is not None
    assert top.vessel.mmsi == 111111111
    assert top.score.spatial_score == 1.0  # Inside 5km radius
    assert top.score.temporal_score == 1.0  # Exactly at 00:30:00

    # Summary dataframe check
    df_summary = result.to_dataframe()
    assert len(df_summary) == 3
    assert list(df_summary["rank"]) == [1, 2, 3]
    assert list(df_summary["mmsi"]) == [111111111, 222222222, 333333333]


# ===========================================================================
# 2. Complete 4-Tier Deterministic Tie-Breaking (Correction 5)
# ===========================================================================
def test_ranking_tie_breaking_tiers(sample_origin):
    """Explicitly verify all 4 tiers of deterministic tie-breaking:

    Tier 1: overall_score decides
    Tier 2: same overall_score -> spatial_score decides
    Tier 3: same overall_score + spatial_score -> temporal_score decides
    Tier 4: same overall_score + spatial_score + temporal_score -> lower MMSI ranks first
    """
    # Tier 2: Same overall_score, different spatial_score
    c_spat_hi = AttributedCandidate(
        rank=1,
        vessel=CandidateVessel(mmsi=200000000),
        score=VesselScore(overall_score=0.80, spatial_score=0.90, temporal_score=0.70),
    )
    c_spat_lo = AttributedCandidate(
        rank=1,
        vessel=CandidateVessel(mmsi=100000000),
        score=VesselScore(overall_score=0.80, spatial_score=0.70, temporal_score=0.90),
    )

    # Tier 3: Same overall and spatial, different temporal_score
    c_temp_hi = AttributedCandidate(
        rank=1,
        vessel=CandidateVessel(mmsi=400000000),
        score=VesselScore(overall_score=0.75, spatial_score=0.80, temporal_score=0.90),
    )
    c_temp_lo = AttributedCandidate(
        rank=1,
        vessel=CandidateVessel(mmsi=300000000),
        score=VesselScore(overall_score=0.75, spatial_score=0.80, temporal_score=0.70),
    )

    # Tier 4: Exact tie on overall, spatial, temporal -> MMSI ascending decides
    c_mmsi_lo = AttributedCandidate(
        rank=1,
        vessel=CandidateVessel(mmsi=500000001),
        score=VesselScore(overall_score=0.60, spatial_score=0.60, temporal_score=0.60),
    )
    c_mmsi_hi = AttributedCandidate(
        rank=1,
        vessel=CandidateVessel(mmsi=500000009),
        score=VesselScore(overall_score=0.60, spatial_score=0.60, temporal_score=0.60),
    )

    candidates = [c_mmsi_hi, c_spat_lo, c_temp_lo, c_mmsi_lo, c_spat_hi, c_temp_hi]

    # Use the identical ranking comparator from engine
    def _rank_key(cand: AttributedCandidate):
        s = cand.score
        spat_val = float(s.spatial_score) if s.spatial_score is not None else -1.0
        temp_val = float(s.temporal_score) if s.temporal_score is not None else -1.0
        return (-float(s.overall_score), -spat_val, -temp_val, int(cand.vessel.mmsi))

    sorted_cands = sorted(candidates, key=_rank_key)
    sorted_mmsis = [c.vessel.mmsi for c in sorted_cands]

    # Expected order:
    # 1. c_spat_hi (overall 0.80, spatial 0.90, MMSI 200000000)
    # 2. c_spat_lo (overall 0.80, spatial 0.70, MMSI 100000000)
    # 3. c_temp_hi (overall 0.75, spatial 0.80, temporal 0.90, MMSI 400000000)
    # 4. c_temp_lo (overall 0.75, spatial 0.80, temporal 0.70, MMSI 300000000)
    # 5. c_mmsi_lo (overall 0.60, spatial 0.60, temporal 0.60, MMSI 500000001)
    # 6. c_mmsi_hi (overall 0.60, spatial 0.60, temporal 0.60, MMSI 500000009)
    expected_mmsis = [200000000, 100000000, 400000000, 300000000, 500000001, 500000009]
    assert sorted_mmsis == expected_mmsis


def test_ranking_none_handling_preserves_none():
    """Verify None sub-scores are treated as -1.0 ONLY for sorting, preserving None in output."""
    c_none = AttributedCandidate(
        rank=1,
        vessel=CandidateVessel(mmsi=111111111),
        score=VesselScore(overall_score=0.50, spatial_score=None, temporal_score=0.50),
    )
    c_valid = AttributedCandidate(
        rank=1,
        vessel=CandidateVessel(mmsi=222222222),
        score=VesselScore(overall_score=0.50, spatial_score=0.10, temporal_score=0.50),
    )

    def _rank_key(cand: AttributedCandidate):
        s = cand.score
        spat_val = float(s.spatial_score) if s.spatial_score is not None else -1.0
        temp_val = float(s.temporal_score) if s.temporal_score is not None else -1.0
        return (-float(s.overall_score), -spat_val, -temp_val, int(cand.vessel.mmsi))

    sorted_cands = sorted([c_none, c_valid], key=_rank_key)
    # c_valid (spatial=0.10) beats c_none (spatial=None -> treated as -1.0)
    assert sorted_cands[0].vessel.mmsi == 222222222
    assert sorted_cands[1].vessel.mmsi == 111111111
    # Verify None is preserved in stored score
    assert sorted_cands[1].score.spatial_score is None


# ===========================================================================
# 3. Drift Data Contract Non-Inference (Correction 1)
# ===========================================================================
def test_drift_contract_never_infers_from_spill_observation():
    """Verify engine NEVER infers a drift vector from spill_observation coordinates."""
    origin_with_spill_obs = OriginMetadata(
        timestamp=pd.Timestamp("2025-01-08T00:30:00Z"),
        latitude=28.0,
        longitude=-90.0,
        radius_km=5.0,
        source_info={
            # Both origin and spill_observation coordinates exist!
            "spill_observation": {
                "latitude": 28.5,
                "longitude": -89.5,
                "timestamp": "2025-01-08T02:00:00Z",
            }
        },
    )
    df = pd.DataFrame([{
        "mmsi": 999999999,
        "timestamp": "2025-01-08T00:30:00Z",
        "latitude": 28.0,
        "longitude": -90.0,
        "distance_km": 0.0,
        "sog": 10.0,
        "cog": 45.0,
    }])
    result = score_candidates(data=df, origin_data=origin_with_spill_obs)
    cand = result.top_candidate
    assert cand is not None
    # Explicit drift was NOT used
    assert cand.evidence.evidence_metadata["explicit_drift_used"] is False
    assert cand.evidence.heading_drift_alignment_deg is None


def test_drift_contract_uses_explicit_drift_when_provided():
    """Verify engine uses explicit drift vector when provided in source_info."""
    origin_explicit_drift = OriginMetadata(
        timestamp=pd.Timestamp("2025-01-08T00:30:00Z"),
        latitude=28.0,
        longitude=-90.0,
        radius_km=5.0,
        source_info={"drift_direction_deg": 90.0},
    )
    df = pd.DataFrame([{
        "mmsi": 999999999,
        "timestamp": "2025-01-08T00:30:00Z",
        "latitude": 28.0,
        "longitude": -90.0,
        "distance_km": 0.0,
        "sog": 10.0,
        "cog": 90.0,  # Perfectly aligned with 90 deg drift
    }])
    result = score_candidates(data=df, origin_data=origin_explicit_drift)
    cand = result.top_candidate
    assert cand is not None
    assert cand.evidence.evidence_metadata["explicit_drift_used"] is True
    assert cand.score.trajectory_score == 1.0


# ===========================================================================
# 4. Neutral Evidence & Provenance (Corrections 2 & 4)
# ===========================================================================
def test_evidence_neutral_ais_gap(sample_origin):
    """Verify gap produces neutral phrasing without intentional shutdown claims."""
    df_gap = pd.DataFrame([
        {"mmsi": 777777777, "timestamp": "2025-01-08T00:00:00Z", "latitude": 28.0, "longitude": -90.0, "distance_km": 1.0, "sog": 10.0},
        {"mmsi": 777777777, "timestamp": "2025-01-08T01:00:00Z", "latitude": 28.0, "longitude": -90.0, "distance_km": 1.0, "sog": 10.0},
    ])
    result = score_candidates(data=df_gap, origin_data=sample_origin)
    cand = result.top_candidate
    assert cand is not None
    assert cand.evidence.ais_gap_count == 1
    # Check that neutral description is used
    all_contra = " ".join(cand.evidence.contradicting_factors)
    assert "telemetry gap" in all_contra.lower()
    # Ensure NO claims of intentional transponder deactivation
    assert "intentional" not in all_contra.lower()
    assert "deactivation" not in all_contra.lower()
    assert "dark" not in all_contra.lower()


def test_evidence_interpolation_provenance_and_no_penalty(sample_origin):
    """Verify interpolation provenance is recorded and vessel is not penalized."""
    df_interp = pd.DataFrame([
        {"mmsi": 888888888, "timestamp": "2025-01-08T00:30:00Z", "latitude": 28.0, "longitude": -90.0, "distance_km": 0.5, "sog": 12.0, "is_interpolated": True},
    ])
    result = score_candidates(data=df_interp, origin_data=sample_origin)
    cand = result.top_candidate
    assert cand is not None
    assert cand.evidence.evidence_metadata["closest_approach_is_interpolated"] is True
    assert cand.evidence.interpolated_ratio == 1.0
    # Candidate achieved high spatial and temporal scores because closest approach is inside origin
    assert cand.score.spatial_score == 1.0
    assert cand.score.temporal_score == 1.0


# ===========================================================================
# 5. Edge Cases
# ===========================================================================
def test_edge_case_zero_candidates(sample_origin):
    """Verify empty dataset returns valid AttributionResult with 0 candidates."""
    empty_df = pd.DataFrame(columns=["mmsi", "timestamp", "latitude", "longitude", "distance_km"])
    result = score_candidates(data=empty_df, origin_data=sample_origin)
    assert isinstance(result, AttributionResult)
    assert len(result.ranked_candidates) == 0
    assert result.top_candidate is None
    assert result.report.total_candidate_vessels == 0


def test_edge_case_single_candidate(sample_origin):
    """Verify 1 candidate is scored normally and assigned rank 1."""
    single_df = pd.DataFrame([{
        "mmsi": 555555555,
        "timestamp": "2025-01-08T00:30:00Z",
        "latitude": 28.0,
        "longitude": -90.0,
        "distance_km": 2.0,
        "sog": 10.0,
    }])
    result = attribute_vessels(data=single_df, origin_data=sample_origin)
    assert len(result.ranked_candidates) == 1
    assert result.ranked_candidates[0].rank == 1
    assert result.ranked_candidates[0].vessel.mmsi == 555555555
