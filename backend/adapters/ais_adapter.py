"""AIS Trajectory & Filtering Adapter (Member 5 Integration).

Bridges the backend to Member 5 AIS ingestion, trajectory reconstruction, kinematic interpolation,
and spatial/temporal filtering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import pandas as pd

from ais.filtering import (
    SpatialFilterConfig,
    SpatialFilterResult,
    TemporalFilterConfig,
    TemporalFilterResult,
    filter_spatial,
    filter_temporal,
)
from ais.integration.adapter import AISIntegrationResult
from ais.integration.search_request import AISSearchRequest
from ais.interpolation import (
    InterpolationConfig,
    InterpolationResult,
    interpolate_trajectories,
)
from ais.providers import LocalAISProvider
from ais.providers.base import AISProvider
from ais.trajectory import TrajectoryConfig, TrajectoryResult, reconstruct_trajectories
from backend.core.config import settings
from backend.core.logging import logger


class AISAdapter:
    """Service adapter interfacing with Member 5 AIS components."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or settings.AIS_DATA_DIR

    def resolve_ais_source(
        self, custom_path: Optional[Union[str, Path, pd.DataFrame]] = None
    ) -> Union[AISProvider, Path, pd.DataFrame]:
        """Resolve AIS source: custom path/dataframe, configured directory, or demo fallback."""
        if isinstance(custom_path, (pd.DataFrame, AISProvider)):
            return custom_path
        if custom_path:
            p = Path(custom_path)
            if p.exists():
                return p

        # Check configured AIS directory
        if self.data_dir.exists() and any(self.data_dir.glob("*.csv")):
            return self.data_dir

        # Check demo synthetic AIS CSV
        demo_ais = settings.DEMO_OUTPUT_DIR / "demo_synthetic_ais.csv"
        if demo_ais.exists():
            return demo_ais

        logger.warning("No AIS dataset found at configured location; using demo synthetic fallback.")
        return demo_ais

    @staticmethod
    def query_and_filter(
        ais_source: Union[AISProvider, str, Path, pd.DataFrame],
        search_req: AISSearchRequest,
        integration_res: AISIntegrationResult,
        ais_buffer_km: float = 1.0,
        ais_before_minutes: float = 30.0,
        ais_after_minutes: float = 30.0,
    ) -> tuple[pd.DataFrame, TrajectoryResult, InterpolationResult, SpatialFilterResult, TemporalFilterResult]:
        """Execute AIS query, trajectory reconstruction, interpolation, and spatio-temporal filtering."""
        if isinstance(ais_source, AISProvider):
            provider = ais_source
        elif isinstance(ais_source, (str, Path)):
            provider = LocalAISProvider(str(ais_source))
        elif isinstance(ais_source, pd.DataFrame):
            from ais.filtering.spatial import filter_by_radius
            from ais.filtering.temporal import filter_by_time_window

            df_in = ais_source.copy()
            if "distance_km" not in df_in.columns:
                df_spat = filter_by_radius(
                    df_in,
                    center_latitude=search_req.latitude,
                    center_longitude=search_req.longitude,
                    radius_km=search_req.effective_radius_km,
                )
            else:
                df_spat = df_in[df_in["distance_km"] <= search_req.effective_radius_km]

            df_matched = filter_by_time_window(
                df_spat,
                start_time=search_req.start_time,
                end_time=search_req.end_time,
            )
            provider = None
        else:
            raise TypeError(f"Unsupported ais_source type: {type(ais_source)}")

        if provider is not None:
            df_matched = provider.fetch_ais_data(search_req)

        # Ensure timestamp is UTC datetime
        if "timestamp" in df_matched.columns and not pd.api.types.is_datetime64_any_dtype(df_matched["timestamp"]):
            df_matched["timestamp"] = pd.to_datetime(df_matched["timestamp"], utc=True)

        # Trajectory reconstruction
        traj_result = reconstruct_trajectories(df_matched)

        # Kinematic interpolation
        interp_result = interpolate_trajectories(
            traj_result,
            time_step_seconds=300.0,
            config=InterpolationConfig(max_gap_seconds=1800.0),
        )

        # Spatial filter
        spatial_result = filter_spatial(
            data=interp_result,
            config=SpatialFilterConfig(buffer_km=ais_buffer_km),
            origin_data=integration_res,
        )

        # Temporal filter
        temporal_result = filter_temporal(
            data=spatial_result,
            config=TemporalFilterConfig(
                before_minutes=ais_before_minutes,
                after_minutes=ais_after_minutes,
            ),
            origin_data=integration_res,
        )

        # Ensure canonical columns exist if empty
        if temporal_result.data.empty:
            for col in ["mmsi", "timestamp", "latitude", "longitude", "distance_km"]:
                if col not in temporal_result.data.columns:
                    if col == "mmsi":
                        temporal_result.data[col] = pd.Series([], dtype="int64")
                    elif col == "timestamp":
                        temporal_result.data[col] = pd.Series([], dtype="datetime64[ns, UTC]")
                    else:
                        temporal_result.data[col] = pd.Series([], dtype="float64")

        return df_matched, traj_result, interp_result, spatial_result, temporal_result
