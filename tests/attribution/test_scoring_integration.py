"""ATTR-02 Integration Tests: Full AIS-07 Handoff to Attribution Scoring Engine.

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
    ↓
=============================================================================
ATTR-02 Attribution Scoring Engine (score_candidates / attribute_vessels)
=============================================================================
    ↓ Spatial, Temporal, Trajectory, and Behaviour Scorers
AttributedCandidate Ranked List (1..N)
    ↓ AttributionResult
Summary DataFrame & Deterministic JSON Serialization
"""

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
    AttributionResult,
    AttributionScoringConfig,
    attribute_vessels,
    score_candidates,
)


@pytest.fixture
def synthetic_scoring_csv(tmp_path: Path) -> Path:
    """Generate controlled synthetic NOAA-like AIS CSV with 3 candidate vessels."""
    csv_file = tmp_path / "synthetic_ais_scoring.csv"
    data = """MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft
205123456,2025-01-08T00:00:00Z,28.0000,-90.0000,10.0,180.0,180.0,ALPHA_TANKER,IMO1111111,WDC1111,80,0,180,30,10.5
205123456,2025-01-08T00:10:00Z,28.0050,-90.0000,10.0,180.0,180.0,ALPHA_TANKER,IMO1111111,WDC1111,80,0,180,30,10.5
205123456,2025-01-08T00:20:00Z,28.0100,-90.0000,10.5,180.0,180.0,ALPHA_TANKER,IMO1111111,WDC1111,80,0,180,30,10.5
211987654,2025-01-08T00:05:00Z,28.0500,-90.0000,12.0,90.0,90.0,BETA_CARGO,IMO2222222,WDC2222,70,0,150,25,8.0
211987654,2025-01-08T00:15:00Z,28.0600,-90.0000,12.0,90.0,90.0,BETA_CARGO,IMO2222222,WDC2222,70,0,150,25,8.0
316000000,2025-01-08T00:10:00Z,28.1500,-90.0000,5.0,0.0,0.0,GAMMA_TUG,IMO3333333,WDC3333,52,0,40,10,4.0
"""
    csv_file.write_text(data, encoding="utf-8")
    return csv_file


def test_synthetic_ais07_to_attr02_full_pipeline(synthetic_scoring_csv):
    """Verify complete vertical chain from synthetic AIS data through ATTR-02 scoring."""
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

    # 1. AIS-08 (Adapt drift origin)
    adapter_res = adapt_drift_origin_result(
        origin_payload,
        before_minutes=30.0,
        after_minutes=30.0,
        buffer_km=2.0,
    )

    # 2. AIS-09 (Fetch via provider)
    provider = LocalAISProvider(synthetic_scoring_csv)
    df_raw = provider.fetch_ais_data(adapter_res.search_request)
    assert not df_raw.empty

    # 3. AIS-04 (Reconstruct trajectories)
    traj_res = reconstruct_trajectories(df_raw)

    # 4. AIS-05 (Kinematic interpolation)
    interp_res = interpolate_trajectories(
        traj_res,
        time_step_seconds=120.0,
        config=InterpolationConfig(max_gap_seconds=1800.0),
    )

    # 5. AIS-06 (Spatial filtering)
    spatial_res = filter_spatial(
        data=interp_res,
        config=SpatialFilterConfig(buffer_km=2.0),
        origin_data=adapter_res,
    )
    assert isinstance(spatial_res, SpatialFilterResult)

    # 6. AIS-07 (Temporal filtering)
    temporal_res = filter_temporal(
        data=spatial_res,
        config=TemporalFilterConfig(before_minutes=30.0, after_minutes=30.0),
        origin_data=adapter_res,
    )
    assert isinstance(temporal_res, TemporalFilterResult)
    assert not temporal_res.data.empty

    # 7. ATTR-02 Scoring Engine
    config = AttributionScoringConfig()
    result = score_candidates(data=temporal_res, origin_data=adapter_res, config=config)

    assert isinstance(result, AttributionResult)
    assert len(result.ranked_candidates) > 0

    # Verify sequential ranks
    assert [c.rank for c in result.ranked_candidates] == list(range(1, len(result.ranked_candidates) + 1))

    # Top candidate should be the close Tanker (205123456) which passed through (28.005, -90.0) at 00:10:00
    top = result.top_candidate
    assert top is not None
    assert top.vessel.mmsi == 205123456
    assert top.score.spatial_score == 1.0  # Inside radius
    assert top.score.temporal_score == 1.0  # Exactly at origin time

    # Verify all scores are bounded in [0.0, 1.0]
    for cand in result.ranked_candidates:
        s = cand.score
        assert 0.0 <= s.overall_score <= 1.0
        if s.spatial_score is not None:
            assert 0.0 <= s.spatial_score <= 1.0
        if s.temporal_score is not None:
            assert 0.0 <= s.temporal_score <= 1.0
        if s.trajectory_score is not None:
            assert 0.0 <= s.trajectory_score <= 1.0
        if s.behaviour_score is not None:
            assert 0.0 <= s.behaviour_score <= 1.0

    # Summary dataframe verification
    df_summary = result.to_dataframe()
    assert len(df_summary) == len(result.ranked_candidates)
    assert "rank" in df_summary.columns
    assert "overall_score" in df_summary.columns


def test_real_noaa_ais07_to_attr02_full_pipeline():
    """Verify end-to-end handoff from actual NOAA AIS-07 output to ATTR-02 scoring engine."""
    real_path = Path("data/ais/2025/AIS_178881322085076878_1697-1788813221032.csv")
    if not real_path.exists():
        pytest.skip(f"Real NOAA dataset not found at {real_path}")

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
    result = attribute_vessels(data=temporal_res, origin_data=adapter_res)
    assert isinstance(result, AttributionResult)
    assert len(result.ranked_candidates) > 0

    top = result.top_candidate
    assert top is not None
    assert top.rank == 1
    assert 0.0 <= top.score.overall_score <= 1.0

    # Verify report provenance
    assert result.report.total_input_observations == len(temporal_res.data)
    assert result.report.total_candidate_vessels == len(result.ranked_candidates)
