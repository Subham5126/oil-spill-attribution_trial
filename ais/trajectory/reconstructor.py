"""AIS Vessel Trajectory Reconstruction.

Reconstructs chronological vessel trajectories from cleaned AIS observations,
detects temporal observation gaps, segments trajectories at domain-specific
latency thresholds (S-AIS vs T-AIS latency and dead-reckoning limits),
and structures trajectories for downstream interpolation and spill origin attribution.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ais.data_loader.schema import REQUIRED_COLUMNS
from ais.trajectory.config import TrajectoryConfig


@dataclass(frozen=True)
class TrajectorySegment:
    """A continuous trajectory segment of an individual vessel without temporal gaps.

    Attributes:
        mmsi: Maritime Mobile Service Identity of the vessel.
        segment_id: Unique string identifier for the segment (e.g., '{mmsi}_seg_{segment_index}').
        segment_index: Zero-based chronological index of the segment for this vessel.
        data: DataFrame containing chronologically sorted observations for this segment.
        start_timestamp: UTC timestamp of the first observation in this segment.
        end_timestamp: UTC timestamp of the last observation in this segment.
        num_observations: Total number of observations in this segment.
        duration_seconds: Elapsed time in seconds between start and end observations.
    """

    mmsi: int
    segment_id: str
    segment_index: int
    data: pd.DataFrame
    start_timestamp: pd.Timestamp
    end_timestamp: pd.Timestamp
    num_observations: int
    duration_seconds: float


@dataclass
class VesselTrajectory:
    """Complete reconstructed trajectory profile for a single vessel across all segments.

    Attributes:
        mmsi: Maritime Mobile Service Identity of the vessel.
        segments: Chronologically ordered list of trajectory segments for this vessel.
        total_observations: Total number of AIS observations across all segments.
        num_segments: Total number of continuous segments for this vessel.
        start_timestamp: UTC timestamp of the earliest observation.
        end_timestamp: UTC timestamp of the latest observation.
    """

    mmsi: int
    segments: List[TrajectorySegment]
    total_observations: int
    num_segments: int
    start_timestamp: pd.Timestamp
    end_timestamp: pd.Timestamp

    def get_segment(self, segment_index: int) -> TrajectorySegment:
        """Retrieve a specific segment by its index.

        Args:
            segment_index: Zero-based segment index.

        Returns:
            The matching TrajectorySegment.

        Raises:
            KeyError: If segment_index is not found.
        """
        for seg in self.segments:
            if seg.segment_index == segment_index:
                return seg
        raise KeyError(
            f"Segment index {segment_index} not found for vessel MMSI {self.mmsi}"
        )

    def to_dataframe(self) -> pd.DataFrame:
        """Consolidate all segments of this vessel into a single DataFrame."""
        if not self.segments:
            return pd.DataFrame()
        return pd.concat([s.data for s in self.segments], ignore_index=True)


@dataclass(frozen=True)
class TrajectoryReport:
    """Audit metrics and summary statistics for trajectory reconstruction.

    Attributes:
        total_input_records: Number of AIS records in the input DataFrame.
        total_vessels: Number of distinct vessels with reconstructed trajectories.
        total_trajectory_segments: Total number of segments across all vessels.
        total_records_assigned: Number of observations successfully assigned to segments.
        number_of_gaps_detected: Count of temporal gaps exceeding max_gap_seconds within vessels.
        segments_created_from_gaps: Number of new segments instantiated due to temporal gaps.
        min_observations_per_segment: Smallest observation count among retained segments.
        max_observations_per_segment: Largest observation count among retained segments.
        avg_observations_per_segment: Mean observations per segment.
    """

    total_input_records: int
    total_vessels: int
    total_trajectory_segments: int
    total_records_assigned: int
    number_of_gaps_detected: int
    segments_created_from_gaps: int
    min_observations_per_segment: int
    max_observations_per_segment: int
    avg_observations_per_segment: float


@dataclass
class TrajectoryResult:
    """Result container for trajectory reconstruction.

    Attributes:
        trajectories: Mapping of MMSI to VesselTrajectory.
        segments: Flat list of all TrajectorySegment instances across all vessels.
        report: TrajectoryReport audit summary.
    """

    trajectories: Dict[int, VesselTrajectory]
    segments: List[TrajectorySegment]
    report: TrajectoryReport
    _dataframe: pd.DataFrame

    def to_dataframe(self) -> pd.DataFrame:
        """Return consolidated DataFrame of all reconstructed trajectories.

        Includes original AIS attributes plus:
        - trajectory_segment_id: Unique string identifier (e.g. '123456789_seg_0')
        - segment_index: Zero-based segment index within vessel track
        - time_gap_seconds: Time delta since previous observation within the same segment (NaN for first observation)
        """
        return self._dataframe.copy()

    def get_vessel(self, mmsi: int) -> VesselTrajectory:
        """Retrieve vessel trajectory by MMSI.

        Args:
            mmsi: Vessel MMSI integer.

        Returns:
            VesselTrajectory for the given MMSI.

        Raises:
            KeyError: If MMSI is not present in trajectories.
        """
        if mmsi not in self.trajectories:
            raise KeyError(f"MMSI {mmsi} not found in reconstructed trajectories")
        return self.trajectories[mmsi]


def reconstruct_trajectories(
    df: pd.DataFrame,
    config: Optional[TrajectoryConfig] = None,
) -> TrajectoryResult:
    """Reconstruct chronological, gap-segmented vessel trajectories from cleaned AIS data.

    Preserves original observations without positional interpolation. Identifies temporal
    gaps exceeding `config.max_gap_seconds` and partitions trajectories into continuous,
    kinematically valid segments.

    Args:
        df: Cleaned AIS DataFrame (e.g., from AIS-03 `clean_ais_data()`).
            Must contain 'mmsi', 'timestamp', 'latitude', 'longitude'.
        config: Optional TrajectoryConfig instance. If None, default settings are used.

    Returns:
        TrajectoryResult containing per-vessel trajectories, segment list, audit report,
        and consolidated DataFrame with trajectory metadata.

    Raises:
        ValueError: If required columns are missing, timestamp is not datetime, or
            timestamp is not UTC-aware.
    """
    if config is None:
        config = TrajectoryConfig()

    # 1. Validate required columns
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Cannot reconstruct trajectories: missing required column(s) {missing}"
        )

    # 2. Validate timestamp dtype & timezone
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        raise ValueError("timestamp column must be a datetime dtype")
    if df["timestamp"].dt.tz is None:
        raise ValueError("timestamp column must be timezone-aware (UTC)")

    # 3. Handle empty DataFrame
    if df.empty:
        empty_df = df.copy()
        for col, dtype in [
            ("trajectory_segment_id", "object"),
            ("segment_index", "int64"),
            ("time_gap_seconds", "float64"),
        ]:
            if col not in empty_df.columns:
                empty_df[col] = pd.Series(dtype=dtype)
        empty_report = TrajectoryReport(
            total_input_records=0,
            total_vessels=0,
            total_trajectory_segments=0,
            total_records_assigned=0,
            number_of_gaps_detected=0,
            segments_created_from_gaps=0,
            min_observations_per_segment=0,
            max_observations_per_segment=0,
            avg_observations_per_segment=0.0,
        )
        return TrajectoryResult(
            trajectories={},
            segments=[],
            report=empty_report,
            _dataframe=empty_df,
        )

    # 4. Sort deterministically by MMSI and UTC timestamp
    df_sorted = df.copy()
    if str(df_sorted["timestamp"].dt.tz) != "UTC":
        df_sorted["timestamp"] = df_sorted["timestamp"].dt.tz_convert("UTC")

    df_sorted["mmsi"] = df_sorted["mmsi"].astype(int)
    df_sorted = df_sorted.sort_values(
        by=["mmsi", "timestamp"], kind="mergesort"
    ).reset_index(drop=True)

    # 5. Vectorized gap detection & segmentation
    mmsi_series = df_sorted["mmsi"]
    prev_mmsi = mmsi_series.shift(1)
    timestamp_series = df_sorted["timestamp"]
    prev_timestamp = timestamp_series.shift(1)
    time_delta = (timestamp_series - prev_timestamp).dt.total_seconds()

    # Temporal gap is detected only within the same MMSI
    same_vessel = mmsi_series == prev_mmsi
    gap_mask = same_vessel & (time_delta > config.max_gap_seconds)
    number_of_gaps_detected = int(gap_mask.sum())

    # Segment boundary occurs at vessel transition OR temporal gap
    is_new_segment = (~same_vessel) | gap_mask

    # Compute 0-based segment_index per MMSI
    df_sorted["segment_index"] = (
        is_new_segment.groupby(df_sorted["mmsi"]).cumsum() - 1
    ).astype(int)

    # Construct unique segment string ID: {mmsi}_seg_{segment_index}
    df_sorted["trajectory_segment_id"] = (
        df_sorted["mmsi"].astype(str) + "_seg_" + df_sorted["segment_index"].astype(str)
    )

    # time_gap_seconds: NaN for the first point of each segment, time_delta for subsequent points
    df_sorted["time_gap_seconds"] = np.where(
        is_new_segment, np.nan, time_delta.values
    ).astype(float)

    # 6. Filter by min_observations_per_segment if configured > 1
    if config.min_observations_per_segment > 1:
        seg_counts = df_sorted.groupby("trajectory_segment_id")["timestamp"].transform("count")
        df_sorted = df_sorted[seg_counts >= config.min_observations_per_segment].reset_index(drop=True)

    # 7. Construct TrajectorySegment and VesselTrajectory objects
    trajectories: Dict[int, VesselTrajectory] = {}
    all_segments: List[TrajectorySegment] = []

    for mmsi_val, vessel_df in df_sorted.groupby("mmsi", sort=False):
        v_segments: List[TrajectorySegment] = []
        for seg_idx, seg_df in vessel_df.groupby("segment_index", sort=False):
            seg_data = seg_df.copy().reset_index(drop=True)
            start_t = seg_data["timestamp"].iloc[0]
            end_t = seg_data["timestamp"].iloc[-1]
            n_obs = len(seg_data)
            duration_s = float((end_t - start_t).total_seconds())

            segment = TrajectorySegment(
                mmsi=int(mmsi_val),
                segment_id=f"{int(mmsi_val)}_seg_{int(seg_idx)}",
                segment_index=int(seg_idx),
                data=seg_data,
                start_timestamp=start_t,
                end_timestamp=end_t,
                num_observations=n_obs,
                duration_seconds=duration_s,
            )
            v_segments.append(segment)
            all_segments.append(segment)

        if v_segments:
            v_trajectory = VesselTrajectory(
                mmsi=int(mmsi_val),
                segments=v_segments,
                total_observations=sum(s.num_observations for s in v_segments),
                num_segments=len(v_segments),
                start_timestamp=v_segments[0].start_timestamp,
                end_timestamp=v_segments[-1].end_timestamp,
            )
            trajectories[int(mmsi_val)] = v_trajectory

    # 8. Compile audit report
    num_segments = len(all_segments)
    seg_obs_counts = [s.num_observations for s in all_segments]
    segments_created_from_gaps = max(0, num_segments - len(trajectories))

    report = TrajectoryReport(
        total_input_records=len(df),
        total_vessels=len(trajectories),
        total_trajectory_segments=num_segments,
        total_records_assigned=len(df_sorted),
        number_of_gaps_detected=number_of_gaps_detected,
        segments_created_from_gaps=segments_created_from_gaps,
        min_observations_per_segment=min(seg_obs_counts) if seg_obs_counts else 0,
        max_observations_per_segment=max(seg_obs_counts) if seg_obs_counts else 0,
        avg_observations_per_segment=float(np.mean(seg_obs_counts)) if seg_obs_counts else 0.0,
    )

    return TrajectoryResult(
        trajectories=trajectories,
        segments=all_segments,
        report=report,
        _dataframe=df_sorted,
    )
