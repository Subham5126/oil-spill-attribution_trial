"""Unit tests for individual attribution scoring components."""

import numpy as np
import pandas as pd
import pytest

from attribution.scoring.config import AttributionScoringConfig
from attribution.scoring.spatial import calculate_spatial_score, find_closest_approach
from attribution.scoring.temporal import calculate_temporal_score, resolve_time_of_closest_approach
from attribution.scoring.trajectory import (
    analyze_ais_gaps,
    calculate_bearing,
    calculate_behaviour_score,
    calculate_trajectory_score,
    determine_vessel_direction,
)


# ===========================================================================
# 1. Spatial Scoring Tests
# ===========================================================================
def test_spatial_inside_origin_radius():
    """Verify d_min <= origin_radius yields exactly 1.0."""
    assert calculate_spatial_score(min_distance_km=0.0, origin_radius_km=5.0, max_distance_km=25.0) == 1.0
    assert calculate_spatial_score(min_distance_km=3.5, origin_radius_km=5.0, max_distance_km=25.0) == 1.0
    assert calculate_spatial_score(min_distance_km=5.0, origin_radius_km=5.0, max_distance_km=25.0) == 1.0


def test_spatial_point_origin():
    """Verify point origin (radius=0) decays smoothly from 1.0 at d=0 to 0.0 at d=max."""
    assert calculate_spatial_score(min_distance_km=0.0, origin_radius_km=0.0, max_distance_km=20.0) == 1.0
    assert calculate_spatial_score(min_distance_km=10.0, origin_radius_km=0.0, max_distance_km=20.0) == 0.5
    assert calculate_spatial_score(min_distance_km=20.0, origin_radius_km=0.0, max_distance_km=20.0) == 0.0


def test_spatial_at_and_beyond_max_distance():
    """Verify d_min >= max_distance yields exactly 0.0."""
    assert calculate_spatial_score(min_distance_km=25.0, origin_radius_km=5.0, max_distance_km=25.0) == 0.0
    assert calculate_spatial_score(min_distance_km=50.0, origin_radius_km=5.0, max_distance_km=25.0) == 0.0


def test_spatial_linear_decay_exact():
    """Verify exact piecewise linear formula: 1 - (d - r) / (d_max - r)."""
    # r=5, max=25 -> span=20. At d=15 -> excess=10 -> score = 1 - 10/20 = 0.5
    score = calculate_spatial_score(min_distance_km=15.0, origin_radius_km=5.0, max_distance_km=25.0, decay_method="linear")
    assert score == pytest.approx(0.5, abs=1e-6)


def test_spatial_gaussian_decay():
    """Verify gaussian decay decays smoothly between r_orig and max_dist."""
    s1 = calculate_spatial_score(min_distance_km=5.0, origin_radius_km=5.0, max_distance_km=25.0, decay_method="gaussian")
    s2 = calculate_spatial_score(min_distance_km=10.0, origin_radius_km=5.0, max_distance_km=25.0, decay_method="gaussian")
    s3 = calculate_spatial_score(min_distance_km=20.0, origin_radius_km=5.0, max_distance_km=25.0, decay_method="gaussian")
    assert s1 == 1.0
    assert 0.0 < s3 < s2 < s1


def test_spatial_degenerate_bounds():
    """Verify degenerate max_distance <= origin_radius boundary handling."""
    assert calculate_spatial_score(min_distance_km=5.0, origin_radius_km=10.0, max_distance_km=10.0) == 1.0
    assert calculate_spatial_score(min_distance_km=12.0, origin_radius_km=10.0, max_distance_km=10.0) == 0.0


def test_spatial_validation_errors():
    """Verify rejection of invalid spatial arguments."""
    with pytest.raises(ValueError):
        calculate_spatial_score(min_distance_km=-1.0)
    with pytest.raises(ValueError):
        calculate_spatial_score(min_distance_km=5.0, origin_radius_km=-2.0)
    with pytest.raises(ValueError):
        calculate_spatial_score(min_distance_km=5.0, max_distance_km=-5.0)
    with pytest.raises(ValueError):
        calculate_spatial_score(min_distance_km=5.0, decay_method="unknown")


def test_find_closest_approach_interpolated_determines_dmin():
    """Verify interpolated fixes closer than actual pings correctly determine d_min."""
    df = pd.DataFrame([
        {
            "mmsi": 205123456,
            "timestamp": "2025-01-08T00:00:00Z",
            "latitude": 28.10,
            "longitude": -90.00,
            "distance_km": 11.1,
            "is_interpolated": False,
        },
        {
            "mmsi": 205123456,
            "timestamp": "2025-01-08T00:05:00Z",
            "latitude": 28.02,
            "longitude": -90.00,
            "distance_km": 2.22,
            "is_interpolated": True,  # Interpolated fix is closest
        },
        {
            "mmsi": 205123456,
            "timestamp": "2025-01-08T00:10:00Z",
            "latitude": 28.15,
            "longitude": -90.00,
            "distance_km": 16.6,
            "is_interpolated": False,
        },
    ])
    d_min, cpa_row, is_interp = find_closest_approach(df, origin_lat=28.0, origin_lon=-90.0)
    assert d_min == pytest.approx(2.22, abs=1e-2)
    assert is_interp is True
    assert cpa_row["timestamp"] == "2025-01-08T00:05:00Z"


# ===========================================================================
# 2. Temporal Scoring Tests
# ===========================================================================
def test_temporal_inside_window():
    """Verify offset <= acceptable_window yields 1.0."""
    assert calculate_temporal_score(time_diff_seconds=0.0, acceptable_window_seconds=1800.0, max_time_diff_seconds=7200.0) == 1.0
    assert calculate_temporal_score(time_diff_seconds=900.0, acceptable_window_seconds=1800.0, max_time_diff_seconds=7200.0) == 1.0
    assert calculate_temporal_score(time_diff_seconds=1800.0, acceptable_window_seconds=1800.0, max_time_diff_seconds=7200.0) == 1.0


def test_temporal_at_and_beyond_cutoff():
    """Verify offset >= max_time_diff yields 0.0."""
    assert calculate_temporal_score(time_diff_seconds=7200.0, acceptable_window_seconds=1800.0, max_time_diff_seconds=7200.0) == 0.0
    assert calculate_temporal_score(time_diff_seconds=10000.0, acceptable_window_seconds=1800.0, max_time_diff_seconds=7200.0) == 0.0


def test_temporal_linear_decay_exact():
    """Verify exact piecewise linear formula: 1 - (dt - w_acc) / (w_max - w_acc)."""
    # w_acc=1800, w_max=7200 -> span=5400. At dt=4500 -> excess=2700 -> score = 1 - 2700/5400 = 0.5
    score = calculate_temporal_score(time_diff_seconds=4500.0, acceptable_window_seconds=1800.0, max_time_diff_seconds=7200.0, decay_method="linear")
    assert score == pytest.approx(0.5, abs=1e-6)


def test_temporal_symmetry_forward_backward():
    """Verify temporal offsets forward and backward in time produce identical positive dt."""
    t_origin = pd.Timestamp("2025-01-08T01:00:00Z")
    df_forward = pd.DataFrame([{
        "mmsi": 123456789,
        "timestamp": "2025-01-08T01:30:00Z",
        "latitude": 28.0,
        "longitude": -90.0,
        "distance_km": 1.0,
    }])
    df_backward = pd.DataFrame([{
        "mmsi": 123456789,
        "timestamp": "2025-01-08T00:30:00Z",
        "latitude": 28.0,
        "longitude": -90.0,
        "distance_km": 1.0,
    }])
    _, dt_fwd, _ = resolve_time_of_closest_approach(df_forward, t_origin, 28.0, -90.0)
    _, dt_bwd, _ = resolve_time_of_closest_approach(df_backward, t_origin, 28.0, -90.0)
    assert dt_fwd == 1800.0
    assert dt_bwd == 1800.0
    assert calculate_temporal_score(dt_fwd) == calculate_temporal_score(dt_bwd)


# ===========================================================================
# 3. Trajectory Scoring Tests
# ===========================================================================
def test_bearing_calculation():
    """Verify standard geodetic bearings."""
    # North
    assert calculate_bearing(28.0, -90.0, 29.0, -90.0) == pytest.approx(0.0, abs=1e-3)
    # East
    assert calculate_bearing(0.0, 0.0, 0.0, 1.0) == pytest.approx(90.0, abs=1e-3)
    # South
    assert calculate_bearing(29.0, -90.0, 28.0, -90.0) == pytest.approx(180.0, abs=1e-3)
    # West
    assert calculate_bearing(0.0, 1.0, 0.0, 0.0) == pytest.approx(270.0, abs=1e-3)


def test_trajectory_explicit_drift_alignments():
    """Verify trajectory scores under parallel, perpendicular, and opposing explicit drift."""
    # Parallel (0 deg difference) -> 1.0
    assert calculate_trajectory_score(vessel_direction_deg=90.0, explicit_drift_direction_deg=90.0) == pytest.approx(1.0, abs=1e-6)
    # Perpendicular (90 deg difference) -> 0.5
    assert calculate_trajectory_score(vessel_direction_deg=90.0, explicit_drift_direction_deg=180.0) == pytest.approx(0.5, abs=1e-6)
    # Opposing (180 deg difference) -> 0.0
    assert calculate_trajectory_score(vessel_direction_deg=90.0, explicit_drift_direction_deg=270.0) == pytest.approx(0.0, abs=1e-6)


def test_trajectory_no_drift_fallback():
    """Verify fallback to track-origin intersection when explicit drift is absent."""
    # Track intersects origin
    assert calculate_trajectory_score(vessel_direction_deg=45.0, explicit_drift_direction_deg=None, trajectory_intersects_origin=True) == 1.0
    # Track passes nearby with spatial score 0.8
    assert calculate_trajectory_score(vessel_direction_deg=45.0, explicit_drift_direction_deg=None, trajectory_intersects_origin=False, spatial_score=0.8) == 0.8
    # Track uncomputable
    assert calculate_trajectory_score(vessel_direction_deg=None, explicit_drift_direction_deg=None) is None


def test_determine_vessel_direction_cog_vs_bearing_fallback():
    """Verify COG is preferred when underway; bearing fallback used when COG is missing."""
    # Case A: Valid COG
    df_cog = pd.DataFrame([
        {"timestamp": "2025-01-08T00:00:00Z", "latitude": 28.0, "longitude": -90.0, "sog": 10.0, "cog": 135.0},
        {"timestamp": "2025-01-08T00:10:00Z", "latitude": 28.05, "longitude": -89.95, "sog": 10.0, "cog": 135.0},
    ])
    assert determine_vessel_direction(df_cog) == 135.0

    # Case B: Missing COG, derived bearing (Northward)
    df_no_cog = pd.DataFrame([
        {"timestamp": "2025-01-08T00:00:00Z", "latitude": 28.0, "longitude": -90.0, "sog": 10.0, "cog": np.nan},
        {"timestamp": "2025-01-08T00:10:00Z", "latitude": 29.0, "longitude": -90.0, "sog": 10.0, "cog": np.nan},
    ])
    direction = determine_vessel_direction(df_no_cog)
    assert direction == pytest.approx(0.0, abs=1e-2)

    # Case C: Single point (N=1) returns None
    df_single = pd.DataFrame([
        {"timestamp": "2025-01-08T00:00:00Z", "latitude": 28.0, "longitude": -90.0, "sog": 10.0, "cog": np.nan},
    ])
    assert determine_vessel_direction(df_single) is None


# ===========================================================================
# 4. Behaviour Scoring Tests
# ===========================================================================
def test_behaviour_observed_cruising_speed():
    """Verify normal cruising transit speed (6-18 kn) without gaps yields high score."""
    df = pd.DataFrame([
        {"timestamp": "2025-01-08T00:00:00Z", "latitude": 28.0, "longitude": -90.0, "sog": 12.0, "distance_km": 1.0, "is_interpolated": False},
        {"timestamp": "2025-01-08T00:05:00Z", "latitude": 28.01, "longitude": -90.0, "sog": 12.5, "distance_km": 1.1, "is_interpolated": False},
        {"timestamp": "2025-01-08T00:10:00Z", "latitude": 28.02, "longitude": -90.0, "sog": 12.0, "distance_km": 1.2, "is_interpolated": False},
    ])
    score = calculate_behaviour_score(df, origin_radius_km=5.0)
    assert score is not None
    assert score > 0.85


def test_behaviour_missing_sog_derives_speed():
    """Verify missing SOG with >=2 fixes derives speed from displacement coordinates."""
    # 1 deg latitude ~ 111.19 km in 1 hour -> ~ 60 knots
    df = pd.DataFrame([
        {"timestamp": "2025-01-08T00:00:00Z", "latitude": 28.0, "longitude": -90.0, "distance_km": 1.0, "is_interpolated": False},
        {"timestamp": "2025-01-08T01:00:00Z", "latitude": 28.18, "longitude": -90.0, "distance_km": 1.0, "is_interpolated": False},
    ])
    score = calculate_behaviour_score(df, origin_radius_km=5.0)
    assert score is not None
    assert 0.0 <= score <= 1.0


def test_behaviour_missing_sog_uncomputable_neutral_fallback():
    """Verify single observation with missing SOG receives neutral fallback (0.70) without penalty."""
    df = pd.DataFrame([
        {"timestamp": "2025-01-08T00:00:00Z", "latitude": 28.0, "longitude": -90.0, "distance_km": 1.0, "is_interpolated": False},
    ])
    cfg = AttributionScoringConfig(neutral_speed_score=0.70)
    score = calculate_behaviour_score(df, origin_radius_km=5.0, config=cfg)
    assert score is not None
    # s_sog = 0.70, s_var = 0.70, s_continuity = 1.0 -> 0.5*0.7 + 0.3*0.7 + 0.2*1.0 = 0.76
    assert score == pytest.approx(0.76, abs=1e-2)


def test_behaviour_ais_gap_neutral_reduction():
    """Verify broadcast gap reduces continuity neutrally without raising errors."""
    df_gap = pd.DataFrame([
        {"timestamp": "2025-01-08T00:00:00Z", "latitude": 28.0, "longitude": -90.0, "sog": 10.0, "distance_km": 1.0, "is_interpolated": False},
        {"timestamp": "2025-01-08T01:00:00Z", "latitude": 28.1, "longitude": -90.0, "sog": 10.0, "distance_km": 2.0, "is_interpolated": False},  # 60 min gap near origin
    ])
    gap_count, gap_near, max_gap = analyze_ais_gaps(df_gap, origin_radius_km=5.0, gap_threshold_seconds=1800.0)
    assert gap_count == 1
    assert gap_near is True
    assert max_gap == 60.0

    score_with_gap = calculate_behaviour_score(df_gap, origin_radius_km=5.0)
    assert score_with_gap is not None
    assert score_with_gap < 0.85
