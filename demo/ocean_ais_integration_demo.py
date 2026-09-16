"""End-to-End Ocean + Drift -> AIS + Attribution Integration Demonstration.

Executes the complete operational pipeline connecting:
1. GIS / Remote Sensing Spill Observation
2. Copernicus Ocean Currents & ERA5 Wind Fields (REAL DATA)
3. Forward Lagrangian particle simulation (OCEAN-06 / DRIFT-04)
4. Backward Lagrangian hindcast (OCEAN-07)
5. KDE/Highest Density Region Origin Analysis (OCEAN-08)
6. Spatial Dispersion Uncertainty Estimation (DRIFT-06)
7. Drift-to-AIS Adapter & Search Request Formulation
8. Historical AIS Trajectory Reconstruction & Kinematic Interpolation (AIS-04, AIS-05)
9. Spatial & Temporal Trajectory Filtering (AIS-06, AIS-07)
10. Multi-Criteria Evidence Attribution Scoring & Ranking (ATTR-02)
11. Explainable Attribution Dossiers & Incident Narrative (ATTR-03)
12. Comprehensive GIS-Style Map Visualization
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import pandas as pd

# Member 4 modules
from ocean.currents import load_currents
from ocean.wind import load_wind
from ocean.time.synchronization import normalize_timestamp
from ocean.drift import Particle, hindcast_particles, simulate_particles
from ocean.drift.origin import analyze_origin
from ocean.drift.uncertainty import calculate_uncertainty

# Integration & Member 5 modules
from integration import (
    OceanDriftResult,
    PipelineResult,
    SpillObservation,
    adapt_ocean_drift_to_ais,
    run_spill_attribution_pipeline,
)
from ais.providers import LocalAISProvider
from ais.trajectory import reconstruct_trajectories
from ais.interpolation import InterpolationConfig, interpolate_trajectories
from ais.filtering import (
    SpatialFilterConfig,
    TemporalFilterConfig,
    filter_spatial,
    filter_temporal,
)
from attribution import (
    AttributionScoringConfig,
    explain_attribution,
    score_candidates,
)


def create_demo_ais_csv(csv_path: Path, center_lat: float, center_lon: float, origin_time: pd.Timestamp) -> Path:
    """Create controlled synthetic AIS dataset simulating realistic commercial traffic."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    
    t_minus_20 = (origin_time - pd.Timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_minus_10 = (origin_time - pd.Timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_cpa = origin_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    t_plus_10 = (origin_time + pd.Timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_plus_20 = (origin_time + pd.Timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Off-window timestamps
    t_yesterday = (origin_time - pd.Timedelta(hours=18)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Vessel 1: Crude Tanker "OCEAN_TITAN" - Passes directly through origin uncertainty zone
    # Course ~ 180° (Southbound), SOG 13.5 kts
    v1_rows = [
        f"367111000,{t_minus_20},{center_lat + 0.020:.5f},{center_lon:.5f},13.5,180.0,180.0,OCEAN_TITAN,IMO9283746,WDC1111,80,0,274,48,16.5",
        f"367111000,{t_minus_10},{center_lat + 0.010:.5f},{center_lon:.5f},13.5,180.0,180.0,OCEAN_TITAN,IMO9283746,WDC1111,80,0,274,48,16.5",
        f"367111000,{t_cpa},{center_lat + 0.001:.5f},{center_lon:.5f},13.2,180.0,180.0,OCEAN_TITAN,IMO9283746,WDC1111,80,0,274,48,16.5",
        f"367111000,{t_plus_10},{center_lat - 0.010:.5f},{center_lon:.5f},13.5,180.0,180.0,OCEAN_TITAN,IMO9283746,WDC1111,80,0,274,48,16.5",
        f"367111000,{t_plus_20},{center_lat - 0.020:.5f},{center_lon:.5f},13.5,180.0,180.0,OCEAN_TITAN,IMO9283746,WDC1111,80,0,274,48,16.5",
    ]

    # Vessel 2: Container Ship "PACIFIC_VOYAGER" - Passes east of origin (~2.0 km away)
    # Course ~ 210° (South-Southwest), SOG 18.0 kts
    v2_rows = [
        f"367222000,{t_minus_10},{center_lat + 0.015:.5f},{center_lon + 0.018:.5f},18.0,210.0,210.0,PACIFIC_VOYAGER,IMO9482103,WDC2222,70,0,330,42,13.0",
        f"367222000,{t_cpa},{center_lat + 0.003:.5f},{center_lon + 0.018:.5f},18.0,210.0,210.0,PACIFIC_VOYAGER,IMO9482103,WDC2222,70,0,330,42,13.0",
        f"367222000,{t_plus_10},{center_lat - 0.009:.5f},{center_lon + 0.018:.5f},18.0,210.0,210.0,PACIFIC_VOYAGER,IMO9482103,WDC2222,70,0,330,42,13.0",
    ]

    # Vessel 3: Bulk Carrier "ATLANTIC_HAULER" - Slower, distant transit (~15 km away)
    # Course ~ 90° (Eastbound), SOG 10.0 kts
    v3_rows = [
        f"367333000,{t_minus_10},{center_lat - 0.120:.5f},{center_lon - 0.040:.5f},10.0,90.0,90.0,ATLANTIC_HAULER,IMO9120491,WDC3333,70,0,190,28,9.5",
        f"367333000,{t_cpa},{center_lat - 0.120:.5f},{center_lon + 0.000:.5f},10.0,90.0,90.0,ATLANTIC_HAULER,IMO9120491,WDC3333,70,0,190,28,9.5",
        f"367333000,{t_plus_10},{center_lat - 0.120:.5f},{center_lon + 0.040:.5f},10.0,90.0,90.0,ATLANTIC_HAULER,IMO9120491,WDC3333,70,0,190,28,9.5",
    ]

    # Vessel 4: Tug "HARBOR_VALIANT" - Operating 18 hours prior (temporal filter exclusion)
    v4_rows = [
        f"367444000,{t_yesterday},{center_lat:.5f},{center_lon:.5f},7.0,0.0,0.0,HARBOR_VALIANT,IMO8923412,WDC4444,52,0,38,11,4.0",
    ]

    # Vessel 5: Patrol Craft "COAST_SENTINEL" - 150 km distant (spatial filter exclusion)
    v5_rows = [
        f"367555000,{t_cpa},{center_lat + 1.50:.5f},{center_lon + 1.50:.5f},22.0,270.0,270.0,COAST_SENTINEL,IMO0000000,WDC5555,51,0,45,9,2.5",
    ]

    header = "MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft\n"
    all_rows = [header] + [r + "\n" for r in v1_rows + v2_rows + v3_rows + v4_rows + v5_rows]
    csv_path.write_text("".join(all_rows), encoding="utf-8")
    return csv_path


def generate_integration_plot(
    spill: SpillObservation,
    ocean_result: OceanDriftResult,
    attr_result: Any,
    pipeline_result: PipelineResult,
    output_path: Path,
) -> None:
    """Generate high-resolution GIS visualization showing all multi-source components."""
    fig, ax = plt.subplots(figsize=(12, 10), dpi=150)

    # 1. Forward drift trajectories (subtle grey)
    df_fwd = ocean_result.forecast_trajectories
    if df_fwd is not None and not df_fwd.empty:
        for pid in df_fwd["particle_id"].unique()[:25]:
            p_data = df_fwd[df_fwd["particle_id"] == pid].sort_values("timestamp")
            ax.plot(
                p_data["longitude"],
                p_data["latitude"],
                color="#888888",
                linestyle=":",
                linewidth=0.9,
                alpha=0.6,
            )

    # 2. Backward hindcast trajectories (blue advection tracks)
    df_bw = ocean_result.hindcast_trajectories
    if df_bw is not None and not df_bw.empty:
        for pid in df_bw["particle_id"].unique()[:35]:
            p_data = df_bw[df_bw["particle_id"] == pid].sort_values("timestamp")
            ax.plot(
                p_data["longitude"],
                p_data["latitude"],
                color="#3b82f6",
                linestyle="-",
                linewidth=1.0,
                alpha=0.5,
            )

    # 3. Observed spill centroid & particle spread (red)
    ax.scatter(
        [spill.longitude],
        [spill.latitude],
        color="#dc2626",
        marker="o",
        s=140,
        edgecolor="black",
        linewidth=1.5,
        zorder=10,
        label=f"Observed Spill Centroid ({spill.timestamp.strftime('%H:%M')} UTC)",
    )

    # 4. Probable origin (bright green star)
    orig_lat = ocean_result.probable_origin_latitude
    orig_lon = ocean_result.probable_origin_longitude
    orig_time = ocean_result.probable_origin_timestamp
    ax.scatter(
        [orig_lon],
        [orig_lat],
        color="#22c55e",
        marker="*",
        s=260,
        edgecolor="black",
        linewidth=1.2,
        zorder=12,
        label=f"Probable Release Origin ({orig_time.strftime('%H:%M')} UTC)",
    )

    # 5. 95% Uncertainty ellipse
    unc_radius_km = ocean_result.uncertainty_radius_km
    # Degree conversions
    d_lat = unc_radius_km / 111.195
    d_lon = unc_radius_km / (111.195 * np.cos(np.radians(orig_lat)))
    ellipse = patches.Ellipse(
        (orig_lon, orig_lat),
        width=2 * d_lon,
        height=2 * d_lat,
        edgecolor="#e11d48",
        facecolor="#f43f5e",
        alpha=0.18,
        linestyle="--",
        linewidth=2.0,
        zorder=5,
        label=f"95% Empirical Uncertainty Zone ({unc_radius_km:.2f} km)",
    )
    ax.add_patch(ellipse)

    # 6. AIS Vessel trajectories and closest points of approach
    vessel_colors = ["#7c3aed", "#d97706", "#0284c7", "#059669"]
    ranked_cands = attr_result.ranked_candidates

    # Plot trajectories from temporal filter result
    tf_df = pipeline_result.temporal_filter_result.to_dataframe()
    if not tf_df.empty:
        for idx, cand in enumerate(ranked_cands[:3]):
            v_data = tf_df[tf_df["mmsi"] == cand.mmsi].sort_values("timestamp")
            if v_data.empty:
                continue
            color = vessel_colors[idx % len(vessel_colors)]
            v_name = cand.vessel.vessel_name or f"MMSI {cand.mmsi}"

            # Continuous track line
            ax.plot(
                v_data["longitude"],
                v_data["latitude"],
                color=color,
                linewidth=2.2,
                alpha=0.85,
                zorder=8,
                label=f"Rank {cand.rank}: {v_name} (Score: {cand.score.overall_score:.3f})",
            )

            # Mark Closest Approach Point
            min_row = v_data.loc[v_data["distance_km"].idxmin()]
            ax.scatter(
                [min_row["longitude"]],
                [min_row["latitude"]],
                color=color,
                marker="^",
                s=120,
                edgecolor="black",
                zorder=11,
            )
            ax.annotate(
                f"#{cand.rank} {v_name}\n({cand.evidence.min_distance_km:.2f} km @ {cand.evidence.time_of_closest_approach.strftime('%H:%M')}Z)",
                xy=(min_row["longitude"], min_row["latitude"]),
                xytext=(15, -15),
                textcoords="offset points",
                fontsize=8.5,
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=color, alpha=0.9),
                arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0", color=color),
                zorder=15,
            )

    ax.set_title(
        "Oil Spill Attribution Pipeline: Ocean Drift Hindcast & AIS Vessel Ranking",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )
    ax.set_xlabel("Longitude (°E)", fontsize=11, fontweight="medium")
    ax.set_ylabel("Latitude (°N)", fontsize=11, fontweight="medium")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="upper left", framealpha=0.92, fontsize=9.0)

    # Save artifact
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    """Execute end-to-end integration demo script."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("=" * 80)
    print("OIL SPILL ATTRIBUTION SYSTEM -- END-TO-END INTEGRATION DEMO")
    print("Connecting: Ocean + Drift (Member 4) -> AIS + Attribution (Member 5)")
    print("=" * 80)

    # 1. Environmental Data Loading (REAL DATA)
    current_path = Path("data/sample/copernicus/current_test.nc")
    wind_path = Path("data/sample/era5/wind_test.nc")

    if not current_path.is_file() or not wind_path.is_file():
        print(f"ERROR: Environmental datasets not found.")
        print(f"  Currents: {current_path}")
        print(f"  Wind:     {wind_path}")
        sys.exit(1)

    current_ds = load_currents(current_path)
    wind_ds = load_wind(wind_path)

    # 2. Derive Valid Observation Time & Location
    c_times = pd.Index(current_ds["time"].values)
    w_times = pd.Index(wind_ds["time"].values)
    overlap = c_times.intersection(w_times)

    if len(overlap) < 5:
        print("ERROR: Insufficient time overlap in sample environmental datasets.")
        sys.exit(1)

    obs_time_naive = overlap[-2]
    obs_time_utc = normalize_timestamp(obs_time_naive, assume_naive_utc=True)
    obs_lon = float(current_ds["longitude"].values.mean())
    obs_lat = float(current_ds["latitude"].values.mean())

    # 3. Create Observed Spill Observation (SYNTHETIC SPILL DETECTED IN SATELLITE)
    spill = SpillObservation(
        spill_id="DET-2025-0101-001",
        latitude=obs_lat,
        longitude=obs_lon,
        timestamp=obs_time_utc,
        area_sq_m=420000.0,
    )

    # 4. Generate Aligned AIS Dataset (SYNTHETIC CONTROLLED TRAFFIC)
    # Align traffic with the probable release origin computed by the ocean model
    df_preview = hindcast_particles(
        [Particle(1, obs_lon, obs_lat)],
        current_dataset=current_ds,
        wind_dataset=wind_ds,
        observation_time=obs_time_utc,
        duration_seconds=14400,
        timestep_seconds=3600,
    )
    preview_origin = analyze_origin(df_preview)
    best_cand = preview_origin["best_candidate"]
    origin_time = pd.Timestamp(best_cand.timestamp)
    origin_lat = float(best_cand.region.centroid_lat)
    origin_lon = float(best_cand.region.centroid_lon)

    demo_ais_csv = Path("demo/output/demo_synthetic_ais.csv")
    create_demo_ais_csv(demo_ais_csv, origin_lat, origin_lon, origin_time)

    # 5. Run Integrated Pipeline
    result: PipelineResult = run_spill_attribution_pipeline(
        spill=spill,
        current_ds=current_ds,
        wind_ds=wind_ds,
        ais_source=demo_ais_csv,
        num_particles=60,
        forward_steps=2,
        hindcast_duration_hours=4.0,
        timestep_seconds=3600,
        uncertainty_confidence=0.95,
        ais_before_minutes=30.0,
        ais_after_minutes=30.0,
        ais_buffer_km=1.5,
        explanation_top_n=3,
    )

    # 6. Print Formatted Inspection Summary (STEP 10 FORMAT)
    print("\n------------------------------------------")
    print("OIL SPILL")
    print("------------------------------------------")
    print(f"Observation time:     {spill.timestamp.isoformat()} (UTC)")
    print(f"Observation location: {spill.latitude:.4f}° N, {spill.longitude:.4f}° E")
    print(f"Spill area/geometry:  {spill.area_sq_m:,.0f} m² (Point centroid / synthetic spread)")

    print("\n------------------------------------------")
    print("OCEAN + DRIFT")
    print("------------------------------------------")
    print(f"Forward forecast:     {len(result.ocean_result.forecast_trajectories)} particle steps forward")
    print(f"Hindcast:             {len(result.ocean_result.hindcast_trajectories)} particle steps backward (4 hours)")
    print(f"Probable origin:      {result.ocean_result.probable_origin_latitude:.4f}° N, {result.ocean_result.probable_origin_longitude:.4f}° E")
    print(f"Origin time:          {result.ocean_result.probable_origin_timestamp.isoformat()} (UTC)")
    print(f"Origin score:         {result.ocean_result.probable_origin_score:.4f} (relative heuristic)")
    print(f"Uncertainty:          {result.ocean_result.uncertainty_radius_km:.2f} km radius (95% empirical confidence)")

    print("\n------------------------------------------")
    print("AIS SEARCH")
    print("------------------------------------------")
    print(f"AIS source:           Local Provider ({demo_ais_csv.name}) [Synthetic Traffic]")
    print(f"Search region:        Center ({result.search_request.latitude:.4f}°N, {result.search_request.longitude:.4f}°E), Radius {result.search_request.effective_radius_km:.2f} km")
    print(f"Search start:         {result.search_request.start_time.isoformat()} (UTC)")
    print(f"Search end:           {result.search_request.end_time.isoformat()} (UTC)")
    print(f"Number of AIS positions:    {len(result.raw_ais_matches)} raw fixes matched")
    print(f"Number of candidate vessels: {len(result.attribution_result.ranked_candidates)} vessels evaluated")

    print("\n------------------------------------------")
    print("ATTRIBUTION")
    print("------------------------------------------")
    print(f"{'Rank':<5} | {'Vessel':<18} | {'MMSI/IMO':<20} | {'Score':<7} | {'Key Evidence'}")
    print("-" * 80)
    for cand in result.attribution_result.ranked_candidates:
        v_name = cand.vessel.vessel_name or "Unknown"
        mmsi_imo = f"{cand.mmsi} / {cand.vessel.imo or 'N/A'}"
        score_str = f"{cand.score.overall_score:.3f}"
        evidence_summary = (
            f"Min dist: {cand.evidence.min_distance_km:.2f} km @ "
            f"{cand.evidence.time_of_closest_approach.strftime('%H:%M')}Z | "
            f"Transit: {cand.evidence.mean_speed_knots or 0.0:.1f} kts"
        )
        print(f"{cand.rank:<5} | {v_name:<18} | {mmsi_imo:<20} | {score_str:<7} | {evidence_summary}")

    print("\n------------------------------------------")
    print("WORKFLOW STATUS")
    print("------------------------------------------")
    for stage, status in result.stage_statuses.items():
        print(f"{stage:<23} {status}")
    print("------------------------------------------")

    # 7. Generate Visualization
    vis_path = Path("demo/output/ocean_ais_integration_demo.png")
    generate_integration_plot(
        spill=spill,
        ocean_result=result.ocean_result,
        attr_result=result.attribution_result,
        pipeline_result=result,
        output_path=vis_path,
    )
    print(f"\nIntegration visualization successfully generated at:\n  {vis_path.resolve()}\n")

    # 8. Data Provenance Summary
    print("==========================================")
    print("DATA PROVENANCE & REALISM CLASSIFICATION")
    print("==========================================")
    print("REAL DATA USED:")
    print(f"  - Copernicus Ocean Surface Currents: {current_path.resolve()}")
    print(f"  - ECMWF ERA5 10m Wind Fields:        {wind_path.resolve()}")
    print("SYNTHETIC DATA USED:")
    print(f"  - Satellite Spill Observation:      Centroid derived from sample ocean domain")
    print(f"  - Historical AIS Vessel Traffic:    NOAA-standard formatted test transits ({demo_ais_csv.resolve()})")
    print("  (Note: No synthetic output is presented as real-world evidentiary truth)")
    print("=" * 80)


if __name__ == "__main__":
    main()
