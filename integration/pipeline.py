"""End-to-End Spill Attribution Pipeline Orchestrator.

Integrates the full operational sequence:
1. Observed spill geometry and timestamp (GIS / Remote Sensing)
2. Environmental currents & wind ingestion (Member 4 / Ocean)
3. Forward simulation & backward hindcast (Member 4 / Drift)
4. Candidate origin identification & spatial uncertainty (Member 4 / DRIFT-06)
5. Drift-to-AIS search request & origin adaptation (Integration Adapter)
6. Historical AIS filtering & trajectory reconstruction (Member 5 / AIS)
7. Multi-criteria evidence scoring & candidate ranking (Member 5 / ATTR-02)
8. Explainable attribution reporting & narrative synthesis (Member 5 / ATTR-03)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
import xarray as xr

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
from ais.trajectory import (
    TrajectoryConfig,
    TrajectoryResult,
    reconstruct_trajectories,
)
from attribution import (
    AttributionExplanationReport,
    AttributionResult,
    AttributionScoringConfig,
    OriginMetadata,
    explain_attribution,
    score_candidates,
)
from gis.geometry.models import (
    BoundingBox,
    Coordinate,
    LineString,
    MultiPolygon,
    OilSpillGeometry,
    Point as GisPoint,
    Polygon as GisPolygon,
)
from gis.measurements.models import SpillMeasurement, measure_oil_spill
from gis.visualization.geojson_layers import (
    combine_feature_collection,
    create_bbox_layer,
    create_drift_cone_layer,
    create_spill_layer,
    create_vessel_track_layer,
)
from integration.adapters.gis_ocean_adapter import (
    extract_spill_observation,
    initialize_particles_from_spill,
)
from integration.adapters.ocean_ais_adapter import adapt_ocean_drift_to_ais
from integration.contracts.spill_contract import OceanDriftResult, SpillObservation
from ocean.drift import Particle, hindcast_particles, simulate_particles
from ocean.drift.origin import analyze_origin
from ocean.drift.uncertainty import calculate_uncertainty


@dataclass
class PipelineResult:
    """Consolidated result container for the complete end-to-end attribution pipeline."""

    spill_observation: SpillObservation
    ocean_result: OceanDriftResult
    search_request: AISSearchRequest
    integration_result: AISIntegrationResult
    origin_metadata: OriginMetadata
    raw_ais_matches: pd.DataFrame
    trajectory_result: TrajectoryResult
    interpolation_result: InterpolationResult
    spatial_filter_result: SpatialFilterResult
    temporal_filter_result: TemporalFilterResult
    attribution_result: AttributionResult
    explanation_report: AttributionExplanationReport
    spill_measurement: Optional[SpillMeasurement] = None
    gis_layers: Optional[Dict[str, Any]] = None
    stage_statuses: Dict[str, str] = field(default_factory=dict)
    execution_notes: List[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        """True if all workflow stages completed with PASS status."""
        return all(status == "PASS" for status in self.stage_statuses.values())


def run_spill_attribution_pipeline(
    spill: Union[OilSpillGeometry, SpillObservation, GisPolygon, MultiPolygon],
    current_ds: xr.Dataset,
    wind_ds: xr.Dataset,
    ais_source: Union[AISProvider, str, Path, pd.DataFrame],
    num_particles: int = 50,
    forward_steps: int = 2,
    hindcast_duration_hours: float = 4.0,
    timestep_seconds: int = 3600,
    uncertainty_confidence: float = 0.95,
    ais_before_minutes: float = 30.0,
    ais_after_minutes: float = 30.0,
    ais_buffer_km: float = 1.0,
    scoring_config: Optional[AttributionScoringConfig] = None,
    explanation_top_n: int = 5,
    random_seed: Optional[int] = 42,
) -> PipelineResult:
    """Execute the full end-to-end Oil Spill Attribution pipeline.

    Args:
        spill: OilSpillGeometry, SpillObservation, or Polygon with UTC timestamp and geometry.
        current_ds: Copernicus currents xarray Dataset.
        wind_ds: ERA5 wind xarray Dataset.
        ais_source: AISProvider instance, Path to AIS CSV/directory, or preloaded DataFrame.
        num_particles: Number of simulation particles initialized across observed spill (default: 50).
        forward_steps: Number of forward forecast simulation steps (default: 2).
        hindcast_duration_hours: Duration in hours for backward hindcast (default: 4.0).
        timestep_seconds: Simulation timestep in seconds (default: 3600 = 1 hour).
        uncertainty_confidence: Empirical confidence fraction for dispersion radius (default: 0.95).
        ais_before_minutes: Query window in minutes prior to origin time (default: 30.0).
        ais_after_minutes: Query window in minutes after origin time (default: 30.0).
        ais_buffer_km: Spatial search buffer in km added to uncertainty radius (default: 1.0).
        scoring_config: Optional AttributionScoringConfig for multi-criteria weights.
        explanation_top_n: Number of top candidate vessels to explain in detail (default: 5).
        random_seed: Random seed for deterministic particle dispersion (default: 42).

    Returns:
        PipelineResult: Complete trace of all intermediate results, metrics, and final report.
    """
    statuses: Dict[str, str] = {
        "GIS → Ocean/Drift": "FAIL",
        "Ocean/Drift → AIS": "FAIL",
        "AIS → Attribution": "FAIL",
        "End-to-end workflow": "FAIL",
    }
    notes: List[str] = []

    # -----------------------------------------------------------------------
    # STAGE 1: GIS Spill Characterization & Ocean/Drift Modelling
    # -----------------------------------------------------------------------
    spill_obs, measurement = extract_spill_observation(spill)

    # Initialize Lagrangian particles distributed across observed spill geometry
    particles = initialize_particles_from_spill(
        spill=spill,
        num_particles=num_particles,
        random_seed=random_seed,
    )

    # Forward drift simulation (forecast)
    df_forward = simulate_particles(
        particles=particles,
        current_dataset=current_ds,
        wind_dataset=wind_ds,
        start_time=spill_obs.timestamp,
        num_steps=forward_steps,
        timestep_seconds=timestep_seconds,
    )

    # Backward hindcast simulation
    hindcast_duration_sec = int(hindcast_duration_hours * 3600)
    df_backward = hindcast_particles(
        particles=particles,
        current_dataset=current_ds,
        wind_dataset=wind_ds,
        observation_time=spill_obs.timestamp,
        duration_seconds=hindcast_duration_sec,
        timestep_seconds=timestep_seconds,
    )

    # Probable origin analysis (OCEAN-08)
    origin_results = analyze_origin(df_backward, coverage_level=0.5)
    best_candidate = origin_results["best_candidate"]
    ranked_candidates = origin_results["ranked_candidates"]

    # Spatial uncertainty analysis (DRIFT-06)
    unc_result = calculate_uncertainty(
        trajectories=df_backward,
        timestamp=best_candidate.timestamp,
        confidence_level=uncertainty_confidence,
    )

    # Build comprehensive OceanDriftResult
    ocean_res = OceanDriftResult(
        spill_observation=spill_obs,
        best_candidate=best_candidate,
        ranked_candidates=ranked_candidates,
        uncertainty=unc_result,
        hindcast_trajectories=df_backward,
        forecast_trajectories=df_forward,
    )
    statuses["GIS → Ocean/Drift"] = "PASS"
    notes.append(
        f"Stage 1 completed: Spill measured ({measurement.area_sq_km:.3f} km²), "
        f"{len(particles)} particles initialized, forward/backward drift, origin, and uncertainty computed."
    )

    # -----------------------------------------------------------------------
    # STAGE 2: Ocean/Drift → AIS Processing
    # -----------------------------------------------------------------------
    integration_res, origin_meta = adapt_ocean_drift_to_ais(
        ocean_result=ocean_res,
        spill_observation=spill_obs,
        buffer_km=ais_buffer_km,
        before_minutes=ais_before_minutes,
        after_minutes=ais_after_minutes,
    )
    search_req = integration_res.search_request

    # Query AIS data
    if isinstance(ais_source, AISProvider):
        provider = ais_source
    elif isinstance(ais_source, (str, Path)):
        provider = LocalAISProvider(ais_source)
    elif isinstance(ais_source, pd.DataFrame):
        # In-memory DataFrame query helper
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

    # Ensure timestamp column has UTC datetime dtype (even when df_matched is empty)
    if "timestamp" in df_matched.columns and not pd.api.types.is_datetime64_any_dtype(df_matched["timestamp"]):
        df_matched["timestamp"] = pd.to_datetime(df_matched["timestamp"], utc=True)

    # Reconstruct trajectories
    traj_result = reconstruct_trajectories(df_matched)

    # Kinematic interpolation
    interp_result = interpolate_trajectories(
        traj_result,
        time_step_seconds=300.0,
        config=InterpolationConfig(max_gap_seconds=1800.0),
    )

    # Apply spatial trajectory filter
    spatial_result = filter_spatial(
        data=interp_result,
        config=SpatialFilterConfig(buffer_km=ais_buffer_km),
        origin_data=integration_res,
    )

    # Apply temporal trajectory filter
    temporal_result = filter_temporal(
        data=spatial_result,
        config=TemporalFilterConfig(
            before_minutes=ais_before_minutes,
            after_minutes=ais_after_minutes,
        ),
        origin_data=integration_res,
    )
    # If no observations remained, ensure canonical columns exist so validation passes cleanly
    if temporal_result.data.empty:
        for col in ["mmsi", "timestamp", "latitude", "longitude", "distance_km"]:
            if col not in temporal_result.data.columns:
                if col == "mmsi":
                    temporal_result.data[col] = pd.Series([], dtype="int64")
                elif col == "timestamp":
                    temporal_result.data[col] = pd.Series([], dtype="datetime64[ns, UTC]")
                else:
                    temporal_result.data[col] = pd.Series([], dtype="float64")

    statuses["Ocean/Drift → AIS"] = "PASS"
    notes.append(
        f"Stage 2 completed: AIS queried ({len(df_matched)} fixes), reconstructed, interpolated, and filtered."
    )

    # -----------------------------------------------------------------------
    # STAGE 3: AIS → Attribution Scoring & Explanation
    # -----------------------------------------------------------------------
    attr_result = score_candidates(
        data=temporal_result,
        origin_data=origin_meta,
        config=scoring_config,
    )

    explanation_report = explain_attribution(
        result=attr_result,
        top_n=explanation_top_n,
    )
    statuses["AIS → Attribution"] = "PASS"
    statuses["End-to-end workflow"] = "PASS"
    notes.append(
        f"Stage 3 completed: Attributed {len(attr_result.ranked_candidates)} candidate vessels with explanation report."
    )

    # -----------------------------------------------------------------------
    # STAGE 4: GIS Layer Generation for Dashboard / Map Export
    # -----------------------------------------------------------------------
    gis_features: List[Dict[str, Any]] = []

    # 1. Spill geometry feature
    if isinstance(spill, OilSpillGeometry):
        spill_geom_model = spill
    else:
        poly = spill_obs.polygon if isinstance(spill_obs.polygon, (GisPolygon, MultiPolygon)) else None
        if poly is None:
            d_deg = math.sqrt(max(measurement.area_sq_m, 1000.0) / math.pi) / 111320.0
            c_lon, c_lat = spill_obs.longitude, spill_obs.latitude
            poly = GisPolygon(
                exterior=[
                    (c_lon - d_deg, c_lat - d_deg),
                    (c_lon + d_deg, c_lat - d_deg),
                    (c_lon + d_deg, c_lat + d_deg),
                    (c_lon - d_deg, c_lat + d_deg),
                    (c_lon - d_deg, c_lat - d_deg),
                ]
            )
        dt = spill_obs.timestamp.to_pydatetime() if hasattr(spill_obs.timestamp, "to_pydatetime") else spill_obs.timestamp
        spill_geom_model = OilSpillGeometry(
            spill_id=spill_obs.spill_id or "spill_detected",
            geometry=poly,
            detection_timestamp=dt,
            source_sensor=spill_obs.source_sensor or "Sentinel-1 SAR",
            confidence=spill_obs.confidence if spill_obs.confidence is not None else 0.95,
        )

    gis_features.append(create_spill_layer(spill_geom_model, measurement))
    gis_features.append(create_bbox_layer(measurement.bounding_box, label="Spill Bounding Box"))

    # 2. Candidate vessel track features
    if not temporal_result.data.empty and "mmsi" in temporal_result.data.columns:
        for mmsi, group in temporal_result.data.groupby("mmsi"):
            group_sorted = group.sort_values("timestamp")
            if len(group_sorted) >= 2:
                coords = [
                    (float(r["longitude"]), float(r["latitude"]))
                    for _, r in group_sorted.iterrows()
                ]
                line_geom = LineString(coordinates=coords)
                cand_score = None
                cand_rank = None
                for cand in attr_result.ranked_candidates:
                    if str(cand.mmsi) == str(mmsi):
                        cand_score = cand.score.overall_score
                        cand_rank = cand.rank
                        break
                vessel_info = {
                    "mmsi": int(mmsi),
                    "vessel_name": f"Vessel {mmsi}",
                    "attribution_score": cand_score,
                    "rank": cand_rank,
                }
                gis_features.append(create_vessel_track_layer(line_geom, vessel_info=vessel_info))

    gis_fc = combine_feature_collection(gis_features)
    notes.append(f"Stage 4 completed: Generated GIS FeatureCollection with {len(gis_features)} layers.")

    return PipelineResult(
        spill_observation=spill_obs,
        ocean_result=ocean_res,
        search_request=search_req,
        integration_result=integration_res,
        origin_metadata=origin_meta,
        raw_ais_matches=df_matched,
        trajectory_result=traj_result,
        interpolation_result=interp_result,
        spatial_filter_result=spatial_result,
        temporal_filter_result=temporal_result,
        attribution_result=attr_result,
        explanation_report=explanation_report,
        spill_measurement=measurement,
        gis_layers=gis_fc,
        stage_statuses=statuses,
        execution_notes=notes,
    )
