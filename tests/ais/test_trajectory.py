"""Tests for AIS Vessel Trajectory Reconstruction (AIS-04).

Covers:
- Configuration validation and constraints
- Chronological ordering within MMSI
- Zero cross-MMSI contamination
- Gap detection and segmentation at threshold (max_gap_seconds)
- Continuous trajectory handling without gaps
- Single-observation vessel handling
- Empty DataFrame handling
- Schema and timestamp validation (missing columns, naive datetime, invalid dtypes)
- Timezone normalization (UTC preservation and conversion)
- Preservation of original AIS-03 attributes and kinematic flags
- Verification of no interpolated/fabricated positions
- Helper accessors on VesselTrajectory and TrajectoryResult
- Custom min_observations_per_segment filtering
- Full end-to-end integration test with real NOAA AIS data (AIS-02 -> AIS-03 -> AIS-04)
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from ais.data_loader import load_ais_csv
from ais.preprocessing import clean_ais_data
from ais.trajectory import (
    TrajectoryConfig,
    TrajectoryReport,
    TrajectoryResult,
    TrajectorySegment,
    VesselTrajectory,
    reconstruct_trajectories,
)


# ===========================================================================
# 1. Configuration Tests
# ===========================================================================

def test_trajectory_config_defaults():
    """Default configuration should reflect standard domain constants (2-hour gap)."""
    cfg = TrajectoryConfig()
    assert cfg.max_gap_seconds == 7200.0
    assert cfg.min_observations_per_segment == 1


def test_trajectory_config_validation():
    """Invalid configuration parameters must raise ValueError."""
    with pytest.raises(ValueError, match="max_gap_seconds must be positive"):
        TrajectoryConfig(max_gap_seconds=0.0)

    with pytest.raises(ValueError, match="max_gap_seconds must be positive"):
        TrajectoryConfig(max_gap_seconds=-100.0)

    with pytest.raises(ValueError, match="min_observations_per_segment must be >= 1"):
        TrajectoryConfig(min_observations_per_segment=0)


# ===========================================================================
# 2. Input Validation Tests
# ===========================================================================

def test_reconstruct_missing_required_columns():
    """Missing required columns must raise ValueError."""
    df_missing = pd.DataFrame({
        "mmsi": [111222333],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00"], utc=True),
        "latitude": [25.0],
        # 'longitude' missing
    })
    with pytest.raises(ValueError, match="missing required column"):
        reconstruct_trajectories(df_missing)


def test_reconstruct_non_datetime_timestamp():
    """Non-datetime timestamp column must raise ValueError."""
    df_str_time = pd.DataFrame({
        "mmsi": [111222333],
        "timestamp": ["2025-01-01 00:00:00"],
        "latitude": [25.0],
        "longitude": [-80.0],
    })
    with pytest.raises(ValueError, match="timestamp column must be a datetime dtype"):
        reconstruct_trajectories(df_str_time)


def test_reconstruct_tz_naive_timestamp():
    """Timezone-naive timestamp must raise ValueError requiring UTC."""
    df_naive = pd.DataFrame({
        "mmsi": [111222333],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00"]),  # tz-naive
        "latitude": [25.0],
        "longitude": [-80.0],
    })
    with pytest.raises(ValueError, match="timestamp column must be timezone-aware"):
        reconstruct_trajectories(df_naive)


def test_reconstruct_non_utc_timezone_converted_to_utc():
    """Non-UTC timezone-aware timestamps should be converted to UTC automatically."""
    df_est = pd.DataFrame({
        "mmsi": [111222333],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00"]).tz_localize("US/Eastern"),
        "latitude": [25.0],
        "longitude": [-80.0],
    })
    res = reconstruct_trajectories(df_est)
    vessel = res.get_vessel(111222333)
    # 00:00 US/Eastern is 05:00 UTC
    assert str(vessel.start_timestamp.tz) == "UTC"
    assert vessel.start_timestamp.hour == 5


# ===========================================================================
# 3. Edge Cases: Empty DataFrame & Single Observations
# ===========================================================================

def test_reconstruct_empty_dataframe():
    """Empty DataFrame input should return empty TrajectoryResult with valid report."""
    empty_df = pd.DataFrame(columns=["mmsi", "timestamp", "latitude", "longitude"])
    empty_df["timestamp"] = pd.to_datetime(empty_df["timestamp"], utc=True)

    result = reconstruct_trajectories(empty_df)
    assert isinstance(result, TrajectoryResult)
    assert len(result.trajectories) == 0
    assert len(result.segments) == 0
    assert result.report.total_input_records == 0
    assert result.report.total_vessels == 0
    assert result.report.total_trajectory_segments == 0
    assert result.report.total_records_assigned == 0
    assert result.report.number_of_gaps_detected == 0

    df_out = result.to_dataframe()
    assert df_out.empty
    assert "trajectory_segment_id" in df_out.columns
    assert "segment_index" in df_out.columns
    assert "time_gap_seconds" in df_out.columns


def test_reconstruct_single_observation_vessel():
    """Single-ping observation should form 1 segment with duration 0.0s and NaN time_gap."""
    df = pd.DataFrame({
        "mmsi": [123456789],
        "timestamp": pd.to_datetime(["2025-01-01 12:00:00"], utc=True),
        "latitude": [28.5],
        "longitude": [-90.0],
    })
    result = reconstruct_trajectories(df)
    assert len(result.trajectories) == 1
    assert len(result.segments) == 1

    vessel = result.get_vessel(123456789)
    assert vessel.total_observations == 1
    assert vessel.num_segments == 1
    assert vessel.start_timestamp == vessel.end_timestamp

    segment = vessel.get_segment(0)
    assert segment.segment_id == "123456789_seg_0"
    assert segment.segment_index == 0
    assert segment.num_observations == 1
    assert segment.duration_seconds == 0.0
    assert np.isnan(segment.data["time_gap_seconds"].iloc[0])

    assert result.report.total_input_records == 1
    assert result.report.total_vessels == 1
    assert result.report.total_trajectory_segments == 1
    assert result.report.min_observations_per_segment == 1
    assert result.report.max_observations_per_segment == 1
    assert result.report.avg_observations_per_segment == 1.0


# ===========================================================================
# 4. Chronological Sorting & Immutability
# ===========================================================================

def test_chronological_ordering_within_mmsi():
    """Observations provided out of order must be sorted chronologically."""
    df = pd.DataFrame({
        "mmsi": [111111111, 111111111, 111111111],
        "timestamp": pd.to_datetime([
            "2025-01-01 02:00:00",
            "2025-01-01 00:00:00",
            "2025-01-01 01:00:00",
        ], utc=True),
        "latitude": [28.2, 28.0, 28.1],
        "longitude": [-90.2, -90.0, -90.1],
    })
    # Original input ordering check
    assert df["timestamp"].iloc[0] > df["timestamp"].iloc[1]

    result = reconstruct_trajectories(df)
    vessel = result.get_vessel(111111111)
    seg = vessel.get_segment(0)

    # Observations in segment must be in strict chronological order
    timestamps = seg.data["timestamp"].tolist()
    assert timestamps == sorted(timestamps)
    assert seg.start_timestamp == pd.to_datetime("2025-01-01 00:00:00", utc=True)
    assert seg.end_timestamp == pd.to_datetime("2025-01-01 02:00:00", utc=True)
    assert seg.duration_seconds == 7200.0

    # Input DataFrame must not be mutated
    assert df["timestamp"].iloc[0] == pd.to_datetime("2025-01-01 02:00:00", utc=True)


# ===========================================================================
# 5. Temporal Gap Segmentation
# ===========================================================================

def test_gap_segmentation_exceeding_threshold():
    """A time gap exceeding max_gap_seconds must split trajectory into separate segments."""
    # max_gap_seconds = 3600 (1 hour)
    # Ping 1: 00:00:00
    # Ping 2: 00:30:00 (dt = 1800s <= 3600s -> same segment)
    # Ping 3: 03:00:00 (dt = 9000s > 3600s -> new segment)
    # Ping 4: 03:15:00 (dt = 900s <= 3600s -> same segment)
    df = pd.DataFrame({
        "mmsi": [222222222] * 4,
        "timestamp": pd.to_datetime([
            "2025-01-01 00:00:00",
            "2025-01-01 00:30:00",
            "2025-01-01 03:00:00",
            "2025-01-01 03:15:00",
        ], utc=True),
        "latitude": [20.0, 20.1, 20.5, 20.6],
        "longitude": [-85.0, -85.1, -85.5, -85.6],
    })

    cfg = TrajectoryConfig(max_gap_seconds=3600.0)
    result = reconstruct_trajectories(df, config=cfg)

    vessel = result.get_vessel(222222222)
    assert vessel.num_segments == 2
    assert vessel.total_observations == 4

    seg0 = vessel.get_segment(0)
    assert seg0.segment_id == "222222222_seg_0"
    assert seg0.num_observations == 2
    assert seg0.start_timestamp == pd.to_datetime("2025-01-01 00:00:00", utc=True)
    assert seg0.end_timestamp == pd.to_datetime("2025-01-01 00:30:00", utc=True)
    assert seg0.duration_seconds == 1800.0
    assert np.isnan(seg0.data["time_gap_seconds"].iloc[0])
    assert seg0.data["time_gap_seconds"].iloc[1] == 1800.0

    seg1 = vessel.get_segment(1)
    assert seg1.segment_id == "222222222_seg_1"
    assert seg1.num_observations == 2
    assert seg1.start_timestamp == pd.to_datetime("2025-01-01 03:00:00", utc=True)
    assert seg1.end_timestamp == pd.to_datetime("2025-01-01 03:15:00", utc=True)
    assert seg1.duration_seconds == 900.0
    # First point of new segment must have NaN time_gap_seconds
    assert np.isnan(seg1.data["time_gap_seconds"].iloc[0])
    assert seg1.data["time_gap_seconds"].iloc[1] == 900.0

    # Report verification
    assert result.report.total_input_records == 4
    assert result.report.total_vessels == 1
    assert result.report.total_trajectory_segments == 2
    assert result.report.number_of_gaps_detected == 1
    assert result.report.segments_created_from_gaps == 1
    assert result.report.min_observations_per_segment == 2
    assert result.report.max_observations_per_segment == 2
    assert result.report.avg_observations_per_segment == 2.0


def test_continuous_trajectory_without_gaps():
    """Continuous track within max_gap_seconds should remain in a single segment."""
    df = pd.DataFrame({
        "mmsi": [333333333] * 3,
        "timestamp": pd.to_datetime([
            "2025-01-01 00:00:00",
            "2025-01-01 01:00:00",
            "2025-01-01 02:00:00",
        ], utc=True),
        "latitude": [10.0, 10.1, 10.2],
        "longitude": [-60.0, -60.1, -60.2],
    })

    result = reconstruct_trajectories(df, config=TrajectoryConfig(max_gap_seconds=7200.0))
    vessel = result.get_vessel(333333333)

    assert vessel.num_segments == 1
    assert vessel.total_observations == 3
    assert result.report.number_of_gaps_detected == 0
    assert result.report.segments_created_from_gaps == 0


# ===========================================================================
# 6. Multi-Vessel Isolation (No Cross-MMSI Contamination)
# ===========================================================================

def test_multi_vessel_isolation():
    """Interleaved observations of multiple vessels must remain completely segregated."""
    # Interleave Vessel A (444444444) and Vessel B (555555555)
    df = pd.DataFrame({
        "mmsi": [444444444, 555555555, 444444444, 555555555],
        "timestamp": pd.to_datetime([
            "2025-01-01 00:00:00",
            "2025-01-01 00:05:00",
            "2025-01-01 00:10:00",
            "2025-01-01 00:15:00",
        ], utc=True),
        "latitude": [1.0, 20.0, 1.1, 20.1],
        "longitude": [1.0, 20.0, 1.1, 20.1],
    })

    result = reconstruct_trajectories(df)
    assert len(result.trajectories) == 2

    v_a = result.get_vessel(444444444)
    v_b = result.get_vessel(555555555)

    assert v_a.total_observations == 2
    assert v_b.total_observations == 2

    seg_a = v_a.get_segment(0)
    seg_b = v_b.get_segment(0)

    assert seg_a.segment_id == "444444444_seg_0"
    assert seg_b.segment_id == "555555555_seg_0"

    # Vessel A delta: 00:10 - 00:00 = 600s
    assert seg_a.duration_seconds == 600.0
    assert seg_a.data["time_gap_seconds"].iloc[1] == 600.0

    # Vessel B delta: 00:15 - 00:05 = 600s
    assert seg_b.duration_seconds == 600.0
    assert seg_b.data["time_gap_seconds"].iloc[1] == 600.0


# ===========================================================================
# 7. Quality Flag and Original Attribute Preservation
# ===========================================================================

def test_preservation_of_ais03_columns():
    """All AIS-03 kinematic fields, anomaly flags, and original columns must be preserved."""
    df = pd.DataFrame({
        "mmsi": [666666666, 666666666],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00", "2025-01-01 00:10:00"], utc=True),
        "latitude": [30.0, 30.1],
        "longitude": [-88.0, -88.1],
        "sog": [12.5, 12.8],
        "cog": [180.0, 182.0],
        "heading": [181.0, 181.0],
        "vessel_type": [70, 70],
        "derived_speed_knots": [np.nan, 14.2],
        "is_speed_anomaly": [False, False],
        "is_position_jump": [False, False],
        "is_sog_inconsistent": [False, False],
        "is_suspicious_zero_jump": [False, False],
    })

    result = reconstruct_trajectories(df)
    df_out = result.to_dataframe()

    # Verify original and AIS-03 fields are present and intact
    for col in [
        "mmsi", "timestamp", "latitude", "longitude", "sog", "cog",
        "heading", "vessel_type", "derived_speed_knots", "is_speed_anomaly",
        "is_position_jump", "is_sog_inconsistent", "is_suspicious_zero_jump",
        "trajectory_segment_id", "segment_index", "time_gap_seconds"
    ]:
        assert col in df_out.columns

    assert df_out["derived_speed_knots"].iloc[1] == 14.2
    assert df_out["sog"].iloc[0] == 12.5
    assert not df_out["is_speed_anomaly"].any()


# ===========================================================================
# 8. No Position Interpolation
# ===========================================================================

def test_no_position_interpolation():
    """AIS-04 must NOT synthesize, interpolate, or invent any trajectory points."""
    df = pd.DataFrame({
        "mmsi": [777777777] * 5,
        "timestamp": pd.to_datetime([
            "2025-01-01 00:00:00",
            "2025-01-01 01:00:00",
            "2025-01-01 05:00:00",  # gap
            "2025-01-01 05:10:00",
            "2025-01-01 05:20:00",
        ], utc=True),
        "latitude": [10.0, 10.1, 10.5, 10.6, 10.7],
        "longitude": [20.0, 20.1, 20.5, 20.6, 20.7],
    })

    result = reconstruct_trajectories(df, config=TrajectoryConfig(max_gap_seconds=3600.0))
    df_out = result.to_dataframe()

    # Exact row count match
    assert len(df_out) == len(df) == 5

    # Exact coordinate match
    assert (df_out["latitude"].values == df["latitude"].values).all()
    assert (df_out["longitude"].values == df["longitude"].values).all()


# ===========================================================================
# 9. Accessor Methods & Error Handling
# ===========================================================================

def test_accessor_methods_and_errors():
    """Verify get_vessel and get_segment accessor behavior and KeyError handling."""
    df = pd.DataFrame({
        "mmsi": [888888888, 888888888],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00", "2025-01-01 00:05:00"], utc=True),
        "latitude": [15.0, 15.1],
        "longitude": [45.0, 45.1],
    })
    result = reconstruct_trajectories(df)

    # Valid access
    vessel = result.get_vessel(888888888)
    assert isinstance(vessel, VesselTrajectory)
    seg = vessel.get_segment(0)
    assert isinstance(seg, TrajectorySegment)

    # Invalid vessel MMSI
    with pytest.raises(KeyError, match="MMSI 999999999 not found"):
        result.get_vessel(999999999)

    # Invalid segment index
    with pytest.raises(KeyError, match="Segment index 5 not found"):
        vessel.get_segment(5)

    # Vessel to_dataframe
    v_df = vessel.to_dataframe()
    assert len(v_df) == 2


# ===========================================================================
# 10. Custom min_observations_per_segment Filtering
# ===========================================================================

def test_min_observations_per_segment_filtering():
    """Config min_observations_per_segment > 1 should filter out single-ping segments."""
    # Vessel 1: 2 observations in seg_0, 1 observation in seg_1 (gap)
    # Vessel 2: 1 observation (isolated ping)
    df = pd.DataFrame({
        "mmsi": [101, 101, 101, 202],
        "timestamp": pd.to_datetime([
            "2025-01-01 00:00:00",
            "2025-01-01 00:10:00",
            "2025-01-01 05:00:00",  # gap (> 3600s) -> seg_1 has 1 observation
            "2025-01-01 00:00:00",  # vessel 202 has 1 observation
        ], utc=True),
        "latitude": [10.0, 10.1, 10.5, 20.0],
        "longitude": [10.0, 10.1, 10.5, 20.0],
    })

    cfg = TrajectoryConfig(max_gap_seconds=3600.0, min_observations_per_segment=2)
    result = reconstruct_trajectories(df, config=cfg)

    # Only Vessel 1's seg_0 has >= 2 observations
    assert len(result.segments) == 1
    assert result.segments[0].mmsi == 101
    assert result.segments[0].segment_index == 0
    assert result.segments[0].num_observations == 2

    # Vessel 202 has no retained segments and should not be in trajectories
    assert 202 not in result.trajectories
    assert len(result.trajectories) == 1

    assert result.report.total_input_records == 4
    assert result.report.total_records_assigned == 2
    assert result.report.total_vessels == 1
    assert result.report.total_trajectory_segments == 1


# ===========================================================================
# 11. Real NOAA Dataset Integration Smoke Test (AIS-02 -> AIS-03 -> AIS-04)
# ===========================================================================

def test_real_noaa_end_to_end_pipeline():
    """End-to-end integration test from raw NOAA archive to reconstructed trajectories."""
    archive_path = Path("data/raw/ais/noaa/ais-2025-01-08.tgz")
    if not archive_path.exists():
        pytest.skip(f"NOAA archive not found at {archive_path}")

    # 1. AIS-02: Load sample
    df_raw = load_ais_csv(archive_path, nrows=500)
    assert not df_raw.empty
    assert "mmsi" in df_raw.columns

    # 2. AIS-03: Clean & validate
    df_clean, clean_report = clean_ais_data(df_raw)
    assert not df_clean.empty
    assert clean_report.clean_records_retained > 0

    # 3. AIS-04: Reconstruct trajectories
    traj_result = reconstruct_trajectories(df_clean)
    assert isinstance(traj_result, TrajectoryResult)
    assert len(traj_result.trajectories) > 0
    assert len(traj_result.segments) > 0

    # Report verification
    rep = traj_result.report
    assert rep.total_input_records == len(df_clean)
    assert rep.total_records_assigned == len(df_clean)
    assert rep.total_vessels == len(traj_result.trajectories)
    assert rep.total_trajectory_segments == len(traj_result.segments)
    assert rep.avg_observations_per_segment > 0.0

    # Consolidated DataFrame check
    df_traj = traj_result.to_dataframe()
    assert len(df_traj) == len(df_clean)
    assert "trajectory_segment_id" in df_traj.columns
    assert "segment_index" in df_traj.columns
    assert "time_gap_seconds" in df_traj.columns

    # Every vessel trajectory must have valid chronological segments
    for mmsi, vessel in traj_result.trajectories.items():
        assert vessel.total_observations > 0
        assert vessel.num_segments > 0
        for seg in vessel.segments:
            assert seg.mmsi == mmsi
            assert seg.num_observations > 0
            assert seg.start_timestamp <= seg.end_timestamp
            if seg.num_observations > 1:
                assert seg.duration_seconds >= 0.0
