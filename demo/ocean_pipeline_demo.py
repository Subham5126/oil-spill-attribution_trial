"""
Standalone Demonstration of the OCEAN-04 through OCEAN-08 Pipeline.
"""

import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt

# Project imports
from ocean.currents import load_currents
from ocean.wind import load_wind
from ocean.time.synchronization import normalize_timestamp
from ocean.interpolation.environment import interpolate_currents, interpolate_wind
from ocean.drift import Particle, simulate_particles, hindcast_particles
from ocean.drift.origin import analyze_origin
from ocean.drift.uncertainty import calculate_uncertainty


def main():
    print("=" * 50)
    print("OCEAN-04 -> OCEAN-08 & DRIFT-06 DEMO")
    print("=" * 50)
    
    # 1. Load Environmental Data
    current_path = Path("data/sample/copernicus/current_test.nc")
    wind_path = Path("data/sample/era5/wind_test.nc")
    
    if not current_path.is_file() or not wind_path.is_file():
        print("ERROR: Required sample files not found.")
        print(f"Currents: {current_path.absolute()}")
        print(f"Wind: {wind_path.absolute()}")
        sys.exit(1)
        
    current_ds = load_currents(current_path)
    wind_ds = load_wind(wind_path)
    
    # 2. Select a valid overlap time and location
    # Get intersection of times
    c_times = pd.Index(current_ds["time"].values)
    w_times = pd.Index(wind_ds["time"].values)
    
    # Select a time near the end of the available overlap to allow hindcasting backward
    overlap_times = c_times.intersection(w_times)
    if len(overlap_times) < 5:
        print("ERROR: Insufficient time overlap in sample datasets for demonstration.")
        sys.exit(1)
        
    obs_time_naive = overlap_times[-2] 
    
    # OCEAN-05: Normalize timestamp to UTC
    obs_time_utc = normalize_timestamp(obs_time_naive, assume_naive_utc=True)
    
    # Select a central location
    lon = float(current_ds["longitude"].values.mean())
    lat = float(current_ds["latitude"].values.mean())
    
    print("\nObservation:")
    print(f"  Location: {lat:.4f} N, {lon:.4f} E")
    print(f"  Time UTC: {obs_time_utc}")
    
    # 3. OCEAN-04 Demonstration
    try:
        time_arg = obs_time_utc.tz_localize(None)
        uo, vo = interpolate_currents(current_ds, [lon], [lat], time_arg)
        u10, v10 = interpolate_wind(wind_ds, [lon], [lat], time_arg)
        
        print("\nEnvironment (OCEAN-04):")
        print(f"  Current: uo = {float(uo[0]):.4f} m/s, vo = {float(vo[0]):.4f} m/s")
        print(f"  Wind:    u10 = {float(u10[0]):.4f} m/s, v10 = {float(v10[0]):.4f} m/s")
    except Exception as e:
        print(f"OCEAN-04 Interpolation failed: {e}")
        sys.exit(1)
        
    # 4. Create Demo Particles (Synthetic Observation)
    num_particles = 50
    np.random.seed(42) # Deterministic demo
    # Small synthetic spread
    initial_lons = np.random.normal(lon, 0.005, num_particles)
    initial_lats = np.random.normal(lat, 0.005, num_particles)
    
    particles = [Particle(i+1, initial_lons[i], initial_lats[i]) for i in range(num_particles)]
    
    # 5. OCEAN-06: Forward Simulation Demo (2 steps forward)
    # Just to show particles moving forward
    print("\nParticles:")
    print("  Demo particle initialization - synthetic observation")
    print(f"  Initial: {num_particles} active particles")
    
    forward_steps = 2
    timestep_sec = 3600
    print(f"  Forward steps: {forward_steps} (timestep: {timestep_sec}s)")
    df_forward = simulate_particles(particles, current_ds, wind_ds, obs_time_utc, num_steps=forward_steps, timestep_seconds=timestep_sec)
    
    # 6. OCEAN-07: Backward Hindcast Demo (4 steps backward)
    hindcast_duration = 3600 * 4
    print(f"  Hindcast steps: {hindcast_duration // timestep_sec} (timestep: {timestep_sec}s)")
    
    # Use the original synthetic particles as the "observed" spill at obs_time_utc
    df_backward = hindcast_particles(particles, current_ds, wind_ds, obs_time_utc, duration_seconds=hindcast_duration, timestep_seconds=timestep_sec)
    
    # 7. OCEAN-08: Origin Analysis
    print("\nOCEAN-08:")
    try:
        origin_results = analyze_origin(df_backward, coverage_level=0.5)
        best_candidate = origin_results["best_candidate"]
        print("  Best candidate origin:")
        print(f"    Time: {best_candidate.timestamp}")
        print(f"    Latitude: {best_candidate.region.centroid_lat:.4f}")
        print(f"    Longitude: {best_candidate.region.centroid_lon:.4f}")
        print(f"    Relative heuristic origin score: {best_candidate.heuristic_score:.4f}")
        
        # DRIFT-06: Uncertainty Analysis
        print("\nDRIFT-06:")
        try:
            unc_result = calculate_uncertainty(df_backward, timestamp=best_candidate.timestamp, confidence_level=0.95)
            print("  Empirical spatial uncertainty estimate:")
            print(f"    Timestamp: {unc_result.timestamp}")
            print(f"    Particle count: {unc_result.particle_count}")
            print(f"    Centroid: {unc_result.centroid_latitude:.4f} N, {unc_result.centroid_longitude:.4f} E")
            print(f"    Spread: {unc_result.spread_km:.4f} km")
            print(f"    95% uncertainty radius: {unc_result.uncertainty_radius_km:.4f} km")
            print("    Bounds:")
            print(f"      Latitude: {unc_result.min_latitude:.4f} to {unc_result.max_latitude:.4f}")
            print(f"      Longitude: {unc_result.min_longitude:.4f} to {unc_result.max_longitude:.4f}")
        except Exception as e:
            print(f"  DRIFT-06 Uncertainty Analysis failed: {e}")
            unc_result = None
            
    except Exception as e:
        print(f"  OCEAN-08 Analysis failed: {e}")
        best_candidate = None
        unc_result = None

    print("=" * 50)
    
    # 8. Visualization
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Plot forward trajectories (grey lines)
    for pid in df_forward["particle_id"].unique():
        p_data = df_forward[df_forward["particle_id"] == pid].sort_values("timestamp")
        ax.plot(p_data["longitude"], p_data["latitude"], color="lightgrey", linewidth=1.0, alpha=0.5)
        
    # Plot backward trajectories (blue lines)
    for pid in df_backward["particle_id"].unique():
        p_data = df_backward[df_backward["particle_id"] == pid].sort_values("timestamp")
        ax.plot(p_data["longitude"], p_data["latitude"], color="cornflowerblue", linewidth=1.0, alpha=0.7)
        
    # Plot initial observed particles (red dots)
    ax.scatter(initial_lons, initial_lats, color="red", s=10, zorder=5, label=f"Observation ({obs_time_utc.strftime('%H:%M')} UTC)")
    
    # Plot best candidate origin (green star)
    if best_candidate is not None:
        ax.scatter(best_candidate.region.centroid_lon, best_candidate.region.centroid_lat, 
                   color="lime", marker="*", s=200, edgecolor="black", zorder=10, 
                   label=f"Best Candidate Origin ({best_candidate.timestamp.strftime('%H:%M')} UTC)")
                   
        # Highlight all particles at that candidate timestamp
        cand_time_data = df_backward[df_backward["timestamp"] == best_candidate.timestamp]
        ax.scatter(cand_time_data["longitude"], cand_time_data["latitude"], 
                   color="green", s=5, alpha=0.6, label="Candidate Historical Distribution")
                   
    # Plot terminal forward particles just for clarity
    t_max = df_forward["timestamp"].max()
    final_fwd = df_forward[df_forward["timestamp"] == t_max]
    ax.scatter(final_fwd["longitude"], final_fwd["latitude"], color="grey", s=5, alpha=0.5, label=f"Forward Drift ({t_max.strftime('%H:%M')} UTC)")
        
    # DRIFT-06: Draw uncertainty radius
    if 'unc_result' in locals() and unc_result is not None:
        import matplotlib.patches as patches
        # Earth-aware conversion: 1 degree latitude ~ 111.1949 km
        # 1 degree longitude ~ 111.1949 * cos(latitude) km
        d_lat = unc_result.uncertainty_radius_km / 111.1949
        d_lon = unc_result.uncertainty_radius_km / (111.1949 * np.cos(np.radians(unc_result.centroid_latitude)))
        
        ellipse = patches.Ellipse(
            (unc_result.centroid_longitude, unc_result.centroid_latitude),
            width=2*d_lon, height=2*d_lat,
            edgecolor='red', facecolor='none', linestyle='--', linewidth=1.5, zorder=6,
            label="95% Empirical Uncertainty Radius"
        )
        ax.add_patch(ellipse)

    ax.set_title("OCEAN Pipeline: Forward Drift, Hindcast, Origin & Uncertainty", fontsize=14)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(loc="best")
    ax.grid(True, linestyle="--", alpha=0.6)
    
    # Save visualization
    out_dir = Path("demo/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ocean_pipeline_demo.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Visualization saved to: {out_path.absolute()}")
    
if __name__ == "__main__":
    main()
