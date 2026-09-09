"""Tests for AIS-07 Temporal Filtering.

Comprehensive test suite covering:
1. Observation exactly at origin timestamp.
2. Observation strictly inside time window.
3. Observation exactly at lower boundary (inclusive).
4. Observation exactly at upper boundary (inclusive).
5. Observation just outside lower boundary (excluded).
6. Observation just outside upper boundary (excluded).
7. Multiple timestamps within and across vessels.
8. Multiple vessels handled independently.
9. Empty DataFrame handling.
10. No matches inside time window.
11. Missing timestamp column raises ValueError.
12. Invalid / unparseable timestamp values raise ValueError.
13. NaT values in timestamp column raise ValueError.
14. Invalid origin timestamp raises ValueError.
15. Naive vs timezone-aware timestamp behavior (rejects naive).
16. Different timezone offsets normalized correctly to UTC.
17. Input DataFrame immutability.
18. Original columns preserved.
19. Correct candidate MMSIs retained.
20. Config validation (TemporalFilterConfig).
21. Zero-minute window boundary behavior.
22. Non-negative / finite window validation.
23. Deterministic output.
24. Compatibility with AIS-06 SpatialFilterResult.
25. Segment retention mode (retain_full_segments=True) & MMSI fallback.
26. Non-datetime dtype string timestamps parsed and normalized safely.
27. Asymmetric windows (before_minutes vs after_minutes precedence).
28. Member 4 origin data dictionary integration.
"""

from typing import Any, Dict
import numpy as np
import pandas as pd
import pytest

from ais.filtering.config import SpatialFilterConfig, TemporalFilterConfig
from ais.filtering.spatial import filter_spatial
from ais.filtering.temporal import (
    TemporalFilterReport,
    TemporalFilterResult,
    filter_by_origin_time,
    filter_by_time_window,
    filter_temporal,
    filter_trajectories_temporally,
)
from ais.trajectory.reconstructor import (
    TrajectoryConfig,
    reconstruct_trajectories,
)


@pytest.fixture
def member4_origin_data() -> Dict[str, Any]:
    """Synthetic fixture matching the Member 4 -> Member 5 handoff contract."""
    return {
        "spill_observation": {
            "timestamp": "2026-09-07T05:00:00Z",
            "latitude": 18.5000,
            "longitude": 72.5000,
        },
        "origin": {
            "timestamp": "2026-09-07T01:00:00Z",
            "latitude": 18.5006,
            "longitude": 72.5156,
            "relative_score": 2.9964,
        },
        "uncertainty": {
            "centroid_latitude": 18.5001,
            "centroid_longitude": 72.5156,
            "radius_km": 1.1039,
            "confidence_level": 0.95,
            "min_latitude": 18.4869,
            "max_latitude": 18.5078,
            "min_longitude": 72.5070,
            "max_longitude": 72.5259,
        },
        "candidate_origins": [],
    }


@pytest.fixture
def sample_temporal_df() -> pd.DataFrame:
    """Synthetic AIS DataFrame with timestamps around 2026-09-07T01:00:00Z."""
    return pd.DataFrame(
        {
            "mmsi": [111222333, 111222333, 444555666, 777888999],
            "timestamp": pd.to_datetime(
                [
                    "2026-09-07T01:00:00Z",
                    "2026-09-07T01:15:00Z",
                    "2026-09-07T01:25:00Z",
                    "2026-09-07T02:30:00Z",
                ],
                utc=True,
            ),
            "latitude": [18.5001, 18.5040, 18.5020, 19.2000],
            "longitude": [72.5156, 72.5156, 72.5160, 73.0000],
            "sog": [12.5, 12.8, 10.0, 15.2],
            "cog": [180.0, 182.0, 90.0, 45.0],
            "heading": [181.0, 183.0, 89.0, 44.0],
            "vessel_name": ["TANKER_ALPHA", "TANKER_ALPHA", "CARGO_BETA", "VESSEL_FAR"],
            "vessel_type": [80, 80, 70, 70],
            "trajectory_segment_id": [
                "111222333_seg_0",
                "111222333_seg_0",
                "444555666_seg_0",
                "777888999_seg_0",
            ],
            "segment_index": [0, 0, 0, 0],
            "is_interpolated": [False, False, True, False],
            "interpolation_method": [None, None, "linear", None],
        }
    )


# ---------------------------------------------------------------------------
# Test 1: Observation exactly at origin timestamp
# ---------------------------------------------------------------------------
def test_observation_exactly_at_origin_timestamp():
    """Observation at exact origin timestamp should be retained."""
    df = pd.DataFrame(
        {
            "mmsi": [123456789],
            "timestamp": pd.to_datetime(["2026-09-07T01:00:00Z"], utc=True),
            "latitude": [18.5001],
            "longitude": [72.5156],
        }
    )
    result = filter_by_time_window(
        data=df,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=30.0,
    )
    assert len(result) == 1
    assert result["mmsi"].iloc[0] == 123456789
    assert result["timestamp"].iloc[0] == pd.Timestamp("2026-09-07T01:00:00Z")


# ---------------------------------------------------------------------------
# Test 2: Observation strictly inside time window
# ---------------------------------------------------------------------------
def test_observation_inside_time_window(sample_temporal_df):
    """Observations within [origin - window, origin + window] are retained."""
    # Origin 01:00:00Z, window 30 min -> [00:30:00, 01:30:00]
    result = filter_by_time_window(
        data=sample_temporal_df,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=30.0,
    )
    assert len(result) == 3
    assert set(result["mmsi"]) == {111222333, 444555666}
    assert 777888999 not in set(result["mmsi"])


# ---------------------------------------------------------------------------
# Test 3: Observation exactly at lower boundary (inclusive)
# ---------------------------------------------------------------------------
def test_observation_exactly_at_lower_boundary():
    """Observation at exactly origin_timestamp - window_minutes must be included."""
    origin = "2026-09-07T01:00:00Z"
    exact_lower = pd.Timestamp("2026-09-07T00:30:00Z")  # exactly -30 min
    df = pd.DataFrame(
        {
            "mmsi": [101],
            "timestamp": [exact_lower],
            "latitude": [18.0],
            "longitude": [72.0],
        }
    )
    result = filter_by_time_window(
        data=df,
        origin_timestamp=origin,
        window_minutes=30.0,
    )
    assert len(result) == 1
    assert result["mmsi"].iloc[0] == 101


# ---------------------------------------------------------------------------
# Test 4: Observation exactly at upper boundary (inclusive)
# ---------------------------------------------------------------------------
def test_observation_exactly_at_upper_boundary():
    """Observation at exactly origin_timestamp + window_minutes must be included."""
    origin = "2026-09-07T01:00:00Z"
    exact_upper = pd.Timestamp("2026-09-07T01:30:00Z")  # exactly +30 min
    df = pd.DataFrame(
        {
            "mmsi": [102],
            "timestamp": [exact_upper],
            "latitude": [18.0],
            "longitude": [72.0],
        }
    )
    result = filter_by_time_window(
        data=df,
        origin_timestamp=origin,
        window_minutes=30.0,
    )
    assert len(result) == 1
    assert result["mmsi"].iloc[0] == 102


# ---------------------------------------------------------------------------
# Test 5: Observation just outside lower boundary (excluded)
# ---------------------------------------------------------------------------
def test_observation_just_outside_lower_boundary():
    """Observation 1 second prior to lower bound must be excluded."""
    origin = "2026-09-07T01:00:00Z"
    outside_lower = pd.Timestamp("2026-09-07T00:29:59Z")  # 30 min 1 sec prior
    df = pd.DataFrame(
        {
            "mmsi": [103],
            "timestamp": [outside_lower],
            "latitude": [18.0],
            "longitude": [72.0],
        }
    )
    result = filter_by_time_window(
        data=df,
        origin_timestamp=origin,
        window_minutes=30.0,
    )
    assert len(result) == 0


# ---------------------------------------------------------------------------
# Test 6: Observation just outside upper boundary (excluded)
# ---------------------------------------------------------------------------
def test_observation_just_outside_upper_boundary():
    """Observation 1 second after upper bound must be excluded."""
    origin = "2026-09-07T01:00:00Z"
    outside_upper = pd.Timestamp("2026-09-07T01:30:01Z")  # 30 min 1 sec after
    df = pd.DataFrame(
        {
            "mmsi": [104],
            "timestamp": [outside_upper],
            "latitude": [18.0],
            "longitude": [72.0],
        }
    )
    result = filter_by_time_window(
        data=df,
        origin_timestamp=origin,
        window_minutes=30.0,
    )
    assert len(result) == 0


# ---------------------------------------------------------------------------
# Test 7: Multiple timestamps within and across vessels
# ---------------------------------------------------------------------------
def test_multiple_timestamps_filtering(sample_temporal_df):
    """Filter correctly partitions multiple observations across time steps."""
    result = filter_by_time_window(
        data=sample_temporal_df,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=20.0,  # [00:40:00, 01:20:00]
    )
    # 01:00:00 and 01:15:00 match; 01:25:00 and 02:30:00 are outside
    assert len(result) == 2
    assert set(result["timestamp"]) == {
        pd.Timestamp("2026-09-07T01:00:00Z"),
        pd.Timestamp("2026-09-07T01:15:00Z"),
    }


# ---------------------------------------------------------------------------
# Test 8: Multiple vessels handled independently
# ---------------------------------------------------------------------------
def test_multiple_vessels_independent(sample_temporal_df):
    """Each vessel is filtered independently based strictly on its own observations."""
    result = filter_by_time_window(
        data=sample_temporal_df,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=10.0,  # [00:50:00, 01:10:00]
    )
    # Only the first ping of 111222333 at 01:00:00 matches
    assert len(result) == 1
    assert result["mmsi"].iloc[0] == 111222333


# ---------------------------------------------------------------------------
# Test 9: Empty DataFrame handling
# ---------------------------------------------------------------------------
def test_empty_dataframe_handling():
    """Empty DataFrame must be handled gracefully, returning empty result with preserved columns."""
    df_empty = pd.DataFrame(columns=["mmsi", "timestamp", "latitude", "longitude"])
    result = filter_by_time_window(
        data=df_empty,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=30.0,
    )
    assert result.empty
    assert list(result.columns) == list(df_empty.columns)

    # Test orchestrator
    res_obj = filter_temporal(
        data=df_empty,
        origin_timestamp="2026-09-07T01:00:00Z",
    )
    assert res_obj.data.empty
    assert res_obj.report.total_input_records == 0
    assert res_obj.report.matched_records == 0
    assert res_obj.candidate_mmsis == set()


# ---------------------------------------------------------------------------
# Test 10: No matches inside time window
# ---------------------------------------------------------------------------
def test_no_matches_handling(sample_temporal_df):
    """When no observations match, return empty DataFrame without error."""
    # Origin 10 hours later
    result = filter_by_time_window(
        data=sample_temporal_df,
        origin_timestamp="2026-09-07T12:00:00Z",
        window_minutes=30.0,
    )
    assert len(result) == 0
    assert list(result.columns) == list(sample_temporal_df.columns)


# ---------------------------------------------------------------------------
# Test 11: Missing timestamp column raises ValueError
# ---------------------------------------------------------------------------
def test_missing_timestamp_column():
    """DataFrame missing 'timestamp' column must raise ValueError."""
    df_no_ts = pd.DataFrame({"mmsi": [1], "latitude": [10.0], "longitude": [20.0]})
    with pytest.raises(ValueError, match="must contain 'timestamp' column"):
        filter_by_time_window(df_no_ts, origin_timestamp="2026-09-07T01:00:00Z")


# ---------------------------------------------------------------------------
# Test 12: Invalid / unparseable timestamp values raise ValueError
# ---------------------------------------------------------------------------
def test_invalid_unparseable_timestamp_values():
    """Unparseable string timestamp values must raise ValueError."""
    df_bad = pd.DataFrame(
        {
            "mmsi": [1],
            "timestamp": ["invalid-date-string"],
            "latitude": [10.0],
            "longitude": [20.0],
        }
    )
    with pytest.raises(ValueError, match="contains unparseable, null, or NaT datetime values"):
        filter_by_time_window(df_bad, origin_timestamp="2026-09-07T01:00:00Z")


# ---------------------------------------------------------------------------
# Test 13: NaT values in timestamp column raise ValueError
# ---------------------------------------------------------------------------
def test_nat_values_raise_error():
    """NaT values in timestamp column must raise ValueError."""
    df_nat = pd.DataFrame(
        {
            "mmsi": [1, 2],
            "timestamp": [pd.Timestamp("2026-09-07T01:00:00Z"), pd.NaT],
            "latitude": [10.0, 11.0],
            "longitude": [20.0, 21.0],
        }
    )
    with pytest.raises(ValueError, match="contains null or NaT values"):
        filter_by_time_window(df_nat, origin_timestamp="2026-09-07T01:00:00Z")


# ---------------------------------------------------------------------------
# Test 14: Invalid origin timestamp raises ValueError
# ---------------------------------------------------------------------------
def test_invalid_origin_timestamp(sample_temporal_df):
    """Invalid or unparseable origin timestamps must raise ValueError."""
    with pytest.raises(ValueError, match="Could not parse datetime"):
        filter_by_time_window(sample_temporal_df, origin_timestamp="not-a-timestamp")

    with pytest.raises(ValueError, match="must be provided and non-null"):
        filter_by_time_window(sample_temporal_df, origin_timestamp=None)

    with pytest.raises(ValueError, match="Value is null or NaT"):
        filter_by_time_window(sample_temporal_df, origin_timestamp=pd.NaT)


# ---------------------------------------------------------------------------
# Test 15: Naive vs timezone-aware timestamp behavior
# ---------------------------------------------------------------------------
def test_naive_vs_timezone_aware_behavior():
    """Timezone-naive timestamps (DataFrame or origin) must raise ValueError."""
    # 1. Naive DataFrame timestamp
    df_naive = pd.DataFrame(
        {
            "mmsi": [1],
            "timestamp": [pd.Timestamp("2026-09-07 01:00:00")],  # tz-naive
            "latitude": [10.0],
            "longitude": [20.0],
        }
    )
    with pytest.raises(ValueError, match="must be timezone-aware"):
        filter_by_time_window(df_naive, origin_timestamp="2026-09-07T01:00:00Z")

    # 2. Naive string in DataFrame without offset
    df_naive_str = pd.DataFrame(
        {
            "mmsi": [1],
            "timestamp": ["2026-09-07 01:00:00"],  # string without tz
            "latitude": [10.0],
            "longitude": [20.0],
        }
    )
    with pytest.raises(ValueError, match="must be timezone-aware"):
        filter_by_time_window(df_naive_str, origin_timestamp="2026-09-07T01:00:00Z")

    # 3. Naive origin timestamp
    df_valid = pd.DataFrame(
        {
            "mmsi": [1],
            "timestamp": [pd.Timestamp("2026-09-07T01:00:00Z")],
            "latitude": [10.0],
            "longitude": [20.0],
        }
    )
    with pytest.raises(ValueError, match="must be timezone-aware"):
        filter_by_time_window(df_valid, origin_timestamp="2026-09-07 01:00:00")


# ---------------------------------------------------------------------------
# Test 16: Different timezone offsets normalized correctly
# ---------------------------------------------------------------------------
def test_different_timezone_offsets_normalized():
    """Non-UTC timezone offsets (e.g. +05:30 IST or -04:00 EDT) are normalized to UTC."""
    # 2026-09-07 06:30:00 +05:30 is exactly 2026-09-07 01:00:00 UTC
    df_ist = pd.DataFrame(
        {
            "mmsi": [999],
            "timestamp": [pd.Timestamp("2026-09-07 06:30:00+05:30")],
            "latitude": [18.0],
            "longitude": [72.0],
        }
    )
    result = filter_by_time_window(
        data=df_ist,
        origin_timestamp="2026-09-07T01:00:00Z",  # UTC origin
        window_minutes=5.0,
    )
    assert len(result) == 1
    assert result["mmsi"].iloc[0] == 999
    # Output timestamp normalized to UTC
    assert str(result["timestamp"].iloc[0].tz) == "UTC"
    assert result["timestamp"].iloc[0] == pd.Timestamp("2026-09-07T01:00:00Z")

    # Non-UTC origin timestamp: 2026-09-06 21:00:00 -04:00 is 2026-09-07 01:00:00 UTC
    origin_edt = pd.Timestamp("2026-09-06 21:00:00-04:00")
    result_origin_tz = filter_by_time_window(
        data=df_ist,
        origin_timestamp=origin_edt,
        window_minutes=5.0,
    )
    assert len(result_origin_tz) == 1


# ---------------------------------------------------------------------------
# Test 17: Input DataFrame is not mutated
# ---------------------------------------------------------------------------
def test_input_dataframe_immutability(sample_temporal_df):
    """Caller's input DataFrame must not be altered in any way."""
    copy_df = sample_temporal_df.copy(deep=True)
    _ = filter_by_time_window(
        data=sample_temporal_df,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=30.0,
    )
    pd.testing.assert_frame_equal(sample_temporal_df, copy_df)


# ---------------------------------------------------------------------------
# Test 18: Original columns preserved
# ---------------------------------------------------------------------------
def test_original_columns_preserved(sample_temporal_df):
    """All input columns are preserved without unintended drops or renames."""
    result = filter_by_time_window(
        data=sample_temporal_df,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=30.0,
    )
    assert list(result.columns) == list(sample_temporal_df.columns)


# ---------------------------------------------------------------------------
# Test 19: Correct candidate MMSIs retained
# ---------------------------------------------------------------------------
def test_correct_candidate_mmsis_retained(sample_temporal_df):
    """Only MMSIs with matching observations are reported as candidates."""
    res_obj = filter_temporal(
        data=sample_temporal_df,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=30.0,
    )
    assert res_obj.candidate_mmsis == {111222333, 444555666}
    assert res_obj.report.unique_vessels_matched == 2


# ---------------------------------------------------------------------------
# Test 20: Config validation
# ---------------------------------------------------------------------------
def test_config_validation():
    """TemporalFilterConfig must validate its numeric attributes."""
    cfg = TemporalFilterConfig(window_minutes=45.0, before_minutes=60.0, after_minutes=30.0)
    assert cfg.window_minutes == 45.0
    assert cfg.effective_before_minutes == 60.0
    assert cfg.effective_after_minutes == 30.0
    assert cfg.retain_full_segments is False

    with pytest.raises(ValueError, match="window_minutes must be a finite non-negative number"):
        TemporalFilterConfig(window_minutes=-10.0)

    with pytest.raises(ValueError, match="window_minutes must be a finite non-negative number"):
        TemporalFilterConfig(window_minutes=np.nan)

    with pytest.raises(ValueError, match="window_minutes must be a finite non-negative number"):
        TemporalFilterConfig(window_minutes=np.inf)

    with pytest.raises(ValueError, match="before_minutes must be a finite non-negative number"):
        TemporalFilterConfig(before_minutes=-5.0)

    with pytest.raises(ValueError, match="after_minutes must be a finite non-negative number"):
        TemporalFilterConfig(after_minutes=-1.0)


# ---------------------------------------------------------------------------
# Test 21: Zero-minute window
# ---------------------------------------------------------------------------
def test_zero_minute_window():
    """A zero-minute window [T - 0, T + 0] matches only exact timestamps."""
    df = pd.DataFrame(
        {
            "mmsi": [1, 2, 3],
            "timestamp": pd.to_datetime(
                [
                    "2026-09-07T01:00:00Z",
                    "2026-09-07T01:00:01Z",
                    "2026-09-07T00:59:59Z",
                ],
                utc=True,
            ),
            "latitude": [18.0, 18.0, 18.0],
            "longitude": [72.0, 72.0, 72.0],
        }
    )
    result = filter_by_time_window(
        data=df,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=0.0,
    )
    assert len(result) == 1
    assert result["mmsi"].iloc[0] == 1


# ---------------------------------------------------------------------------
# Test 22: Non-negative window validation in filter functions
# ---------------------------------------------------------------------------
def test_non_negative_window_validation(sample_temporal_df):
    """Passing negative window values to filter functions raises ValueError."""
    with pytest.raises(ValueError, match="window_minutes must be a finite non-negative number"):
        filter_by_time_window(
            sample_temporal_df,
            origin_timestamp="2026-09-07T01:00:00Z",
            window_minutes=-10.0,
        )


# ---------------------------------------------------------------------------
# Test 23: Deterministic output
# ---------------------------------------------------------------------------
def test_deterministic_output(sample_temporal_df):
    """Consecutive filtering executions produce identical output."""
    res1 = filter_by_time_window(
        sample_temporal_df,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=30.0,
    )
    res2 = filter_by_time_window(
        sample_temporal_df,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=30.0,
    )
    pd.testing.assert_frame_equal(res1, res2)


# ---------------------------------------------------------------------------
# Test 24: Compatibility with AIS-06 SpatialFilterResult
# ---------------------------------------------------------------------------
def test_compatibility_with_ais06_output(sample_temporal_df):
    """Temporal filter accepts AIS-06 SpatialFilterResult directly in pipeline."""
    # 1. Run AIS-06 spatial filter
    spatial_res = filter_spatial(
        data=sample_temporal_df,
        center_latitude=18.5001,
        center_longitude=72.5156,
        config=SpatialFilterConfig(radius_km=1.0),
    )
    assert len(spatial_res.data) > 0
    assert "distance_km" in spatial_res.data.columns

    # 2. Feed spatial_res directly into AIS-07 temporal filter
    temporal_res = filter_temporal(
        data=spatial_res,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=20.0,
    )
    assert isinstance(temporal_res, TemporalFilterResult)
    assert "distance_km" in temporal_res.data.columns
    assert len(temporal_res.data) > 0
    assert temporal_res.candidate_mmsis == {111222333}


# ---------------------------------------------------------------------------
# Test 25: Segment retention mode (retain_full_segments=True) & MMSI fallback
# ---------------------------------------------------------------------------
def test_segment_retention_mode(sample_temporal_df):
    """When retain_full_segments=True, retaining any ping retains entire segment."""
    # MMSI 111222333 has 2 pings in seg_0: at 01:00:00Z and 01:15:00Z
    # If window is [00:55:00, 01:05:00], only 01:00:00Z is in window
    # Under retain_full_segments=False, only 1 ping returned
    res_obs = filter_by_time_window(
        sample_temporal_df,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=5.0,  # [00:55:00, 01:05:00]
        retain_full_segments=False,
    )
    assert len(res_obs) == 1
    assert res_obs["timestamp"].iloc[0] == pd.Timestamp("2026-09-07T01:00:00Z")

    # Under retain_full_segments=True, both pings of seg_0 are retained
    res_seg = filter_by_time_window(
        sample_temporal_df,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=5.0,
        retain_full_segments=True,
    )
    assert len(res_seg) == 2
    assert set(res_seg["timestamp"]) == {
        pd.Timestamp("2026-09-07T01:00:00Z"),
        pd.Timestamp("2026-09-07T01:15:00Z"),
    }
    assert (res_seg["trajectory_segment_id"] == "111222333_seg_0").all()
    # Unrelated segments excluded
    assert "777888999_seg_0" not in res_seg["trajectory_segment_id"].values

    # MMSI-level fallback when trajectory_segment_id is absent
    df_no_seg = sample_temporal_df.drop(columns=["trajectory_segment_id"])
    res_mmsi = filter_by_time_window(
        df_no_seg,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=5.0,
        retain_full_segments=True,
    )
    assert len(res_mmsi) == 2
    assert set(res_mmsi["mmsi"]) == {111222333}


# ---------------------------------------------------------------------------
# Test 26: Non-datetime dtype string timestamps parsed and normalized safely
# ---------------------------------------------------------------------------
def test_non_datetime_dtype_string_parsing():
    """String timestamps with ISO timezone notation are parsed without requiring prior datetime dtype."""
    df_str = pd.DataFrame(
        {
            "mmsi": [501, 502],
            "timestamp": [
                "2026-09-07T01:05:00Z",
                "2026-09-07T03:00:00Z",
            ],  # string dtype
            "latitude": [18.0, 18.0],
            "longitude": [72.0, 72.0],
        }
    )
    orig_dtype = df_str["timestamp"].dtype
    assert pd.api.types.is_string_dtype(df_str["timestamp"])

    result = filter_by_time_window(
        data=df_str,
        origin_timestamp="2026-09-07T01:00:00Z",
        window_minutes=30.0,
    )
    assert len(result) == 1
    assert result["mmsi"].iloc[0] == 501
    assert pd.api.types.is_datetime64_any_dtype(result["timestamp"])
    assert str(result["timestamp"].dt.tz) == "UTC"
    # Caller input unchanged
    assert df_str["timestamp"].dtype == orig_dtype


# ---------------------------------------------------------------------------
# Test 27: Asymmetric windows (before_minutes vs after_minutes precedence)
# ---------------------------------------------------------------------------
def test_asymmetric_windows_precedence():
    """Asymmetric window uses before_minutes/after_minutes overriding window_minutes."""
    # Origin: 01:00:00Z
    # Config: window_minutes=30, before_minutes=60, after_minutes=None
    # Effective window: [01:00 - 60 min, 01:00 + 30 min] = [00:00:00, 01:30:00]
    df = pd.DataFrame(
        {
            "mmsi": [1, 2, 3],
            "timestamp": pd.to_datetime(
                [
                    "2026-09-07T00:10:00Z",  # In window (within -60 min)
                    "2026-09-07T01:20:00Z",  # In window (within +30 min)
                    "2026-09-07T01:40:00Z",  # Outside window (exceeds +30 min)
                ],
                utc=True,
            ),
            "latitude": [18.0, 18.0, 18.0],
            "longitude": [72.0, 72.0, 72.0],
        }
    )
    cfg = TemporalFilterConfig(
        window_minutes=30.0,
        before_minutes=60.0,
        after_minutes=None,
    )
    assert cfg.effective_before_minutes == 60.0
    assert cfg.effective_after_minutes == 30.0

    res = filter_temporal(
        data=df,
        origin_timestamp="2026-09-07T01:00:00Z",
        config=cfg,
    )
    assert len(res.data) == 2
    assert set(res.data["mmsi"]) == {1, 2}
    assert res.report.before_minutes == 60.0
    assert res.report.after_minutes == 30.0
    assert res.report.start_timestamp == "2026-09-07T00:00:00+00:00"
    assert res.report.end_timestamp == "2026-09-07T01:30:00+00:00"


# ---------------------------------------------------------------------------
# Test 28: Member 4 origin data dictionary integration
# ---------------------------------------------------------------------------
def test_member4_origin_data_integration(member4_origin_data, sample_temporal_df):
    """filter_by_origin_time and filter_temporal integrate with Member 4 origin data contract."""
    # member4_origin_data origin timestamp is "2026-09-07T01:00:00Z"
    res_direct = filter_by_origin_time(
        data=sample_temporal_df,
        origin_data=member4_origin_data,
        window_minutes=30.0,
    )
    assert len(res_direct) == 3
    assert set(res_direct["mmsi"]) == {111222333, 444555666}

    # High-level orchestrator
    res_orch = filter_temporal(
        data=sample_temporal_df,
        origin_data=member4_origin_data,
        window_minutes=30.0,
    )
    assert isinstance(res_orch, TemporalFilterResult)
    assert res_orch.report.origin_timestamp == "2026-09-07T01:00:00+00:00"
    assert res_orch.candidate_mmsis == {111222333, 444555666}
    assert res_orch.report.segments_matched == 2
