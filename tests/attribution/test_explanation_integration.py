"""ATTR-03 Integration Tests: Full AIS-07 Handoff to Attribution Explanation Engine.

Validates the complete vertical processing pipeline:
Member 4 Origin Analysis
    ↓ (AIS-08)
AISIntegrationResult & AISSearchRequest
    ↓ (AIS-09)
Raw Observations (LocalAISProvider)
    ↓ (AIS-04)
Trajectory Reconstruction
    ↓ (AIS-05)
Kinematic Interpolation
    ↓ (AIS-06)
Spatial Filtering
    ↓ (AIS-07)
TemporalFilterResult
    ↓ (ATTR-01, ATTR-02)
AttributionResult (score_candidates / attribute_vessels)
    ↓
=============================================================================
ATTR-03 Attribution Explanation Engine (explain_attribution)
=============================================================================
    ↓ Candidate Dossiers, Factor Synthesis, Natural Language Narratives
AttributionExplanationReport
    ↓
Multi-Format Export: JSON Dict, Markdown Document, Tabular DataFrame
"""

import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import pytest

from ais.filtering import (
    SpatialFilterConfig,
    SpatialFilterResult,
    TemporalFilterConfig,
    TemporalFilterResult,
    filter_spatial,
    filter_temporal,
)
from ais.integration.adapter import adapt_drift_origin_result
from ais.interpolation import InterpolationConfig, interpolate_trajectories
from ais.providers import LocalAISProvider
from ais.trajectory import reconstruct_trajectories
from attribution import (
    AttributionExplanationReport,
    AttributionResult,
    AttributionScoringConfig,
    ConfidenceTier,
    DEFAULT_ATTRIBUTION_DISCLAIMER,
    attribute_vessels,
    explain_attribution,
    score_candidates,
)


@pytest.fixture
def synthetic_scoring_csv(tmp_path: Path) -> Path:
    """Generate controlled synthetic AIS CSV with 3 candidate vessels."""
    csv_file = tmp_path / "synthetic_ais_explanation.csv"
    data = """MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft
205123456,2025-01-08T00:00:00Z,28.0000,-90.0000,10.0,180.0,180.0,ALPHA_TANKER,IMO1111111,WDC1111,80,0,180,30,10.5
205123456,2025-01-08T00:10:00Z,28.0050,-90.0000,10.0,180.0,180.0,ALPHA_TANKER,IMO1111111,WDC1111,80,0,180,30,10.5
205123456,2025-01-08T00:20:00Z,28.0100,-90.0000,10.5,180.0,180.0,ALPHA_TANKER,IMO1111111,WDC1111,80,0,180,30,10.5
211987654,2025-01-08T00:05:00Z,28.0500,-90.0000,12.0,90.0,90.0,BETA_CARGO,IMO2222222,WDC2222,70,0,150,25,8.0
211987654,2025-01-08T00:15:00Z,28.0600,-90.0000,12.0,90.0,90.0,BETA_CARGO,IMO2222222,WDC2222,70,0,150,25,8.0
316000000,2025-01-08T00:08:00Z,28.0400,-90.0000,5.0,0.0,0.0,GAMMA_TUG,IMO3333333,WDC3333,52,0,40,10,4.0
316000000,2025-01-08T00:18:00Z,28.0450,-90.0000,5.0,0.0,0.0,GAMMA_TUG,IMO3333333,WDC3333,52,0,40,10,4.0
"""
    csv_file.write_text(data, encoding="utf-8")
    return csv_file


# =============================================================================
# 1. Synthetic Full Pipeline Integration Test
# =============================================================================

def test_synthetic_pipeline_to_attr03_explanation(synthetic_scoring_csv):
    """Verify full vertical pipeline from synthetic AIS data to ATTR-03 explanation report."""
    origin_payload: Dict[str, Any] = {
        "status": "success",
        "best_candidate": {
            "timestamp": "2025-01-08T00:10:00Z",
            "region": {
                "centroid_lat": 28.005,
                "centroid_lon": -90.000,
                "radius_km": 5.0,
            },
        },
    }

    adapter_res = adapt_drift_origin_result(
        origin_payload,
        before_minutes=30.0,
        after_minutes=30.0,
        buffer_km=2.0,
    )

    provider = LocalAISProvider(synthetic_scoring_csv)
    df_raw = provider.fetch_ais_data(adapter_res.search_request)
    traj_res = reconstruct_trajectories(df_raw)
    interp_res = interpolate_trajectories(traj_res, time_step_seconds=120.0)
    spatial_res = filter_spatial(interp_res, SpatialFilterConfig(buffer_km=2.0), origin_data=adapter_res)
    temporal_res = filter_temporal(spatial_res, TemporalFilterConfig(before_minutes=30.0, after_minutes=30.0), origin_data=adapter_res)

    # 1. ATTR-02 Scoring
    scoring_result = score_candidates(data=temporal_res, origin_data=adapter_res)
    assert isinstance(scoring_result, AttributionResult)
    assert len(scoring_result.ranked_candidates) == 3

    # 2. ATTR-03 Explanation
    report = explain_attribution(scoring_result, top_n=2)
    assert isinstance(report, AttributionExplanationReport)
    assert report.total_candidates == 3
    assert len(report.candidate_explanations) == 3

    # Rank 1: Tanker (205123456)
    top_cand = report.candidate_explanations[0]
    assert top_cand.rank == 1
    assert top_cand.mmsi == 205123456
    assert top_cand.vessel_name == "ALPHA_TANKER"
    assert top_cand.confidence_tier == ConfidenceTier.HIGH_CONFIDENCE.value
    assert "ALPHA_TANKER" in top_cand.summary_narrative
    assert "closest approach" in top_cand.summary_narrative
    assert len(top_cand.key_supporting_factors) > 0
    assert top_cand.comparative_note is not None

    # Rank 2: Cargo (211987654) - within top_n=2
    second_cand = report.candidate_explanations[1]
    assert second_cand.rank == 2
    assert second_cand.mmsi == 211987654
    assert second_cand.vessel_name == "BETA_CARGO"

    # Rank 3: Tug (316000000) - outside top_n=2, should have standardized summary
    third_cand = report.candidate_explanations[2]
    assert third_cand.rank == 3
    assert "outside top 2 detailed narrative review" in third_cand.summary_narrative

    # Test JSON serialization
    report_dict = report.to_dict()
    assert report_dict["total_candidates"] == 3
    json_str = json.dumps(report_dict)
    assert isinstance(json_str, str)

    # Test DataFrame export
    df_exp = report.to_dataframe()
    assert len(df_exp) == 3
    assert list(df_exp["rank"]) == [1, 2, 3]

    # Test Markdown export
    md_exp = report.to_markdown()
    assert "# Marine Oil Spill Attribution & Explainability Report" in md_exp
    assert "ALPHA_TANKER" in md_exp
    assert DEFAULT_ATTRIBUTION_DISCLAIMER in md_exp


def test_custom_disclaimer_override(synthetic_scoring_csv):
    """Verify that a custom disclaimer is respected in reports and markdown."""
    origin_payload: Dict[str, Any] = {
        "status": "success",
        "best_candidate": {
            "timestamp": "2025-01-08T00:10:00Z",
            "region": {"centroid_lat": 28.005, "centroid_lon": -90.000, "radius_km": 5.0},
        },
    }
    adapter_res = adapt_drift_origin_result(origin_payload)
    provider = LocalAISProvider(synthetic_scoring_csv)
    df_raw = provider.fetch_ais_data(adapter_res.search_request)
    traj_res = reconstruct_trajectories(df_raw)
    interp_res = interpolate_trajectories(traj_res, time_step_seconds=120.0)
    spatial_res = filter_spatial(interp_res, origin_data=adapter_res)
    temporal_res = filter_temporal(spatial_res, origin_data=adapter_res)
    scoring_result = score_candidates(data=temporal_res, origin_data=adapter_res)

    custom_text = "CONFIDENTIAL TEST AUDIT REPORT: STRICTLY INTERNAL"
    report = explain_attribution(scoring_result, custom_disclaimer=custom_text)
    assert report.disclaimer == custom_text
    assert custom_text in report.to_markdown()


# =============================================================================
# 2. Real NOAA San Francisco Bay Integration Test
# =============================================================================

def test_real_noaa_san_francisco_bay_to_attr03_explanation():
    """Verify full end-to-end integration on the real NOAA San Francisco Bay dataset."""
    real_path = Path("data/ais/2025/AIS_178881322085076878_1697-1788813221032.csv")
    if not real_path.exists():
        pytest.skip(f"Real NOAA dataset not found at {real_path}")

    # San Francisco Bay estimated origin coordinates
    origin_payload: Dict[str, Any] = {
        "status": "success",
        "best_candidate": {
            "timestamp": "2025-01-07T01:00:04Z",
            "region": {
                "centroid_lat": 37.80115,
                "centroid_lon": -122.39649,
                "radius_km": 8.0,
            },
        },
    }

    adapter_res = adapt_drift_origin_result(
        origin_payload,
        before_minutes=30.0,
        after_minutes=30.0,
        buffer_km=2.0,
    )

    provider = LocalAISProvider(real_path)
    df_raw = provider.fetch_ais_data(adapter_res.search_request)
    assert not df_raw.empty

    traj_res = reconstruct_trajectories(df_raw)
    interp_res = interpolate_trajectories(
        traj_res,
        time_step_seconds=120.0,
        config=InterpolationConfig(max_gap_seconds=1800.0),
    )
    spatial_res = filter_spatial(
        data=interp_res,
        config=SpatialFilterConfig(buffer_km=2.0),
        origin_data=adapter_res,
    )
    temporal_res = filter_temporal(
        data=spatial_res,
        config=TemporalFilterConfig(before_minutes=30.0, after_minutes=30.0),
        origin_data=adapter_res,
    )
    assert not temporal_res.data.empty

    # Execute ATTR-02 scoring
    scoring_result = attribute_vessels(data=temporal_res, origin_data=adapter_res)
    assert isinstance(scoring_result, AttributionResult)
    assert len(scoring_result.ranked_candidates) == 110

    # Execute ATTR-03 explanation
    report = explain_attribution(scoring_result, top_n=5)
    assert isinstance(report, AttributionExplanationReport)
    assert report.total_candidates == 110
    assert len(report.candidate_explanations) == 110

    # 1. Verify Top Candidate (KENDRA JEAN, MMSI 338205367)
    top_cand = report.candidate_explanations[0]
    assert top_cand.rank == 1
    assert top_cand.mmsi == 338205367
    assert top_cand.vessel_name == "KENDRA JEAN"
    assert top_cand.confidence_tier == ConfidenceTier.HIGH_CONFIDENCE.value
    assert top_cand.overall_score >= 0.99
    assert "KENDRA JEAN" in top_cand.summary_narrative
    assert "they do not establish that the vessel caused the spill" in top_cand.summary_narrative
    assert len(top_cand.key_supporting_factors) > 0
    assert len(top_cand.data_quality_notes) > 0
    assert top_cand.comparative_note is not None

    # 2. Verify Top-N detailed vs peripheral candidates
    for idx, c in enumerate(report.candidate_explanations):
        if idx < 5:
            assert "outside top" not in c.summary_narrative
        else:
            assert "outside top 5 detailed narrative review" in c.summary_narrative

    # 3. Verify JSON serialization
    report_dict = report.to_dict()
    assert report_dict["total_candidates"] == 110
    assert report_dict["origin_summary"]["latitude"] == 37.80115
    json_str = json.dumps(report_dict)
    assert isinstance(json_str, str)
    assert "KENDRA JEAN" in json_str

    # 4. Verify DataFrame export
    df_exp = report.to_dataframe()
    assert isinstance(df_exp, pd.DataFrame)
    assert len(df_exp) == 110
    assert list(df_exp["rank"]) == list(range(1, 111))
    assert df_exp.iloc[0]["mmsi"] == 338205367
    assert df_exp.iloc[0]["vessel_name"] == "KENDRA JEAN"

    # 5. Verify Markdown export
    md_exp = report.to_markdown()
    assert "# Marine Oil Spill Attribution & Explainability Report" in md_exp
    assert "Latitude 37.80115°, Longitude -122.39649°" in md_exp
    assert "KENDRA JEAN" in md_exp
    assert DEFAULT_ATTRIBUTION_DISCLAIMER in md_exp

    # 6. Verify 100% Determinism across repeated runs
    report2 = explain_attribution(scoring_result, top_n=5)
    assert report.to_dict() == report2.to_dict()
    assert report.to_markdown() == report2.to_markdown()
