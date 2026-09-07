"""Tests for AIS-06 Spatial Filtering.

Comprehensive test suite covering:
1. AIS point exactly at origin.
2. AIS point inside radius.
3. AIS point outside radius.
4. Radius boundary behavior (inclusive).
5. Correct Haversine distance accuracy against known geodesics.
6. Invalid center latitude.
7. Invalid center longitude.
8. Negative radius.
9. Negative buffer.
10. Empty AIS DataFrame handling.
11. Immutability of caller's input DataFrame.
12. Preservation of all original AIS and AIS-04/05 columns.
13. Correct computation and addition of distance_km.
14. Independent handling of multiple vessels.
15. Correct handling of multiple trajectory segments.
16. Member 4 uncertainty radius utilization.
17. Additional search buffer expansion.
18. Member 4 bounding-box filtering and coarse optimization.
19. Anti-meridian (+/-180 deg) bounding-box and distance behavior.
20. Rejection of invalid/out-of-bounds AIS coordinates.
21. Realistic test case using Member 4 conceptual values.
22. Polymorphic TrajectoryResult input handling.
23. Rejection of NaN / non-finite center latitude, longitude, radius, and buffer.
24. Correct preservation of zero coordinates (0.0 latitude and 0.0 longitude).
25. Member 4 bounding-box metadata does not exclude points within Haversine uncertainty radius.
"""

from typing import Any, Dict
import numpy as np
import pandas as pd
import pytest

from ais.filtering.config import SpatialFilterConfig
from ais.filtering.spatial import (
    EARTH_RADIUS_KM,
    SpatialFilterReport,
    SpatialFilterResult,
    derive_bounding_box,
    filter_by_bounding_box,
    filter_by_origin_uncertainty,
    filter_by_radius,
    filter_spatial,
    filter_trajectories_spatially,
    haversine_distance_km,
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
def sample_ais_df() -> pd.DataFrame:
    """Synthetic AIS DataFrame with multiple vessels and trajectory metadata."""
    return pd.DataFrame(
        {
            "mmsi": [111222333, 111222333, 444555666, 777888999],
            "timestamp": pd.to_datetime(
                [
                    "2026-09-07T01:00:00Z",
                    "2026-09-07T01:10:00Z",
                    "2026-09-07T01:05:00Z",
                    "2026-09-07T01:00:00Z",
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
# Test 1: AIS point exactly at origin
# ---------------------------------------------------------------------------
def test_point_exactly_at_origin():
    """An observation located exactly at the origin coordinates should have distance_km == 0.0 and be retained."""
    df = pd.DataFrame(
        {
            "mmsi": [123456789],
            "timestamp": pd.to_datetime(["2026-09-07T01:00:00Z"], utc=True),
            "latitude": [18.5001],
            "longitude": [72.5156],
        }
    )
    result = filter_by_radius(
        data=df,
        center_latitude=18.5001,
        center_longitude=72.5156,
        radius_km=1.1039,
    )
    assert len(result) == 1
    assert "distance_km" in result.columns
    assert np.isclose(result["distance_km"].iloc[0], 0.0, atol=1e-6)
    assert result["mmsi"].iloc[0] == 123456789


# ---------------------------------------------------------------------------
# Test 2: AIS point inside radius
# ---------------------------------------------------------------------------
def test_point_inside_radius():
    """An observation strictly inside the radius should be retained with correct distance."""
    # 0.005 degrees latitude is ~0.556 km
    df = pd.DataFrame(
        {
            "mmsi": [123456789],
            "timestamp": pd.to_datetime(["2026-09-07T01:00:00Z"], utc=True),
            "latitude": [18.5051],
            "longitude": [72.5156],
        }
    )
    result = filter_by_radius(
        data=df,
        center_latitude=18.5001,
        center_longitude=72.5156,
        radius_km=1.1039,
    )
    assert len(result) == 1
    assert result["distance_km"].iloc[0] < 1.1039
    assert result["distance_km"].iloc[0] > 0.5


# ---------------------------------------------------------------------------
# Test 3: AIS point outside radius
# ---------------------------------------------------------------------------
def test_point_outside_radius():
    """An observation beyond the search radius should be excluded."""
    # 0.05 degrees latitude is ~5.56 km (> 1.1039 km)
    df = pd.DataFrame(
        {
            "mmsi": [123456789],
            "timestamp": pd.to_datetime(["2026-09-07T01:00:00Z"], utc=True),
            "latitude": [18.5501],
            "longitude": [72.5156],
        }
    )
    result = filter_by_radius(
        data=df,
        center_latitude=18.5001,
        center_longitude=72.5156,
        radius_km=1.1039,
    )
    assert len(result) == 0
    assert "distance_km" in result.columns


# ---------------------------------------------------------------------------
# Test 4: Radius boundary behavior (inclusive)
# ---------------------------------------------------------------------------
def test_radius_boundary_inclusive():
    """Points exactly on the boundary are included; points slightly beyond are excluded."""
    center_lat = 0.0
    center_lon = 0.0
    radius = 10.0
    dlat = (radius / EARTH_RADIUS_KM) * (180.0 / np.pi)

    lat_exact = dlat
    lat_just_inside = dlat - 1e-7
    lat_just_outside = dlat + 1e-5

    df = pd.DataFrame(
        {
            "mmsi": [1, 2, 3],
            "timestamp": pd.to_datetime(
                ["2026-09-07T01:00:00Z", "2026-09-07T01:00:00Z", "2026-09-07T01:00:00Z"],
                utc=True,
            ),
            "latitude": [lat_exact, lat_just_inside, lat_just_outside],
            "longitude": [0.0, 0.0, 0.0],
        }
    )
    result = filter_by_radius(
        data=df,
        center_latitude=center_lat,
        center_longitude=center_lon,
        radius_km=radius,
    )
    # Both exact and just inside must be retained; just outside must be excluded
    assert len(result) == 2
    assert set(result["mmsi"]) == {1, 2}
    assert np.isclose(result[result["mmsi"] == 1]["distance_km"].iloc[0], radius, atol=1e-5)


# ---------------------------------------------------------------------------
# Test 5: Correct Haversine distance accuracy against known geodesics
# ---------------------------------------------------------------------------
def test_correct_haversine_distance():
    """Haversine distance matches spherical geodesic theory."""
    # 1 degree of latitude along meridian: (pi / 180) * 6371.0088 km = ~111.1949 km
    dist_1deg_lat = haversine_distance_km(0.0, 0.0, 1.0, 0.0)
    expected_1deg = (np.pi / 180.0) * EARTH_RADIUS_KM
    assert np.isclose(dist_1deg_lat, expected_1deg, atol=1e-4)

    # 1 degree of longitude at equator: same distance
    dist_1deg_lon = haversine_distance_km(0.0, 0.0, 0.0, 1.0)
    assert np.isclose(dist_1deg_lon, expected_1deg, atol=1e-4)

    # Quarter meridian (Equator to North Pole): (pi / 2) * R = ~10007.5434 km
    dist_pole = haversine_distance_km(0.0, 0.0, 90.0, 0.0)
    assert np.isclose(dist_pole, (np.pi / 2.0) * EARTH_RADIUS_KM, atol=1e-4)

    # Known transatlantic distance: NYC (40.7128, -74.0060) to London (51.5074, -0.1278)
    dist_nyc_lon = haversine_distance_km(40.7128, -74.0060, 51.5074, -0.1278)
    assert 5560.0 < dist_nyc_lon < 5580.0


# ---------------------------------------------------------------------------
# Test 6: Invalid center latitude
# ---------------------------------------------------------------------------
def test_invalid_center_latitude(sample_ais_df):
    """Out-of-range center latitude must raise ValueError."""
    with pytest.raises(ValueError, match="Center latitude must be a finite number"):
        filter_by_radius(sample_ais_df, center_latitude=95.0, center_longitude=72.0, radius_km=5.0)

    with pytest.raises(ValueError, match="Center latitude must be a finite number"):
        filter_by_radius(sample_ais_df, center_latitude=-90.1, center_longitude=72.0, radius_km=5.0)


# ---------------------------------------------------------------------------
# Test 7: Invalid center longitude
# ---------------------------------------------------------------------------
def test_invalid_center_longitude(sample_ais_df):
    """Out-of-range center longitude must raise ValueError."""
    with pytest.raises(ValueError, match="Center longitude must be a finite number"):
        filter_by_radius(sample_ais_df, center_latitude=18.0, center_longitude=185.0, radius_km=5.0)

    with pytest.raises(ValueError, match="Center longitude must be a finite number"):
        filter_by_radius(sample_ais_df, center_latitude=18.0, center_longitude=-180.1, radius_km=5.0)


# ---------------------------------------------------------------------------
# Test 8: Negative radius
# ---------------------------------------------------------------------------
def test_negative_radius(sample_ais_df):
    """Negative radius_km must raise ValueError."""
    with pytest.raises(ValueError, match="radius_km must be a finite non-negative number"):
        filter_by_radius(sample_ais_df, center_latitude=18.0, center_longitude=72.0, radius_km=-1.0)


# ---------------------------------------------------------------------------
# Test 9: Negative buffer
# ---------------------------------------------------------------------------
def test_negative_buffer(sample_ais_df):
    """Negative buffer_km must raise ValueError."""
    with pytest.raises(ValueError, match="buffer_km must be a finite non-negative number"):
        filter_by_radius(
            sample_ais_df,
            center_latitude=18.0,
            center_longitude=72.0,
            radius_km=5.0,
            buffer_km=-0.5,
        )


# ---------------------------------------------------------------------------
# Test 10: Empty AIS DataFrame
# ---------------------------------------------------------------------------
def test_empty_ais_dataframe():
    """Empty DataFrame must be handled cleanly without errors, returning empty result with distance_km."""
    empty_df = pd.DataFrame(columns=["mmsi", "timestamp", "latitude", "longitude"])
    result = filter_by_radius(
        data=empty_df,
        center_latitude=18.5001,
        center_longitude=72.5156,
        radius_km=5.0,
    )
    assert result.empty
    assert "distance_km" in result.columns
    assert "mmsi" in result.columns


# ---------------------------------------------------------------------------
# Test 11: Original input is not mutated
# ---------------------------------------------------------------------------
def test_input_immutability(sample_ais_df):
    """Caller's input DataFrame must not be modified in any way."""
    original_copy = sample_ais_df.copy(deep=True)
    _ = filter_by_radius(
        data=sample_ais_df,
        center_latitude=18.5001,
        center_longitude=72.5156,
        radius_km=1.1039,
    )
    pd.testing.assert_frame_equal(sample_ais_df, original_copy)
    assert "distance_km" not in sample_ais_df.columns


# ---------------------------------------------------------------------------
# Test 12: Original AIS columns are preserved
# ---------------------------------------------------------------------------
def test_columns_preserved(sample_ais_df):
    """All input columns (canonical, optional, AIS-04/05 metadata) must be present in output."""
    result = filter_by_radius(
        data=sample_ais_df,
        center_latitude=18.5001,
        center_longitude=72.5156,
        radius_km=1.1039,
    )
    expected_cols = set(sample_ais_df.columns).union({"distance_km"})
    assert set(result.columns) == expected_cols


# ---------------------------------------------------------------------------
# Test 13: distance_km is added correctly
# ---------------------------------------------------------------------------
def test_distance_km_added_correctly(sample_ais_df):
    """distance_km column must contain correct numeric floats."""
    result = filter_by_radius(
        data=sample_ais_df,
        center_latitude=18.5001,
        center_longitude=72.5156,
        radius_km=5.0,
    )
    assert not result.empty
    assert pd.api.types.is_float_dtype(result["distance_km"])
    assert (result["distance_km"] >= 0.0).all()
    assert (result["distance_km"] <= 5.0).all()


# ---------------------------------------------------------------------------
# Test 14: Multiple vessels handled independently
# ---------------------------------------------------------------------------
def test_multiple_vessels_independent(sample_ais_df):
    """Different vessels are evaluated strictly by their individual coordinates."""
    result = filter_by_radius(
        data=sample_ais_df,
        center_latitude=18.5001,
        center_longitude=72.5156,
        radius_km=1.1039,
    )
    retained_mmsis = set(result["mmsi"])
    assert 111222333 in retained_mmsis
    assert 444555666 in retained_mmsis
    assert 777888999 not in retained_mmsis


# ---------------------------------------------------------------------------
# Test 15: Multiple trajectory segments handled correctly
# ---------------------------------------------------------------------------
def test_multiple_trajectory_segments(sample_ais_df):
    """Multiple trajectory segments for a vessel are preserved and filtered by segment."""
    distant_row = pd.DataFrame(
        {
            "mmsi": [111222333],
            "timestamp": pd.to_datetime(["2026-09-07T04:00:00Z"], utc=True),
            "latitude": [20.5000],
            "longitude": [75.0000],
            "sog": [12.0],
            "cog": [180.0],
            "heading": [180.0],
            "vessel_name": ["TANKER_ALPHA"],
            "vessel_type": [80],
            "trajectory_segment_id": ["111222333_seg_1"],
            "segment_index": [1],
            "is_interpolated": [False],
            "interpolation_method": [None],
        }
    )
    multi_seg_df = pd.concat([sample_ais_df, distant_row], ignore_index=True)

    # Observation-level filtering: only observations from seg_0 qualify
    res_obs = filter_by_radius(
        data=multi_seg_df,
        center_latitude=18.5001,
        center_longitude=72.5156,
        radius_km=1.1039,
    )
    assert set(res_obs["trajectory_segment_id"]) == {"111222333_seg_0", "444555666_seg_0"}
    assert "111222333_seg_1" not in res_obs["trajectory_segment_id"].values

    # Full segment retention mode:
    res_seg = filter_trajectories_spatially(
        data=multi_seg_df,
        center_latitude=18.5001,
        center_longitude=72.5156,
        radius_km=1.1039,
        retain_full_segments=True,
    )
    assert "111222333_seg_0" in res_seg["trajectory_segment_id"].values
    assert "111222333_seg_1" not in res_seg["trajectory_segment_id"].values


# ---------------------------------------------------------------------------
# Test 16: Member 4 uncertainty radius is used
# ---------------------------------------------------------------------------
def test_member4_uncertainty_radius_used(member4_origin_data):
    """filter_by_origin_uncertainty extracts uncertainty.centroid and radius_km."""
    df = pd.DataFrame(
        {
            "mmsi": [100, 200],
            "timestamp": pd.to_datetime(["2026-09-07T01:00:00Z", "2026-09-07T01:00:00Z"], utc=True),
            "latitude": [18.5050, 18.5200],
            "longitude": [72.5156, 72.5156],
        }
    )
    res = filter_by_origin_uncertainty(
        data=df,
        origin_data=member4_origin_data,
        buffer_km=0.0,
    )
    assert len(res) == 1
    assert res["mmsi"].iloc[0] == 100


# ---------------------------------------------------------------------------
# Test 17: Additional buffer expands the search region
# ---------------------------------------------------------------------------
def test_additional_buffer_expansion(member4_origin_data):
    """Adding buffer_km expands effective search radius R_search = radius_km + buffer_km."""
    df = pd.DataFrame(
        {
            "mmsi": [100],
            "timestamp": pd.to_datetime(["2026-09-07T01:00:00Z"], utc=True),
            "latitude": [18.5160],
            "longitude": [72.5156],
        }
    )
    res_no_buf = filter_by_origin_uncertainty(
        data=df,
        origin_data=member4_origin_data,
        buffer_km=0.0,
    )
    assert len(res_no_buf) == 0

    res_buf = filter_by_origin_uncertainty(
        data=df,
        origin_data=member4_origin_data,
        buffer_km=1.0,
    )
    assert len(res_buf) == 1
    assert res_buf["mmsi"].iloc[0] == 100
    assert np.isclose(res_buf["distance_km"].iloc[0], 1.768, atol=0.05)


# ---------------------------------------------------------------------------
# Test 18: Member 4 bounding-box filtering
# ---------------------------------------------------------------------------
def test_bounding_box_filtering():
    """filter_by_bounding_box correctly prunes points outside bounding box."""
    df = pd.DataFrame(
        {
            "mmsi": [1, 2, 3, 4],
            "timestamp": pd.to_datetime(["2026-09-07T01:00:00Z"] * 4, utc=True),
            "latitude": [18.5000, 18.4900, 18.4500, 18.5200],
            "longitude": [72.5100, 72.5200, 72.5150, 72.5150],
        }
    )
    res = filter_by_bounding_box(
        data=df,
        min_latitude=18.4869,
        max_latitude=18.5078,
        min_longitude=72.5070,
        max_longitude=72.5259,
    )
    assert set(res["mmsi"]) == {1, 2}


# ---------------------------------------------------------------------------
# Test 19: Anti-meridian (+/- 180 deg) behavior
# ---------------------------------------------------------------------------
def test_anti_meridian_handling():
    """Bounding box and distance calculations work seamlessly across the 180th meridian."""
    df = pd.DataFrame(
        {
            "mmsi": [10, 20, 30, 40],
            "timestamp": pd.to_datetime(["2026-09-07T01:00:00Z"] * 4, utc=True),
            "latitude": [0.0, 0.0, 0.0, 0.0],
            "longitude": [178.0, -178.0, 160.0, 0.0],
        }
    )
    res_bbox = filter_by_bounding_box(
        data=df,
        min_latitude=-10.0,
        max_latitude=10.0,
        min_longitude=175.0,
        max_longitude=-175.0,
    )
    assert set(res_bbox["mmsi"]) == {10, 20}

    df_radius = pd.DataFrame(
        {
            "mmsi": [1, 2],
            "timestamp": pd.to_datetime(["2026-09-07T01:00:00Z"] * 2, utc=True),
            "latitude": [0.0, 0.0],
            "longitude": [-179.9, 170.0],
        }
    )
    res_rad = filter_by_radius(
        data=df_radius,
        center_latitude=0.0,
        center_longitude=179.9,
        radius_km=30.0,
    )
    assert len(res_rad) == 1
    assert res_rad["mmsi"].iloc[0] == 1
    assert np.isclose(res_rad["distance_km"].iloc[0], 22.24, atol=0.2)


# ---------------------------------------------------------------------------
# Test 20: Invalid AIS coordinates
# ---------------------------------------------------------------------------
def test_invalid_ais_coordinates():
    """Invalid latitude (>90 or <-90), longitude (>180 or <-180), or NaN must raise ValueError."""
    # Latitude out of bounds
    df_bad_lat = pd.DataFrame(
        {
            "mmsi": [1],
            "timestamp": pd.to_datetime(["2026-09-07T01:00:00Z"], utc=True),
            "latitude": [95.0],
            "longitude": [72.0],
        }
    )
    with pytest.raises(ValueError, match="latitude coordinates outside"):
        filter_by_radius(df_bad_lat, center_latitude=18.0, center_longitude=72.0, radius_km=10.0)

    # Longitude out of bounds
    df_bad_lon = pd.DataFrame(
        {
            "mmsi": [1],
            "timestamp": pd.to_datetime(["2026-09-07T01:00:00Z"], utc=True),
            "latitude": [18.0],
            "longitude": [200.0],
        }
    )
    with pytest.raises(ValueError, match="longitude coordinates outside"):
        filter_by_radius(df_bad_lon, center_latitude=18.0, center_longitude=72.0, radius_km=10.0)

    # NaN coordinates
    df_nan = pd.DataFrame(
        {
            "mmsi": [1],
            "timestamp": pd.to_datetime(["2026-09-07T01:00:00Z"], utc=True),
            "latitude": [np.nan],
            "longitude": [72.0],
        }
    )
    with pytest.raises(ValueError, match="contains null, non-numeric, or non-finite"):
        filter_by_radius(df_nan, center_latitude=18.0, center_longitude=72.0, radius_km=10.0)


# ---------------------------------------------------------------------------
# Test 21: Realistic example using Member 4 conceptual values
# ---------------------------------------------------------------------------
def test_realistic_member4_workflow(member4_origin_data):
    """End-to-end realistic simulation utilizing the Member 4 handoff specification."""
    records = [
        # Vessel 1: Directly inside uncertainty radius (dist ~0.3 km)
        {
            "mmsi": 419000111,
            "timestamp": pd.to_datetime("2026-09-07T01:00:00Z"),
            "latitude": 18.5020,
            "longitude": 72.5165,
            "vessel_name": "COASTAL_CRUDE",
            "vessel_type": 80,
            "trajectory_segment_id": "419000111_seg_0",
            "segment_index": 0,
        },
        # Vessel 2: Inside bounding box and inside radius (dist ~0.8 km)
        {
            "mmsi": 419000222,
            "timestamp": pd.to_datetime("2026-09-07T01:02:00Z"),
            "latitude": 18.4950,
            "longitude": 72.5120,
            "vessel_name": "HARBOR_TUG",
            "vessel_type": 52,
            "trajectory_segment_id": "419000222_seg_0",
            "segment_index": 0,
        },
        # Vessel 3: Outside uncertainty radius (dist ~3.5 km)
        {
            "mmsi": 419000333,
            "timestamp": pd.to_datetime("2026-09-07T01:00:00Z"),
            "latitude": 18.5300,
            "longitude": 72.5156,
            "vessel_name": "CONTAINER_ONE",
            "vessel_type": 70,
            "trajectory_segment_id": "419000333_seg_0",
            "segment_index": 0,
        },
        # Vessel 4: Far away at Mumbai port anchorage (~35 km away)
        {
            "mmsi": 419000444,
            "timestamp": pd.to_datetime("2026-09-07T01:00:00Z"),
            "latitude": 18.8000,
            "longitude": 72.7500,
            "vessel_name": "PILOT_BOAT",
            "vessel_type": 50,
            "trajectory_segment_id": "419000444_seg_0",
            "segment_index": 0,
        },
    ]
    df = pd.DataFrame(records)

    config = SpatialFilterConfig(buffer_km=0.5)  # R_search = 1.1039 + 0.5 = 1.6039 km
    filter_result = filter_spatial(
        data=df,
        origin_data=member4_origin_data,
        config=config,
    )

    assert isinstance(filter_result, SpatialFilterResult)
    matched_df = filter_result.data
    report = filter_result.report

    assert len(matched_df) == 2
    assert filter_result.candidate_mmsis == {419000111, 419000222}
    assert filter_result.candidate_segment_ids == {"419000111_seg_0", "419000222_seg_0"}

    assert report.total_input_records == 4
    assert report.matched_records == 2
    assert report.unique_vessels_in == 4
    assert report.unique_vessels_matched == 2
    assert report.base_radius_km == 1.1039
    assert report.buffer_km == 0.5
    assert np.isclose(report.effective_radius_km, 1.6039, atol=1e-4)
    assert report.segments_matched == 2
    assert (matched_df["distance_km"] <= 1.6039).all()


# ---------------------------------------------------------------------------
# Test 22: Polymorphic TrajectoryResult input
# ---------------------------------------------------------------------------
def test_polymorphic_trajectory_result_input():
    """filter_spatial accepts TrajectoryResult instances seamlessly."""
    df = pd.DataFrame(
        {
            "mmsi": [999000111, 999000111, 888000222],
            "timestamp": pd.to_datetime(
                ["2026-09-07T01:00:00Z", "2026-09-07T01:10:00Z", "2026-09-07T01:00:00Z"],
                utc=True,
            ),
            "latitude": [18.5001, 18.5010, 25.0000],
            "longitude": [72.5156, 72.5160, 80.0000],
        }
    )
    traj_res = reconstruct_trajectories(df)
    filtered = filter_by_radius(
        data=traj_res,
        center_latitude=18.5001,
        center_longitude=72.5156,
        radius_km=2.0,
    )
    assert len(filtered) == 2
    assert set(filtered["mmsi"]) == {999000111}


# ---------------------------------------------------------------------------
# Test 23: Rejection of NaN / non-finite center latitude, longitude, radius, buffer
# ---------------------------------------------------------------------------
def test_nan_and_non_finite_inputs(sample_ais_df):
    """NaN and non-finite numbers must be explicitly rejected with ValueError."""
    # NaN center latitude
    with pytest.raises(ValueError, match="Center latitude must be a finite number"):
        filter_by_radius(sample_ais_df, center_latitude=np.nan, center_longitude=72.0, radius_km=5.0)

    # Infinite center latitude
    with pytest.raises(ValueError, match="Center latitude must be a finite number"):
        filter_by_radius(sample_ais_df, center_latitude=np.inf, center_longitude=72.0, radius_km=5.0)

    # NaN center longitude
    with pytest.raises(ValueError, match="Center longitude must be a finite number"):
        filter_by_radius(sample_ais_df, center_latitude=18.0, center_longitude=np.nan, radius_km=5.0)

    # Infinite center longitude
    with pytest.raises(ValueError, match="Center longitude must be a finite number"):
        filter_by_radius(sample_ais_df, center_latitude=18.0, center_longitude=-np.inf, radius_km=5.0)

    # NaN radius_km in filter_by_radius
    with pytest.raises(ValueError, match="radius_km must be a finite non-negative number"):
        filter_by_radius(sample_ais_df, center_latitude=18.0, center_longitude=72.0, radius_km=np.nan)

    # Infinite radius_km in filter_by_radius
    with pytest.raises(ValueError, match="radius_km must be a finite non-negative number"):
        filter_by_radius(sample_ais_df, center_latitude=18.0, center_longitude=72.0, radius_km=np.inf)

    # NaN buffer_km in filter_by_radius
    with pytest.raises(ValueError, match="buffer_km must be a finite non-negative number"):
        filter_by_radius(
            sample_ais_df,
            center_latitude=18.0,
            center_longitude=72.0,
            radius_km=5.0,
            buffer_km=np.nan,
        )

    # NaN in SpatialFilterConfig
    with pytest.raises(ValueError, match="radius_km must be a finite non-negative number"):
        SpatialFilterConfig(radius_km=np.nan)

    with pytest.raises(ValueError, match="buffer_km must be a finite non-negative number"):
        SpatialFilterConfig(buffer_km=np.nan)

    with pytest.raises(ValueError, match="min_latitude must be a finite number"):
        SpatialFilterConfig(min_latitude=np.nan)

    with pytest.raises(ValueError, match="min_longitude must be a finite number"):
        SpatialFilterConfig(min_longitude=np.nan)


# ---------------------------------------------------------------------------
# Test 24: Preservation of valid zero coordinates (0.0 lat, 0.0 lon)
# ---------------------------------------------------------------------------
def test_zero_coordinates_preserved():
    """A valid coordinate of 0.0 must be preserved and not treated as falsy/missing."""
    # Vessel right at (0.0, 0.0) in the Gulf of Guinea
    df = pd.DataFrame(
        {
            "mmsi": [555000111],
            "timestamp": pd.to_datetime(["2026-09-07T01:00:00Z"], utc=True),
            "latitude": [0.0],
            "longitude": [0.0],
        }
    )

    # 1. Search center with latitude = 0.0
    origin_data_zero_lat = {
        "origin": {"latitude": 0.0, "longitude": 10.0},
        "uncertainty": {"centroid_latitude": 0.0, "centroid_longitude": 10.0, "radius_km": 50.0},
    }
    res_lat = filter_spatial(df, origin_data=origin_data_zero_lat)
    assert res_lat.report.center_latitude == 0.0
    assert not np.isnan(res_lat.report.center_latitude)

    # 2. Search center with longitude = 0.0
    origin_data_zero_lon = {
        "origin": {"latitude": 5.0, "longitude": 0.0},
        "uncertainty": {"centroid_latitude": 5.0, "centroid_longitude": 0.0, "radius_km": 50.0},
    }
    res_lon = filter_spatial(df, origin_data=origin_data_zero_lon)
    assert res_lon.report.center_longitude == 0.0
    assert not np.isnan(res_lon.report.center_longitude)

    # 3. Direct origin uncertainty filter at (0.0, 0.0)
    origin_data_zero_both = {
        "origin": {"latitude": 0.0, "longitude": 0.0},
        "uncertainty": {"centroid_latitude": 0.0, "centroid_longitude": 0.0, "radius_km": 5.0},
    }
    res_both = filter_by_origin_uncertainty(df, origin_data=origin_data_zero_both)
    assert len(res_both) == 1
    assert res_both["mmsi"].iloc[0] == 555000111
    assert np.isclose(res_both["distance_km"].iloc[0], 0.0, atol=1e-6)


# ---------------------------------------------------------------------------
# Test 25: Member 4 bounding-box metadata does not exclude points within Haversine uncertainty radius
# ---------------------------------------------------------------------------
def test_member4_bounding_box_metadata_does_not_exclude_points_in_radius():
    """Member 4's bounding-box metadata must NOT exclude any point within the Haversine radius."""
    # A point slightly diagonally offset from center, within radius 2.0 km
    center_lat = 18.5000
    center_lon = 72.5000
    radius = 2.0  # 2 km

    # Distance ~1.5 km northeast
    # dlat = 0.01 deg (~1.11 km), dlon = 0.01 deg (~0.01 * 111 * cos(18.5) ~ 1.05 km)
    # dist = sqrt(1.11^2 + 1.05^2) ~ 1.53 km (< 2.0 km)
    pt_lat = 18.5100
    pt_lon = 72.5100

    df = pd.DataFrame(
        {
            "mmsi": [777],
            "timestamp": pd.to_datetime(["2026-09-07T01:00:00Z"], utc=True),
            "latitude": [pt_lat],
            "longitude": [pt_lon],
        }
    )

    # Suppose Member 4's unbuffered/narrow bounding box metadata in 'uncertainty'
    # did NOT encompass pt_lat (e.g. max_latitude was set to 18.5050)
    origin_data_narrow_box = {
        "origin": {"latitude": center_lat, "longitude": center_lon},
        "uncertainty": {
            "centroid_latitude": center_lat,
            "centroid_longitude": center_lon,
            "radius_km": radius,
            # Narrow bounding box metadata:
            "min_latitude": 18.4950,
            "max_latitude": 18.5050,  # Below pt_lat!
            "min_longitude": 72.4950,
            "max_longitude": 72.5050,  # Below pt_lon!
        },
    }

    # The authoritative spatial filter must retain this point based on Haversine distance!
    res = filter_by_origin_uncertainty(df, origin_data=origin_data_narrow_box)
    assert len(res) == 1
    assert res["mmsi"].iloc[0] == 777
    assert res["distance_km"].iloc[0] < radius
