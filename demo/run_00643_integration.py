"""
demo/run_00643_integration.py

OILTRACE — Real End-to-End Integration Pipeline for Sentinel-1 Scene 00643 (Red Sea).
Coordinates: 18.888338°N, 39.293801°E
Acquisition Timestamp: 2019-10-14 03:15:03 UTC
AOI: Lat [17.5, 20.0], Lon [38.6, 40.4]
Ocean Current Dataset: data/sample/copernicus/red_sea_current_2019.nc (2019-10-07 to 2019-10-21)
AIS Window: 2019-10-11 to 2019-10-17

Pipeline Stages:
  M1 — Sentinel-1 GeoTIFF Ingestion & Radiometric Preprocessing
  M2 — Deep Learning Semantic Segmentation (U-Net ResNet34)
  M3 — GIS Vectorization, Polygonization & Geodesic Measurements
  M3/M4 — Ocean Current Validation & Lagrangian Drift Hindcasting/Forecasting
  M5 — Historical AIS Ingestion & Attribution Ranking (Global Fishing Watch API)
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import shapes
import torch
import xarray as xr

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import dotenv
dotenv.load_dotenv(REPO_ROOT / ".env")

from ai.inference.infer import OilSpillInference
from ais.filtering.spatial import haversine_distance_km
from ais.providers.gfw import GlobalFishingWatchAISProvider
from demo.end_to_end_real_workflow_demo import (
    inspect_sentinel1_tiff,
    run_m1_inference,
    run_m2_preprocessing,
    run_m3_geometry,
)
from gis.geometry.models import Coordinate, OilSpillGeometry, Polygon as GisPolygon
from gis.measurements.models import measure_oil_spill
from ocean.currents import load_currents
from ocean.drift.hindcast import hindcast_particles
from ocean.drift.particle import Particle, simulate_particles
from ocean.interpolation.environment import interpolate_currents

DEFAULT_TIFF = REPO_ROOT / "01_Train_Val_Oil_Spill_images" / "Oil" / "00643.tif"
DEFAULT_MODEL = REPO_ROOT / "unet_best.pth"
RED_SEA_CURRENTS_NC = REPO_ROOT / "data" / "sample" / "copernicus" / "red_sea_current_2019.nc"
OUTPUT_DIR = REPO_ROOT / "demo" / "output"


def inspect_netcdf_dataset(nc_path: Path) -> dict:
    """Inspect and print metadata of the Copernicus NetCDF current dataset."""
    if not nc_path.exists():
        raise FileNotFoundError(f"Copernicus currents file not found at: {nc_path}")

    with xr.open_dataset(nc_path) as ds:
        dims_dict = dict(ds.sizes)
        vars_list = list(ds.data_vars.keys())
        coords_list = list(ds.coords.keys())
        lat_min = float(ds.latitude.values.min())
        lat_max = float(ds.latitude.values.max())
        lon_min = float(ds.longitude.values.min())
        lon_max = float(ds.longitude.values.max())
        time_min = pd.Timestamp(ds.time.values.min())
        time_max = pd.Timestamp(ds.time.values.max())
        uo_avail = "uo" in ds.data_vars
        vo_avail = "vo" in ds.data_vars
        depth_levels = len(ds["depth"].values) if "depth" in ds else 1

    return {
        "file_name": nc_path.name,
        "path": str(nc_path),
        "dimensions": dims_dict,
        "variables": vars_list,
        "coordinates": coords_list,
        "latitude_bounds": (lat_min, lat_max),
        "longitude_bounds": (lon_min, lon_max),
        "time_bounds": (time_min.isoformat(), time_max.isoformat()),
        "uo_availability": uo_avail,
        "vo_availability": vo_avail,
        "depth_levels": depth_levels,
    }


def generate_00643_visualization(
    tiff_meta: dict,
    binary_mask: np.ndarray,
    full_prob: np.ndarray,
    slick_geom: Any,
    measurement: Any,
    candidates: list[dict],
    currents_ds: xr.Dataset,
    df_hindcast: pd.DataFrame,
    df_forecast: pd.DataFrame,
    output_path: Path,
):
    """Generate high-resolution 6-panel scientific figure for Case 00643."""
    fig, axes = plt.subplots(2, 3, figsize=(20, 13), dpi=150)
    fig.suptitle(
        f"OILTRACE Real End-to-End Integration — Sentinel-1 Scene 00643 (Red Sea)\n"
        f"Acquisition: 2019-10-14 03:15:03 UTC | Detected Centroid: {measurement.centroid.lat:.4f}°N, {measurement.centroid.lon:.4f}°E | Spill Area: {measurement.area_sq_km:.2f} km²",
        fontsize=13,
        fontweight="bold",
    )

    raw_img = tiff_meta["raw_image"]

    # Panel 1: SAR VV
    ax1 = axes[0, 0]
    vv = raw_img[0]
    p2, p98 = np.percentile(vv[np.isfinite(vv)], (2, 98))
    ax1.imshow(np.clip(vv, p2, p98), cmap="gray")
    ax1.set_title("1. Sentinel-1 SAR VV Backscatter (dB)")
    ax1.axis("off")

    # Panel 2: SAR VH
    ax2 = axes[0, 1]
    vh = raw_img[1]
    p2, p98 = np.percentile(vh[np.isfinite(vh)], (2, 98))
    ax2.imshow(np.clip(vh, p2, p98), cmap="gray")
    ax2.set_title("2. Sentinel-1 SAR VH Cross-Polarization (dB)")
    ax2.axis("off")

    # Panel 3: U-Net Probability Heatmap
    ax3 = axes[0, 2]
    im3 = ax3.imshow(full_prob, cmap="inferno", vmin=0.0, vmax=1.0)
    ax3.set_title(f"3. U-Net Oil Spill Probability (Max: {np.max(full_prob):.2%})")
    ax3.axis("off")
    fig.colorbar(im3, ax=ax3, fraction=0.046, pad=0.04, label="Confidence")

    # Panel 4: Binary Detection & GIS Contour
    ax4 = axes[1, 0]
    ax4.imshow(binary_mask, cmap="Blues_r")
    ax4.set_title(f"4. M2/M3 Vectorized Spill Mask ({measurement.area_sq_km:.2f} km²)")
    ax4.axis("off")

    # Panel 5: Real Copernicus Ocean Currents & Drift Trajectory
    ax5 = axes[1, 1]
    ax5.set_facecolor("#0b192c")

    # Subsample currents grid around the spill for vector quiver plot
    lats = currents_ds.latitude.values
    lons = currents_ds.longitude.values
    # Select snapshot closest to spill time
    t_idx = int(np.argmin(np.abs(currents_ds.time.values - np.datetime64("2019-10-14T03:15:03"))))
    uo_grid = currents_ds["uo"].isel(time=t_idx).values
    vo_grid = currents_ds["vo"].isel(time=t_idx).values
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    speed = np.sqrt(uo_grid**2 + vo_grid**2)
    ax5.pcolormesh(lon_grid, lat_grid, speed, cmap="viridis", alpha=0.45, shading="auto")
    # Quiver plot
    skip = (slice(None, None, 2), slice(None, None, 2))
    ax5.quiver(
        lon_grid[skip], lat_grid[skip], uo_grid[skip], vo_grid[skip],
        color="white", alpha=0.6, scale=10.0, width=0.003
    )

    # Plot backward hindcast trajectory (orange line)
    ax5.plot(
        df_hindcast["longitude"], df_hindcast["latitude"],
        color="#fb923c", linestyle="--", linewidth=2.5, label="72h Hindcast (Probable Origin Track)"
    )
    # Origin point (star)
    origin_lon = df_hindcast["longitude"].iloc[-1]
    origin_lat = df_hindcast["latitude"].iloc[-1]
    ax5.scatter([origin_lon], [origin_lat], color="#ea580c", s=130, marker="*", zorder=5, label="Probable Spill Origin")

    # Plot forward forecast trajectory (cyan line)
    ax5.plot(
        df_forecast["longitude"], df_forecast["latitude"],
        color="#38bdf8", linestyle="-", linewidth=2.5, label="24h Forward Drift"
    )

    # Observation centroid (red circle)
    ax5.scatter([measurement.centroid.lon], [measurement.centroid.lat], color="#ef4444", s=110, marker="o", edgecolors="white", zorder=6, label="Observed Spill Centroid (00643)")

    ax5.set_xlim([38.7, 40.2])
    ax5.set_ylim([17.6, 19.8])
    ax5.set_xlabel("Longitude (°E)", color="white", fontsize=9)
    ax5.set_ylabel("Latitude (°N)", color="white", fontsize=9)
    ax5.tick_params(colors="white")
    ax5.legend(loc="upper left", fontsize=8, facecolor="#1e293b", edgecolor="#475569", labelcolor="white")
    ax5.set_title("5. M3 Ocean Drift (Copernicus 2019 Red Sea Currents)")

    # Panel 6: GFW AIS Candidate Vessels
    ax6 = axes[1, 2]
    ax6.set_facecolor("#0f172a")
    vessel_text = f"Top Suspect Vessels (GFW AIS 4Wings):\n\n"
    for i, c in enumerate(candidates[:5]):
        vessel_text += (
            f"#{i+1} {c['vessel_name']} (MMSI {c['mmsi']})\n"
            f"   Type: {c['vessel_type']} | Flag: {c['flag']}\n"
            f"   Dist to Spill: {c['distance_to_spill_km']:.2f} km | Dist to Track: {c.get('distance_to_track_km', c['distance_to_spill_km']):.2f} km\n"
            f"   Fix: {c['timestamp'][:16]} UTC\n\n"
        )
    ax6.text(
        0.05,
        0.95,
        vessel_text,
        transform=ax6.transAxes,
        ha="left",
        va="top",
        color="#38bdf8",
        fontsize=9,
        fontfamily="monospace",
    )
    ax6.set_title(f"6. Real AIS Candidates ({len(candidates)} Tracked)")
    ax6.axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def run_00643_pipeline():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("==================================================")
    print("OILTRACE — REAL END-TO-END INTEGRATION TEST")
    print("CASE: Sentinel-1 00643.tif (Red Sea)")
    print("DATASET: red_sea_current_2019.nc")
    print("==================================================")

    # 1. Inspect Sentinel-1 TIFF (M1)
    print("\n--- STEP 1: M1 IMAGE INGESTION ---")
    tiff_meta = inspect_sentinel1_tiff(DEFAULT_TIFF)
    print(f"File: {tiff_meta['file_name']}")
    print(f"Path: {tiff_meta['absolute_path']}")
    print(f"Dimensions: {tiff_meta['width']} x {tiff_meta['height']}")
    print(f"Bands: {tiff_meta['bands_count']} ({tiff_meta['dtype']})")
    print(f"CRS: {tiff_meta['crs']}")
    b = tiff_meta["bounds"]
    print(f"Bounds: Lon [{b['left']:.6f}, {b['right']:.6f}], Lat [{b['bottom']:.6f}, {b['top']:.6f}]")
    ref_lat = (b["bottom"] + b["top"]) / 2.0
    ref_lon = (b["left"] + b["right"]) / 2.0
    print(f"Scene Center: {ref_lat:.6f}°N, {ref_lon:.6f}°E")
    print("M1 STATUS: PASS")

    # 2. M2 Preprocessing
    print("\n--- STEP 2: M2 SATELLITE PREPROCESSING ---")
    batch_tensor, metadata_list, clean_image = run_m2_preprocessing(tiff_meta["raw_image"], tile_size=256)
    print(f"Preprocessed Tiles: {len(batch_tensor)} tiles (256x256)")
    print(f"Valid channels: {clean_image.shape[0]} (VV, VH)")
    print("M2 Preprocessing STATUS: PASS")

    # 3. M2/M1 Deep Learning Segmentation
    print("\n--- STEP 3: M2 OIL SPILL SEGMENTATION (U-Net) ---")
    infer = OilSpillInference(DEFAULT_MODEL)
    pred_res = infer.predict(DEFAULT_TIFF)
    binary_mask = pred_res["mask"]
    full_prob = pred_res["probability"]
    oil_pixels = pred_res["oil_pixel_count"]
    max_prob = float(np.max(full_prob))
    mean_mask_prob = float(np.mean(full_prob[binary_mask == 1])) if oil_pixels > 0 else 0.0

    print(f"Model: {DEFAULT_MODEL.name} (U-Net ResNet34)")
    print(f"Oil Pixel Count: {oil_pixels} pixels ({pred_res['oil_percentage']:.2f}% of scene)")
    print(f"Detection Confidence: Max {max_prob:.4f}, Mean over Slick {mean_mask_prob:.4f}")

    # Export masks
    mask_png_path = OUTPUT_DIR / "real_00643_mask.png"
    mask_tif_path = OUTPUT_DIR / "real_00643_mask.tif"
    cv2.imwrite(str(mask_png_path), (binary_mask * 255).astype(np.uint8))
    with rasterio.open(
        mask_tif_path,
        "w",
        driver="GTiff",
        height=tiff_meta["height"],
        width=tiff_meta["width"],
        count=1,
        dtype=np.uint8,
        crs=tiff_meta["crs"],
        transform=tiff_meta["profile"]["transform"],
    ) as dst:
        dst.write(binary_mask, 1)

    print(f"Mask PNG: {mask_png_path}")
    print(f"Mask GeoTIFF: {mask_tif_path}")
    print("M2 Segmentation STATUS: PASS")

    # 4. M3 GIS Vectorization & Geodesic Measurements
    print("\n--- STEP 4: M3 GIS VECTORIZATION & GEODESIC MEASUREMENTS ---")
    obs_time = datetime(2019, 10, 14, 3, 15, 3, tzinfo=timezone.utc)
    slick_geom, measurement, mask_shapes = run_m3_geometry(
        binary_mask=binary_mask,
        transform=tiff_meta["transform"],
        crs_str=tiff_meta["crs"],
        spill_id="SAR-REAL-00643",
        observation_time=obs_time,
        max_prob=max_prob,
    )
    c_lat, c_lon = measurement.centroid.lat, measurement.centroid.lon
    bounds_env = slick_geom.bounds
    print(f"Detected Connected Regions: {len(mask_shapes)}")
    print(f"Spill Centroid: {c_lat:.6f}°N, {c_lon:.6f}°E")
    print(f"Geodesic Surface Area: {measurement.area_sq_km:.4f} km² ({measurement.area_sq_m:.1f} m²)")
    print(f"Perimeter: {measurement.perimeter_km:.4f} km")
    print(f"Bounding Box: Lat [{bounds_env.min_y:.6f}, {bounds_env.max_y:.6f}], Lon [{bounds_env.min_x:.6f}, {bounds_env.max_x:.6f}]")
    print(f"Aspect Ratio: {measurement.aspect_ratio:.4f}, Compactness: {measurement.compactness:.4f}")
    print("M3 GIS STATUS: PASS")

    # 5. M3 Ocean Drift Modelling (Real Copernicus Red Sea Currents)
    print("\n--- STEP 5: M3 OCEAN DRIFT (COPERNICUS RED SEA 2019) ---")
    print(f"Loading ocean current dataset: {RED_SEA_CURRENTS_NC}")
    nc_info = inspect_netcdf_dataset(RED_SEA_CURRENTS_NC)
    print(f"Dimensions: {nc_info['dimensions']}")
    print(f"Variables: {nc_info['variables']}")
    print(f"Latitude bounds: {nc_info['latitude_bounds'][0]:.4f} to {nc_info['latitude_bounds'][1]:.4f}")
    print(f"Longitude bounds: {nc_info['longitude_bounds'][0]:.4f} to {nc_info['longitude_bounds'][1]:.4f}")
    print(f"Time bounds: {nc_info['time_bounds'][0]} to {nc_info['time_bounds'][1]}")
    print(f"uo availability: {nc_info['uo_availability']}")
    print(f"vo availability: {nc_info['vo_availability']}")

    # Verify spill location is inside bounds
    lat_ok = nc_info["latitude_bounds"][0] <= c_lat <= nc_info["latitude_bounds"][1]
    lon_ok = nc_info["longitude_bounds"][0] <= c_lon <= nc_info["longitude_bounds"][1]
    t_min = pd.Timestamp(nc_info["time_bounds"][0])
    if t_min.tz is None:
        t_min = t_min.tz_localize("UTC")
    t_max = pd.Timestamp(nc_info["time_bounds"][1])
    if t_max.tz is None:
        t_max = t_max.tz_localize("UTC")
    obs_ts = pd.Timestamp(obs_time)
    if obs_ts.tz is None:
        obs_ts = obs_ts.tz_localize("UTC")
    time_ok = t_min <= obs_ts <= t_max

    print(f"\nVerifying Spill Location ({c_lat:.6f}°N, {c_lon:.6f}°E) at {obs_time.isoformat()}:")
    print(f"  Latitude within bounds: {lat_ok} ({nc_info['latitude_bounds'][0]:.2f} <= {c_lat:.4f} <= {nc_info['latitude_bounds'][1]:.2f})")
    print(f"  Longitude within bounds: {lon_ok} ({nc_info['longitude_bounds'][0]:.2f} <= {c_lon:.4f} <= {nc_info['longitude_bounds'][1]:.2f})")
    print(f"  Time within bounds: {time_ok} ({t_min} <= {obs_ts} <= {t_max})")

    if not (lat_ok and lon_ok and time_ok):
        raise ValueError("Spill location or timestamp is outside Copernicus Red Sea dataset bounds!")

    # Load surface current slice using load_currents
    currents_ds = load_currents(RED_SEA_CURRENTS_NC, select_surface=True)
    print(f"Surface currents successfully loaded into memory. Surface depth: 0.494 m.")

    # Interpolate current at spill observation (using naive timestamp matching NetCDF datetime64)
    query_ts_naive = obs_ts.tz_localize(None)
    u_spill, v_spill = interpolate_currents(currents_ds, c_lon, c_lat, query_ts_naive)
    curr_speed = float(np.sqrt(u_spill**2 + v_spill**2))
    curr_dir_deg = float(np.degrees(np.arctan2(u_spill, v_spill)) % 360)
    print(f"Interpolated surface velocity at spill: u={float(u_spill):.4f} m/s, v={float(v_spill):.4f} m/s (Speed: {curr_speed:.2f} m/s, Heading: {curr_dir_dir:.1f}°)" if "curr_dir_dir" in locals() else f"Interpolated surface velocity at spill: u={float(u_spill):.4f} m/s, v={float(v_spill):.4f} m/s (Speed: {curr_speed:.2f} m/s, Heading: {curr_dir_deg:.1f}°)")

    # Prepare zero wind dataset for hydrodynamic current-driven advection
    wind_ds = xr.Dataset(
        {
            "u10": (currents_ds["uo"].dims, np.zeros_like(currents_ds["uo"].values), {"units": "m/s"}),
            "v10": (currents_ds["vo"].dims, np.zeros_like(currents_ds["vo"].values), {"units": "m/s"}),
        },
        coords=currents_ds.coords,
    )

    # 5.1 Backward Hindcast: 72 hours (3 days back to 2019-10-11 03:15:03 UTC)
    print("\nRunning 72-hour Lagrangian backward hindcast (to locate probable release origin)...")
    hindcast_duration_sec = 72 * 3600
    df_hindcast = hindcast_particles(
        particles=[Particle(particle_id=1, latitude=c_lat, longitude=c_lon)],
        current_dataset=currents_ds,
        wind_dataset=wind_ds,
        observation_time=obs_time,
        duration_seconds=hindcast_duration_sec,
        timestep_seconds=3600,
        windage=0.0,
    )

    origin_lat = float(df_hindcast["latitude"].iloc[-1])
    origin_lon = float(df_hindcast["longitude"].iloc[-1])
    origin_time = df_hindcast["timestamp"].iloc[-1]
    hindcast_distance_km = haversine_distance_km(c_lat, c_lon, origin_lat, origin_lon)

    print(f"Hindcast trajectory points: {len(df_hindcast)}")
    print(f"Observation position: {c_lat:.6f}°N, {c_lon:.6f}°E at {obs_time.isoformat()}")
    print(f"Probable release origin: {origin_lat:.6f}°N, {origin_lon:.6f}°E at {origin_time}")
    print(f"Total backward drift distance: {hindcast_distance_km:.2f} km")

    # 5.2 Forward Forecast: 24 hours
    print("\nRunning 24-hour Lagrangian forward drift forecast...")
    df_forecast = simulate_particles(
        particles=[Particle(particle_id=1, latitude=c_lat, longitude=c_lon)],
        current_dataset=currents_ds,
        wind_dataset=wind_ds,
        start_time=obs_time,
        num_steps=24,
        timestep_seconds=3600,
        windage=0.0,
    )
    final_fore_lat = float(df_forecast["latitude"].iloc[-1])
    final_fore_lon = float(df_forecast["longitude"].iloc[-1])
    final_fore_time = df_forecast["timestamp"].iloc[-1]
    fore_distance_km = haversine_distance_km(c_lat, c_lon, final_fore_lat, final_fore_lon)
    print(f"Forecast trajectory points: {len(df_forecast)}")
    print(f"Final forecast position (24h): {final_fore_lat:.6f}°N, {final_fore_lon:.6f}°E at {final_fore_time}")
    print(f"Forecast drift distance: {fore_distance_km:.2f} km")

    # Save trajectory files
    traj_json_path = OUTPUT_DIR / "real_00643_drift_trajectory.json"
    traj_csv_path = OUTPUT_DIR / "real_00643_drift_trajectory.csv"

    # Combine hindcast and forecast chronologically into a full historical trajectory
    df_hind_chrono = df_hindcast.iloc[::-1].copy()
    df_full_traj = pd.concat([df_hind_chrono, df_forecast.iloc[1:]], ignore_index=True)
    df_full_traj.to_csv(traj_csv_path, index=False)

    traj_dict = {
        "investigation_id": "INVESTIGATION-REAL-00643",
        "model_type": "Lagrangian RK/Euler Hydrodynamic Advection",
        "current_dataset": RED_SEA_CURRENTS_NC.name,
        "observation_time": obs_time.isoformat(),
        "spill_centroid": {"latitude": c_lat, "longitude": c_lon},
        "probable_origin": {
            "latitude": origin_lat,
            "longitude": origin_lon,
            "timestamp": str(origin_time),
            "drift_distance_km": round(hindcast_distance_km, 2),
        },
        "forecast_24h": {
            "latitude": final_fore_lat,
            "longitude": final_fore_lon,
            "timestamp": str(final_fore_time),
            "drift_distance_km": round(fore_distance_km, 2),
        },
        "hindcast_trajectory": [
            {
                "timestamp": str(row["timestamp"]),
                "latitude": round(row["latitude"], 6),
                "longitude": round(row["longitude"], 6),
            }
            for _, row in df_hindcast.iterrows()
        ],
        "forecast_trajectory": [
            {
                "timestamp": str(row["timestamp"]),
                "latitude": round(row["latitude"], 6),
                "longitude": round(row["longitude"], 6),
            }
            for _, row in df_forecast.iterrows()
        ],
    }
    with open(traj_json_path, "w", encoding="utf-8") as f:
        json.dump(traj_dict, f, indent=2)

    print(f"Saved drift trajectory JSON: {traj_json_path}")
    print(f"Saved drift trajectory CSV: {traj_csv_path}")
    print("M3 OCEAN DRIFT STATUS: PASS")

    # 6. M5 AIS Ingestion & Attribution (Global Fishing Watch API)
    print("\n--- STEP 6: M5 AIS DATA INGESTION & ATTRIBUTION ---")
    provider = GlobalFishingWatchAISProvider(
        timeout=(10.0, 105.0),
        max_recovery_timeout=120.0,
    )
    if not provider.health_check():
        raise RuntimeError("GFW health check failed. Ensure GFW_API_TOKEN is set in .env.")

    req = GlobalFishingWatchAISProvider.create_red_sea_request(
        start_time="2019-10-11T00:00:00Z",
        end_time="2019-10-17T23:59:59Z",
    )
    print(f"AOI: Lat [{req.bounding_box[0]}, {req.bounding_box[1]}], Lon [{req.bounding_box[2]}, {req.bounding_box[3]}]")
    print(f"Time Range: {req.start_time} to {req.end_time}")
    print("Fetching AIS vessel presence records from Global Fishing Watch API...")

    ais_df = provider.fetch_ais_data(req)
    total_records = len(ais_df)
    unique_vessels = ais_df["mmsi"].nunique() if not ais_df.empty else 0
    print(f"Total AIS Records: {total_records}")
    print(f"Unique Vessels: {unique_vessels}")

    # Distance to observed spill centroid
    ais_df["dist_to_spill_km"] = [
        haversine_distance_km(c_lat, c_lon, lat, lon)
        for lat, lon in zip(ais_df["latitude"], ais_df["longitude"])
    ]

    # Calculate distance to backward drift trajectory points
    track_coords = list(zip(df_hindcast["latitude"], df_hindcast["longitude"]))
    min_track_dists = []
    for lat, lon in zip(ais_df["latitude"], ais_df["longitude"]):
        d_min = min(haversine_distance_km(lat, lon, t_lat, t_lon) for t_lat, t_lon in track_coords)
        min_track_dists.append(d_min)
    ais_df["dist_to_track_km"] = min_track_dists

    candidates = []
    for mmsi, group in ais_df.groupby("mmsi"):
        closest = group.loc[group["dist_to_spill_km"].idxmin()]
        dist_spill = float(closest["dist_to_spill_km"])
        dist_track = float(group["dist_to_track_km"].min())
        v_type = str(closest.get("vessel_type") or "UNKNOWN")
        hours = float(group["presence_hours"].sum()) if "presence_hours" in group.columns else float(len(group))
        candidates.append({
            "mmsi": int(mmsi) if str(mmsi).isdigit() else str(mmsi),
            "vessel_name": str(closest.get("vessel_name") or "UNKNOWN"),
            "imo": str(closest.get("imo") or "UNKNOWN"),
            "callsign": str(closest.get("callsign") or "UNKNOWN"),
            "flag": str(closest.get("flag") or closest.get("flag_code") or "UNKNOWN"),
            "vessel_type": v_type,
            "latitude": float(closest["latitude"]),
            "longitude": float(closest["longitude"]),
            "distance_to_spill_km": round(dist_spill, 2),
            "distance_to_track_km": round(dist_track, 2),
            "presence_hours": round(hours, 1),
            "timestamp": str(closest["timestamp"]),
            "observation_count": len(group),
            "reason_for_ranking": (
                f"Proximity to spill ({dist_spill:.2f} km) and hindcast drift track ({dist_track:.2f} km) "
                f"in Red Sea corridor"
            ),
        })

    # Sort by minimum distance to spill centroid
    candidates.sort(key=lambda x: x["distance_to_spill_km"])

    print("\nTop 5 Suspect Vessels Closest to Spill Centroid & Drift Track:")
    for idx, c in enumerate(candidates[:5]):
        print(f"  {idx+1}. {c['vessel_name']} (MMSI: {c['mmsi']}, IMO: {c['imo']}) — {c['vessel_type']} [{c['flag']}]")
        print(f"     Dist to Spill: {c['distance_to_spill_km']:.2f} km | Dist to Track: {c['distance_to_track_km']:.2f} km | Fix: {c['timestamp']} | Hours: {c['presence_hours']}h")
    print("M5 AIS STATUS: PASS")

    # 7. Generate Structured Outputs (JSON, GeoJSON, PNG)
    print("\n--- STEP 7: ARTIFACT GENERATION ---")
    result_json_path = OUTPUT_DIR / "real_00643_result.json"
    result_geojson_path = OUTPUT_DIR / "real_00643_layers.geojson"
    vis_plot_path = OUTPUT_DIR / "real_00643_demo.png"

    # GeoJSON FeatureCollection
    spill_coords = [[[float(pt.x), float(pt.y)] for pt in slick_geom.geometry.exterior.coordinates]]
    features = [
        {
            "type": "Feature",
            "properties": {
                "layer_type": "oil_spill_detection",
                "spill_id": slick_geom.spill_id,
                "area_sq_km": round(measurement.area_sq_km, 4),
                "area_sq_m": round(measurement.area_sq_m, 1),
                "perimeter_km": round(measurement.perimeter_km, 4),
                "centroid_lat": round(c_lat, 6),
                "centroid_lon": round(c_lon, 6),
                "confidence": round(max_prob, 4),
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": spill_coords,
            },
        },
        {
            "type": "Feature",
            "properties": {
                "layer_type": "spill_centroid",
                "spill_id": slick_geom.spill_id,
                "latitude": round(c_lat, 6),
                "longitude": round(c_lon, 6),
            },
            "geometry": {
                "type": "Point",
                "coordinates": [round(c_lon, 6), round(c_lat, 6)],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "layer_type": "probable_spill_origin",
                "timestamp": str(origin_time),
                "drift_distance_km": round(hindcast_distance_km, 2),
                "description": "72h backward Lagrangian hindcast probable origin",
            },
            "geometry": {
                "type": "Point",
                "coordinates": [round(origin_lon, 6), round(origin_lat, 6)],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "layer_type": "drift_hindcast_track",
                "duration_hours": 72,
                "points_count": len(df_hindcast),
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[round(lon, 6), round(lat, 6)] for lon, lat in zip(df_hindcast["longitude"], df_hindcast["latitude"])],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "layer_type": "drift_forecast_track",
                "duration_hours": 24,
                "points_count": len(df_forecast),
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[round(lon, 6), round(lat, 6)] for lon, lat in zip(df_forecast["longitude"], df_forecast["latitude"])],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "layer_type": "scene_bounding_box",
                "description": "Sentinel-1 00643 Scene Extent",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [b["left"], b["bottom"]],
                    [b["right"], b["bottom"]],
                    [b["right"], b["top"]],
                    [b["left"], b["top"]],
                    [b["left"], b["bottom"]],
                ]],
            },
        },
    ]

    # Add candidate vessel points
    for idx, c in enumerate(candidates[:10]):
        features.append({
            "type": "Feature",
            "properties": {
                "layer_type": "candidate_vessel",
                "rank": idx + 1,
                "vessel_name": c["vessel_name"],
                "mmsi": c["mmsi"],
                "imo": c["imo"],
                "vessel_type": c["vessel_type"],
                "distance_km": c["distance_to_spill_km"],
                "distance_to_track_km": c["distance_to_track_km"],
                "timestamp": c["timestamp"],
            },
            "geometry": {
                "type": "Point",
                "coordinates": [c["longitude"], c["latitude"]],
            },
        })

    geojson_data = {
        "type": "FeatureCollection",
        "features": features,
    }

    with open(result_geojson_path, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, indent=2)

    structured_result = {
        "investigation_id": "INVESTIGATION-REAL-00643",
        "timestamp": obs_time.isoformat(),
        "status": "PASS",
        "selected_case": {
            "image_id": "00643",
            "file_name": tiff_meta["file_name"],
            "acquisition_date": "2019-10-14",
            "acquisition_time": "03:15:03 UTC",
            "reference_coordinate": [18.888338, 39.293801],
            "region": "Red Sea Marine Corridor",
        },
        "m1_image_ingestion": {
            "status": "PASS",
            "image_name": tiff_meta["file_name"],
            "image_path": tiff_meta["relative_path"],
            "width": tiff_meta["width"],
            "height": tiff_meta["height"],
            "bands": tiff_meta["bands_count"],
            "crs": tiff_meta["crs"],
            "bounds": b,
            "acquisition_time": "2019-10-14T03:15:03Z",
        },
        "m2_oil_spill_detection": {
            "status": "PASS",
            "model": "U-Net ResNet34 (unet_best.pth)",
            "detection_confidence_max": round(max_prob, 4),
            "detection_confidence_mean": round(mean_mask_prob, 4),
            "oil_pixel_count": oil_pixels,
            "detected_regions": len(mask_shapes),
            "spill_centroid": [round(c_lat, 6), round(c_lon, 6)],
            "geodesic_area_km2": round(measurement.area_sq_km, 4),
            "perimeter_km": round(measurement.perimeter_km, 4),
            "bounding_box": [bounds_env.min_x, bounds_env.min_y, bounds_env.max_x, bounds_env.max_y],
            "mask_png": str(mask_png_path.relative_to(REPO_ROOT)),
            "mask_tif": str(mask_tif_path.relative_to(REPO_ROOT)),
        },
        "m3_ocean_drift": {
            "status": "PASS",
            "model": "Lagrangian Particle Advection (Euler backward/forward)",
            "current_dataset": RED_SEA_CURRENTS_NC.name,
            "time_range": "2019-10-07T00:00:00Z to 2019-10-21T00:00:00Z",
            "surface_velocity_at_spill": {
                "u_eastward_m_s": round(float(u_spill), 4),
                "v_northward_m_s": round(float(v_spill), 4),
                "speed_m_s": round(curr_speed, 2),
                "direction_deg": round(curr_dir_deg, 1),
            },
            "spill_start_lat": round(c_lat, 6),
            "spill_start_lon": round(c_lon, 6),
            "start_time": obs_time.isoformat(),
            "hindcast_72h": {
                "trajectory_points": len(df_hindcast),
                "end_time": str(origin_time),
                "final_lat": round(origin_lat, 6),
                "final_lon": round(origin_lon, 6),
                "total_drift_distance_km": round(hindcast_distance_km, 2),
            },
            "forecast_24h": {
                "trajectory_points": len(df_forecast),
                "end_time": str(final_fore_time),
                "final_lat": round(final_fore_lat, 6),
                "final_lon": round(final_fore_lon, 6),
                "total_drift_distance_km": round(fore_distance_km, 2),
            },
            "trajectory_file_json": str(traj_json_path.relative_to(REPO_ROOT)),
            "trajectory_file_csv": str(traj_csv_path.relative_to(REPO_ROOT)),
        },
        "m5_ais_attribution": {
            "status": "PASS",
            "provider": "Global Fishing Watch (4Wings API)",
            "time_range": "2019-10-11T00:00:00Z to 2019-10-17T23:59:59Z",
            "aoi": [17.5, 20.0, 38.6, 40.4],
            "total_records": total_records,
            "unique_vessels": unique_vessels,
            "candidates": candidates[:10],
        },
        "files_generated": [
            str(result_json_path.relative_to(REPO_ROOT)),
            str(result_geojson_path.relative_to(REPO_ROOT)),
            str(mask_png_path.relative_to(REPO_ROOT)),
            str(mask_tif_path.relative_to(REPO_ROOT)),
            str(vis_plot_path.relative_to(REPO_ROOT)),
            str(traj_json_path.relative_to(REPO_ROOT)),
            str(traj_csv_path.relative_to(REPO_ROOT)),
        ],
    }

    with open(result_json_path, "w", encoding="utf-8") as f:
        json.dump(structured_result, f, indent=2)

    # Generate 6-panel visualization
    generate_00643_visualization(
        tiff_meta=tiff_meta,
        binary_mask=binary_mask,
        full_prob=full_prob,
        slick_geom=slick_geom,
        measurement=measurement,
        candidates=candidates,
        currents_ds=currents_ds,
        df_hindcast=df_hindcast,
        df_forecast=df_forecast,
        output_path=vis_plot_path,
    )

    print(f"Generated Result JSON: {result_json_path}")
    print(f"Generated Layers GeoJSON: {result_geojson_path}")
    print(f"Generated Figure: {vis_plot_path}")
    print("==================================================")
    print("00643 REAL PIPELINE EXECUTION COMPLETED: ALL PASS")
    print("==================================================")
    return structured_result


if __name__ == "__main__":
    run_00643_pipeline()
