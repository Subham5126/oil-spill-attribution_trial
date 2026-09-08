"""AIS Temporal Filtering Implementation.

Provides UTC timezone-aware temporal filtering of AIS observations and vessel
trajectories against Member 4 estimated spill origin timestamps and configurable
temporal uncertainty windows.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Union

import numpy as np
import pandas as pd

from ais.filtering.config import TemporalFilterConfig


@dataclass(frozen=True)
class TemporalFilterReport:
    """Audit metrics and summary statistics for AIS temporal filtering.

    Attributes:
        total_input_records: Total AIS observation rows passed to the filter.
        matched_records: Number of observation records within the temporal window.
        unique_vessels_in: Distinct MMSIs present in the input.
        unique_vessels_matched: Distinct candidate MMSIs retained.
        origin_timestamp: Target spill origin timestamp (UTC ISO format).
        window_minutes: Baseline symmetric temporal search window in minutes.
        before_minutes: Effective time window prior to origin in minutes.
        after_minutes: Effective time window following origin in minutes.
        start_timestamp: Lower bound of the temporal window (UTC ISO format).
        end_timestamp: Upper bound of the temporal window (UTC ISO format).
        earliest_retained_timestamp: Earliest timestamp among retained records (or None if 0 matches).
        latest_retained_timestamp: Latest timestamp among retained records (or None if 0 matches).
        segments_matched: Count of distinct trajectory segments with matching observations.
    """

    total_input_records: int
    matched_records: int
    unique_vessels_in: int
    unique_vessels_matched: int
    origin_timestamp: str
    window_minutes: float
    before_minutes: float
    after_minutes: float
    start_timestamp: str
    end_timestamp: str
    earliest_retained_timestamp: Optional[str]
    latest_retained_timestamp: Optional[str]
    segments_matched: int


@dataclass
class TemporalFilterResult:
    """Result container for AIS temporal filtering.

    Attributes:
        data: Filtered DataFrame containing qualifying AIS observations.
        report: TemporalFilterReport audit summary.
    """

    data: pd.DataFrame
    report: TemporalFilterReport

    def to_dataframe(self) -> pd.DataFrame:
        """Return a copy of the filtered DataFrame."""
        return self.data.copy()

    @property
    def candidate_mmsis(self) -> Set[int]:
        """Set of distinct vessel MMSIs that qualified within the temporal window."""
        if "mmsi" in self.data.columns and not self.data.empty:
            return set(self.data["mmsi"].dropna().astype(int).unique())
        return set()

    @property
    def candidate_segment_ids(self) -> Set[str]:
        """Set of distinct trajectory segment IDs that qualified."""
        if "trajectory_segment_id" in self.data.columns and not self.data.empty:
            return set(
                self.data["trajectory_segment_id"].dropna().astype(str).unique()
            )
        return set()


def _extract_dataframe(data: Any) -> pd.DataFrame:
    """Extract a pandas DataFrame from supported polymorphic inputs.

    Supports:
        - pd.DataFrame
        - SpatialFilterResult (from AIS-06)
        - TemporalFilterResult
        - TrajectoryResult (from AIS-04)
        - InterpolationResult (from AIS-05)
        - TrajectorySegment / InterpolatedSegment
        - List of TrajectorySegment / InterpolatedSegment
    """
    if isinstance(data, pd.DataFrame):
        return data.copy()
    if hasattr(data, "to_dataframe") and callable(data.to_dataframe):
        return data.to_dataframe()
    if hasattr(data, "_dataframe") and isinstance(data._dataframe, pd.DataFrame):
        return data._dataframe.copy()
    if isinstance(data, list):
        dfs = [
            item.data
            for item in data
            if hasattr(item, "data") and isinstance(item.data, pd.DataFrame)
        ]
        if dfs:
            return pd.concat(dfs, ignore_index=True)
        return pd.DataFrame()
    if hasattr(data, "data") and isinstance(data.data, pd.DataFrame):
        return data.data.copy()

    raise TypeError(
        f"Unsupported data type for temporal filtering: {type(data)}. "
        "Expected pd.DataFrame, SpatialFilterResult, TemporalFilterResult, TrajectoryResult, InterpolationResult, TrajectorySegment, or list of segments."
    )


def _validate_origin_timestamp(
    origin_timestamp: Union[str, pd.Timestamp, datetime, np.datetime64],
) -> pd.Timestamp:
    """Validate and normalize origin timestamp to UTC pd.Timestamp.

    Raises:
        ValueError: If timestamp is null, unparseable, NaT, or timezone-naive.
    """
    if origin_timestamp is None:
        raise ValueError("origin_timestamp must be provided and non-null")

    try:
        ts = pd.Timestamp(origin_timestamp)
    except Exception as exc:
        raise ValueError(
            f"Invalid origin timestamp: {origin_timestamp}. Could not parse datetime."
        ) from exc

    if pd.isna(ts) or ts is pd.NaT:
        raise ValueError(
            f"Invalid origin timestamp: {origin_timestamp}. Value is null or NaT."
        )

    # Timezone validation: must be timezone-aware (expected UTC)
    if ts.tzinfo is None:
        raise ValueError(
            f"origin_timestamp must be timezone-aware (expected UTC), got naive timestamp '{origin_timestamp}'"
        )

    # Normalize to UTC
    return ts.tz_convert("UTC")


def _validate_and_parse_ais_timestamps(df: pd.DataFrame) -> pd.Series:
    """Validate and parse AIS DataFrame timestamp column to UTC pd.Series.

    Does not require DataFrame timestamp column to already have pandas datetime dtype.
    Validates that:
    1. The timestamp column exists.
    2. All values can be parsed into valid datetimes.
    3. Invalid/unparseable values, nulls, and NaT raise ValueError.
    4. Timezone-naive timestamps raise ValueError (do not assume a local timezone).
    5. Timezone-aware timestamps are normalized to UTC.
    6. Does not mutate the caller's input DataFrame.

    Returns:
        pd.Series of dtype datetime64[ns, UTC].

    Raises:
        ValueError: If column is missing, contains nulls/NaT, unparseable values,
            or timezone-naive entries.
    """
    if "timestamp" not in df.columns:
        raise ValueError("AIS DataFrame must contain 'timestamp' column")

    raw_ts = df["timestamp"]

    if raw_ts.isna().any():
        raise ValueError(
            "AIS DataFrame 'timestamp' column contains null or NaT values"
        )

    # If already datetime-like
    if pd.api.types.is_datetime64_any_dtype(raw_ts):
        if raw_ts.dt.tz is None:
            raise ValueError(
                "AIS DataFrame 'timestamp' column must be timezone-aware (expected UTC), got naive timestamps"
            )
        return raw_ts.dt.tz_convert("UTC")

    # If object / string or mixed, parse explicitly
    try:
        parsed_ts = pd.to_datetime(raw_ts, errors="coerce")
    except Exception as exc:
        raise ValueError(
            f"Failed to parse AIS DataFrame 'timestamp' column: {exc}"
        ) from exc

    if parsed_ts.isna().any():
        raise ValueError(
            "AIS DataFrame 'timestamp' column contains unparseable, null, or NaT datetime values"
        )

    if parsed_ts.dt.tz is None:
        raise ValueError(
            "AIS DataFrame 'timestamp' column must be timezone-aware (expected UTC), got naive timestamps"
        )

    return parsed_ts.dt.tz_convert("UTC")


def filter_by_time_window(
    data: Union[pd.DataFrame, Any],
    origin_timestamp: Union[str, pd.Timestamp, datetime, np.datetime64],
    window_minutes: float = 30.0,
    before_minutes: Optional[float] = None,
    after_minutes: Optional[float] = None,
    retain_full_segments: bool = False,
) -> pd.DataFrame:
    """Filter AIS observations within a configurable temporal window around origin_timestamp.

    Lower and upper window boundaries are strictly inclusive:
    [origin_timestamp - before_minutes, origin_timestamp + after_minutes].

    Precedence rule:
    - before_minutes if explicitly provided, otherwise window_minutes
    - after_minutes if explicitly provided, otherwise window_minutes

    Args:
        data: Input DataFrame or polymorphic trajectory object.
        origin_timestamp: Reference estimated spill origin timestamp (timezone-aware).
        window_minutes: Baseline symmetric search window in minutes (>= 0.0).
        before_minutes: Optional explicit time window prior to origin (>= 0.0).
        after_minutes: Optional explicit time window following origin (>= 0.0).
        retain_full_segments: If False (default), returns only observations falling
            within the time window.
            If True, retains all observations of any continuous trajectory segment
            that has at least one observation within the time window.
            NOTE ON FALLBACK: When 'trajectory_segment_id' is absent from the dataset
            (e.g. raw or unsegmented observations), an MMSI-level fallback is applied,
            retaining all observations for an MMSI if any observation matches.

    Returns:
        Filtered copy of DataFrame with preserved columns. Does not mutate input.

    Raises:
        ValueError: If origin timestamp or window parameters are invalid, or AIS
            timestamps are missing, invalid, or timezone-naive.
    """
    config = TemporalFilterConfig(
        window_minutes=window_minutes,
        before_minutes=before_minutes,
        after_minutes=after_minutes,
        retain_full_segments=retain_full_segments,
    )

    norm_origin_ts = _validate_origin_timestamp(origin_timestamp)

    df = _extract_dataframe(data)
    if df.empty:
        return df.copy()

    norm_ais_ts = _validate_and_parse_ais_timestamps(df)

    start_window = norm_origin_ts - pd.Timedelta(
        minutes=config.effective_before_minutes
    )
    end_window = norm_origin_ts + pd.Timedelta(
        minutes=config.effective_after_minutes
    )

    # Inclusive boundary mask
    mask = (norm_ais_ts >= start_window) & (norm_ais_ts <= end_window)

    if not config.retain_full_segments:
        matched_df = df[mask].copy().reset_index(drop=True)
        # Update timestamp column to normalized UTC in the returned copy
        matched_df["timestamp"] = norm_ais_ts[mask].reset_index(drop=True)
        return matched_df

    # Segment retention mode
    matching_indices = df[mask].index
    if len(matching_indices) == 0:
        empty_res = df.iloc[0:0].copy().reset_index(drop=True)
        return empty_res

    if "trajectory_segment_id" in df.columns:
        qualifying_segments = set(
            df.loc[matching_indices, "trajectory_segment_id"].dropna().unique()
        )
        seg_mask = df["trajectory_segment_id"].isin(qualifying_segments)
    else:
        # Documented MMSI-level fallback when trajectory_segment_id is absent
        qualifying_mmsis = set(
            df.loc[matching_indices, "mmsi"].dropna().unique()
        )
        seg_mask = df["mmsi"].isin(qualifying_mmsis)

    retained_df = df[seg_mask].copy().reset_index(drop=True)
    retained_df["timestamp"] = norm_ais_ts[seg_mask].reset_index(drop=True)
    return retained_df


def filter_by_origin_time(
    data: Union[pd.DataFrame, Any],
    origin_data: Dict[str, Any],
    config: Optional[TemporalFilterConfig] = None,
    window_minutes: Optional[float] = None,
    before_minutes: Optional[float] = None,
    after_minutes: Optional[float] = None,
    retain_full_segments: Optional[bool] = None,
) -> pd.DataFrame:
    """Filter AIS data using Member 4 origin handoff data contract.

    Extracts:
        - origin.timestamp (ISO 8601 string) as reference time.
        (fallback to spill_observation.timestamp if origin.timestamp is absent)

    Args:
        data: Input DataFrame or polymorphic trajectory object.
        origin_data: Dictionary conforming to Member 4 -> Member 5 handoff contract.
        config: Optional TemporalFilterConfig instance.
        window_minutes: Optional override for baseline window_minutes.
        before_minutes: Optional override for before_minutes.
        after_minutes: Optional override for after_minutes.
        retain_full_segments: Optional override for retain_full_segments.

    Returns:
        pd.DataFrame containing matching observations with preserved columns.
    """
    if config is None:
        config = TemporalFilterConfig()

    origin = origin_data.get("origin", {})
    origin_ts = origin.get("timestamp")

    if origin_ts is None:
        spill_obs = origin_data.get("spill_observation", {})
        origin_ts = spill_obs.get("timestamp")

    if origin_ts is None:
        raise ValueError(
            "origin_data must contain 'timestamp' in 'origin' (or 'spill_observation')"
        )

    eff_window = window_minutes if window_minutes is not None else config.window_minutes
    eff_before = before_minutes if before_minutes is not None else config.before_minutes
    eff_after = after_minutes if after_minutes is not None else config.after_minutes
    eff_retain = retain_full_segments if retain_full_segments is not None else config.retain_full_segments

    return filter_by_time_window(
        data=data,
        origin_timestamp=origin_ts,
        window_minutes=eff_window,
        before_minutes=eff_before,
        after_minutes=eff_after,
        retain_full_segments=eff_retain,
    )


def filter_trajectories_temporally(
    data: Union[pd.DataFrame, Any],
    origin_timestamp: Union[str, pd.Timestamp, datetime, np.datetime64],
    window_minutes: float = 30.0,
    before_minutes: Optional[float] = None,
    after_minutes: Optional[float] = None,
    retain_full_segments: bool = False,
) -> pd.DataFrame:
    """Filter vessel trajectories temporally against an origin timestamp.

    Convenience wrapper around filter_by_time_window for explicit trajectory filtering.
    """
    return filter_by_time_window(
        data=data,
        origin_timestamp=origin_timestamp,
        window_minutes=window_minutes,
        before_minutes=before_minutes,
        after_minutes=after_minutes,
        retain_full_segments=retain_full_segments,
    )


def filter_temporal(
    data: Union[pd.DataFrame, Any],
    config: Optional[TemporalFilterConfig] = None,
    origin_timestamp: Optional[Union[str, pd.Timestamp, datetime, np.datetime64]] = None,
    origin_data: Optional[Dict[str, Any]] = None,
    window_minutes: Optional[float] = None,
    before_minutes: Optional[float] = None,
    after_minutes: Optional[float] = None,
    retain_full_segments: Optional[bool] = None,
) -> TemporalFilterResult:
    """High-level temporal filtering orchestrator returning a TemporalFilterResult.

    Accepts explicit origin timestamp or Member 4 origin_data handoff dictionary.

    Args:
        data: Input DataFrame or polymorphic trajectory object.
        config: Optional TemporalFilterConfig.
        origin_timestamp: Optional explicit search origin timestamp.
        origin_data: Optional Member 4 origin/uncertainty dictionary.
        window_minutes: Optional override for baseline window_minutes.
        before_minutes: Optional override for before_minutes.
        after_minutes: Optional override for after_minutes.
        retain_full_segments: Optional override for retain_full_segments.

    Returns:
        TemporalFilterResult containing filtered DataFrame and TemporalFilterReport.
    """
    if config is None:
        config = TemporalFilterConfig()

    df_in = _extract_dataframe(data)
    total_input = len(df_in)
    unique_vessels_in = (
        int(df_in["mmsi"].dropna().nunique())
        if not df_in.empty and "mmsi" in df_in.columns
        else 0
    )

    # Determine origin timestamp
    if origin_data is not None:
        origin = origin_data.get("origin", {})
        ts_val = origin.get("timestamp")
        if ts_val is None:
            spill_obs = origin_data.get("spill_observation", {})
            ts_val = spill_obs.get("timestamp")
        if ts_val is None and origin_timestamp is not None:
            ts_val = origin_timestamp
        if ts_val is None:
            raise ValueError(
                "origin_data must contain 'timestamp' in 'origin' or explicit origin_timestamp must be provided"
            )
    else:
        if origin_timestamp is None:
            raise ValueError(
                "Either origin_timestamp or origin_data must be provided"
            )
        ts_val = origin_timestamp

    norm_origin_ts = _validate_origin_timestamp(ts_val)

    eff_window = window_minutes if window_minutes is not None else config.window_minutes
    eff_before = before_minutes if before_minutes is not None else config.before_minutes
    eff_after = after_minutes if after_minutes is not None else config.after_minutes
    eff_retain = retain_full_segments if retain_full_segments is not None else config.retain_full_segments

    active_config = TemporalFilterConfig(
        window_minutes=eff_window,
        before_minutes=eff_before,
        after_minutes=eff_after,
        retain_full_segments=eff_retain,
    )

    start_window = norm_origin_ts - pd.Timedelta(
        minutes=active_config.effective_before_minutes
    )
    end_window = norm_origin_ts + pd.Timedelta(
        minutes=active_config.effective_after_minutes
    )

    filtered_df = filter_by_time_window(
        data=df_in,
        origin_timestamp=norm_origin_ts,
        window_minutes=active_config.window_minutes,
        before_minutes=active_config.before_minutes,
        after_minutes=active_config.after_minutes,
        retain_full_segments=active_config.retain_full_segments,
    )

    matched_records = len(filtered_df)
    unique_vessels_matched = (
        int(filtered_df["mmsi"].dropna().nunique())
        if not filtered_df.empty and "mmsi" in filtered_df.columns
        else 0
    )
    segments_matched = (
        int(filtered_df["trajectory_segment_id"].dropna().nunique())
        if not filtered_df.empty and "trajectory_segment_id" in filtered_df.columns
        else 0
    )

    earliest_retained = (
        str(filtered_df["timestamp"].min().isoformat())
        if not filtered_df.empty and "timestamp" in filtered_df.columns
        else None
    )
    latest_retained = (
        str(filtered_df["timestamp"].max().isoformat())
        if not filtered_df.empty and "timestamp" in filtered_df.columns
        else None
    )

    report = TemporalFilterReport(
        total_input_records=total_input,
        matched_records=matched_records,
        unique_vessels_in=unique_vessels_in,
        unique_vessels_matched=unique_vessels_matched,
        origin_timestamp=str(norm_origin_ts.isoformat()),
        window_minutes=active_config.window_minutes,
        before_minutes=active_config.effective_before_minutes,
        after_minutes=active_config.effective_after_minutes,
        start_timestamp=str(start_window.isoformat()),
        end_timestamp=str(end_window.isoformat()),
        earliest_retained_timestamp=earliest_retained,
        latest_retained_timestamp=latest_retained,
        segments_matched=segments_matched,
    )

    return TemporalFilterResult(
        data=filtered_df,
        report=report,
    )
