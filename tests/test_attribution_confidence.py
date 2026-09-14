"""Unit tests for vessel attribution confidence scoring."""

import pytest
from backend.services.confidence_scoring import (
    compute_vessel_confidence,
    get_vessel_type_relevance,
    resolve_confidence_level,
)
from backend.schemas.vessel import CandidateVessel


def test_resolve_confidence_level():
    assert resolve_confidence_level(95.0) == "VERY HIGH"
    assert resolve_confidence_level(90.0) == "VERY HIGH"
    assert resolve_confidence_level(89.9) == "HIGH"
    assert resolve_confidence_level(75.0) == "HIGH"
    assert resolve_confidence_level(74.9) == "MODERATE"
    assert resolve_confidence_level(50.0) == "MODERATE"
    assert resolve_confidence_level(49.9) == "LOW"
    assert resolve_confidence_level(25.0) == "LOW"
    assert resolve_confidence_level(24.9) == "VERY LOW"
    assert resolve_confidence_level(0.0) == "VERY LOW"


def test_vessel_type_relevance():
    assert get_vessel_type_relevance("Crude Oil Tanker") == 1.0
    assert get_vessel_type_relevance(80) == 1.0
    assert get_vessel_type_relevance("Container Ship") == 0.85
    assert get_vessel_type_relevance(70) == 0.85
    assert get_vessel_type_relevance("Tug") == 0.60
    assert get_vessel_type_relevance("Fishing Trawler") == 0.45
    assert get_vessel_type_relevance("Pleasure Craft") == 0.20
    assert get_vessel_type_relevance(None) is None


def test_compute_vessel_confidence_full_evidence():
    result = compute_vessel_confidence(
        spatial_score=0.95,
        temporal_score=0.90,
        trajectory_score=0.88,
        behaviour_score=0.85,
        overall_score=0.92,
        min_distance_km=1.2,
        time_difference_minutes=15.0,
        vessel_type="Tanker",
        transit_speed_knots=11.5,
        ais_gap_count=0,
        total_observations=45,
    )

    assert result["confidence_score"] >= 90.0
    assert result["confidence_level"] == "VERY HIGH"
    assert len(result["confidence_factors"]["supporting"]) > 0
    assert result["confidence_factors"]["spatial_proximity"] == 0.95
    assert result["confidence_factors"]["temporal_overlap"] == 0.90
    assert result["confidence_factors"]["vessel_type_relevance"] == 1.0


def test_compute_vessel_confidence_missing_factors():
    # Verify missing factors are omitted from denominator without penalizing score
    result = compute_vessel_confidence(
        spatial_score=0.85,
        temporal_score=0.80,
        trajectory_score=None,  # missing drift
        behaviour_score=None,
        overall_score=0.82,
        min_distance_km=3.5,
        time_difference_minutes=40.0,
        vessel_type=None,  # unverified type
        transit_speed_knots=None,
    )

    assert 75.0 <= result["confidence_score"] <= 89.9
    assert result["confidence_level"] == "HIGH"
    assert result["confidence_factors"]["drift_consistency"] is None
    assert result["confidence_factors"]["vessel_type_relevance"] is None
    assert any("not computed" in note.lower() for note in result["confidence_factors"]["limitations"])


def test_candidate_vessel_schema_auto_enrichment():
    # Verify CandidateVessel automatically derives confidence
    raw_data = {
        "rank": 1,
        "mmsi": 413999001,
        "vessel_name": "T.SADBERK",
        "imo": "9123456",
        "vessel_type": "Tanker",
        "scores": {
            "overall": 0.88,
            "spatial": 0.90,
            "temporal": 0.85,
            "trajectory": 0.80,
            "behaviour": 0.85,
        },
        "metrics": {
            "min_distance_km": 1.8,
            "time_difference_minutes": 20.0,
            "transit_speed_knots": 12.0,
        },
    }
    vessel = CandidateVessel.model_validate(raw_data)
    assert vessel.confidence_score > 80.0
    assert vessel.confidence_level in ["HIGH", "VERY HIGH"]
    assert vessel.confidence_factors is not None
    assert len(vessel.confidence_factors.supporting) >= 1
