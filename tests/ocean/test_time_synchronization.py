import pytest
import pandas as pd
import numpy as np
import xarray as xr
from pathlib import Path

from ocean.time import (
    TimeSynchronizationError,
    normalize_timestamp,
    normalize_timestamps,
    validate_time_sequence,
    normalize_dataset_time,
)
from ocean.interpolation import interpolate_currents, interpolate_wind
from ocean.currents import load_currents
from ocean.wind import load_wind

def test_utc_aware_timestamp_remains_same():
    ts = pd.Timestamp("2025-01-01 03:30:00+00:00")
    norm = normalize_timestamp(ts)
    assert norm == ts
    assert norm.tz.tzname(None) == "UTC"

def test_ist_timestamp_converts_correctly():
    ts_ist = pd.Timestamp("2025-01-01 09:00:00+05:30")
    norm = normalize_timestamp(ts_ist)
    assert norm == pd.Timestamp("2025-01-01 03:30:00+00:00")
    assert norm.tz.tzname(None) == "UTC"

def test_new_york_timestamp_converts_correctly():
    ts_ny = pd.Timestamp("2025-01-01 09:00:00", tz="America/New_York")
    norm = normalize_timestamp(ts_ny)
    assert norm == pd.Timestamp("2025-01-01 14:00:00+00:00")
    assert norm.tz.tzname(None) == "UTC"

def test_same_instant_different_timezones():
    ts1 = pd.Timestamp("2025-01-01 03:30:00+00:00")
    ts2 = pd.Timestamp("2025-01-01 09:00:00+05:30")
    assert normalize_timestamp(ts1) == normalize_timestamp(ts2)

def test_naive_timestamp_rejected_by_default():
    ts_naive = pd.Timestamp("2025-01-01 09:00:00")
    with pytest.raises(TimeSynchronizationError, match="Timezone information is required"):
        normalize_timestamp(ts_naive)

def test_naive_timestamp_accepted_when_declared_utc():
    ts_naive = pd.Timestamp("2025-01-01 09:00:00")
    norm = normalize_timestamp(ts_naive, assume_naive_utc=True)
    assert norm == pd.Timestamp("2025-01-01 09:00:00+00:00")

def test_invalid_timestamp_raises_error():
    with pytest.raises(TimeSynchronizationError, match="Invalid timestamp format"):
        normalize_timestamp("not a timestamp")

def test_none_timestamp_raises_error():
    with pytest.raises(TimeSynchronizationError, match="Timestamp cannot be None or NaT"):
        normalize_timestamp(None)

def test_nat_timestamp_raises_error():
    with pytest.raises(TimeSynchronizationError, match="Timestamp cannot be None or NaT"):
        normalize_timestamp(pd.NaT)

def test_empty_timestamp_sequence_raises_error():
    with pytest.raises(TimeSynchronizationError, match="Timestamps sequence cannot be empty"):
        normalize_timestamps([])

def test_mixed_timezone_aware_timestamps():
    seq = [
        pd.Timestamp("2025-01-01 03:30:00+00:00"),
        pd.Timestamp("2025-01-01 10:00:00+05:30")
    ]
    norm = normalize_timestamps(seq)
    assert norm[0] == pd.Timestamp("2025-01-01 03:30:00+00:00")
    assert norm[1] == pd.Timestamp("2025-01-01 04:30:00+00:00")
    assert norm.tz.tzname(None) == "UTC"

def test_monotonically_increasing_timestamps_accepted():
    seq = pd.DatetimeIndex(["2025-01-01 00:00:00+00:00", "2025-01-01 01:00:00+00:00"])
    valid = validate_time_sequence(seq)
    assert valid.equals(seq)

def test_non_monotonic_timestamps_rejected():
    seq = pd.DatetimeIndex(["2025-01-01 01:00:00+00:00", "2025-01-01 00:00:00+00:00"])
    with pytest.raises(TimeSynchronizationError, match="monotonically increasing"):
        validate_time_sequence(seq)

def test_duplicate_timestamps_rejected():
    seq = pd.DatetimeIndex(["2025-01-01 00:00:00+00:00", "2025-01-01 00:00:00+00:00"])
    with pytest.raises(TimeSynchronizationError, match="strictly monotonically increasing"):
        validate_time_sequence(seq)

def test_irregular_but_monotonic_timestamps_accepted():
    seq = pd.DatetimeIndex(["2025-01-01 00:00:00+00:00", "2025-01-01 00:17:00+00:00", "2025-01-01 01:03:00+00:00"])
    valid = validate_time_sequence(seq)
    assert valid.equals(seq)

def test_environmental_data_preserved_during_dataset_normalization():
    # Create simple dataset
    time = pd.date_range("2025-01-01", periods=2, tz="UTC")
    ds = xr.Dataset(
        {"uo": (("time", "lat", "lon"), np.array([[[1.0]], [[2.0]]]))},
        coords={"time": time, "lat": [10.0], "lon": [70.0]}
    )
    norm_ds = normalize_dataset_time(ds)
    # Check data is not zeroed or modified
    np.testing.assert_array_equal(norm_ds["uo"].values, ds["uo"].values)

def test_missing_time_coordinate_raises_error():
    ds = xr.Dataset({"uo": (("lat", "lon"), np.array([[1.0]]))}, coords={"lat": [10.0], "lon": [70.0]})
    with pytest.raises(TimeSynchronizationError, match="missing required 'time' coordinate"):
        normalize_dataset_time(ds)

# Integration with OCEAN-04
@pytest.mark.parametrize(
    ("path", "loader", "interpolator"),
    [
        (
            Path("data/sample/copernicus/current_test.nc"),
            load_currents,
            interpolate_currents,
        ),
        (
            Path("data/sample/era5/wind_test.nc"),
            load_wind,
            interpolate_wind,
        ),
    ],
)
def test_ocean04_accepts_normalized_utc_and_produces_equivalent_results(
    path: Path, loader, interpolator
):
    if not path.is_file():
        pytest.skip(f"Sample NetCDF is not available: {path}")

    dataset = loader(path)
    longitude = float(dataset["longitude"].values.mean())
    latitude = float(dataset["latitude"].values.mean())
    
    # Take a time from the middle of the dataset
    ds_time = pd.Timestamp(dataset["time"].values[len(dataset["time"]) // 2])
    
    # ds_time is naive but represents UTC in standard OCEAN-02/03 datasets
    ts_utc = ds_time.tz_localize("UTC")
    ts_ist = ts_utc.tz_convert("Asia/Kolkata")
    
    norm_utc = normalize_timestamp(ts_utc)
    norm_ist = normalize_timestamp(ts_ist)
    
    # Strip tz for xarray interp (as it expects datetime64[ns])
    time_arg_utc = norm_utc.tz_localize(None)
    time_arg_ist = norm_ist.tz_localize(None)
    
    u_utc, v_utc = interpolator(dataset, longitude, latitude, time_arg_utc)
    u_ist, v_ist = interpolator(dataset, longitude, latitude, time_arg_ist)
    
    assert np.isclose(u_utc, u_ist)
    assert np.isclose(v_utc, v_ist)

