"""Unit tests for Attribution Explanation data models, contracts, and serialization (ATTR-03)."""

from dataclasses import FrozenInstanceError
import json
from typing import Any, Dict

import numpy as np
import pandas as pd
import pytest

from attribution.explanation.models import (
    DEFAULT_ATTRIBUTION_DISCLAIMER,
    AttributionExplanationReport,
    CandidateExplanation,
    ConfidenceTier,
)


# =============================================================================
# 1. ConfidenceTier Enumeration Tests
# =============================================================================

def test_confidence_tier_constants():
    """Verify analytical confidence tier enum constants."""
    assert ConfidenceTier.HIGH_CONFIDENCE.value == "HIGH_CONFIDENCE"
    assert ConfidenceTier.MODERATE_CONFIDENCE.value == "MODERATE_CONFIDENCE"
    assert ConfidenceTier.LOW_CONFIDENCE.value == "LOW_CONFIDENCE"
    assert ConfidenceTier.NEGLIGIBLE_CORRELATION.value == "NEGLIGIBLE_CORRELATION"


# =============================================================================
# 2. CandidateExplanation Instantiation & Validation Tests
# =============================================================================

def test_candidate_explanation_valid():
    """Verify complete, valid CandidateExplanation construction."""
    cand = CandidateExplanation(
        mmsi=368021480,
        rank=1,
        overall_score=0.9970,
        confidence_tier=ConfidenceTier.HIGH_CONFIDENCE.value,
        summary_narrative="Vessel passed close to the estimated release origin.",
        vessel_name="KENDRA JEAN",
        vessel_type="Towing",
        key_supporting_factors=["CPA 2.34 km <= radius 8.0 km", "CPA within 23 sec"],
        key_contradicting_factors=["Tug vessel type"],
        data_quality_notes=["Continuous AIS telemetry"],
        comparative_note="Rank #1: Highest analytical score.",
    )

    assert cand.mmsi == 368021480
    assert cand.rank == 1
    assert cand.overall_score == 0.9970
    assert cand.confidence_tier == "HIGH_CONFIDENCE"
    assert cand.vessel_name == "KENDRA JEAN"
    assert cand.vessel_type == "Towing"
    assert len(cand.key_supporting_factors) == 2
    assert len(cand.key_contradicting_factors) == 1
    assert len(cand.data_quality_notes) == 1
    assert cand.comparative_note == "Rank #1: Highest analytical score."


def test_candidate_explanation_immutability():
    """Verify that CandidateExplanation is frozen and immutable."""
    cand = CandidateExplanation(
        mmsi=205123456,
        rank=1,
        overall_score=0.85,
        confidence_tier="HIGH_CONFIDENCE",
        summary_narrative="Test narrative",
    )

    with pytest.raises((FrozenInstanceError, AttributeError)):
        cand.rank = 2  # type: ignore

    with pytest.raises((FrozenInstanceError, AttributeError)):
        cand.overall_score = 0.50  # type: ignore


@pytest.mark.parametrize("bad_mmsi", [0, -100, True, False, "invalid", 12.34])
def test_candidate_explanation_invalid_mmsi(bad_mmsi):
    """Verify rejection of invalid MMSI values."""
    with pytest.raises(ValueError):
        CandidateExplanation(
            mmsi=bad_mmsi,  # type: ignore
            rank=1,
            overall_score=0.75,
            confidence_tier="MODERATE_CONFIDENCE",
            summary_narrative="Valid narrative",
        )


@pytest.mark.parametrize("bad_rank", [0, -1, True, False, "not_rank"])
def test_candidate_explanation_invalid_rank(bad_rank):
    """Verify rejection of non-positive or non-integer rank."""
    with pytest.raises(ValueError):
        CandidateExplanation(
            mmsi=205123456,
            rank=bad_rank,  # type: ignore
            overall_score=0.75,
            confidence_tier="MODERATE_CONFIDENCE",
            summary_narrative="Valid narrative",
        )


@pytest.mark.parametrize("bad_score", [-0.1, 1.1, np.nan, np.inf, True, False, "bad"])
def test_candidate_explanation_invalid_score(bad_score):
    """Verify rejection of out-of-bounds or non-finite overall_score."""
    with pytest.raises(ValueError):
        CandidateExplanation(
            mmsi=205123456,
            rank=1,
            overall_score=bad_score,  # type: ignore
            confidence_tier="MODERATE_CONFIDENCE",
            summary_narrative="Valid narrative",
        )


def test_candidate_explanation_invalid_tier():
    """Verify rejection of unknown confidence tier."""
    with pytest.raises(ValueError, match="confidence_tier must be one of"):
        CandidateExplanation(
            mmsi=205123456,
            rank=1,
            overall_score=0.75,
            confidence_tier="CERTAIN_GUILT",
            summary_narrative="Valid narrative",
        )


@pytest.mark.parametrize("bad_narrative", ["", "   ", None, 123])
def test_candidate_explanation_invalid_narrative(bad_narrative):
    """Verify rejection of empty or non-string summary_narrative."""
    with pytest.raises(ValueError):
        CandidateExplanation(
            mmsi=205123456,
            rank=1,
            overall_score=0.75,
            confidence_tier="MODERATE_CONFIDENCE",
            summary_narrative=bad_narrative,  # type: ignore
        )


def test_candidate_explanation_serialization():
    """Verify deterministic JSON serialization of CandidateExplanation."""
    cand = CandidateExplanation(
        mmsi=205123456,
        rank=1,
        overall_score=0.8521,
        confidence_tier="HIGH_CONFIDENCE",
        summary_narrative="Test narrative",
        vessel_name="TEST_VESSEL",
        key_supporting_factors=["Factor A", "Factor B"],
        key_contradicting_factors=["Contra A"],
        data_quality_notes=["Quality Note"],
        comparative_note="Outranks candidate 2",
    )

    d = cand.to_dict()
    assert d["rank"] == 1
    assert d["mmsi"] == 205123456
    assert d["overall_score"] == 0.8521
    assert d["confidence_tier"] == "HIGH_CONFIDENCE"
    assert d["vessel_name"] == "TEST_VESSEL"
    assert d["key_supporting_factors"] == ["Factor A", "Factor B"]
    assert d["key_contradicting_factors"] == ["Contra A"]
    assert d["data_quality_notes"] == ["Quality Note"]
    assert d["comparative_note"] == "Outranks candidate 2"

    # Verify JSON serializability
    json_str = json.dumps(d)
    assert isinstance(json_str, str)
    loaded = json.loads(json_str)
    assert loaded["mmsi"] == 205123456


# =============================================================================
# 3. AttributionExplanationReport Tests
# =============================================================================

def test_attribution_explanation_report_valid():
    """Verify complete AttributionExplanationReport creation and methods."""
    c1 = CandidateExplanation(
        mmsi=205123456,
        rank=1,
        overall_score=0.92,
        confidence_tier="HIGH_CONFIDENCE",
        summary_narrative="Rank 1 narrative",
        vessel_name="ALPHA",
    )
    c2 = CandidateExplanation(
        mmsi=316000000,
        rank=2,
        overall_score=0.45,
        confidence_tier="LOW_CONFIDENCE",
        summary_narrative="Rank 2 narrative",
        vessel_name="BETA",
    )

    origin_dict = {
        "latitude": 37.80,
        "longitude": -122.40,
        "timestamp": "2025-01-07T01:00:00Z",
        "radius_km": 5.0,
        "confidence_level": 0.95,
    }

    report = AttributionExplanationReport(
        incident_summary="Incident evaluation summary test.",
        origin_summary=origin_dict,
        candidate_explanations=(c1, c2),
        top_candidate_summary="Rank 1 narrative",
        metadata={"run_id": "test_run_01"},
    )

    assert report.total_candidates == 2
    assert report.get_candidate(205123456) == c1
    assert report.get_candidate(316000000) == c2
    assert report.get_candidate(999999999) is None
    assert report.disclaimer == DEFAULT_ATTRIBUTION_DISCLAIMER

    # Test to_dict
    d = report.to_dict()
    assert d["total_candidates"] == 2
    assert d["origin_summary"]["latitude"] == 37.80
    assert len(d["candidate_explanations"]) == 2
    json_str = json.dumps(d)
    assert "Incident evaluation summary test." in json_str

    # Test to_dataframe
    df = report.to_dataframe()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert list(df["mmsi"]) == [205123456, 316000000]
    assert list(df["rank"]) == [1, 2]
    assert "confidence_tier" in df.columns

    # Test to_markdown
    md = report.to_markdown()
    assert isinstance(md, str)
    assert "# Marine Oil Spill Attribution & Explainability Report" in md
    assert "Latitude 37.80000°, Longitude -122.40000°" in md
    assert "ALPHA" in md
    assert "BETA" in md
    assert DEFAULT_ATTRIBUTION_DISCLAIMER in md


def test_attribution_explanation_report_empty():
    """Verify AttributionExplanationReport behavior with zero candidates."""
    origin_dict = {
        "latitude": 28.0,
        "longitude": -90.0,
        "timestamp": "2025-01-08T00:00:00Z",
        "radius_km": 0.0,
    }

    report = AttributionExplanationReport(
        incident_summary="No candidate vessels found.",
        origin_summary=origin_dict,
        candidate_explanations=(),
    )

    assert report.total_candidates == 0
    assert report.get_candidate(123456789) is None

    # DataFrame should be empty with correct columns
    df = report.to_dataframe()
    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert "mmsi" in df.columns
    assert "rank" in df.columns

    # Markdown should state no candidate vessels identified
    md = report.to_markdown()
    assert "No candidate vessels identified" in md
    assert DEFAULT_ATTRIBUTION_DISCLAIMER in md
