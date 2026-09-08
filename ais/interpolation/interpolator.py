"""AIS Vessel Position Interpolation Implementation.

Provides scientifically defensible, great-circle shortest-path kinematic
position interpolation strictly within individual continuous AIS-04 trajectory
segments, respecting domain boundaries, anti-meridian crossings, temporal
blackout gaps, and explicit provenance auditing.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from ais.interpolation.config import InterpolationConfig
from ais.trajectory.config import TrajectoryConfig
from ais.trajectory.reconstructor import (
    TrajectoryResult,
    TrajectorySegment,
    VesselTrajectory,
    reconstruct_trajectories,
)

# Static vessel identification fields safe to propagate to interpolated points
STATIC_VESSEL_COLUMNS = [
    "vessel_name",
    "imo",
    "callsign",
    "vessel_type",
    "length",
    "width",
    "draught",
]


def interpolate_coordinates(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    alpha: float,
) -> Tuple[float, float]:
    """Interpolate latitude and longitude along the shortest great-circle path.

    Latitude is linearly interpolated. Longitude is interpolated along the
    shortest angular path across the spherical anti-meridian (+/-180 deg),
    safeguarding against crossing the 0-degree prime meridian when crossing +/-180.

    Args:
        lat1: Latitude of starting observation in decimal degrees [-90, 90].
        lon1: Longitude of starting observation in decimal degrees [-180, 180].
        lat2: Latitude of ending observation in decimal degrees [-90, 90].
        lon2: Longitude of ending observation in decimal degrees [-180, 180].
        alpha: Normalized temporal fraction in [0.0, 1.0].

    Returns:
        Tuple of (interpolated_latitude, interpolated_longitude).
    """
    # Linear interpolation for latitude
    interp_lat = float(lat1 + alpha * (lat2 - lat1))

    # Shortest-path angular difference for longitude in [-180, 180]
    dlon = (lon2 - lon1 + 180.0) % 360.0 - 180.0
    raw_lon = lon1 + alpha * dlon

    # Wrap into [-180, 180]
    interp_lon = (raw_lon + 180.0) % 360.0 - 180.0

    # Preserve exact +/-180 boundary values
    if abs(raw_lon - 180.0) < 1e-9:
        interp_lon = 180.0
    elif abs(raw_lon + 180.0) < 1e-9:
        interp_lon = -180.0

    return interp_lat, float(interp_lon)


@dataclass(frozen=True)
class InterpolatedSegment:
    """A trajectory segment containing original observations and generated points.

    Attributes:
        mmsi: Maritime Mobile Service Identity of the vessel.
        segment_id: String identifier inherited from AIS-04 (e.g., '{mmsi}_seg_{idx}').
        segment_index: Zero-based segment index within vessel track.
        data: DataFrame containing chronologically sorted actual and interpolated points.
        num_actual_observations: Count of genuine AIS pings in this segment.
        num_interpolated_points: Count of scientifically generated positions in this segment.
        total_points: Total points in the segment (num_actual + num_interpolated).
    """

    mmsi: int
    segment_id: str
    segment_index: int
    data: pd.DataFrame
    num_actual_observations: int
    num_interpolated_points: int
    total_points: int


@dataclass(frozen=True)
class InterpolationReport:
    """Summary audit metrics for trajectory interpolation.

    Attributes:
        total_input_segments: Number of trajectory segments provided to the interpolator.
        total_actual_observations: Total count of real AIS observations preserved.
        total_interpolated_points: Total count of intermediate positions generated.
        total_output_records: Total combined records in the output.
        segments_interpolated: Count of segments where interpolation was performed.
        segments_skipped_gap_too_large: Count of intervals skipped because time gap > max_gap_seconds.
        single_ping_segments_skipped: Count of segments with only 1 observation that cannot be interpolated.
    """

    total_input_segments: int
    total_actual_observations: int
    total_interpolated_points: int
    total_output_records: int
    segments_interpolated: int
    segments_skipped_gap_too_large: int
    single_ping_segments_skipped: int


@dataclass
class InterpolationResult:
    """Result container for vessel trajectory interpolation.

    Attributes:
        segments: Flat list of all InterpolatedSegment instances.
        trajectories: Mapping of MMSI to list of InterpolatedSegment instances.
        report: InterpolationReport audit metrics.
    """

    segments: List[InterpolatedSegment]
    trajectories: Dict[int, List[InterpolatedSegment]]
    report: InterpolationReport
    _dataframe: pd.DataFrame

    def to_dataframe(self) -> pd.DataFrame:
        """Return consolidated DataFrame of all actual and interpolated observations.

        Includes provenance columns:
        - is_interpolated: False for genuine AIS pings, True for generated points
        - interpolation_method: None for genuine AIS pings, 'linear' for generated points
        """
        return self._dataframe.copy()


def _extract_segments(
    trajectories: Union[
        TrajectoryResult, List[TrajectorySegment], TrajectorySegment, pd.DataFrame
    ],
) -> List[TrajectorySegment]:
    """Extract a list of TrajectorySegment instances from supported polymorphic inputs."""
    if isinstance(trajectories, TrajectoryResult):
        return list(trajectories.segments)

    if isinstance(trajectories, TrajectorySegment):
        return [trajectories]

    if isinstance(trajectories, list):
        if not trajectories:
            return []
        if all(isinstance(s, TrajectorySegment) for s in trajectories):
            return list(trajectories)
        raise TypeError("List must contain only TrajectorySegment instances")

    if isinstance(trajectories, pd.DataFrame):
        if trajectories.empty:
            return []

        # If already annotated with trajectory_segment_id, reconstruct segments directly
        if "trajectory_segment_id" in trajectories.columns and "segment_index" in trajectories.columns:
            segments: List[TrajectorySegment] = []
            for (mmsi_val, seg_idx), seg_df in trajectories.groupby(
                ["mmsi", "segment_index"], sort=False
            ):
                s_data = seg_df.sort_values(by="timestamp").reset_index(drop=True)
                start_t = s_data["timestamp"].iloc[0]
                end_t = s_data["timestamp"].iloc[-1]
                duration_s = float((end_t - start_t).total_seconds())
                seg = TrajectorySegment(
                    mmsi=int(mmsi_val),
                    segment_id=str(s_data["trajectory_segment_id"].iloc[0]),
                    segment_index=int(seg_idx),
                    data=s_data,
                    start_timestamp=start_t,
                    end_timestamp=end_t,
                    num_observations=len(s_data),
                    duration_seconds=duration_s,
                )
                segments.append(seg)
            return segments

        # Otherwise, pass through AIS-04 reconstruct_trajectories
        res = reconstruct_trajectories(trajectories)
        return list(res.segments)

    raise TypeError(
        f"Unsupported trajectories input type: {type(trajectories)}. "
        "Expected TrajectoryResult, List[TrajectorySegment], TrajectorySegment, or pd.DataFrame."
    )


def _interpolate_single_segment(
    segment: TrajectorySegment,
    target_timestamps: Optional[List[pd.Timestamp]],
    time_step_seconds: Optional[float],
    config: InterpolationConfig,
) -> Tuple[InterpolatedSegment, bool, int, int]:
    """Interpolate positions within a single TrajectorySegment.

    Returns:
        Tuple of (InterpolatedSegment, was_interpolated, skipped_gaps_count, is_single_ping).
    """
    if segment.data.empty:
        empty_data = segment.data.copy()
        empty_data["is_interpolated"] = pd.Series(dtype=bool)
        empty_data["interpolation_method"] = pd.Series(dtype=object)
        return (
            InterpolatedSegment(
                mmsi=segment.mmsi,
                segment_id=segment.segment_id,
                segment_index=segment.segment_index,
                data=empty_data,
                num_actual_observations=0,
                num_interpolated_points=0,
                total_points=0,
            ),
            False,
            0,
            0,
        )

    # Annotate original data with provenance flags
    orig_df = segment.data.copy()
    if str(orig_df["timestamp"].dt.tz) != "UTC":
        orig_df["timestamp"] = orig_df["timestamp"].dt.tz_convert("UTC")

    orig_df = orig_df.sort_values(by="timestamp").reset_index(drop=True)
    orig_df["is_interpolated"] = False
    orig_df["interpolation_method"] = None

    n_actual = len(orig_df)

    # Single-ping segment cannot be interpolated
    if n_actual <= 1:
        return (
            InterpolatedSegment(
                mmsi=segment.mmsi,
                segment_id=segment.segment_id,
                segment_index=segment.segment_index,
                data=orig_df,
                num_actual_observations=n_actual,
                num_interpolated_points=0,
                total_points=n_actual,
            ),
            False,
            0,
            1,
        )

    # Collect candidate timestamps to evaluate
    t_start = orig_df["timestamp"].iloc[0]
    t_end = orig_df["timestamp"].iloc[-1]
    candidate_timestamps: List[pd.Timestamp] = []

    # 1. Regular grid timestamps
    if time_step_seconds is not None and time_step_seconds > 0:
        step_td = pd.Timedelta(seconds=time_step_seconds)
        # Generate grid points strictly between start and end
        grid = pd.date_range(start=t_start, end=t_end, freq=step_td)
        candidate_timestamps.extend(grid)

    # 2. Specific target timestamps
    if target_timestamps:
        for t in target_timestamps:
            if not isinstance(t, pd.Timestamp):
                t = pd.to_datetime(t, utc=True)
            elif t.tz is None:
                raise ValueError("Target timestamp must be timezone-aware (UTC)")
            elif str(t.tz) != "UTC":
                t = t.tz_convert("UTC")

            if t_start <= t <= t_end:
                candidate_timestamps.append(t)

    if not candidate_timestamps:
        return (
            InterpolatedSegment(
                mmsi=segment.mmsi,
                segment_id=segment.segment_id,
                segment_index=segment.segment_index,
                data=orig_df,
                num_actual_observations=n_actual,
                num_interpolated_points=0,
                total_points=n_actual,
            ),
            False,
            0,
            0,
        )

    # Deduplicate and sort candidate timestamps
    actual_ts_set = set(orig_df["timestamp"])
    unique_candidates = sorted(
        {t for t in candidate_timestamps if t not in actual_ts_set and t_start < t < t_end}
    )

    if not unique_candidates:
        return (
            InterpolatedSegment(
                mmsi=segment.mmsi,
                segment_id=segment.segment_id,
                segment_index=segment.segment_index,
                data=orig_df,
                num_actual_observations=n_actual,
                num_interpolated_points=0,
                total_points=n_actual,
            ),
            False,
            0,
            0,
        )

    # Perform interpolation between bounding actual observations
    generated_rows: List[dict] = []
    skipped_gaps = 0
    all_actual_ts = orig_df["timestamp"].tolist()

    for t_cand in unique_candidates:
        # Locate interval [t1, t2] containing t_cand
        idx = orig_df["timestamp"].searchsorted(t_cand)
        if idx <= 0 or idx >= len(orig_df):
            continue

        row1 = orig_df.iloc[idx - 1]
        row2 = orig_df.iloc[idx]

        t1 = row1["timestamp"]
        t2 = row2["timestamp"]
        gap_s = (t2 - t1).total_seconds()

        # Enforce max_gap_seconds constraint
        if gap_s > config.max_gap_seconds:
            skipped_gaps += 1
            continue

        if gap_s <= 0:
            continue

        alpha = (t_cand - t1).total_seconds() / gap_s
        interp_lat, interp_lon = interpolate_coordinates(
            float(row1["latitude"]),
            float(row1["longitude"]),
            float(row2["latitude"]),
            float(row2["longitude"]),
            alpha,
        )

        # Construct interpolated record
        new_row: dict = {
            "mmsi": segment.mmsi,
            "timestamp": t_cand,
            "latitude": interp_lat,
            "longitude": interp_lon,
            "trajectory_segment_id": segment.segment_id,
            "segment_index": segment.segment_index,
            "is_interpolated": True,
            "interpolation_method": config.method,
            "time_gap_seconds": np.nan,
        }

        # Propagate safe static vessel attributes if present
        for col in STATIC_VESSEL_COLUMNS:
            if col in orig_df.columns:
                new_row[col] = row1[col]

        # Sensor/dynamic fields are explicitly set to NaN/False
        for col in orig_df.columns:
            if col not in new_row:
                if col in ["is_speed_anomaly", "is_position_jump", "is_sog_inconsistent", "is_suspicious_zero", "is_suspicious_zero_jump"]:
                    new_row[col] = False
                elif col == "previous_timestamp":
                    new_row[col] = pd.NaT
                else:
                    new_row[col] = np.nan

        generated_rows.append(new_row)

    if generated_rows:
        gen_df = pd.DataFrame(generated_rows)
        # Ensure identical column order
        for col in orig_df.columns:
            if col not in gen_df.columns:
                gen_df[col] = np.nan
        gen_df = gen_df[orig_df.columns]

        combined_df = pd.concat([orig_df, gen_df], ignore_index=True)
        combined_df = combined_df.sort_values(by="timestamp").reset_index(drop=True)
        was_interpolated = True
    else:
        combined_df = orig_df
        was_interpolated = False

    n_gen = len(generated_rows)
    return (
        InterpolatedSegment(
            mmsi=segment.mmsi,
            segment_id=segment.segment_id,
            segment_index=segment.segment_index,
            data=combined_df,
            num_actual_observations=n_actual,
            num_interpolated_points=n_gen,
            total_points=len(combined_df),
        ),
        was_interpolated,
        skipped_gaps,
        0,
    )


def interpolate_trajectories(
    trajectories: Union[
        TrajectoryResult, List[TrajectorySegment], TrajectorySegment, pd.DataFrame
    ],
    time_step_seconds: Optional[float] = None,
    target_timestamps: Optional[List[Union[pd.Timestamp, datetime, str]]] = None,
    config: Optional[InterpolationConfig] = None,
) -> InterpolationResult:
    """Interpolate vessel positions within continuous AIS-04 trajectory segments.

    Estimates vessel latitude and longitude between known AIS observations strictly
    within the same segment. Never interpolates across different MMSIs or across
    segment blackout boundaries. All positions are tagged with provenance flags.

    Args:
        trajectories: Input trajectories as a TrajectoryResult, a TrajectorySegment,
            a list of TrajectorySegments, or an AIS-04 DataFrame.
        time_step_seconds: Optional uniform resampling frequency in seconds.
        target_timestamps: Optional list of explicit target timestamps to interpolate.
        config: Optional InterpolationConfig. If None, default settings are used.

    Returns:
        InterpolationResult containing interpolated segments, vessel trajectories,
        audit report, and consolidated DataFrame.
    """
    if config is None:
        config = InterpolationConfig()

    # Default to 300s (5 minutes) if neither frequency nor timestamps specified
    if time_step_seconds is None and target_timestamps is None:
        time_step_seconds = 300.0

    # Normalize target_timestamps to UTC Timestamps
    norm_target_ts: Optional[List[pd.Timestamp]] = None
    if target_timestamps:
        norm_target_ts = []
        for t in target_timestamps:
            if not isinstance(t, pd.Timestamp):
                t_obj = pd.to_datetime(t, utc=True)
            elif t.tz is None:
                raise ValueError("target_timestamps must be timezone-aware (UTC)")
            else:
                t_obj = t.tz_convert("UTC") if str(t.tz) != "UTC" else t
            norm_target_ts.append(t_obj)

    segments_in = _extract_segments(trajectories)

    if not segments_in:
        empty_report = InterpolationReport(
            total_input_segments=0,
            total_actual_observations=0,
            total_interpolated_points=0,
            total_output_records=0,
            segments_interpolated=0,
            segments_skipped_gap_too_large=0,
            single_ping_segments_skipped=0,
        )
        empty_df = pd.DataFrame()
        return InterpolationResult(
            segments=[],
            trajectories={},
            report=empty_report,
            _dataframe=empty_df,
        )

    out_segments: List[InterpolatedSegment] = []
    out_trajectories: Dict[int, List[InterpolatedSegment]] = {}

    total_actual = 0
    total_interpolated = 0
    segments_interp_count = 0
    skipped_gaps_count = 0
    single_ping_count = 0

    for seg in segments_in:
        interp_seg, was_interp, skipped_gaps, is_single_ping = _interpolate_single_segment(
            segment=seg,
            target_timestamps=norm_target_ts,
            time_step_seconds=time_step_seconds,
            config=config,
        )
        out_segments.append(interp_seg)

        if interp_seg.mmsi not in out_trajectories:
            out_trajectories[interp_seg.mmsi] = []
        out_trajectories[interp_seg.mmsi].append(interp_seg)

        total_actual += interp_seg.num_actual_observations
        total_interpolated += interp_seg.num_interpolated_points
        if was_interp:
            segments_interp_count += 1
        skipped_gaps_count += skipped_gaps
        single_ping_count += is_single_ping

    # Consolidate all segments into a unified DataFrame
    if out_segments:
        consolidated_df = pd.concat(
            [s.data for s in out_segments], ignore_index=True
        )
        consolidated_df = consolidated_df.sort_values(
            by=["mmsi", "timestamp"], kind="mergesort"
        ).reset_index(drop=True)
    else:
        consolidated_df = pd.DataFrame()

    report = InterpolationReport(
        total_input_segments=len(segments_in),
        total_actual_observations=total_actual,
        total_interpolated_points=total_interpolated,
        total_output_records=total_actual + total_interpolated,
        segments_interpolated=segments_interp_count,
        segments_skipped_gap_too_large=skipped_gaps_count,
        single_ping_segments_skipped=single_ping_count,
    )

    return InterpolationResult(
        segments=out_segments,
        trajectories=out_trajectories,
        report=report,
        _dataframe=consolidated_df,
    )


def resample_trajectory(
    trajectories: Union[
        TrajectoryResult, List[TrajectorySegment], TrajectorySegment, pd.DataFrame
    ],
    time_step_seconds: float = 300.0,
    config: Optional[InterpolationConfig] = None,
) -> InterpolationResult:
    """Resample vessel trajectories at a regular temporal interval.

    Retains all actual AIS observations and synthesizes regular grid points
    only where strictly bounded by actual observations within the same segment.
    Never crosses segment boundaries or interpolates intervals > max_gap_seconds.

    Args:
        trajectories: Input AIS-04 trajectory structure or DataFrame.
        time_step_seconds: Resampling frequency in seconds. Defaults to 300.0 (5 min).
        config: Optional InterpolationConfig.

    Returns:
        InterpolationResult containing resampled segments and consolidated DataFrame.
    """
    if time_step_seconds <= 0:
        raise ValueError(
            f"time_step_seconds must be positive, got {time_step_seconds}"
        )
    return interpolate_trajectories(
        trajectories=trajectories,
        time_step_seconds=time_step_seconds,
        target_timestamps=None,
        config=config,
    )


def interpolate_at_timestamp(
    trajectories: Union[
        TrajectoryResult, List[TrajectorySegment], TrajectorySegment, pd.DataFrame
    ],
    target_timestamp: Union[pd.Timestamp, datetime, str],
    config: Optional[InterpolationConfig] = None,
) -> pd.DataFrame:
    """Estimate vessel positions at a specific target timestamp.

    Searches valid individual trajectory segments. If target_timestamp exactly matches
    an actual observation, returns that actual observation with is_interpolated=False.
    If target_timestamp falls between two observations with gap <= max_gap_seconds,
    linearly interpolates coordinates with is_interpolated=True. If timestamp lies in
    a blackout gap or outside track boundaries, no position is generated (no extrapolation).

    Args:
        trajectories: Input AIS-04 trajectory structure or DataFrame.
        target_timestamp: UTC timestamp to estimate vessel positions for.
        config: Optional InterpolationConfig.

    Returns:
        pd.DataFrame containing one row per candidate vessel having a valid position
        at target_timestamp, sorted by MMSI.
    """
    if config is None:
        config = InterpolationConfig()

    if not isinstance(target_timestamp, pd.Timestamp):
        t_target = pd.to_datetime(target_timestamp, utc=True)
    elif target_timestamp.tz is None:
        raise ValueError("target_timestamp must be timezone-aware (UTC)")
    else:
        t_target = (
            target_timestamp.tz_convert("UTC")
            if str(target_timestamp.tz) != "UTC"
            else target_timestamp
        )

    segments_in = _extract_segments(trajectories)
    if not segments_in:
        return pd.DataFrame()

    matched_rows: List[dict] = []

    for seg in segments_in:
        if seg.data.empty:
            continue

        df_seg = seg.data.copy().sort_values(by="timestamp").reset_index(drop=True)
        if str(df_seg["timestamp"].dt.tz) != "UTC":
            df_seg["timestamp"] = df_seg["timestamp"].dt.tz_convert("UTC")

        t_start = df_seg["timestamp"].iloc[0]
        t_end = df_seg["timestamp"].iloc[-1]

        # 1. Check bounds: never extrapolate before start or after end
        if t_target < t_start or t_target > t_end:
            continue

        # 2. Check for exact timestamp match
        exact_matches = df_seg[df_seg["timestamp"] == t_target]
        if not exact_matches.empty:
            match_row = exact_matches.iloc[0].to_dict()
            match_row["is_interpolated"] = False
            match_row["interpolation_method"] = None
            matched_rows.append(match_row)
            continue

        # 3. Single-ping segment cannot be interpolated
        if len(df_seg) <= 1:
            continue

        # 4. Locate bounding observations
        idx = df_seg["timestamp"].searchsorted(t_target)
        if idx <= 0 or idx >= len(df_seg):
            continue

        row1 = df_seg.iloc[idx - 1]
        row2 = df_seg.iloc[idx]

        t1 = row1["timestamp"]
        t2 = row2["timestamp"]
        gap_s = (t2 - t1).total_seconds()

        # 5. Check gap constraint
        if gap_s > config.max_gap_seconds or gap_s <= 0:
            continue

        alpha = (t_target - t1).total_seconds() / gap_s
        interp_lat, interp_lon = interpolate_coordinates(
            float(row1["latitude"]),
            float(row1["longitude"]),
            float(row2["latitude"]),
            float(row2["longitude"]),
            alpha,
        )

        new_row: dict = {
            "mmsi": seg.mmsi,
            "timestamp": t_target,
            "latitude": interp_lat,
            "longitude": interp_lon,
            "trajectory_segment_id": seg.segment_id,
            "segment_index": seg.segment_index,
            "is_interpolated": True,
            "interpolation_method": config.method,
            "time_gap_seconds": np.nan,
        }

        # Propagate static vessel metadata
        for col in STATIC_VESSEL_COLUMNS:
            if col in df_seg.columns:
                new_row[col] = row1[col]

        # Other sensor fields set to NaN/False
        for col in df_seg.columns:
            if col not in new_row:
                if col in ["is_speed_anomaly", "is_position_jump", "is_sog_inconsistent", "is_suspicious_zero", "is_suspicious_zero_jump"]:
                    new_row[col] = False
                elif col == "previous_timestamp":
                    new_row[col] = pd.NaT
                else:
                    new_row[col] = np.nan

        matched_rows.append(new_row)

    if not matched_rows:
        return pd.DataFrame()

    res_df = pd.DataFrame(matched_rows)
    # Deduplicate in rare case multiple segments matched (e.g. edge boundary)
    res_df = res_df.drop_duplicates(subset=["mmsi"], keep="first")
    return res_df.sort_values(by="mmsi").reset_index(drop=True)
