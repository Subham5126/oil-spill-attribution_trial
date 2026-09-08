"""AIS Data Cleaner and Quality Reporting.

Performs sequence-aware multi-ping kinematic validation, anomaly detection
(impossible speed, position jumps/spikes), contextual (0,0) jump classification,
reported SOG cross-validation, and structured quality reporting.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from ais.data_loader.schema import REQUIRED_COLUMNS
from ais.preprocessing.config import CleaningConfig
from ais.preprocessing.kinematics import (
    compute_inter_ping_kinematics,
    haversine_distance_nm,
)


@dataclass(frozen=True)
class CleaningReport:
    """Summary audit report of the AIS data cleaning process.

    Provides transparent audit metrics for scientific reproducibility and explainability.
    Distinguishes detected data-quality anomalies from rows actually removed.

    Attributes:
        total_input_records: Total number of records passed to the cleaner.
        clean_records_retained: Number of clean records preserved in the output.
        speed_anomalies_detected: Total count of observations with derived speed > max_speed_knots.
        position_jumps_detected: Total count of observations flagged as implausible position jumps.
        suspicious_zero_jumps_filtered: Count of (0,0) discontinuous jump records removed.
        unique_vessels: Total distinct vessel MMSIs represented in the input dataset.
    """

    total_input_records: int
    clean_records_retained: int
    speed_anomalies_detected: int
    position_jumps_detected: int
    suspicious_zero_jumps_filtered: int
    unique_vessels: int

    @property
    def records_removed(self) -> int:
        """Total number of records removed during cleaning."""
        return self.total_input_records - self.clean_records_retained


def _detect_anomalies(df: pd.DataFrame, config: CleaningConfig) -> pd.DataFrame:
    """Compute and attach data-quality anomaly flags to a DataFrame with kinematics.

    Flags added:
    - is_speed_anomaly: bool
    - is_position_jump: bool
    - is_sog_inconsistent: bool
    - is_suspicious_zero_jump: bool
    """
    res = df.copy()

    # 1. Speed Anomaly: derived speed > max_speed_knots
    # NaN derived speeds (e.g. first ping of a vessel) are strictly NOT anomalies
    speed_anom = res["derived_speed_knots"].notna() & (
        res["derived_speed_knots"] > config.max_speed_knots
    )

    # Optional acceleration check
    if config.max_acceleration_knots_per_s is not None:
        grouped = res.groupby("mmsi")
        prev_speed = grouped["derived_speed_knots"].shift(1)
        dv = (res["derived_speed_knots"] - prev_speed).abs()
        accel = dv / np.maximum(res["time_delta_s"], 1.0)
        accel_anom = accel > config.max_acceleration_knots_per_s
        speed_anom = speed_anom | accel_anom

    res["is_speed_anomaly"] = speed_anom

    # 2. Position Jump: Spatial counterpart of speed anomaly representing
    # an implausible movement rate between consecutive pings
    res["is_position_jump"] = speed_anom.copy()

    # 3. Reported SOG Cross-Validation
    # Compare reported SOG (independent sensor field) against inter-ping derived speed
    if "sog" in res.columns:
        sog_valid = res["sog"].notna()
        derived_valid = res["derived_speed_knots"].notna()
        both_valid = sog_valid & derived_valid
        diff = (res["sog"] - res["derived_speed_knots"]).abs()
        res["is_sog_inconsistent"] = both_valid & (
            diff > config.sog_inconsistency_threshold_knots
        )
    else:
        res["is_sog_inconsistent"] = False

    # 4. Contextual (0,0) Jump Detection
    # If is_suspicious_zero is present (from AIS-02) or coordinates are exactly (0,0)
    if "is_suspicious_zero" not in res.columns:
        res["is_suspicious_zero"] = (res["latitude"] == 0.0) & (
            res["longitude"] == 0.0
        )

    grouped = res.groupby("mmsi")
    is_zero = res["is_suspicious_zero"].fillna(False).astype(bool)
    prev_is_zero = (
        grouped["is_suspicious_zero"]
        .shift(1)
        .astype("boolean")
        .fillna(False)
        .astype(bool)
    )
    next_is_zero = (
        grouped["is_suspicious_zero"]
        .shift(-1)
        .astype("boolean")
        .fillna(False)
        .astype(bool)
    )
    next_speed_anom = (
        grouped["is_speed_anomaly"]
        .shift(-1)
        .astype("boolean")
        .fillna(False)
        .astype(bool)
    )

    # A zero point is classified as a jump if entering it or exiting it involves an anomalous speed
    jump_in = is_zero & (~prev_is_zero) & res["is_speed_anomaly"]
    jump_out = is_zero & (~next_is_zero) & next_speed_anom

    res["is_suspicious_zero_jump"] = is_zero & (jump_in | jump_out)

    return res


def clean_ais_data(
    df: pd.DataFrame,
    config: Optional[CleaningConfig] = None,
) -> Tuple[pd.DataFrame, CleaningReport]:
    """Clean and validate an AIS DataFrame using sequence-aware kinematic checks.

    Args:
        df: Input DataFrame conforming to the canonical AIS schema (from AIS-02).
        config: Optional CleaningConfig instance. If None, default thresholds are used.

    Returns:
        Tuple of (cleaned_or_flagged_dataframe, CleaningReport).

    Raises:
        ValueError: If required columns ('mmsi', 'timestamp', 'latitude', 'longitude')
            are missing from the input DataFrame.
    """
    if config is None:
        config = CleaningConfig()

    # Check required columns
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Cannot clean AIS DataFrame: missing required column(s) {missing}"
        )

    if df.empty:
        empty_res = df.copy()
        for col in [
            "previous_timestamp",
            "time_delta_s",
            "distance_nm",
            "derived_speed_knots",
            "is_speed_anomaly",
            "is_position_jump",
            "is_sog_inconsistent",
            "is_suspicious_zero_jump",
        ]:
            if col not in empty_res.columns:
                if col == "previous_timestamp":
                    empty_res[col] = pd.Series(dtype="datetime64[ns, UTC]")
                elif col in ["time_delta_s", "distance_nm", "derived_speed_knots"]:
                    empty_res[col] = pd.Series(dtype="float64")
                else:
                    empty_res[col] = pd.Series(dtype="bool")
        report = CleaningReport(
            total_input_records=0,
            clean_records_retained=0,
            speed_anomalies_detected=0,
            position_jumps_detected=0,
            suspicious_zero_jumps_filtered=0,
            unique_vessels=0,
        )
        return empty_res, report

    # 1. Compute kinematics on input dataset
    df_kin = compute_inter_ping_kinematics(
        df, min_time_delta_seconds=config.min_time_delta_seconds
    )

    # 2. Attach anomaly flags
    df_flagged = _detect_anomalies(df_kin, config)

    # Audit statistics from input
    total_input = len(df_flagged)
    speed_anomalies_count = int(df_flagged["is_speed_anomaly"].sum())
    position_jumps_count = int(df_flagged["is_position_jump"].sum())
    unique_vessels_count = int(df_flagged["mmsi"].nunique())

    # 3. Filtering vs. Flagging
    if not config.filter_anomalies:
        # Flagging mode: retain all rows, do not delete anything
        report = CleaningReport(
            total_input_records=total_input,
            clean_records_retained=total_input,
            speed_anomalies_detected=speed_anomalies_count,
            position_jumps_detected=position_jumps_count,
            suspicious_zero_jumps_filtered=0,
            unique_vessels=unique_vessels_count,
        )
        return df_flagged, report

    # Filtering mode: determine removable rows conservatively
    # A. Suspicious zero jumps (if enabled)
    zero_jump_mask = (
        df_flagged["is_suspicious_zero_jump"]
        if config.filter_suspicious_zero_jumps
        else pd.Series(False, index=df_flagged.index)
    )

    # B. Isolated position spikes / outlier jumps:
    # Ping i has anomalous speed from i-1, and ping i+1 has anomalous speed from ping i,
    # but the direct transition between i-1 and i+1 is physically plausible (<= max_speed_knots).
    # Then ping i is definitively the isolated spike and should be removed.
    grouped = df_flagged.groupby("mmsi")
    prev_lat = grouped["latitude"].shift(1)
    prev_lon = grouped["longitude"].shift(1)
    prev_t = grouped["timestamp"].shift(1)
    next_lat = grouped["latitude"].shift(-1)
    next_lon = grouped["longitude"].shift(-1)
    next_t = grouped["timestamp"].shift(-1)
    next_speed_anom = (
        grouped["is_speed_anomaly"]
        .shift(-1)
        .astype("boolean")
        .fillna(False)
        .astype(bool)
    )

    dt_bridge = (next_t - prev_t).dt.total_seconds()
    dist_bridge = haversine_distance_nm(prev_lat, prev_lon, next_lat, next_lon)
    speed_bridge = np.where(
        dt_bridge >= config.min_time_delta_seconds,
        dist_bridge / (dt_bridge / 3600.0),
        np.nan,
    )

    is_isolated_spike = (
        df_flagged["is_speed_anomaly"]
        & next_speed_anom
        & (speed_bridge <= config.max_speed_knots)
    )

    # Identify preceding anomalous removal to avoid false terminal jump flagging
    df_flagged["_candidate_removable"] = is_isolated_spike | zero_jump_mask
    prev_removed = (
        df_flagged.groupby("mmsi")["_candidate_removable"]
        .shift(1)
        .astype("boolean")
        .fillna(False)
        .astype(bool)
    )
    df_flagged.drop(columns=["_candidate_removable"], inplace=True)

    # C. Trailing jump at the end of track:
    # Ping is the last ping of vessel, it has an anomalous jump from previous ping,
    # and the previous ping was NOT already an isolated spike / zero jump being removed.
    is_last_ping = next_t.isna()
    is_terminal_jump = df_flagged["is_speed_anomaly"] & is_last_ping & (~prev_removed)

    # Rows to remove (never delete rows due to SOG inconsistency alone)
    to_remove_mask = zero_jump_mask | is_isolated_spike | is_terminal_jump

    suspicious_zeros_removed = int(zero_jump_mask.sum())
    cleaned_df = df_flagged[~to_remove_mask].copy().reset_index(drop=True)

    # If rows were removed, recompute kinematics on the cleaned trajectory
    if bool(to_remove_mask.any()) and not cleaned_df.empty:
        cleaned_df = compute_inter_ping_kinematics(
            cleaned_df, min_time_delta_seconds=config.min_time_delta_seconds
        )
        cleaned_df = _detect_anomalies(cleaned_df, config)

    report = CleaningReport(
        total_input_records=total_input,
        clean_records_retained=len(cleaned_df),
        speed_anomalies_detected=speed_anomalies_count,
        position_jumps_detected=position_jumps_count,
        suspicious_zero_jumps_filtered=suspicious_zeros_removed,
        unique_vessels=unique_vessels_count,
    )

    return cleaned_df, report
