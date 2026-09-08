"""End-to-End AIS Integration Pipeline Tests.

Validates the full vertical integration flow:
Fake Member-4 Output
    ↓ (AIS-08: Drift-to-AIS Integration Adapter)
AISSearchRequest & AISIntegrationResult
    ↓ (AIS-09: AIS Provider Layer / LocalAISProvider)
Raw Filtered Observations (Canonical Schema + distance_km)
    ↓ (AIS-04: Trajectory Reconstruction)
Reconstructed Gap-Segmented Trajectories
    ↓ (AIS-05: Great-Circle Kinematic Interpolation)
Continuous Resampled Vessel Trajectories (with Provenance Flags)
    ↓ (AIS-06: Spatial Trajectory Filtering)
SpatialFilterResult (Attributed Distance Metrics to Spill Envelope)
    ↓ (AIS-07: Temporal Trajectory Filtering)
TemporalFilterResult
    ↓
Final Attributed Trajectory Dataset (Ready for ATTR Scoring)
"""

from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
import pytest

from ais.data_loader import load_ais_csv
from ais.data_loader.schema import REQUIRED_COLUMNS
from ais.filtering import (
    SpatialFilterConfig,
    SpatialFilterResult,
    TemporalFilterConfig,
    TemporalFilterResult,
    filter_spatial,
    filter_temporal,
)
from ais.integration.adapter import adapt_drift_origin_result
from ais.integration.search_request import AISSearchRequest
from ais.interpolation import (
    InterpolationConfig,
    interpolate_trajectories,
)
from ais.providers import LocalAISProvider
from ais.trajectory import TrajectoryConfig, reconstruct_trajectories


# ---------------------------------------------------------------------------
# Synthetic Pipeline Fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def synthetic_ais_dataset(tmp_path: Path) -> Path:
    """Generate a multi-vessel synthetic NOAA-like CSV with controlled scenarios.

    Scenarios:
    - Vessel 1 (MMSI 205123456): In-window, in-radius, 4 pings (reconstructable & interpolatable)
    - Vessel 2 (MMSI 211987654): In-window, in-radius, 1 ping (single-ping boundary case)
    - Vessel 3 (MMSI 316000000): In-radius, but 3 hours earlier (must be filtered temporally)
    - Vessel 4 (MMSI 412000000): In-window, but 50 km away (must be filtered spatially)
    """
    csv_file = tmp_path / "synthetic_ais_pipeline.csv"
    data = """MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft
205123456,2025-01-08T00:00:00Z,28.0000,-90.0000,10.0,180.0,180.0,VESSEL_A,IMO1111111,WDC1111,70,0,150,25,8.0
205123456,2025-01-08T00:10:00Z,28.0100,-90.0000,10.0,180.0,180.0,VESSEL_A,IMO1111111,WDC1111,70,0,150,25,8.0
205123456,2025-01-08T00:20:00Z,28.0200,-90.0000,10.0,180.0,180.0,VESSEL_A,IMO1111111,WDC1111,70,0,150,25,8.0
205123456,2025-01-08T00:30:00Z,28.0300,-90.0000,10.0,180.0,180.0,VESSEL_A,IMO1111111,WDC1111,70,0,150,25,8.0
211987654,2025-01-08T00:15:00Z,28.0050,-90.0050,4.5,90.0,90.0,VESSEL_B,IMO2222222,WDC2222,52,0,30,8,3.5
316000000,2025-01-07T21:00:00Z,28.0000,-90.0000,12.0,0.0,0.0,VESSEL_C,IMO3333333,WDC3333,80,0,200,30,10.0
412000000,2025-01-08T00:15:00Z,28.5000,-90.0000,15.0,270.0,270.0,VESSEL_D,IMO4444444,WDC4444,70,0,120,20,7.0
"""
    csv_file.write_text(data, encoding="utf-8")
    return csv_file


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------
def test_full_e2e_pipeline_with_member4_adapter(synthetic_ais_dataset: Path):
    """Test full integration: Fake M4 -> AIS-08 -> AIS-09 -> AIS-04 -> AIS-05 -> AIS-06 -> AIS-07 -> Final."""
    # Stage 0: Fake Member 4 Origin Analysis Output
    member4_output: Dict[str, Any] = {
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

    # Stage 1: AIS-08 (Adapt drift origin result to AISSearchRequest & AISIntegrationResult)
    integration_result = adapt_drift_origin_result(
        member4_output,
        before_minutes=20.0,  # 2025-01-07 23:55:00Z
        after_minutes=20.0,   # 2025-01-08 00:35:00Z
        buffer_km=1.0,        # Effective radius = 6.0 km
    )
    req = integration_result.search_request
    assert req.latitude == 28.0000
    assert req.longitude == -90.0000
    assert req.radius_km == 5.0
    assert req.buffer_km == 1.0
    assert req.effective_radius_km == 6.0
    print(
        f"\n[Synthetic Stage 1: AIS-08] Produced request: center=({req.latitude}, {req.longitude}), "
        f"radius={req.radius_km}km, eff={req.effective_radius_km}km"
    )

    # Stage 2: AIS-09 (Fetch matching observations via LocalAISProvider)
    provider = LocalAISProvider(synthetic_ais_dataset)
    assert provider.health_check() is True

    df_matched = provider.fetch_ais_data(req)
    assert not df_matched.empty
    assert "distance_km" in df_matched.columns

    # Candidate verification
    matched_mmsis = set(df_matched["mmsi"].unique())
    # Vessel 1 (205123456) and Vessel 2 (211987654) qualify
    assert 205123456 in matched_mmsis
    assert 211987654 in matched_mmsis
    # Vessel 3 (out of time) and Vessel 4 (out of space) must be excluded
    assert 316000000 not in matched_mmsis
    assert 412000000 not in matched_mmsis

    # All observations strictly within effective radius and temporal window
    assert (df_matched["distance_km"] <= req.effective_radius_km).all()
    assert (df_matched["timestamp"] >= req.start_time).all()
    assert (df_matched["timestamp"] <= req.end_time).all()
    print(f"[Synthetic Stage 2: AIS-09] Fetched {len(df_matched)} observations across {len(matched_mmsis)} vessels")

    # Stage 3: AIS-04 (Trajectory Reconstruction)
    traj_result = reconstruct_trajectories(df_matched)
    assert traj_result.report.total_records_assigned == len(df_matched)
    assert len(traj_result.trajectories) == 2
    assert 205123456 in traj_result.trajectories
    assert 211987654 in traj_result.trajectories

    traj_vessel1 = traj_result.get_vessel(205123456)
    assert traj_vessel1.total_observations == 4
    assert traj_vessel1.num_segments == 1

    traj_vessel2 = traj_result.get_vessel(211987654)
    assert traj_vessel2.total_observations == 1
    print(f"[Synthetic Stage 3: AIS-04] Reconstructed {len(traj_result.segments)} segments across {len(traj_result.trajectories)} vessels")

    # Stage 4: AIS-05 (Kinematic Position Interpolation)
    interp_result = interpolate_trajectories(
        traj_result,
        time_step_seconds=300.0,
        config=InterpolationConfig(max_gap_seconds=1800.0),
    )
    df_interp = interp_result.to_dataframe()

    assert not df_interp.empty
    assert "is_interpolated" in df_interp.columns
    assert interp_result.report.total_input_segments == len(traj_result.segments)
    assert interp_result.report.total_actual_observations == len(df_matched)

    # Vessel 1 should have generated interpolated fixes
    vessel1_interp = df_interp[df_interp["mmsi"] == 205123456]
    assert (vessel1_interp["is_interpolated"] == True).sum() > 0
    assert (vessel1_interp["is_interpolated"] == False).sum() == 4

    # Vessel 2 (single ping) cannot be interpolated; only the actual ping is present
    vessel2_interp = df_interp[df_interp["mmsi"] == 211987654]
    assert len(vessel2_interp) == 1
    assert (vessel2_interp["is_interpolated"] == False).all()
    print(f"[Synthetic Stage 4: AIS-05] Interpolated into {len(df_interp)} points ({interp_result.report.total_actual_observations} actual, {interp_result.report.total_interpolated_points} interpolated)")

    # Stage 5: AIS-06 (Spatial Filtering on Interpolated Result)
    spatial_result = filter_spatial(
        data=interp_result,
        config=SpatialFilterConfig(buffer_km=1.0),
        origin_data=integration_result,
    )
    assert isinstance(spatial_result, SpatialFilterResult)
    assert spatial_result.report.total_input_records == len(df_interp)
    assert 205123456 in spatial_result.candidate_mmsis
    assert 211987654 in spatial_result.candidate_mmsis
    assert (spatial_result.data["distance_km"] <= req.effective_radius_km).all()
    print(f"[Synthetic Stage 5: AIS-06] Spatial filter retained {len(spatial_result.data)} fixes across {len(spatial_result.candidate_mmsis)} vessels")

    # Stage 6: AIS-07 (Temporal Filtering on Spatial Filter Result)
    temporal_result = filter_temporal(
        data=spatial_result,
        config=TemporalFilterConfig(before_minutes=20.0, after_minutes=20.0),
        origin_data=integration_result,
    )
    assert isinstance(temporal_result, TemporalFilterResult)
    assert temporal_result.report.total_input_records == len(spatial_result.data)
    assert 205123456 in temporal_result.candidate_mmsis
    assert 211987654 in temporal_result.candidate_mmsis
    assert (temporal_result.data["timestamp"] >= req.start_time).all()
    assert (temporal_result.data["timestamp"] <= req.end_time).all()
    print(f"[Synthetic Stage 6: AIS-07] Temporal filter retained {len(temporal_result.data)} fixes across {len(temporal_result.candidate_mmsis)} vessels")

    # Stage 7: Final Attributed Dataset
    final_df = temporal_result.to_dataframe()
    assert len(final_df) == len(temporal_result.data)
    assert not final_df.empty
    print(f"[Synthetic Stage 7: Final] Produced final dataset of shape {final_df.shape}")


def test_e2e_pipeline_without_source_timestamp(synthetic_ais_dataset: Path):
    """Test full pipeline when search request has no source_timestamp (authoritative bounds only)."""
    req = AISSearchRequest(
        latitude=28.0000,
        longitude=-90.0000,
        radius_km=5.0,
        buffer_km=1.0,
        start_time=pd.Timestamp("2025-01-08T00:05:00Z"),
        end_time=pd.Timestamp("2025-01-08T00:25:00Z"),
        source_timestamp=None,  # No source timestamp
    )

    provider = LocalAISProvider(synthetic_ais_dataset)
    df_matched = provider.fetch_ais_data(req)

    # Within 00:05 to 00:25:
    # Vessel 1 pings at 00:10 and 00:20 match (00:00 and 00:30 excluded)
    # Vessel 2 ping at 00:15 matches
    assert len(df_matched) == 3
    assert set(df_matched["mmsi"].unique()) == {205123456, 211987654}
    assert (df_matched["timestamp"] >= req.start_time).all()
    assert (df_matched["timestamp"] <= req.end_time).all()

    # Continue into reconstructor & interpolator
    traj_result = reconstruct_trajectories(df_matched)
    assert len(traj_result.trajectories) == 2

    interp_result = interpolate_trajectories(traj_result, time_step_seconds=300.0)
    df_interp = interp_result.to_dataframe()
    assert not df_interp.empty

    # Continue through spatial and temporal filters with explicit parameters
    spatial_result = filter_spatial(
        interp_result,
        center_latitude=req.latitude,
        center_longitude=req.longitude,
        config=SpatialFilterConfig(radius_km=req.radius_km, buffer_km=req.buffer_km),
    )
    assert isinstance(spatial_result, SpatialFilterResult)

    midpoint = req.start_time + (req.end_time - req.start_time) / 2
    half_win = (req.end_time - req.start_time).total_seconds() / 120.0
    temporal_result = filter_temporal(
        spatial_result,
        origin_timestamp=midpoint,
        window_minutes=half_win,
    )
    assert isinstance(temporal_result, TemporalFilterResult)
    final_df = temporal_result.to_dataframe()
    assert not final_df.empty
    assert (final_df["timestamp"] >= req.start_time).all()
    assert (final_df["timestamp"] <= req.end_time).all()


def test_e2e_pipeline_empty_query(synthetic_ais_dataset: Path):
    """Test graceful handling when query returns zero records through the entire pipeline."""
    req = AISSearchRequest(
        latitude=0.0,
        longitude=0.0,
        radius_km=1.0,
        start_time=pd.Timestamp("2025-01-08T00:00:00Z"),
        end_time=pd.Timestamp("2025-01-08T01:00:00Z"),
    )

    provider = LocalAISProvider(synthetic_ais_dataset)
    df_matched = provider.fetch_ais_data(req)

    assert df_matched.empty
    assert "distance_km" in df_matched.columns
    assert "timestamp" in df_matched.columns

    # Verify spatial and temporal filtering on empty DataFrame
    spatial_result = filter_spatial(
        df_matched,
        center_latitude=0.0,
        center_longitude=0.0,
        config=SpatialFilterConfig(radius_km=1.0),
    )
    assert spatial_result.data.empty
    assert isinstance(spatial_result, SpatialFilterResult)

    temporal_result = filter_temporal(
        spatial_result,
        origin_timestamp="2025-01-08T00:30:00Z",
        window_minutes=30.0,
    )
    assert temporal_result.data.empty
    assert isinstance(temporal_result, TemporalFilterResult)
    assert temporal_result.to_dataframe().empty


def test_e2e_pipeline_multi_file_support(tmp_path: Path):
    """Test pipeline execution across multiple partitioned AIS files with deduplication."""
    file1 = tmp_path / "part_1.csv"
    file2 = tmp_path / "part_2.csv"

    header = "MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft\n"
    common = "555555555,2025-01-08T00:10:00Z,28.0,-90.0,10.0,180.0,180.0,SHIP5,IMO5,CALL5,70,0,100,20,5\n"

    file1.write_text(
        header
        + "555555555,2025-01-08T00:00:00Z,28.0,-90.0,10.0,180.0,180.0,SHIP5,IMO5,CALL5,70,0,100,20,5\n"
        + common,
        encoding="utf-8",
    )
    file2.write_text(
        header
        + common
        + "555555555,2025-01-08T00:20:00Z,28.0,-90.0,10.0,180.0,180.0,SHIP5,IMO5,CALL5,70,0,100,20,5\n",
        encoding="utf-8",
    )

    provider = LocalAISProvider([file1, file2])
    req = AISSearchRequest(
        latitude=28.0,
        longitude=-90.0,
        radius_km=10.0,
        start_time=pd.Timestamp("2025-01-08T00:00:00Z"),
        end_time=pd.Timestamp("2025-01-08T01:00:00Z"),
    )

    df_matched = provider.fetch_ais_data(req)
    assert len(df_matched) == 3

    traj_result = reconstruct_trajectories(df_matched)
    assert len(traj_result.trajectories) == 1
    vessel = traj_result.get_vessel(555555555)
    assert vessel.total_observations == 3


def test_e2e_pipeline_real_noaa_dataset():
    """Real NOAA AIS dataset end-to-end pipeline test across all 7 stages.

    Chain:
    Fake Member-4 output
    → AIS-08: Drift-to-AIS Adapter (AISSearchRequest)
    → AIS-09: LocalAISProvider (Real NOAA raw CSV observations)
    → AIS-04: Trajectory Reconstruction (Continuous gap-segmented tracks)
    → AIS-05: Kinematic Position Interpolation (Shortest-path great-circle)
    → AIS-06: Spatial Trajectory Filtering (Spill envelope distance check)
    → AIS-07: Temporal Trajectory Filtering (Observation window qualification)
    → Final: Attributed Trajectory Dataset (Ready for ATTR scoring)
    """
    real_path = Path("data/ais/2025/AIS_178881322085076878_1697-1788813221032.csv")
    if not real_path.exists():
        pytest.skip(f"Real NOAA dataset not found at {real_path}")

    # Stage 0: Fake Member 4 origin analysis output
    origin_payload = {
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

    # Stage 1: AIS-08 (Drift-to-AIS Adapter)
    adapter_res = adapt_drift_origin_result(
        origin_payload,
        before_minutes=30.0,
        after_minutes=30.0,
        buffer_km=2.0,  # Effective radius = 10.0 km
    )
    req = adapter_res.search_request
    assert req.latitude == origin_payload["best_candidate"]["region"]["centroid_lat"]
    assert req.longitude == origin_payload["best_candidate"]["region"]["centroid_lon"]
    assert req.radius_km == origin_payload["best_candidate"]["region"]["radius_km"]
    assert req.effective_radius_km == 10.0
    print(
        f"\n[Stage 1: AIS-08] Converted Member-4 output -> AISSearchRequest: "
        f"center=({req.latitude:.5f}, {req.longitude:.5f}), r_eff={req.effective_radius_km}km, "
        f"window=[{req.start_time} to {req.end_time}]"
    )

    # Stage 2: AIS-09 (LocalAISProvider Data Fetching)
    provider = LocalAISProvider(real_path)
    assert provider.health_check() is True
    df_matched = provider.fetch_ais_data(req)
    assert not df_matched.empty
    assert len(df_matched) > 500  # Expect ~1,626 observations in SF Bay
    assert (df_matched["distance_km"] <= req.effective_radius_km).all()
    assert (df_matched["timestamp"] >= req.start_time).all()
    assert (df_matched["timestamp"] <= req.end_time).all()
    print(
        f"[Stage 2: AIS-09] LocalAISProvider fetched {len(df_matched):,} observations "
        f"across {df_matched['mmsi'].nunique():,} unique vessels"
    )

    # Stage 3: AIS-04 (Trajectory Reconstruction)
    traj_result = reconstruct_trajectories(df_matched)
    assert traj_result.report.total_records_assigned == len(df_matched)
    assert len(traj_result.trajectories) > 50
    assert len(traj_result.segments) > 50
    print(
        f"[Stage 3: AIS-04] ReconstructTrajectories assembled {len(traj_result.segments):,} "
        f"continuous segments across {len(traj_result.trajectories):,} vessels"
    )

    # Stage 4: AIS-05 (Great-Circle Kinematic Interpolation)
    interp_result = interpolate_trajectories(
        traj_result,
        time_step_seconds=120.0,
        config=InterpolationConfig(max_gap_seconds=1800.0),
    )
    df_interp = interp_result.to_dataframe()
    assert not df_interp.empty
    assert interp_result.report.total_input_segments == len(traj_result.segments)
    assert interp_result.report.total_actual_observations == len(df_matched)
    assert interp_result.report.total_interpolated_points > 0
    assert len(df_interp) > len(df_matched)
    print(
        f"[Stage 4: AIS-05] InterpolateTrajectories expanded to {len(df_interp):,} records "
        f"({interp_result.report.total_actual_observations:,} actual + "
        f"{interp_result.report.total_interpolated_points:,} interpolated)"
    )

    # Stage 5: AIS-06 (Spatial Filtering on Interpolated Tracks)
    spatial_cfg = SpatialFilterConfig(buffer_km=2.0)
    spatial_result = filter_spatial(
        data=interp_result,
        config=spatial_cfg,
        origin_data=adapter_res,
    )
    assert isinstance(spatial_result, SpatialFilterResult)
    assert spatial_result.report.total_input_records == len(df_interp)
    assert not spatial_result.data.empty
    assert len(spatial_result.data) <= len(df_interp)
    assert (spatial_result.data["distance_km"] <= req.effective_radius_km).all()
    print(
        f"[Stage 5: AIS-06] FilterSpatial retained {len(spatial_result.data):,} points "
        f"across {len(spatial_result.candidate_mmsis):,} candidate vessels "
        f"(max dist: {spatial_result.data['distance_km'].max():.3f} km)"
    )

    # Stage 6: AIS-07 (Temporal Filtering on Candidate Tracks)
    temporal_cfg = TemporalFilterConfig(before_minutes=30.0, after_minutes=30.0)
    temporal_result = filter_temporal(
        data=spatial_result,
        config=temporal_cfg,
        origin_data=adapter_res,
    )
    assert isinstance(temporal_result, TemporalFilterResult)
    assert temporal_result.report.total_input_records == len(spatial_result.data)
    assert not temporal_result.data.empty
    assert len(temporal_result.data) <= len(spatial_result.data)
    assert (temporal_result.data["timestamp"] >= req.start_time).all()
    assert (temporal_result.data["timestamp"] <= req.end_time).all()
    print(
        f"[Stage 6: AIS-07] FilterTemporal retained {len(temporal_result.data):,} points "
        f"across {len(temporal_result.candidate_mmsis):,} candidate vessels "
        f"(time window: {temporal_result.report.start_timestamp} to {temporal_result.report.end_timestamp})"
    )

    # Stage 7: Final Output Extraction and Integrity Checks
    final_df = temporal_result.to_dataframe()
    assert len(final_df) == len(temporal_result.data)
    assert not final_df.empty

    # Verify column presence
    expected_cols = [
        "mmsi",
        "timestamp",
        "latitude",
        "longitude",
        "distance_km",
        "trajectory_segment_id",
        "is_interpolated",
    ]
    for col in expected_cols:
        assert col in final_df.columns, f"Missing expected column: {col}"

    # Verify coordinate validity
    assert (final_df["latitude"] >= -90.0).all() and (final_df["latitude"] <= 90.0).all()
    assert (final_df["longitude"] >= -180.0).all() and (final_df["longitude"] <= 180.0).all()

    # Verify temporal validity
    assert (final_df["timestamp"] >= req.start_time).all()
    assert (final_df["timestamp"] <= req.end_time).all()

    # Ground-truth check: verify actual (non-interpolated) observations exist in original NOAA file
    df_raw = load_ais_csv(real_path)
    raw_indexed = set(zip(df_raw["mmsi"], df_raw["timestamp"].dt.round("ms")))
    actual_fixes = final_df[~final_df["is_interpolated"]]
    for mmsi, ts in zip(actual_fixes["mmsi"], actual_fixes["timestamp"]):
        assert (mmsi, ts.round("ms")) in raw_indexed, f"Fabricated actual fix found: {mmsi} at {ts}"

    print(
        f"[Stage 7: Final] Successfully produced final candidate trajectory dataset with "
        f"{len(final_df):,} fixes ({len(actual_fixes):,} actual, "
        f"{len(final_df) - len(actual_fixes):,} interpolated)"
    )
