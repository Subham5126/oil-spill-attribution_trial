"""Tests for AIS Preprocessing and Kinematic Cleaning (AIS-03).

Covers:
- Vectorized Haversine distance calculation and boundary conditions
- Inter-ping kinematics derivation (time delta, distance, derived speed)
- Strict per-MMSI movement isolation (no cross-vessel calculation)
- Speed anomaly and position jump detection
- Contextual (0,0) jump classification vs legitimate near-(0,0) transit
- Reported SOG cross-validation (inconsistency never causes deletion)
- Filtering vs flagging modes (filter_anomalies=True / False)
- CleaningReport audit metrics
- Edge cases (empty DataFrame, single row, missing SOG, NaN kinematics)
- Real NOAA AIS dataset smoke test
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from ais.data_loader import load_ais_csv
from ais.preprocessing import (
    CleaningConfig,
    CleaningReport,
    clean_ais_data,
    compute_inter_ping_kinematics,
    haversine_distance_nm,
)


# ===========================================================================
# 1. Haversine Distance Tests
# ===========================================================================

def test_haversine_identical_coordinates():
    """Identical coordinates should yield exactly or approximately 0 NM."""
    dist = haversine_distance_nm(0.0, 0.0, 0.0, 0.0)
    assert pytest.approx(dist, abs=1e-5) == 0.0

    dist_coords = haversine_distance_nm(40.7128, -74.0060, 40.7128, -74.0060)
    assert pytest.approx(dist_coords, abs=1e-5) == 0.0


def test_haversine_equator_one_degree_longitude():
    """1 degree longitude at the equator should be approximately 60 NM."""
    dist = haversine_distance_nm(0.0, 0.0, 0.0, 1.0)
    assert 59.5 < dist < 60.5
    assert pytest.approx(dist, rel=1e-2) == 60.04


def test_haversine_known_nonzero_coordinate_pair():
    """Test known distance between New York (40.7128, -74.0060) and London (51.5074, -0.1278)."""
    dist = haversine_distance_nm(40.7128, -74.0060, 51.5074, -0.1278)
    # Great-circle distance NYC to London is ~2999 - 3005 NM
    assert 2990.0 < dist < 3010.0


def test_haversine_nan_inputs():
    """NaN in any coordinate should return NaN without raising exceptions."""
    assert np.isnan(haversine_distance_nm(np.nan, 0.0, 10.0, 20.0))
    assert np.isnan(haversine_distance_nm(10.0, np.nan, 10.0, 20.0))
    assert np.isnan(haversine_distance_nm(10.0, 20.0, np.nan, 20.0))
    assert np.isnan(haversine_distance_nm(10.0, 20.0, 10.0, np.nan))


def test_haversine_vectorized():
    """Vectorized calculation on NumPy arrays."""
    lats1 = np.array([0.0, 10.0, np.nan])
    lons1 = np.array([0.0, 20.0, 30.0])
    lats2 = np.array([0.0, 10.0, 40.0])
    lons2 = np.array([1.0, 20.0, 50.0])

    dists = haversine_distance_nm(lats1, lons1, lats2, lons2)
    assert len(dists) == 3
    assert pytest.approx(dists[0], rel=1e-2) == 60.04
    assert pytest.approx(dists[1], abs=1e-5) == 0.0
    assert np.isnan(dists[2])


# ===========================================================================
# 2. Kinematics Derivation Tests
# ===========================================================================

def test_kinematics_derivation_single_vessel():
    """Test time delta, distance, and derived speed on a normal transit."""
    # Vessel travels 1 degree north in 6 hours = ~60 NM / 6h = ~10 knots
    df = pd.DataFrame({
        "mmsi": [200000001, 200000001],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00", "2025-01-01 06:00:00"], utc=True),
        "latitude": [0.0, 1.0],
        "longitude": [0.0, 0.0],
    })

    res = compute_inter_ping_kinematics(df)

    # First ping
    assert pd.isna(res.loc[0, "previous_timestamp"])
    assert np.isnan(res.loc[0, "time_delta_s"])
    assert np.isnan(res.loc[0, "distance_nm"])
    assert np.isnan(res.loc[0, "derived_speed_knots"])

    # Second ping
    assert res.loc[1, "previous_timestamp"] == pd.Timestamp("2025-01-01 00:00:00", tz="UTC")
    assert res.loc[1, "time_delta_s"] == 6.0 * 3600.0
    assert pytest.approx(res.loc[1, "distance_nm"], rel=1e-2) == 60.04
    assert pytest.approx(res.loc[1, "derived_speed_knots"], rel=1e-2) == 10.01


def test_kinematics_strict_per_mmsi_isolation():
    """Verify that inter-ping kinematics are NEVER computed across different vessels."""
    df = pd.DataFrame({
        "mmsi": [200000001, 200000001, 300000002, 300000002],
        "timestamp": pd.to_datetime([
            "2025-01-01 00:00:00",
            "2025-01-01 01:00:00",
            "2025-01-01 02:00:00",
            "2025-01-01 03:00:00",
        ], utc=True),
        "latitude": [10.0, 10.1, 50.0, 50.1],
        "longitude": [-20.0, -20.0, 0.0, 0.0],
    })

    res = compute_inter_ping_kinematics(df)

    # First ping of vessel 1
    assert pd.isna(res.loc[0, "previous_timestamp"])
    assert np.isnan(res.loc[0, "derived_speed_knots"])

    # Second ping of vessel 1 (valid movement)
    assert res.loc[1, "previous_timestamp"] == res.loc[0, "timestamp"]
    assert res.loc[1, "derived_speed_knots"] > 0

    # First ping of vessel 2 MUST be NaN (never computed against vessel 1)
    assert pd.isna(res.loc[2, "previous_timestamp"])
    assert np.isnan(res.loc[2, "time_delta_s"])
    assert np.isnan(res.loc[2, "distance_nm"])
    assert np.isnan(res.loc[2, "derived_speed_knots"])

    # Second ping of vessel 2 (valid movement)
    assert res.loc[3, "previous_timestamp"] == res.loc[2, "timestamp"]
    assert res.loc[3, "derived_speed_knots"] > 0


def test_kinematics_does_not_mutate_input():
    """Verify compute_inter_ping_kinematics does not mutate caller's DataFrame."""
    df = pd.DataFrame({
        "mmsi": [200000001, 200000001],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00", "2025-01-01 01:00:00"], utc=True),
        "latitude": [10.0, 10.1],
        "longitude": [-20.0, -20.0],
    })
    orig_cols = list(df.columns)
    _ = compute_inter_ping_kinematics(df)
    assert list(df.columns) == orig_cols


# ===========================================================================
# 3. Speed Anomaly & Position Jump Tests
# ===========================================================================

def test_speed_anomaly_and_position_jump_flagging():
    """Synthetic impossible jump (teleportation) should be flagged."""
    # Vessel jumps 5 degrees (~300 NM) in 5 minutes (derived speed ~3600 knots)
    df = pd.DataFrame({
        "mmsi": [200000001, 200000001],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00", "2025-01-01 00:05:00"], utc=True),
        "latitude": [25.0, 30.0],
        "longitude": [-80.0, -80.0],
    })

    cleaned_df, report = clean_ais_data(df, CleaningConfig(filter_anomalies=False))

    assert len(cleaned_df) == 2
    assert cleaned_df.loc[0, "is_speed_anomaly"] is False or cleaned_df.loc[0, "is_speed_anomaly"] == 0
    assert cleaned_df.loc[1, "is_speed_anomaly"] is True or cleaned_df.loc[1, "is_speed_anomaly"] == 1
    assert cleaned_df.loc[1, "is_position_jump"] is True or cleaned_df.loc[1, "is_position_jump"] == 1
    assert report.speed_anomalies_detected == 1
    assert report.position_jumps_detected == 1
    assert report.clean_records_retained == 2


def test_position_jump_legitimate_far_movement_not_flagged():
    """Legitimate long-distance transit with sufficient elapsed time is NOT flagged."""
    # Vessel travels 60 NM over 6 hours = 10 knots (normal cargo speed)
    df = pd.DataFrame({
        "mmsi": [200000001, 200000001],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00", "2025-01-01 06:00:00"], utc=True),
        "latitude": [25.0, 26.0],
        "longitude": [-80.0, -80.0],
    })

    cleaned_df, report = clean_ais_data(df, CleaningConfig(max_speed_knots=60.0))

    assert len(cleaned_df) == 2
    assert cleaned_df["is_speed_anomaly"].sum() == 0
    assert cleaned_df["is_position_jump"].sum() == 0
    assert report.speed_anomalies_detected == 0
    assert report.clean_records_retained == 2


def test_isolated_spike_filtering_preserves_valid_neighbor():
    """An isolated position spike p1 -> p2 (spike) -> p3 should remove ONLY p2, preserving p3."""
    # p1 at (25.0, -80.0), p2 jumped to (35.0, -80.0), p3 back at (25.02, -80.0)
    df = pd.DataFrame({
        "mmsi": [200000001, 200000001, 200000001],
        "timestamp": pd.to_datetime([
            "2025-01-01 00:00:00",
            "2025-01-01 00:10:00",
            "2025-01-01 00:20:00",
        ], utc=True),
        "latitude": [25.0, 35.0, 25.02],
        "longitude": [-80.0, -80.0, -80.0],
    })

    cleaned_df, report = clean_ais_data(df, CleaningConfig(filter_anomalies=True))

    # Exactly p2 should be removed, retaining p1 and p3
    assert len(cleaned_df) == 2
    assert report.clean_records_retained == 2
    assert report.speed_anomalies_detected == 2  # p1->p2 is anomaly, p2->p3 is anomaly

    # The retained coordinates should be p1 and p3
    assert list(cleaned_df["latitude"]) == [25.0, 25.02]
    # On the cleaned trajectory, derived speed between p1 and p3 is plausible (~3.6 knots)
    assert cleaned_df.loc[1, "derived_speed_knots"] < 10.0


# ===========================================================================
# 4. Contextual (0, 0) Tests
# ===========================================================================

def test_legitimate_continuous_sequence_near_zero_is_preserved():
    """Vessels operating legitimately near Null Island (Gulf of Guinea) must NOT be deleted."""
    # Vessel transits near (0, 0) at ~10 knots
    df = pd.DataFrame({
        "mmsi": [200000001, 200000001, 200000001],
        "timestamp": pd.to_datetime([
            "2025-01-01 00:00:00",
            "2025-01-01 00:10:00",
            "2025-01-01 00:20:00",
        ], utc=True),
        "latitude": [0.02, 0.0, -0.02],
        "longitude": [0.0, 0.0, 0.0],
        "is_suspicious_zero": [False, True, False],
    })

    cleaned_df, report = clean_ais_data(df, CleaningConfig(filter_suspicious_zero_jumps=True))

    assert len(cleaned_df) == 3
    assert report.clean_records_retained == 3
    assert report.suspicious_zero_jumps_filtered == 0
    # Center ping at (0,0) was NOT a jump
    assert cleaned_df.loc[1, "is_suspicious_zero_jump"] is False or cleaned_df.loc[1, "is_suspicious_zero_jump"] == 0


def test_anomalous_zero_jump_is_flagged_and_filtered():
    """A vessel in US waters jumping to (0,0) and back is detected and removed."""
    df = pd.DataFrame({
        "mmsi": [200000001, 200000001, 200000001],
        "timestamp": pd.to_datetime([
            "2025-01-01 00:00:00",
            "2025-01-01 00:05:00",
            "2025-01-01 00:10:00",
        ], utc=True),
        "latitude": [28.0, 0.0, 28.01],
        "longitude": [-89.0, 0.0, -89.01],
        "is_suspicious_zero": [False, True, False],
    })

    # In flagging mode: row is retained with is_suspicious_zero_jump=True
    flagged_df, report_flag = clean_ais_data(df, CleaningConfig(filter_anomalies=False))
    assert len(flagged_df) == 3
    assert flagged_df.loc[1, "is_suspicious_zero_jump"] is True or flagged_df.loc[1, "is_suspicious_zero_jump"] == 1

    # In filtering mode: the (0,0) jump row is removed
    filtered_df, report_filt = clean_ais_data(df, CleaningConfig(filter_anomalies=True, filter_suspicious_zero_jumps=True))
    assert len(filtered_df) == 2
    assert report_filt.clean_records_retained == 2
    assert report_filt.suspicious_zero_jumps_filtered == 1
    assert 0.0 not in list(filtered_df["latitude"])


# ===========================================================================
# 5. Reported SOG Cross-Validation Tests
# ===========================================================================

def test_sog_consistency_validation():
    """Reported SOG is compared against derived speed; inconsistency never deletes row."""
    df = pd.DataFrame({
        "mmsi": [200000001, 200000001, 200000001],
        "timestamp": pd.to_datetime([
            "2025-01-01 00:00:00",
            "2025-01-01 01:00:00",
            "2025-01-01 02:00:00",
        ], utc=True),
        "latitude": [20.0, 20.1, 20.2],
        "longitude": [0.0, 0.0, 0.0],
        # Ping 1: derived speed ~6 kn, SOG=6.2 kn (consistent)
        # Ping 2: derived speed ~6 kn, SOG=45.0 kn (clearly inconsistent, diff=39 kn > 20 kn)
        "sog": [6.0, 6.2, 45.0],
    })

    cleaned_df, report = clean_ais_data(df, CleaningConfig(filter_anomalies=True))

    # All rows are retained (SOG inconsistency alone NEVER causes deletion)
    assert len(cleaned_df) == 3
    assert report.clean_records_retained == 3

    # Ping 1 is consistent
    assert cleaned_df.loc[1, "is_sog_inconsistent"] is False or cleaned_df.loc[1, "is_sog_inconsistent"] == 0
    # Ping 2 is inconsistent
    assert cleaned_df.loc[2, "is_sog_inconsistent"] is True or cleaned_df.loc[2, "is_sog_inconsistent"] == 1


def test_missing_sog_not_flagged_inconsistent():
    """Missing or NaN SOG should not be flagged as inconsistent."""
    df = pd.DataFrame({
        "mmsi": [200000001, 200000001],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00", "2025-01-01 01:00:00"], utc=True),
        "latitude": [20.0, 20.1],
        "longitude": [0.0, 0.0],
        "sog": [np.nan, np.nan],
    })

    cleaned_df, _ = clean_ais_data(df)
    assert cleaned_df["is_sog_inconsistent"].sum() == 0


# ===========================================================================
# 6. CleaningConfig Validation Tests
# ===========================================================================

def test_cleaning_config_validation():
    """CleaningConfig rejects negative or invalid thresholds."""
    with pytest.raises(ValueError, match="max_speed_knots must be positive"):
        CleaningConfig(max_speed_knots=-10.0)

    with pytest.raises(ValueError, match="min_time_delta_seconds must be non-negative"):
        CleaningConfig(min_time_delta_seconds=-1.0)

    with pytest.raises(ValueError, match="max_acceleration_knots_per_s must be positive"):
        CleaningConfig(max_acceleration_knots_per_s=-5.0)

    with pytest.raises(ValueError, match="sog_inconsistency_threshold_knots must be positive"):
        CleaningConfig(sog_inconsistency_threshold_knots=-1.0)


# ===========================================================================
# 7. Edge Cases Tests
# ===========================================================================

def test_empty_dataframe():
    """Empty DataFrame input should return empty DataFrame with report."""
    empty_df = pd.DataFrame(columns=["mmsi", "timestamp", "latitude", "longitude"])
    cleaned_df, report = clean_ais_data(empty_df)

    assert len(cleaned_df) == 0
    assert report.total_input_records == 0
    assert report.clean_records_retained == 0
    assert report.unique_vessels == 0


def test_single_row_input():
    """Single row input (one ping) should return successfully with NaNs for kinematics."""
    df = pd.DataFrame({
        "mmsi": [200000001],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00"], utc=True),
        "latitude": [25.0],
        "longitude": [-80.0],
    })
    cleaned_df, report = clean_ais_data(df)

    assert len(cleaned_df) == 1
    assert report.total_input_records == 1
    assert report.clean_records_retained == 1
    assert report.unique_vessels == 1
    assert np.isnan(cleaned_df.loc[0, "derived_speed_knots"])
    assert cleaned_df.loc[0, "is_speed_anomaly"] is False or cleaned_df.loc[0, "is_speed_anomaly"] == 0


def test_missing_required_column_raises_error():
    """Missing required canonical column should raise ValueError."""
    df = pd.DataFrame({
        "mmsi": [200000001],
        "timestamp": pd.to_datetime(["2025-01-01 00:00:00"], utc=True),
        "latitude": [25.0],
        # longitude missing
    })
    with pytest.raises(ValueError, match="missing required column"):
        clean_ais_data(df)


def test_unsorted_input_ordered_deterministically():
    """Unsorted input should be handled in chronological order per vessel."""
    df = pd.DataFrame({
        "mmsi": [200000001, 200000001],
        "timestamp": pd.to_datetime(["2025-01-01 02:00:00", "2025-01-01 01:00:00"], utc=True),
        "latitude": [25.1, 25.0],
        "longitude": [-80.0, -80.0],
    })
    cleaned_df, _ = clean_ais_data(df)
    assert cleaned_df.loc[0, "timestamp"] < cleaned_df.loc[1, "timestamp"]


# ===========================================================================
# 8. Real NOAA AIS Dataset Smoke Test
# ===========================================================================

def test_real_noaa_dataset_cleaning_smoke_test():
    """Smoke test running AIS-03 cleaning on actual NOAA 2025 dataset preview."""
    raw_path = Path("data/raw/ais/noaa/ais-2025-01-08.tgz")
    if not raw_path.exists():
        pytest.skip("Local NOAA raw file not present (as expected in CI/clean repos)")

    # Load 50 rows via AIS-02 loader
    df_noaa = load_ais_csv(raw_path, nrows=50)
    assert isinstance(df_noaa, pd.DataFrame)
    assert len(df_noaa) == 50

    # Clean through AIS-03
    cleaned_df, report = clean_ais_data(df_noaa, CleaningConfig(filter_anomalies=True))

    assert isinstance(cleaned_df, pd.DataFrame)
    assert isinstance(report, CleaningReport)
    assert report.total_input_records == 50
    assert report.clean_records_retained > 0
    assert report.unique_vessels > 0
    assert "derived_speed_knots" in cleaned_df.columns
    assert "is_speed_anomaly" in cleaned_df.columns
    assert "is_position_jump" in cleaned_df.columns
    assert "is_sog_inconsistent" in cleaned_df.columns
    assert "is_suspicious_zero_jump" in cleaned_df.columns
