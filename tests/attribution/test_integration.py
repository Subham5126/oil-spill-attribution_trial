"""ATTR-01 Integration Tests: AIS-07 Handoff to Attribution Foundation.

Validates the vertical handoff:
Fake Member-4 Output
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
ATTR-01 Attribution Layer
=============================================================================
    ↓ validate_ais_observations() & validate_origin_metadata()
Validated Telemetry DataFrame & OriginMetadata
    ↓ extract_candidate_vessels()
Vessel-Level CandidateVessel Objects
    ↓ AttributionEvidence & VesselScore (neutral test containers)
AttributedCandidate List (Ranked 1..N)
    ↓ AttributionResult
Deterministic JSON Dictionary & Summary DataFrame
"""

import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pytest

from ais.filtering import (
    SpatialFilterConfig,
    SpatialFilterResult,
    TemporalFilterConfig,
    TemporalFilterReport,
    TemporalFilterResult,
    filter_spatial,
    filter_temporal,
)
from ais.integration.adapter import adapt_drift_origin_result
from ais.interpolation import InterpolationConfig, interpolate_trajectories
from ais.providers import LocalAISProvider
from ais.trajectory import reconstruct_trajectories
from attribution import (
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


# ---------------------------------------------------------------------------
# Synthetic Pipeline Fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def synthetic_ais_dataset(tmp_path: Path) -> Path:
    """Generate controlled synthetic NOAA-like AIS CSV."""
    csv_file = tmp_path / "synthetic_ais_attr.csv"
    data = """MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft
205123456,2025-01-08T00:00:00Z,28.0000,-90.0000,10.0,180.0,180.0,ALPHA_CARGO,IMO1111111,WDC1111,70,0,150,25,8.0
205123456,2025-01-08T00:10:00Z,28.0100,-90.0000,10.5,180.0,180.0,ALPHA_CARGO,IMO1111111,WDC1111,70,0,150,25,8.0
205123456,2025-01-08T00:20:00Z,28.0200,-90.0000,11.0,180.0,180.0,ALPHA_CARGO,IMO1111111,WDC1111,70,0,150,25,8.0
211987654,2025-01-08T00:15:00Z,28.0050,-90.0050,5.0,90.0,90.0,BETA_TANKER,IMO2222222,WDC2222,80,0,180,30,10.5
316000000,2025-01-07T21:00:00Z,28.0000,-90.0000,12.0,0.0,0.0,GAMMA_TUG,IMO3333333,WDC3333,52,0,40,10,4.0
"""
    csv_file.write_text(data, encoding="utf-8")
    return csv_file


# ===========================================================================
# 1. Real NOAA Dataset End-to-End AIS-07 -> ATTR-01 Handoff
# ===========================================================================
def test_real_noaa_ais07_to_attr01_handoff():
    """Verify end-to-end handoff from actual NOAA AIS-07 output to ATTR-01 models."""
    real_path = Path("data/ais/2025/AIS_178881322085076878_1697-1788813221032.csv")
    if not real_path.exists():
        pytest.skip(f"Real NOAA dataset not found at {real_path}")

    # Stage 0: Fake Member 4 origin analysis output
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

    # Stage 1: AIS-08 (Adapt drift origin result)
    adapter_res = adapt_drift_origin_result(
        origin_payload,
        before_minutes=30.0,
        after_minutes=30.0,
        buffer_km=2.0,  # Effective radius = 10.0 km
    )
    req = adapter_res.search_request

    # Stage 2: AIS-09 (Fetch via LocalAISProvider)
    provider = LocalAISProvider(real_path)
    df_matched = provider.fetch_ais_data(req)
    assert not df_matched.empty

    # Stage 3: AIS-04 (Trajectory Reconstruction)
    traj_result = reconstruct_trajectories(df_matched)

    # Stage 4: AIS-05 (Kinematic Interpolation)
    interp_result = interpolate_trajectories(
        traj_result,
        time_step_seconds=120.0,
        config=InterpolationConfig(max_gap_seconds=1800.0),
    )

    # Stage 5: AIS-06 (Spatial Filtering)
    spatial_result = filter_spatial(
        data=interp_result,
        config=SpatialFilterConfig(buffer_km=2.0),
        origin_data=adapter_res,
    )
    assert isinstance(spatial_result, SpatialFilterResult)

    # Stage 6: AIS-07 (Temporal Filtering)
    temporal_result = filter_temporal(
        data=spatial_result,
        config=TemporalFilterConfig(before_minutes=30.0, after_minutes=30.0),
        origin_data=adapter_res,
    )
    assert isinstance(temporal_result, TemporalFilterResult)
    assert not temporal_result.data.empty

    # -----------------------------------------------------------------------
    # ATTR-01 HANDOFF & VALIDATION
    # -----------------------------------------------------------------------
    # Requirement 4 & 9: Pass origin metadata produced by AIS-08 into ATTR validation
    origin_meta = validate_origin_metadata(adapter_res)
    assert isinstance(origin_meta, OriginMetadata)
    assert origin_meta.latitude == 37.80115
    assert origin_meta.longitude == -122.39649
    assert origin_meta.radius_km == 8.0
    assert origin_meta.timestamp == pd.Timestamp("2025-01-07T01:00:04Z")

    # Requirement 2: Take ACTUAL AIS-07 final output object directly into ATTR validation
    validated_telemetry = validate_ais_observations(temporal_result)
    assert isinstance(validated_telemetry, pd.DataFrame)
    assert len(validated_telemetry) == len(temporal_result.data)

    # Requirement 5 & 6: Extract vessel-level CandidateVessel objects
    candidate_vessels: List[CandidateVessel] = extract_candidate_vessels(temporal_result)
    assert len(candidate_vessels) > 0

    # Number of candidate vessels must exactly match unique MMSIs in AIS-07
    expected_mmsis = set(temporal_result.data["mmsi"].dropna().astype(int).unique())
    extracted_mmsis = {v.mmsi for v in candidate_vessels}
    assert extracted_mmsis == expected_mmsis
    assert len(candidate_vessels) == len(expected_mmsis)

    # Verify observation count conservation
    total_extracted_obs = sum(v.total_observations for v in candidate_vessels)
    assert total_extracted_obs == len(validated_telemetry)

    total_actual_obs = sum(v.actual_observations for v in candidate_vessels)
    expected_actual = int((~validated_telemetry["is_interpolated"]).sum())
    assert total_actual_obs == expected_actual

    total_interp_obs = sum(v.interpolated_observations for v in candidate_vessels)
    expected_interp = int(validated_telemetry["is_interpolated"].sum())
    assert total_interp_obs == expected_interp

    # Verify individual vessel attribute accuracy against raw group data
    for vessel in candidate_vessels:
        v_group = validated_telemetry[validated_telemetry["mmsi"] == vessel.mmsi]
        assert vessel.total_observations == len(v_group)
        assert vessel.min_distance_km == pytest.approx(v_group["distance_km"].min(), rel=1e-5)
        assert vessel.first_observed_time == v_group["timestamp"].min()
        assert vessel.last_observed_time == v_group["timestamp"].max()

        # Closest approach time must match the timestamp of the row with minimum distance
        min_row_idx = v_group["distance_km"].idxmin()
        assert vessel.closest_approach_time == v_group.loc[min_row_idx, "timestamp"]

        # Trajectory segment IDs match
        expected_segs = sorted(list(v_group["trajectory_segment_id"].dropna().astype(str).unique()))
        assert vessel.segment_ids == expected_segs

        # Mean SOG matches
        if not v_group["sog"].dropna().empty:
            assert vessel.mean_sog_knots == pytest.approx(v_group["sog"].dropna().mean(), rel=1e-5)

    # -----------------------------------------------------------------------
    # Requirement 10, 11, 12, 13: Build AttributionResult with Neutral Test Scores
    # -----------------------------------------------------------------------
    # Rank candidates 1..N based on proximity order (closest first)
    ranked_candidates: List[AttributedCandidate] = []
    for rank_idx, vessel in enumerate(candidate_vessels, start=1):
        # Build evidence container
        evidence = AttributionEvidence(
            min_distance_km=vessel.min_distance_km,
            time_of_closest_approach=vessel.closest_approach_time,
            mean_speed_knots=vessel.mean_sog_knots,
            telemetry_continuity=1.0 if vessel.actual_observations > 0 else 0.0,
            supporting_factors=[f"Approached within {vessel.min_distance_km:.2f} km of origin"],
        )
        # Neutral test scores in [0.0, 1.0] (no real scoring logic yet)
        test_score = VesselScore(
            spatial_score=0.5,
            temporal_score=0.5,
            trajectory_score=0.5,
            overall_score=round(max(0.01, 1.0 - (rank_idx * 0.01)), 4),
        )
        candidate = AttributedCandidate(
            rank=rank_idx,
            vessel=vessel,
            score=test_score,
            evidence=evidence,
        )
        ranked_candidates.append(candidate)

    report = AttributionReport(
        total_input_observations=len(validated_telemetry),
        total_candidate_vessels=len(candidate_vessels),
        evaluation_timestamp="2026-09-08T15:30:00Z",
        origin_timestamp=origin_meta.timestamp.isoformat(),
        origin_center=(origin_meta.latitude, origin_meta.longitude),
        origin_radius_km=origin_meta.radius_km,
        execution_notes=["ATTR-01 NOAA integration handoff validation"],
    )

    attr_result = AttributionResult(
        ranked_candidates=ranked_candidates,
        origin_metadata=origin_meta,
        report=report,
    )

    # Verify top candidate access
    top_cand = attr_result.top_candidate
    assert top_cand is not None
    assert top_cand.rank == 1
    assert top_cand.mmsi == candidate_vessels[0].mmsi

    # Requirement 11: Serialization and deterministic representation
    result_dict = attr_result.to_dict()
    assert isinstance(result_dict, dict)
    assert len(result_dict["ranked_candidates"]) == len(candidate_vessels)
    # Check JSON serializability
    json_bytes = json.dumps(result_dict)
    assert len(json_bytes) > 0

    # Tabular export
    summary_df = attr_result.to_dataframe()
    assert isinstance(summary_df, pd.DataFrame)
    assert len(summary_df) == len(candidate_vessels)
    assert list(summary_df["rank"]) == list(range(1, len(candidate_vessels) + 1))
    assert list(summary_df["mmsi"]) == [c.mmsi for c in candidate_vessels]

    print(
        f"\n[ATTR-01 Real NOAA Integration] Consumed {len(validated_telemetry):,} AIS-07 fixes "
        f"across {len(candidate_vessels):,} vessels. Top candidate MMSI: {top_cand.mmsi} "
        f"at {top_cand.vessel.min_distance_km:.3f} km. "
        f"Result DataFrame shape: {summary_df.shape}"
    )


# ===========================================================================
# 2. Synthetic AIS-07 -> ATTR-01 Full Pipeline Integration
# ===========================================================================
def test_synthetic_ais07_to_attr01_handoff(synthetic_ais_dataset: Path):
    """Test full synthetic chain to ensure contract stability across all stages."""
    origin_payload = {
        "status": "success",
        "best_candidate": {
            "timestamp": "2025-01-08T00:15:00Z",
            "region": {
                "centroid_lat": 28.0000,
                "centroid_lon": -90.0000,
                "radius_km": 5.0,
            },
        },
    }

    adapter_res = adapt_drift_origin_result(
        origin_payload,
        before_minutes=20.0,
        after_minutes=20.0,
        buffer_km=1.0,
    )
    req = adapter_res.search_request

    provider = LocalAISProvider(synthetic_ais_dataset)
    df_matched = provider.fetch_ais_data(req)
    traj_result = reconstruct_trajectories(df_matched)
    interp_result = interpolate_trajectories(traj_result, time_step_seconds=300.0)
    spatial_result = filter_spatial(interp_result, origin_data=adapter_res)
    temporal_result = filter_temporal(spatial_result, origin_data=adapter_res)

    # Pass into ATTR-01
    origin_meta = validate_origin_metadata(adapter_res)
    validated_telemetry = validate_ais_observations(temporal_result)
    candidates = extract_candidate_vessels(temporal_result)

    # In synthetic dataset: Vessel 205123456 and 211987654 qualify
    assert len(candidates) == 2
    cand_mmsis = {c.mmsi for c in candidates}
    assert cand_mmsis == {205123456, 211987654}

    # Vessel 1 (205123456) has interpolated fixes
    v1 = next(c for c in candidates if c.mmsi == 205123456)
    assert v1.vessel_name == "ALPHA_CARGO"
    assert v1.imo == "IMO1111111"
    assert v1.callsign == "WDC1111"
    assert v1.actual_observations == 3
    assert v1.interpolated_observations == 2
    assert v1.total_observations == 5

    # Vessel 2 (211987654) single fix
    v2 = next(c for c in candidates if c.mmsi == 211987654)
    assert v2.vessel_name == "BETA_TANKER"
    assert v2.actual_observations == 1
    assert v2.interpolated_observations == 0

    # Build AttributionResult
    ranked = [
        AttributedCandidate(
            rank=i + 1,
            vessel=cand,
            score=VesselScore(overall_score=0.8 - (i * 0.1)),
            evidence=AttributionEvidence(min_distance_km=cand.min_distance_km),
        )
        for i, cand in enumerate(candidates)
    ]
    report = AttributionReport(
        total_input_observations=len(validated_telemetry),
        total_candidate_vessels=len(candidates),
        evaluation_timestamp="2026-09-08T15:00:00Z",
    )
    result = AttributionResult(
        ranked_candidates=ranked,
        origin_metadata=origin_meta,
        report=report,
    )
    assert result.candidate_mmsis == [ranked[0].mmsi, ranked[1].mmsi]
    df_out = result.to_dataframe()
    assert len(df_out) == 2
    assert set(df_out["mmsi"]) == {205123456, 211987654}


# ===========================================================================
# 3. Empty AIS-07 Input Handling
# ===========================================================================
def test_empty_ais07_input_handling():
    """Requirement 7: Verify empty AIS-07 input is handled correctly."""
    empty_df = pd.DataFrame(
        columns=[
            "mmsi",
            "timestamp",
            "latitude",
            "longitude",
            "distance_km",
            "is_interpolated",
            "trajectory_segment_id",
        ]
    )
    empty_report = TemporalFilterReport(
        total_input_records=0,
        matched_records=0,
        unique_vessels_in=0,
        unique_vessels_matched=0,
        origin_timestamp="2025-01-08T00:15:00Z",
        window_minutes=30.0,
        before_minutes=30.0,
        after_minutes=30.0,
        start_timestamp="2025-01-07T23:45:00Z",
        end_timestamp="2025-01-08T00:45:00Z",
        earliest_retained_timestamp=None,
        latest_retained_timestamp=None,
        segments_matched=0,
    )
    empty_t_result = TemporalFilterResult(data=empty_df, report=empty_report)

    # 1. Validation returns empty DataFrame without error
    validated = validate_ais_observations(empty_t_result)
    assert isinstance(validated, pd.DataFrame)
    assert len(validated) == 0

    # 2. extract_candidate_vessels returns empty list
    candidates = extract_candidate_vessels(empty_t_result)
    assert candidates == []

    # 3. AttributionResult initializes cleanly
    origin = OriginMetadata(
        timestamp=pd.Timestamp("2025-01-08T00:15:00Z"),
        latitude=28.0,
        longitude=-90.0,
    )
    report = AttributionReport(
        total_input_observations=0,
        total_candidate_vessels=0,
        evaluation_timestamp="2026-09-08T15:00:00Z",
    )
    result = AttributionResult(
        ranked_candidates=[],
        origin_metadata=origin,
        report=report,
    )
    assert result.candidate_mmsis == []
    assert result.top_candidate is None
    assert result.to_dataframe().empty
    assert result.to_dict()["ranked_candidates"] == []


# ===========================================================================
# 4. Invalid AIS Input Rejection
# ===========================================================================
def test_invalid_ais_input_rejection():
    """Requirement 8: Verify invalid AIS input is rejected."""
    # Missing required distance_km
    df_missing_dist = pd.DataFrame({
        "mmsi": [205123456],
        "timestamp": [pd.Timestamp("2025-01-08T00:00:00Z")],
        "latitude": [28.0],
        "longitude": [-90.0],
    })
    with pytest.raises(ValueError, match="missing required columns"):
        validate_ais_observations(df_missing_dist)

    # Negative distance_km
    df_neg_dist = pd.DataFrame({
        "mmsi": [205123456],
        "timestamp": [pd.Timestamp("2025-01-08T00:00:00Z")],
        "latitude": [28.0],
        "longitude": [-90.0],
        "distance_km": [-1.5],
    })
    with pytest.raises(ValueError, match="negative distance_km"):
        validate_ais_observations(df_neg_dist)

    # Non-UTC timezone-naive timestamp
    df_naive_ts = pd.DataFrame({
        "mmsi": [205123456],
        "timestamp": ["2025-01-08 00:00:00"],  # naive
        "latitude": [28.0],
        "longitude": [-90.0],
        "distance_km": [1.5],
    })
    with pytest.raises(ValueError, match="timezone-aware"):
        validate_ais_observations(df_naive_ts)
