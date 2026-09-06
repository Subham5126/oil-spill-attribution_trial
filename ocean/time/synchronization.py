"""Time synchronization and UTC normalization for the Ocean + Drift system."""

from typing import Any
import pandas as pd
import xarray as xr


class TimeSynchronizationError(ValueError):
    """Raised when timestamps are invalid, non-monotonic, or missing timezone information."""
    pass


def normalize_timestamp(timestamp: Any, assume_naive_utc: bool = False) -> pd.Timestamp:
    """
    Normalize a single timestamp to a timezone-aware UTC pandas Timestamp.
    
    Args:
        timestamp: The timestamp to normalize.
        assume_naive_utc: Whether to assume naive timestamps are UTC.
        
    Returns:
        A timezone-aware UTC pandas Timestamp.
        
    Raises:
        TimeSynchronizationError: For invalid/null timestamps, or naive timestamps
            when assume_naive_utc is False.
    """
    if timestamp is None or pd.isna(timestamp):
        raise TimeSynchronizationError("Timestamp cannot be None or NaT.")
    
    try:
        ts = pd.Timestamp(timestamp)
    except Exception as e:
        raise TimeSynchronizationError(f"Invalid timestamp format: {timestamp}") from e

    if pd.isna(ts):
        raise TimeSynchronizationError("Timestamp cannot be NaT.")

    if ts.tz is None:
        if not assume_naive_utc:
            raise TimeSynchronizationError(
                "Timezone information is required unless assume_naive_utc=True."
            )
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
        
    return ts


def normalize_timestamps(timestamps: Any, assume_naive_utc: bool = False) -> pd.DatetimeIndex:
    """
    Normalize a sequence of timestamps to UTC.
    
    Args:
        timestamps: Sequence of timestamps to normalize.
        assume_naive_utc: Whether to assume naive timestamps are UTC.
        
    Returns:
        A timezone-aware UTC pandas DatetimeIndex.
        
    Raises:
        TimeSynchronizationError: For empty sequences, invalid/null timestamps,
            or naive timestamps when assume_naive_utc is False.
    """
    if timestamps is None:
        raise TimeSynchronizationError("Timestamps sequence cannot be None.")
        
    # Check if list-like but empty before passing to DatetimeIndex to catch earlier
    if hasattr(timestamps, "__len__") and len(timestamps) == 0:
        raise TimeSynchronizationError("Timestamps sequence cannot be empty.")
            
    try:
        dt_index = pd.DatetimeIndex(timestamps)
        
        if len(dt_index) == 0:
            raise TimeSynchronizationError("Timestamps sequence cannot be empty.")
            
        if dt_index.hasnans:
            raise TimeSynchronizationError("Timestamps sequence cannot contain NaT.")

        if dt_index.tz is None:
            if not assume_naive_utc:
                raise TimeSynchronizationError(
                    "Timezone information is required unless assume_naive_utc=True."
                )
            dt_index = dt_index.tz_localize("UTC")
        else:
            dt_index = dt_index.tz_convert("UTC")
            
        return dt_index
        
    except TimeSynchronizationError:
        raise
    except Exception:
        # Fallback to item-by-item normalization to handle mixed timezones
        try:
            normalized_list = [normalize_timestamp(t, assume_naive_utc) for t in timestamps]
            return pd.DatetimeIndex(normalized_list)
        except Exception as e:
            if isinstance(e, TimeSynchronizationError):
                raise
            raise TimeSynchronizationError("Invalid timestamps sequence.") from e


def validate_time_sequence(timestamps: Any) -> pd.DatetimeIndex:
    """
    Validate that a sequence of timestamps is strictly monotonically increasing.
    
    Args:
        timestamps: Sequence of timestamps (preferably already normalized).
        
    Returns:
        The validated DatetimeIndex.
        
    Raises:
        TimeSynchronizationError: If not strictly monotonic increasing.
    """
    try:
        dt_index = pd.DatetimeIndex(timestamps)
    except Exception as e:
        raise TimeSynchronizationError("Invalid timestamps sequence.") from e
        
    if not dt_index.is_monotonic_increasing:
        raise TimeSynchronizationError("Timestamps must be monotonically increasing.")
        
    if not dt_index.is_unique:
        raise TimeSynchronizationError("Timestamps must be strictly monotonically increasing (no duplicates allowed).")
        
    return dt_index


def normalize_dataset_time(dataset: xr.Dataset, assume_naive_utc: bool = True) -> xr.Dataset:
    """
    Normalize the time coordinate of an xarray Dataset to UTC.
    
    Args:
        dataset: The xarray Dataset.
        assume_naive_utc: Whether to assume naive timestamps in the time coordinate are UTC.
            Defaults to True for Datasets since environmental standard coordinates often drop tz.
            
    Returns:
        A new Dataset with normalized UTC time coordinate.
        
    Raises:
        TimeSynchronizationError: If the 'time' coordinate is missing or invalid.
    """
    if "time" not in dataset.coords:
        raise TimeSynchronizationError("Dataset is missing required 'time' coordinate.")
        
    time_values = dataset["time"].values
    
    try:
        normalized_time = normalize_timestamps(time_values, assume_naive_utc=assume_naive_utc)
    except TimeSynchronizationError as e:
        raise TimeSynchronizationError(f"Invalid dataset time coordinate: {e}") from e
        
    # Convert to tz-naive UTC datetime64[ns] for xarray compatibility
    utc_naive = normalized_time.tz_localize(None)
    
    result = dataset.copy()
    result = result.assign_coords(time=utc_naive)
    return result
