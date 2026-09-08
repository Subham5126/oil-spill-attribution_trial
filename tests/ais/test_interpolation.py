"""Tests for AIS Vessel Position Interpolation (AIS-05).

Covers:
1. Basic midpoint linear interpolation
2. Multiple interpolation points in one interval (resample_trajectory)
3. Single-ping segment handling (no interpolation, no crash)
4. Exact timestamp match (returns real observation, is_interpolated=False)
5. Target timestamp before segment start (strictly no extrapolation)
6. Target timestamp after segment end (strictly no extrapolation)
7. Target timestamp inside AIS-04 cross-segment blackout (no position generated)
8. Interval exceeding max_gap_seconds inside segment (un-interpolated)
9. Configurable max_gap_seconds threshold
10. Anti-meridian crossing (+/-180 deg longitude wrap)
11. Multiple MMSIs with zero cross-vessel contamination
12. Multiple trajectory segments for a single MMSI
13. UTC timezone safety and normalization
14. Caller input immutability
15. Actual observations preserved unchanged
16. Provenance flags audit (is_interpolated, interpolation_method)
17. No duplicate rows at exact real timestamps
18. Empty input handling
19. Invalid configuration validation
20. Real NOAA dataset integration smoke test (AIS-02 -> AIS-03 -> AIS-04 -> AIS-05)
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from ais.data_loader import load_ais_csv
from ais.interpolation import (
    InterpolatedSegment,
    InterpolationConfig,
    InterpolationReport,
    InterpolationResult,
    interpolate_at_timestamp,
    interpolate_coordinates,
    interpolate_trajectories,
    resample_trajectory,
)
from ais.preprocessing import clean_ais_data
from ais.trajectory import (
    TrajectoryConfig,
    TrajectorySegment,
    reconstruct_trajectories,
)


# ===========================================================================
# 1. Configuration Validation (Requirement 19)
# ===========================================================================

def test_interpolation_config_defaults():
    """Default configuration should specify 3600s max gap and 'linear' method."""
    cfg = InterpolationConfig()
    assert cfg.max_gap_seconds == 3600.0
    assert cfg.method == "linear"


def test_interpolation_config_validation():
    """Invalid configuration parameters must raise ValueError."""
    with pytest.raises(ValueError, match="max_gap_seconds must be positive"):
        InterpolationConfig(max_gap_seconds=0.0)

    with pytest.raises(ValueError, match="max_gap_seconds must be positive"):
        InterpolationConfig(max_gap_seconds=-60.0)

    with pytest.raises(ValueError, match="Unsupported interpolation method"):
        InterpolationConfig(method="cubic_spline")


# ===========================================================================
# 2. Anti-Meridian Crossing (Requirement 10)
# ===========================================================================

def test_anti_meridian_crossing_east_to_west():
    """Crossing 180 deg from +179.9 to -179.9 must follow the short 0.2 deg path."""
    lat1, lon1 = 10.0, 179.9
    lat2, lon2 = 12.0, -179.9

    # Midpoint alpha = 0.5
    lat_mid, lon_mid = interpolate_coordinates(lat1, lon1, lat2, lon2, 0.5)
    assert pytest.approx(lat_mid, abs=1e-5) == 11.0
    # Expected midpoint is +/-180 degrees, NOT 0.0 degrees!
    assert abs(abs(lon_mid) - 180.0) < 1e-4

    # Quarter point alpha = 0.25 (lon = 179.95)
    _, lon_q1 = interpolate_coordinates(lat1, lon1, lat2, lon2, 0.25)
    assert pytest.approx(lon_q1, abs=1e-4) == 179.95

    # Three-quarter point alpha = 0.75 (lon = -179.95)
    _, lon_q3 = interpolate_coordinates(lat1, lon1, lat2, lon2, 0.75)
    assert pytest.approx(lon_q3, abs=1e-4) == -179.95


def test_anti_meridian_crossing_west_to_east():
    """Crossing 180 deg from -179.9 to +179.9 must follow the short 0.2 deg path."""
    lat1, lon1 = 20.0, -179.9
    lat2, lon2 = 20.0, 179.9

    lat_mid, lon_mid = interpolate_coordinates(lat1, lon1, lat2, lon2, 0.5)
    assert pytest.approx(lat_mid, abs=1e-5) == 20.0
    assert abs(abs(lon_mid) - 180.0) < 1e-4


def test_standard_prime_meridian_crossing():
    """Crossing 0 deg from -1.0 to +1.0 must interpolate across 0.0 deg."""
    lat_mid, lon_mid = interpolate_coordinates(50.0, -1.0, 50.0, 1.0, 0.5)
    assert pytest.approx(lat_mid, abs=1e-5) == 50.0
    assert pytest.approx(lon_mid, abs=1e-5) == 0.0


# ===========================================================================
# 3. Basic Midpoint Interpolation (Requirement 1 & 16)
# ===========================================================================

def test_basic_midpoint_interpolation():
    """Interpolate exactly at midpoint of a 10-minute interval."""
    df = pd.DataFrame({
        "mmsi": [111111111, 111111111],
        "timestamp": pd.to_datetime(["2025-01-01 12:00:00", "2025-01-01 12:10:00"], utc=True),
        "latitude": [28.0, 28.2],
        "longitude": [-90.0, -90.4],
    })
    traj_res = reconstruct_trajectories(df)

    # Query midpoint: 12:05:00
    t_mid = pd.to_datetime("2025-01-01 12:05:00", utc=True)
    res_df = interpolate_at_timestamp(traj_res, t_mid)

    assert len(res_df) == 1
    row = res_df.iloc[0]
    assert row["mmsi"] == 111111111
    assert row["timestamp"] == t_mid
    assert pytest.approx(row["latitude"], abs=1e-5) == 28.1
    assert pytest.approx(row["longitude"], abs=1e-5) == -90.2
    assert bool(row["is_interpolated"]) is True
    assert row["interpolation_method"] == "linear"


# ===========================================================================
# 4. Multiple Points in One Interval (Requirement 2 & 17)
# ===========================================================================

def test_multiple_interpolation_points_resampling():
    """Resample a 300s interval with time_step=60s: generates 4 new points without duplicates."""
    df = pd.DataFrame({
        "mmsi": [222222222, 222222222],
        "timestamp": pd.to_datetime(["2025-01-01 12:00:00", "2025-01-01 12:05:00"], utc=True),
        "latitude": [25.0, 25.5],
        "longitude": [-80.0, -80.5],
    })
    traj_res = reconstruct_trajectories(df)

    res = resample_trajectory(traj_res, time_step_seconds=60.0)
    assert len(res.segments) == 1
    seg = res.segments[0]

    assert seg.num_actual_observations == 2
    assert seg.num_interpolated_points == 4
    assert seg.total_points == 6

    df_out = seg.data
    # Verify strict monotonic ordering
    assert df_out["timestamp"].is_monotonic_increasing

    # Check timestamps: 12:00 (actual), 12:01 (interp), 12:02 (interp), 12:03 (interp), 12:04 (interp), 12:05 (actual)
    assert df_out["is_interpolated"].tolist() == [False, True, True, True, True, False]
    assert df_out["interpolation_method"].tolist() == [None, "linear", "linear", "linear", "linear", None]

    # No duplicate timestamps
    assert df_out["timestamp"].nunique() == 6


# ===========================================================================
# 5. Single-Ping Segment Handling (Requirement 3)
# ===========================================================================

def test_single_ping_segment():
    """Single observation cannot be interpolated and must not crash."""
    df = pd.DataFrame({
        "mmsi": [333333333],
        "timestamp": pd.to_datetime(["2025-01-01 12:00:00"], utc=True),
        "latitude": [30.0],
        "longitude": [-85.0],
    })
    traj_res = reconstruct_trajectories(df)

    # 1. Resample
    res = resample_trajectory(traj_res, time_step_seconds=60.0)
    seg = res.segments[0]
    assert seg.num_actual_observations == 1
    assert seg.num_interpolated_points == 0
    assert seg.total_points == 1
    assert res.report.single_ping_segments_skipped == 1

    # 2. Query at different timestamp returns empty
    t_other = pd.to_datetime("2025-01-01 12:05:00", utc=True)
    res_at_t = interpolate_at_timestamp(traj_res, t_other)
    assert res_at_t.empty


# ===========================================================================
# 6. Exact Timestamp Match (Requirement 4)
# ===========================================================================

def test_exact_timestamp_match():
    """Querying at exact real observation timestamp returns actual observation with is_interpolated=False."""
    t_exact = pd.to_datetime("2025-01-01 12:00:00", utc=True)
    df = pd.DataFrame({
        "mmsi": [444444444, 444444444],
        "timestamp": [t_exact, pd.to_datetime("2025-01-01 12:10:00", utc=True)],
        "latitude": [20.0, 20.2],
        "longitude": [-70.0, -70.2],
        "sog": [10.5, 11.0],
    })
    traj_res = reconstruct_trajectories(df)

    res_df = interpolate_at_timestamp(traj_res, t_exact)
    assert len(res_df) == 1
    row = res_df.iloc[0]
    assert row["timestamp"] == t_exact
    assert row["latitude"] == 20.0
    assert row["longitude"] == -70.0
    assert row["sog"] == 10.5  # Real observation retains SOG
    assert bool(row["is_interpolated"]) is False
    assert row["interpolation_method"] is None


# ===========================================================================
# 7. Strictly No Extrapolation: Before Start & After End (Requirements 5 & 6)
# ===========================================================================

def test_no_extrapolation_before_start():
    """Query before start of track must return empty (strictly no extrapolation)."""
    df = pd.DataFrame({
        "mmsi": [555555555, 555555555],
        "timestamp": pd.to_datetime(["2025-01-01 12:00:00", "2025-01-01 12:10:00"], utc=True),
        "latitude": [10.0, 10.1],
        "longitude": [-60.0, -60.1],
    })
    traj_res = reconstruct_trajectories(df)

    t_before = pd.to_datetime("2025-01-01 11:59:00", utc=True)
    res_df = interpolate_at_timestamp(traj_res, t_before)
    assert res_df.empty


def test_no_extrapolation_after_end():
    """Query after end of track must return empty (strictly no extrapolation)."""
    df = pd.DataFrame({
        "mmsi": [555555555, 555555555],
        "timestamp": pd.to_datetime(["2025-01-01 12:00:00", "2025-01-01 12:10:00"], utc=True),
        "latitude": [10.0, 10.1],
        "longitude": [-60.0, -60.1],
    })
    traj_res = reconstruct_trajectories(df)

    t_after = pd.to_datetime("2025-01-01 12:11:00", utc=True)
    res_df = interpolate_at_timestamp(traj_res, t_after)
    assert res_df.empty


# ===========================================================================
# 8. Cross-Segment Blackout Gap Handling (Requirement 7)
# ===========================================================================

def test_no_interpolation_across_segment_blackout():
    """Timestamp falling inside an AIS-04 transmission blackout between segments must not be interpolated."""
    # max_gap_seconds=7200 in AIS-04
    # Seg 0: 00:00:00 -> 00:30:00
    # Blackout: 00:30:00 -> 04:00:00 (3.5 hours > 2 hours)
    # Seg 1: 04:00:00 -> 04:30:00
    df = pd.DataFrame({
        "mmsi": [666666666] * 4,
        "timestamp": pd.to_datetime([
            "2025-01-01 00:00:00",
            "2025-01-01 00:30:00",
            "2025-01-01 04:00:00",
            "2025-01-01 04:30:00",
        ], utc=True),
        "latitude": [15.0, 15.1, 16.0, 16.1],
        "longitude": [-75.0, -75.1, -76.0, -76.1],
    })
    traj_res = reconstruct_trajectories(df)
    vessel = traj_res.get_vessel(666666666)
    assert vessel.num_segments == 2

    # Query timestamp at 02:00:00 (inside blackout gap between seg_0 and seg_1)
    t_blackout = pd.to_datetime("2025-01-01 02:00:00", utc=True)
    res_df = interpolate_at_timestamp(traj_res, t_blackout)
    assert res_df.empty, "Interpolated across an unobserved cross-segment blackout gap!"


# ===========================================================================
# 9. Intra-Segment Gap Exceeding Threshold (Requirements 8 & 9)
# ===========================================================================

def test_interval_exceeding_max_gap_seconds():
    """Intervals exceeding max_gap_seconds (e.g. 5400s > 3600s) must remain un-interpolated."""
    # Ping 1: 00:00:00
    # Ping 2: 01:30:00 (dt = 5400s <= 7200s for AIS-04, but > 3600s for AIS-05)
    df = pd.DataFrame({
        "mmsi": [777777777, 777777777],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00", "2025-01-01 01:30:00"], utc=True),
        "latitude": [22.0, 22.5],
        "longitude": [-88.0, -88.5],
    })
    traj_res = reconstruct_trajectories(df)

    # 1. Default max_gap_seconds=3600s: query at 00:45:00 should return empty
    t_query = pd.to_datetime("2025-01-01 00:45:00", utc=True)
    res_df = interpolate_at_timestamp(traj_res, t_query)
    assert res_df.empty

    # 2. Configured max_gap_seconds=7200s: query at 00:45:00 succeeds
    cfg_lenient = InterpolationConfig(max_gap_seconds=7200.0)
    res_lenient = interpolate_at_timestamp(traj_res, t_query, config=cfg_lenient)
    assert len(res_lenient) == 1
    assert pytest.approx(res_lenient.iloc[0]["latitude"], abs=1e-4) == 22.25


# ===========================================================================
# 10. Multi-Vessel Isolation (Requirement 11)
# ===========================================================================

def test_multi_vessel_isolation():
    """Multiple vessels must be interpolated strictly independently with zero cross-MMSI leakage."""
    # Vessel A (888888888) at lat 10.0
    # Vessel B (999999999) at lat 40.0
    df = pd.DataFrame({
        "mmsi": [888888888, 999999999, 888888888, 999999999],
        "timestamp": pd.to_datetime([
            "2025-01-01 00:00:00",
            "2025-01-01 00:00:00",
            "2025-01-01 00:10:00",
            "2025-01-01 00:10:00",
        ], utc=True),
        "latitude": [10.0, 40.0, 10.2, 40.2],
        "longitude": [20.0, 50.0, 20.2, 50.2],
    })
    traj_res = reconstruct_trajectories(df)

    t_mid = pd.to_datetime("2025-01-01 00:05:00", utc=True)
    res_df = interpolate_at_timestamp(traj_res, t_mid)

    assert len(res_df) == 2
    row_a = res_df[res_df["mmsi"] == 888888888].iloc[0]
    row_b = res_df[res_df["mmsi"] == 999999999].iloc[0]

    assert pytest.approx(row_a["latitude"], abs=1e-5) == 10.1
    assert pytest.approx(row_b["latitude"], abs=1e-5) == 40.1


# ===========================================================================
# 11. Multi-Segment Vessel Interpolation (Requirement 12)
# ===========================================================================

def test_multiple_segments_for_single_vessel():
    """A vessel with multiple segments should interpolate within valid segments independently."""
    df = pd.DataFrame({
        "mmsi": [101010101] * 4,
        "timestamp": pd.to_datetime([
            "2025-01-01 00:00:00",
            "2025-01-01 00:10:00",
            # Blackout > 2h -> seg 1
            "2025-01-01 05:00:00",
            "2025-01-01 05:10:00",
        ], utc=True),
        "latitude": [10.0, 10.2, 20.0, 20.2],
        "longitude": [-10.0, -10.2, -20.0, -20.2],
    })
    traj_res = reconstruct_trajectories(df)

    # Query in seg 0
    res_seg0 = interpolate_at_timestamp(traj_res, "2025-01-01 00:05:00")
    assert len(res_seg0) == 1
    assert res_seg0.iloc[0]["trajectory_segment_id"] == "101010101_seg_0"
    assert pytest.approx(res_seg0.iloc[0]["latitude"], abs=1e-4) == 10.1

    # Query in seg 1
    res_seg1 = interpolate_at_timestamp(traj_res, "2025-01-01 05:05:00")
    assert len(res_seg1) == 1
    assert res_seg1.iloc[0]["trajectory_segment_id"] == "101010101_seg_1"
    assert pytest.approx(res_seg1.iloc[0]["latitude"], abs=1e-4) == 20.1


# ===========================================================================
# 12. Timezone Safety & Immutability (Requirements 13, 14, 15)
# ===========================================================================

def test_timezone_safety_and_input_immutability():
    """All output timestamps must be UTC-aware, and input structures must remain unmutated."""
    df = pd.DataFrame({
        "mmsi": [121212121, 121212121],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00", "2025-01-01 00:10:00"], utc=True),
        "latitude": [30.0, 30.2],
        "longitude": [-90.0, -90.2],
    })
    traj_res = reconstruct_trajectories(df)
    df_snapshot = traj_res.to_dataframe()

    res = resample_trajectory(traj_res, time_step_seconds=300.0)
    df_res = res.to_dataframe()

    # Timezone check
    assert str(df_res["timestamp"].dt.tz) == "UTC"

    # Input immutability check
    assert len(traj_res.to_dataframe()) == len(df_snapshot)
    assert "is_interpolated" not in traj_res.to_dataframe().columns

    # Actual observations preserved unchanged
    actual_rows = df_res[~df_res["is_interpolated"]]
    assert len(actual_rows) == 2
    assert (actual_rows["latitude"].values == df["latitude"].values).all()


# ===========================================================================
# 13. Empty Input Handling (Requirement 18)
# ===========================================================================

def test_empty_input_handling():
    """Empty input should return empty InterpolationResult and report."""
    empty_df = pd.DataFrame(columns=["mmsi", "timestamp", "latitude", "longitude"])
    empty_df["timestamp"] = pd.to_datetime(empty_df["timestamp"], utc=True)

    traj_res = reconstruct_trajectories(empty_df)
    res = resample_trajectory(traj_res)

    assert isinstance(res, InterpolationResult)
    assert len(res.segments) == 0
    assert len(res.trajectories) == 0
    assert res.report.total_input_segments == 0
    assert res.report.total_output_records == 0
    assert res.to_dataframe().empty

    res_at_t = interpolate_at_timestamp(traj_res, "2025-01-01 00:00:00")
    assert res_at_t.empty


# ===========================================================================
# 14. Real NOAA Dataset Integration Smoke Test (Requirement 20)
# ===========================================================================

def test_real_noaa_end_to_end_pipeline():
    """End-to-end smoke test: NOAA raw -> AIS-02 -> AIS-03 -> AIS-04 -> AIS-05."""
    archive_path = Path("data/raw/ais/noaa/ais-2025-01-08.tgz")
    if not archive_path.exists():
        pytest.skip(f"NOAA archive not found at {archive_path}")

    # 1. Load sample via AIS-02
    df_raw = load_ais_csv(archive_path, nrows=500)
    # 2. Clean via AIS-03
    df_clean, _ = clean_ais_data(df_raw)
    # 3. Reconstruct via AIS-04
    traj_res = reconstruct_trajectories(df_clean)
    assert len(traj_res.segments) > 0

    # 4. Interpolate via AIS-05
    interp_res = resample_trajectory(traj_res, time_step_seconds=300.0)
    assert isinstance(interp_res, InterpolationResult)
    assert len(interp_res.segments) == len(traj_res.segments)

    df_out = interp_res.to_dataframe()
    assert not df_out.empty
    assert "is_interpolated" in df_out.columns
    assert "interpolation_method" in df_out.columns
    assert len(df_out) >= len(df_clean)

    # Check query at first timestamp of first segment
    t_first = traj_res.segments[0].start_timestamp
    df_query = interpolate_at_timestamp(traj_res, t_first)
    assert not df_query.empty
    assert bool(df_query.iloc[0]["is_interpolated"]) is False


# ===========================================================================
# 15. Additional Feature Tests: Target Timestamps & Polymorphic DataFrame
# ===========================================================================

def test_interpolate_trajectories_explicit_target_timestamps():
    """interpolate_trajectories with explicit target_timestamps list."""
    df = pd.DataFrame({
        "mmsi": [131313131, 131313131],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00", "2025-01-01 00:20:00"], utc=True),
        "latitude": [10.0, 10.4],
        "longitude": [20.0, 20.4],
    })
    traj_res = reconstruct_trajectories(df)

    t1 = pd.to_datetime("2025-01-01 00:05:00", utc=True)
    t2 = pd.to_datetime("2025-01-01 00:15:00", utc=True)
    t_out = pd.to_datetime("2025-01-01 01:00:00", utc=True)  # Outside bounds

    res = interpolate_trajectories(traj_res, target_timestamps=[t1, t2, t_out])
    seg = res.segments[0]
    assert seg.num_actual_observations == 2
    assert seg.num_interpolated_points == 2
    assert seg.total_points == 4

    df_out = seg.data
    assert df_out["timestamp"].tolist() == [
        pd.to_datetime("2025-01-01 00:00:00", utc=True),
        t1,
        t2,
        pd.to_datetime("2025-01-01 00:20:00", utc=True),
    ]


def test_polymorphic_dataframe_input():
    """AIS-05 should seamlessly accept a DataFrame previously returned by TrajectoryResult."""
    df = pd.DataFrame({
        "mmsi": [141414141, 141414141],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00", "2025-01-01 00:10:00"], utc=True),
        "latitude": [15.0, 15.2],
        "longitude": [30.0, 30.2],
    })
    traj_res = reconstruct_trajectories(df)
    df_annotated = traj_res.to_dataframe()

    # Pass the DataFrame directly to resample_trajectory
    res = resample_trajectory(df_annotated, time_step_seconds=300.0)
    assert len(res.segments) == 1
    assert res.segments[0].num_interpolated_points == 1


def test_resample_invalid_time_step():
    """time_step_seconds <= 0 must raise ValueError."""
    df = pd.DataFrame({
        "mmsi": [151515151, 151515151],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00", "2025-01-01 00:10:00"], utc=True),
        "latitude": [10.0, 10.1],
        "longitude": [20.0, 20.1],
    })
    traj_res = reconstruct_trajectories(df)
    with pytest.raises(ValueError, match="time_step_seconds must be positive"):
        resample_trajectory(traj_res, time_step_seconds=0.0)
