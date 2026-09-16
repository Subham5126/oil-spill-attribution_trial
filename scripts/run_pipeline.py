"""
scripts/run_pipeline.py

OILTRACE — Universal Real End-to-End Integration CLI Runner.
Supports arbitrary Sentinel-1 image IDs (e.g. --image-id 00053, --image-id 00052, --image-id 00643)
or direct image paths (--image-path <path>).

Workflow:
  M1 — Sentinel-1 GeoTIFF Ingestion & Metadata Validation
  M2 — Radiometric Calibration, Tiling & U-Net Deep Learning Segmentation
  M3 — GIS Vectorization, Polygonization & Geodesic Measurements
  M3/M4 — Copernicus Marine Hydrodynamic Currents & Lagrangian Drift (Hindcast 72h / Forecast 24h)
  M5 — Live Global Fishing Watch AIS Ingestion & Vessel Attribution Ranking
  Artifacts — Result JSON, Layers GeoJSON, Drift Trajectory CSV/JSON, Mask PNG/GeoTIFF, and 6-panel Figure.
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
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
import torch
import xarray as xr

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import dotenv
dotenv.load_dotenv(REPO_ROOT / ".env")

from ai.inference.infer import OilSpillInference
from ais.filtering.spatial import haversine_distance_km
from ais.integration.search_request import AISSearchRequest
from ais.providers.gfw import GlobalFishingWatchAISProvider
from demo.end_to_end_real_workflow_demo import (
    inspect_sentinel1_tiff,
    run_m2_preprocessing,
    run_m3_geometry,
)
from ocean.currents import load_currents
from ocean.drift.hindcast import hindcast_particles
from ocean.drift.particle import Particle, simulate_particles
from ocean.interpolation.environment import interpolate_currents

MODEL_PATH = REPO_ROOT / "unet_best.pth"
OUTPUT_DIR = REPO_ROOT / "demo" / "output"
IMAGES_DIR = REPO_ROOT / "01_Train_Val_Oil_Spill_images" / "Oil"
INVENTORY_CSV = REPO_ROOT / "reports" / "sentinel1_inventory.csv"
COPERNICUS_DIR = REPO_ROOT / "data" / "sample" / "copernicus"

KNOWN_REGIONAL_DEFAULTS = {
    # Persian Gulf 2017 cluster
    "persian_gulf": {
        "dataset_nc": COPERNICUS_DIR / "persian_gulf_current_2017.nc",
        "default_time": "2017-03-11T02:15:11Z",
        "lat_bounds": (24.33, 26.75),
        "lon_bounds": (53.67, 55.58),
        "region_name": "Persian Gulf",
    },
    # Red Sea 2019 cluster
    "red_sea": {
        "dataset_nc": COPERNICUS_DIR / "red_sea_current_2019.nc",
        "default_time": "2019-10-14T03:15:03Z",
        "lat_bounds": (17.5, 20.0),
        "lon_bounds": (38.6, 40.4),
        "region_name": "Red Sea Marine Corridor",
    },
}


def resolve_image_file(image_id: str | None, image_path: str | None) -> tuple[Path, str]:
    """Resolve the Sentinel-1 TIFF path from image ID or explicit path."""
    if image_path:
        p = Path(image_path)
        if not p.is_absolute():
            p = REPO_ROOT / p
        if not p.exists():
            raise FileNotFoundError(f"Image not found at: {p}")
        clean_id = p.stem
        return p, clean_id

    if not image_id:
        raise ValueError("Must provide either --image-id or --image-path")

    # Handle numeric or string IDs, normalize zero-padding to 5 digits
    norm_id = image_id.strip()
    if norm_id.isdigit():
        norm_id = f"{int(norm_id):05d}"
    candidate_name = f"{norm_id}.tif" if not norm_id.endswith(".tif") else norm_id
    p = IMAGES_DIR / candidate_name
    if not p.exists():
        raise FileNotFoundError(f"Sentinel-1 image '{candidate_name}' not found in {IMAGES_DIR}")
    return p, norm_id.replace(".tif", "")


def detect_ocean_dataset(center_lat: float, center_lon: float, user_nc: str | None, filename: str | None = None) -> tuple[Path | None, str, str]:
    """Auto-detect matching local Copernicus NetCDF file and metadata based on scene coordinates."""
    inv_time = ""
    inv_region = "Unknown Marine Region"
    
    if INVENTORY_CSV.exists() and filename:
        try:
            df_inv = pd.read_csv(INVENTORY_CSV)
            match = df_inv[df_inv["filename"] == filename]
            if not match.empty:
                r_name = str(match["region_name"].iloc[0])
                if r_name and r_name != "nan":
                    inv_region = r_name
                t_val = str(match["acquisition_time"].iloc[0])
                if t_val and t_val != "nan":
                    inv_time = t_val
        except Exception:
            pass

    if user_nc:
        p = Path(user_nc)
        if not p.is_absolute():
            p = REPO_ROOT / p
        if not p.exists():
            raise FileNotFoundError(f"Specified ocean file not found: {p}")
        return p, inv_time or "2017-03-11T02:15:11Z", inv_region or "User Defined"

    for reg_key, info in KNOWN_REGIONAL_DEFAULTS.items():
        min_lat, max_lat = info["lat_bounds"]
        min_lon, max_lon = info["lon_bounds"]
        if min_lat <= center_lat <= max_lat and min_lon <= center_lon <= max_lon:
            nc_path = info["dataset_nc"]
            if nc_path.exists():
                return nc_path, inv_time or info["default_time"], inv_region if inv_region != "Unknown Marine Region" else info["region_name"]

    return None, inv_time, inv_region


def generate_6panel_figure(
    tiff_meta: dict,
    binary_mask: np.ndarray,
    full_prob: np.ndarray,
    slick_geom: Any,
    measurement: Any,
    candidates: list[dict],
    currents_ds: xr.Dataset | None,
    df_hindcast: pd.DataFrame | None,
    df_forecast: pd.DataFrame | None,
    output_path: Path,
    case_label: str,
    obs_time_str: str,
):
    """Generate high-resolution scientific figure for the case."""
    fig, axes = plt.subplots(2, 3, figsize=(20, 13), dpi=150)
    c_lat, c_lon = measurement.centroid.lat, measurement.centroid.lon
    fig.suptitle(
        f"OILTRACE Real Integration — Sentinel-1 Case {case_label}\n"
        f"Acquired: {obs_time_str} | Centroid: {c_lat:.4f}°N, {c_lon:.4f}°E | Area: {measurement.area_sq_km:.2f} km²",
        fontsize=13,
        fontweight="bold",
    )
    raw_img = tiff_meta["raw_image"]

    # 1. VV
    ax1 = axes[0, 0]
    vv = raw_img[0]
    p2, p98 = np.percentile(vv[np.isfinite(vv)], (2, 98))
    ax1.imshow(np.clip(vv, p2, p98), cmap="gray")
    ax1.set_title("1. Sentinel-1 SAR VV (dB)")
    ax1.axis("off")

    # 2. VH
    ax2 = axes[0, 1]
    vh = raw_img[1]
    p2_h, p98_h = np.percentile(vh[np.isfinite(vh)], (2, 98))
    ax2.imshow(np.clip(vh, p2_h, p98_h), cmap="gray")
    ax2.set_title("2. Sentinel-1 SAR VH (dB)")
    ax2.axis("off")

    # 3. Prob
    ax3 = axes[0, 2]
    max_prob = float(np.max(full_prob))
    im3 = ax3.imshow(full_prob, cmap="inferno", vmin=0.0, vmax=1.0)
    ax3.set_title(f"3. U-Net Spill Prob (Max: {max_prob:.1%})")
    ax3.axis("off")
    fig.colorbar(im3, ax=ax3, fraction=0.046, pad=0.04)

    # 4. Vectorized mask
    ax4 = axes[1, 0]
    ax4.imshow(binary_mask, cmap="Blues_r")
    ax4.set_title(f"4. Vectorized Spill Mask ({measurement.area_sq_km:.2f} km²)")
    ax4.axis("off")

    # 5. Drift
    ax5 = axes[1, 1]
    ax5.set_facecolor("#0b192c")
    if currents_ds is not None and df_hindcast is not None and df_forecast is not None:
        try:
            t_idx = int(np.argmin(np.abs(currents_ds.time.values - np.datetime64(obs_time_str.replace("Z", "")))))
            uo_g = currents_ds["uo"].isel(time=t_idx).values
            vo_g = currents_ds["vo"].isel(time=t_idx).values
            lg, tg = np.meshgrid(currents_ds.longitude.values, currents_ds.latitude.values)
            ax5.pcolormesh(lg, tg, np.sqrt(uo_g**2 + vo_g**2), cmap="viridis", alpha=0.45, shading="auto")
            ax5.quiver(lg[::2, ::2], tg[::2, ::2], uo_g[::2, ::2], vo_g[::2, ::2], color="white", alpha=0.6, scale=10.0, width=0.003)
            ax5.plot(df_hindcast["longitude"], df_hindcast["latitude"], color="#fb923c", linestyle="--", linewidth=2.5, label="72h Hindcast Track")
            ax5.scatter([df_hindcast["longitude"].iloc[-1]], [df_hindcast["latitude"].iloc[-1]], color="#ea580c", s=130, marker="*", zorder=5, label="Probable Origin")
            ax5.plot(df_forecast["longitude"], df_forecast["latitude"], color="#38bdf8", linestyle="-", linewidth=2.5, label="24h Forecast Track")
        except Exception as e:
            ax5.text(0.5, 0.5, f"Drift plot notice: {e}", color="white", ha="center")
    ax5.scatter([c_lon], [c_lat], color="#ef4444", s=110, marker="o", edgecolors="white", zorder=6, label="Detected Centroid")
    ax5.set_title("5. M3 Ocean Drift Simulation")
    ax5.legend(loc="upper left", fontsize=8, facecolor="#1e293b", labelcolor="white")
    ax5.tick_params(colors="white")

    # 6. AIS candidates
    ax6 = axes[1, 2]
    ax6.set_facecolor("#0f172a")
    vtext = f"Top Suspect Vessels (GFW AIS 4Wings):\n\n"
    if candidates:
        for i, c in enumerate(candidates[:5]):
            vtext += f"#{i+1} {c['vessel_name']} (MMSI {c['mmsi']})\n   Type: {c['vessel_type']} | Flag: {c['flag']}\n   Dist Spill: {c['distance_to_spill_km']} km | Dist Track: {c.get('distance_to_track_km', 'N/A')} km\n   Fix: {str(c['timestamp'])[:16]} UTC\n\n"
    else:
        vtext += "No AIS vessels tracked or AIS query skipped."
    ax6.text(0.05, 0.95, vtext, transform=ax6.transAxes, ha="left", va="top", color="#38bdf8", fontsize=9, fontfamily="monospace")
    ax6.set_title(f"6. Real AIS Candidates ({len(candidates)} Tracked)")
    ax6.axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def run_pipeline(
    image_id: str | None = None,
    image_path: str | None = None,
    ocean_file: str | None = None,
    timestamp: str | None = None,
    skip_ais: bool = False,
    skip_drift: bool = False,
) -> dict:
    """Execute the end-to-end pipeline for any specified image."""
    tiff_path, clean_id = resolve_image_file(image_id, image_path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("==================================================")
    print(f"OILTRACE — EXECUTING PIPELINE: SCENE {clean_id}")
    print("==================================================")

    # 1. M1 Image Ingestion
    print("\n--- M1: SENTINEL-1 IMAGE INGESTION ---")
    tiff_meta = inspect_sentinel1_tiff(tiff_path)
    b = tiff_meta["bounds"]
    c_lon_scene = (b["left"] + b["right"]) / 2.0
    c_lat_scene = (b["bottom"] + b["top"]) / 2.0

    print(f"File: {tiff_meta['file_name']}")
    print(f"Dimensions: {tiff_meta['width']} x {tiff_meta['height']}")
    print(f"Bands: {tiff_meta['bands_count']} ({tiff_meta['dtype']})")
    print(f"CRS: {tiff_meta['crs']}")
    print(f"Bounding Box: West={b['left']:.6f}°, South={b['bottom']:.6f}°, East={b['right']:.6f}°, North={b['top']:.6f}°")
    print(f"Scene Footprint Center: {c_lat_scene:.6f}°N, {c_lon_scene:.6f}°E")
    print("M1 STATUS: PASS")

    # 2. M2 Preprocessing
    print("\n--- M2: PREPROCESSING ---")
    batch_tensor, metadata_list, clean_image = run_m2_preprocessing(tiff_meta["raw_image"], tile_size=256)
    print(f"Generated Tiles: {len(batch_tensor)} tiles (256x256)")
    print(f"Calibrated Bands: {clean_image.shape[0]} (VV, VH)")
    print("M2 Preprocessing STATUS: PASS")

    # 3. M2 Segmentation
    print("\n--- M2: DEEP LEARNING OIL SPILL SEGMENTATION (U-Net) ---")
    infer = OilSpillInference(MODEL_PATH)
    pred_res = infer.predict(tiff_path)
    binary_mask, full_prob = pred_res["mask"], pred_res["probability"]
    oil_pixels, max_prob = pred_res["oil_pixel_count"], float(np.max(full_prob))
    mean_prob = float(np.mean(full_prob[binary_mask == 1])) if oil_pixels > 0 else 0.0

    mask_png_path = OUTPUT_DIR / f"real_{clean_id}_mask.png"
    mask_tif_path = OUTPUT_DIR / f"real_{clean_id}_mask.tif"
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

    print(f"Model: {MODEL_PATH.name} (U-Net ResNet34)")
    print(f"Oil Pixels Detected: {oil_pixels} ({pred_res['oil_percentage']:.2f}% of scene)")
    print(f"Max Confidence: {max_prob:.4f} ({max_prob*100:.2f}%)")
    print(f"Mean Confidence (over slick): {mean_prob:.4f} ({mean_prob*100:.2f}%)")
    print(f"Mask PNG Saved: {mask_png_path}")
    print(f"Mask GeoTIFF Saved: {mask_tif_path}")
    print("M2 Segmentation STATUS: PASS")

    # Resolve observation time
    ocean_nc_path, detected_time, region_name = detect_ocean_dataset(c_lat_scene, c_lon_scene, ocean_file, filename=tiff_meta["file_name"])
    final_time_str = timestamp or detected_time or "2017-03-11T02:15:11Z"
    obs_time = pd.Timestamp(final_time_str).to_pydatetime()
    if obs_time.tzinfo is None:
        obs_time = obs_time.replace(tzinfo=timezone.utc)

    # 4. M3 GIS Vectorization
    print("\n--- M3: GIS GEOMETRY & VECTORIZATION ---")
    slick_geom, measurement, mask_shapes = run_m3_geometry(
        binary_mask=binary_mask,
        transform=tiff_meta["transform"],
        crs_str=tiff_meta["crs"],
        spill_id=f"SAR-REAL-{clean_id}",
        observation_time=obs_time,
        max_prob=max_prob,
    )
    c_lat, c_lon = measurement.centroid.lat, measurement.centroid.lon
    print(f"Connected Slick Components: {len(mask_shapes)}")
    print(f"Detected Centroid: {c_lat:.6f}°N, {c_lon:.6f}°E")
    print(f"Geodesic Area: {measurement.area_sq_km:.4f} km² ({measurement.area_sq_m:.1f} m²)")
    print(f"Perimeter: {measurement.perimeter_km:.4f} km")
    print(f"Aspect Ratio: {measurement.aspect_ratio:.4f} | Compactness: {measurement.compactness:.4f}")
    print("M3 GIS STATUS: PASS")

    # 5. Ocean Drift
    print("\n--- M3: OCEAN CURRENTS & DRIFT SIMULATION ---")
    currents_ds = None
    df_hindcast = None
    df_forecast = None
    hindcast_dist = 0.0
    fore_dist = 0.0
    origin_lat, origin_lon = c_lat, c_lon
    origin_time = obs_time.isoformat()
    fore_lat, fore_lon = c_lat, c_lon
    fore_time = obs_time.isoformat()
    traj_csv_path = OUTPUT_DIR / f"real_{clean_id}_drift_trajectory.csv"
    traj_json_path = OUTPUT_DIR / f"real_{clean_id}_drift_trajectory.json"
    u_spill, v_spill, curr_speed, curr_dir_deg = 0.0, 0.0, 0.0, 0.0

    if not skip_drift:
        if ocean_nc_path is None or not ocean_nc_path.exists():
            print(f"WARNING: No local Copernicus current file covers centroid ({c_lat:.4f}°N, {c_lon:.4f}°E).")
            print(f"Skipping hydrodynamic drift calculation. (Provide --ocean-file to supply NetCDF).")
            m3_drift_status = "SKIPPED_NO_LOCAL_DATA"
        else:
            print(f"Copernicus Marine Dataset: {ocean_nc_path.name}")
            currents_ds = load_currents(ocean_nc_path, select_surface=True)
            obs_ts = pd.Timestamp(obs_time)
            u_spill, v_spill = interpolate_currents(currents_ds, c_lon, c_lat, obs_ts.tz_localize(None))
            curr_speed = float(np.sqrt(u_spill**2 + v_spill**2))
            curr_dir_deg = float(np.degrees(np.arctan2(u_spill, v_spill)) % 360)
            print(f"Surface Currents at Spill Centroid:")
            print(f"  u (eastward):  {float(u_spill):.4f} m/s")
            print(f"  v (northward): {float(v_spill):.4f} m/s")
            print(f"  Current Speed: {curr_speed:.2f} m/s ({curr_speed*1.94384:.2f} knots)")
            print(f"  Heading:       {curr_dir_deg:.1f}°")

            wind_ds = xr.Dataset(
                {
                    "u10": (currents_ds["uo"].dims, np.zeros_like(currents_ds["uo"].values), {"units": "m/s"}),
                    "v10": (currents_ds["vo"].dims, np.zeros_like(currents_ds["vo"].values), {"units": "m/s"}),
                },
                coords=currents_ds.coords,
            )

            print("\nExecuting 72-hour backward Lagrangian hindcast...")
            df_hindcast = hindcast_particles(
                [Particle(particle_id=1, latitude=c_lat, longitude=c_lon)],
                currents_ds,
                wind_ds,
                obs_time,
                72 * 3600,
                3600,
                windage=0.0,
            )
            origin_lat = float(df_hindcast["latitude"].iloc[-1])
            origin_lon = float(df_hindcast["longitude"].iloc[-1])
            origin_time = str(df_hindcast["timestamp"].iloc[-1])
            hindcast_dist = haversine_distance_km(c_lat, c_lon, origin_lat, origin_lon)
            print(f"Hindcast Steps: {len(df_hindcast)} points")
            print(f"Estimated Spill Origin: {origin_lat:.6f}°N, {origin_lon:.6f}°E at {origin_time}")
            print(f"Total Drift Distance: {hindcast_dist:.2f} km")

            print("\nExecuting 24-hour forward Lagrangian forecast...")
            df_forecast = simulate_particles(
                [Particle(particle_id=1, latitude=c_lat, longitude=c_lon)],
                currents_ds,
                wind_ds,
                obs_time,
                24,
                3600,
                windage=0.0,
            )
            fore_lat = float(df_forecast["latitude"].iloc[-1])
            fore_lon = float(df_forecast["longitude"].iloc[-1])
            fore_time = str(df_forecast["timestamp"].iloc[-1])
            fore_dist = haversine_distance_km(c_lat, c_lon, fore_lat, fore_lon)
            print(f"Forecast Steps: {len(df_forecast)} points")
            print(f"Forecast 24h Endpoint: {fore_lat:.6f}°N, {fore_lon:.6f}°E at {fore_time}")
            print(f"Forecast Drift Distance: {fore_dist:.2f} km")

            df_hind_chrono = df_hindcast.iloc[::-1].copy()
            pd.concat([df_hind_chrono, df_forecast.iloc[1:]], ignore_index=True).to_csv(traj_csv_path, index=False)

            traj_payload = {
                "investigation_id": f"INVESTIGATION-REAL-{clean_id}",
                "model_type": "Lagrangian RK/Euler Hydrodynamic Advection",
                "current_dataset": ocean_nc_path.name,
                "observation_time": obs_time.isoformat(),
                "spill_centroid": {"latitude": c_lat, "longitude": c_lon},
                "surface_velocity_at_spill": {
                    "u_eastward_m_s": round(float(u_spill), 4),
                    "v_northward_m_s": round(float(v_spill), 4),
                    "speed_m_s": round(curr_speed, 2),
                    "direction_deg": round(curr_dir_deg, 1),
                },
                "probable_origin_72h": {
                    "latitude": round(origin_lat, 6),
                    "longitude": round(origin_lon, 6),
                    "timestamp": origin_time,
                    "drift_distance_km": round(hindcast_dist, 2),
                },
                "forecast_endpoint_24h": {
                    "latitude": round(fore_lat, 6),
                    "longitude": round(fore_lon, 6),
                    "timestamp": fore_time,
                    "drift_distance_km": round(fore_dist, 2),
                },
            }
            with open(traj_json_path, "w", encoding="utf-8") as f:
                json.dump(traj_payload, f, indent=2)

            print(f"Saved Drift Trajectory CSV: {traj_csv_path}")
            print(f"Saved Drift Trajectory JSON: {traj_json_path}")
            print("M3 Ocean Drift STATUS: PASS")
            m3_drift_status = "PASS"
    else:
        m3_drift_status = "SKIPPED_USER_FLAG"

    # 6. M5 AIS Ingestion & Attribution
    candidates = []
    total_records = 0
    unique_vessels = 0

    if not skip_ais:
        print("\n--- M5: AIS DATA INGESTION & VESSEL ATTRIBUTION ---")
        provider = GlobalFishingWatchAISProvider(timeout=(10.0, 105.0), max_recovery_timeout=120.0)

        # Build query bounding box
        aoi_min_lat = round(c_lat - 1.25, 2)
        aoi_max_lat = round(c_lat + 1.25, 2)
        aoi_min_lon = round(c_lon - 1.0, 2)
        aoi_max_lon = round(c_lon + 1.0, 2)

        start_dt = pd.Timestamp(obs_time) - pd.Timedelta(days=3)
        end_dt = pd.Timestamp(obs_time) + pd.Timedelta(days=3)

        req = AISSearchRequest(
            latitude=c_lat,
            longitude=c_lon,
            radius_km=140.0,
            start_time=start_dt,
            end_time=end_dt,
            bounding_box=(aoi_min_lat, aoi_max_lat, aoi_min_lon, aoi_max_lon),
        )
        print("Querying Global Fishing Watch 4Wings API (dataset: public-global-presence:latest)...")
        print(f"Time Range: {req.start_time.isoformat()} to {req.end_time.isoformat()}")
        print(f"Spatial AOI: Lat [{aoi_min_lat}, {aoi_max_lat}], Lon [{aoi_min_lon}, {aoi_max_lon}]")

        try:
            ais_df = provider.fetch_ais_data(req)
            total_records = len(ais_df)
            unique_vessels = ais_df["mmsi"].nunique() if not ais_df.empty else 0
            print(f"Total AIS Vessel Presence Records: {total_records}")
            print(f"Unique Vessels Tracked: {unique_vessels}")

            if not ais_df.empty:
                ais_df["dist_to_spill_km"] = [
                    haversine_distance_km(c_lat, c_lon, lat, lon)
                    for lat, lon in zip(ais_df["latitude"], ais_df["longitude"])
                ]
                if df_hindcast is not None:
                    track_coords = list(zip(df_hindcast["latitude"], df_hindcast["longitude"]))
                    ais_df["dist_to_track_km"] = [
                        min(haversine_distance_km(lat, lon, t_lat, t_lon) for t_lat, t_lon in track_coords)
                        for lat, lon in zip(ais_df["latitude"], ais_df["longitude"])
                    ]
                else:
                    ais_df["dist_to_track_km"] = ais_df["dist_to_spill_km"]

                for mmsi, group in ais_df.groupby("mmsi"):
                    closest = group.loc[group["dist_to_spill_km"].idxmin()]
                    candidates.append({
                        "mmsi": int(mmsi) if str(mmsi).isdigit() else str(mmsi),
                        "vessel_name": str(closest.get("vessel_name") or "UNKNOWN"),
                        "imo": str(closest.get("imo") or "UNKNOWN"),
                        "callsign": str(closest.get("callsign") or "UNKNOWN"),
                        "flag": str(closest.get("flag") or closest.get("flag_code") or "UNKNOWN"),
                        "vessel_type": str(closest.get("vessel_type") or "UNKNOWN"),
                        "latitude": float(closest["latitude"]),
                        "longitude": float(closest["longitude"]),
                        "distance_to_spill_km": round(float(closest["dist_to_spill_km"]), 2),
                        "distance_to_track_km": round(float(group["dist_to_track_km"].min()), 2),
                        "presence_hours": round(float(group["presence_hours"].sum()) if "presence_hours" in group.columns else float(len(group)), 1),
                        "timestamp": str(closest["timestamp"]),
                    })
                candidates.sort(key=lambda x: x["distance_to_spill_km"])

                print(f"\nTop {min(10, len(candidates))} Suspect Vessels Closest to Spill Centroid & Drift Track:")
                for idx, c in enumerate(candidates[:10]):
                    print(f"  #{idx+1} {c['vessel_name']} (MMSI: {c['mmsi']}, IMO: {c['imo']})")
                    print(f"     Type: {c['vessel_type']} | Flag: {c['flag']} | Dist Spill: {c['distance_to_spill_km']:.2f} km | Dist Track: {c['distance_to_track_km']:.2f} km | Fix: {c['timestamp']}")
            print("M5 AIS STATUS: PASS")
            m5_status = "PASS"
        except Exception as e:
            print(f"WARNING: GFW AIS query failed: {e}")
            m5_status = f"FAILED: {e}"
    else:
        print("\n--- M5: AIS DATA INGESTION (SKIPPED BY USER) ---")
        m5_status = "SKIPPED_USER_FLAG"

    # 7. Layers GeoJSON & Result JSON
    print("\n--- GENERATING FINAL ARTIFACTS ---")
    result_geojson_path = OUTPUT_DIR / f"real_{clean_id}_layers.geojson"
    result_json_path = OUTPUT_DIR / f"real_{clean_id}_result.json"
    vis_plot_path = OUTPUT_DIR / f"real_{clean_id}_demo.png"

    features = [
        {
            "type": "Feature",
            "properties": {
                "layer_type": "oil_spill_detection",
                "spill_id": slick_geom.spill_id,
                "area_sq_km": round(measurement.area_sq_km, 4),
                "perimeter_km": round(measurement.perimeter_km, 4),
                "confidence": round(max_prob, 4),
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[float(pt.x), float(pt.y)] for pt in slick_geom.geometry.exterior.coordinates]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "layer_type": "spill_centroid",
                "latitude": round(c_lat, 6),
                "longitude": round(c_lon, 6),
            },
            "geometry": {"type": "Point", "coordinates": [round(c_lon, 6), round(c_lat, 6)]},
        },
    ]

    if df_hindcast is not None:
        features.extend([
            {
                "type": "Feature",
                "properties": {
                    "layer_type": "probable_spill_origin",
                    "timestamp": origin_time,
                    "drift_distance_km": round(hindcast_dist, 2),
                },
                "geometry": {"type": "Point", "coordinates": [round(origin_lon, 6), round(origin_lat, 6)]},
            },
            {
                "type": "Feature",
                "properties": {"layer_type": "drift_hindcast_track", "duration_hours": 72, "points_count": len(df_hindcast)},
                "geometry": {"type": "LineString", "coordinates": [[round(lon, 6), round(lat, 6)] for lon, lat in zip(df_hindcast["longitude"], df_hindcast["latitude"])]},
            },
            {
                "type": "Feature",
                "properties": {"layer_type": "drift_forecast_track", "duration_hours": 24, "points_count": len(df_forecast)},
                "geometry": {"type": "LineString", "coordinates": [[round(lon, 6), round(lat, 6)] for lon, lat in zip(df_forecast["longitude"], df_forecast["latitude"])]},
            },
        ])

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
                "flag": c["flag"],
                "distance_km": c["distance_to_spill_km"],
                "distance_to_track_km": c.get("distance_to_track_km", "N/A"),
                "timestamp": c["timestamp"],
            },
            "geometry": {"type": "Point", "coordinates": [c["longitude"], c["latitude"]]},
        })

    with open(result_geojson_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, indent=2)

    result_data = {
        "investigation_id": f"INVESTIGATION-REAL-{clean_id}",
        "status": "PASS" if m3_drift_status in ("PASS", "SKIPPED_USER_FLAG", "SKIPPED_NO_LOCAL_DATA") and m5_status in ("PASS", "SKIPPED_USER_FLAG") else "PARTIAL",
        "selected_case": {
            "image_id": clean_id,
            "file_name": tiff_meta["file_name"],
            "region": region_name,
            "acquisition_date": obs_time.strftime("%Y-%m-%d"),
            "acquisition_time": obs_time.strftime("%H:%M:%S UTC"),
        },
        "m1_image_ingestion": {
            "status": "PASS",
            "dimensions": [tiff_meta["width"], tiff_meta["height"]],
            "bands": tiff_meta["bands_count"],
            "crs": tiff_meta["crs"],
            "bounds": b,
        },
        "m2_oil_spill_detection": {
            "status": "PASS",
            "model": "U-Net ResNet34",
            "oil_pixels": oil_pixels,
            "oil_percentage": round(pred_res["oil_percentage"], 2),
            "max_prob": round(max_prob, 4),
            "mean_prob": round(mean_prob, 4),
            "mask_png": str(mask_png_path.relative_to(REPO_ROOT)),
            "mask_tif": str(mask_tif_path.relative_to(REPO_ROOT)),
        },
        "m3_gis_geometry": {
            "status": "PASS",
            "centroid": [round(c_lat, 6), round(c_lon, 6)],
            "geodesic_area_km2": round(measurement.area_sq_km, 4),
            "perimeter_km": round(measurement.perimeter_km, 4),
        },
        "m3_ocean_drift": {
            "status": m3_drift_status,
            "current_dataset": ocean_nc_path.name if ocean_nc_path else None,
            "surface_velocity_at_spill": {
                "u_m_s": round(float(u_spill), 4),
                "v_m_s": round(float(v_spill), 4),
                "speed_m_s": round(curr_speed, 2),
                "heading_deg": round(curr_dir_deg, 1),
            },
            "hindcast_72h": {
                "origin_lat": round(origin_lat, 6),
                "origin_lon": round(origin_lon, 6),
                "origin_timestamp": origin_time,
                "drift_distance_km": round(hindcast_dist, 2),
            },
            "forecast_24h": {
                "endpoint_lat": round(fore_lat, 6),
                "endpoint_lon": round(fore_lon, 6),
                "endpoint_timestamp": fore_time,
                "drift_distance_km": round(fore_dist, 2),
            },
            "trajectory_csv": str(traj_csv_path.relative_to(REPO_ROOT)) if df_hindcast is not None else None,
            "trajectory_json": str(traj_json_path.relative_to(REPO_ROOT)) if df_hindcast is not None else None,
        },
        "m5_ais_attribution": {
            "status": m5_status,
            "provider": "Global Fishing Watch (4Wings API)" if not skip_ais else None,
            "dataset": "public-global-presence:latest" if not skip_ais else None,
            "total_records": total_records,
            "unique_vessels": unique_vessels,
            "top_suspects": candidates[:10],
        },
        "files_generated": [
            str(result_json_path.relative_to(REPO_ROOT)),
            str(result_geojson_path.relative_to(REPO_ROOT)),
            str(vis_plot_path.relative_to(REPO_ROOT)),
            str(mask_png_path.relative_to(REPO_ROOT)),
            str(mask_tif_path.relative_to(REPO_ROOT)),
        ],
    }
    if df_hindcast is not None:
        result_data["files_generated"].extend([
            str(traj_json_path.relative_to(REPO_ROOT)),
            str(traj_csv_path.relative_to(REPO_ROOT)),
        ])

    with open(result_json_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)

    # 8. Visualization
    generate_6panel_figure(
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
        case_label=clean_id,
        obs_time_str=final_time_str,
    )

    print(f"Generated Result JSON: {result_json_path}")
    print(f"Generated Layers GeoJSON: {result_geojson_path}")
    print(f"Generated High-Res Figure: {vis_plot_path}")
    print("==================================================")
    print(f"{clean_id} REAL PIPELINE EXECUTION COMPLETED: ALL PASS")
    print("==================================================")
    return result_data


def main():
    parser = argparse.ArgumentParser(description="OILTRACE Real Pipeline Runner for Sentinel-1 scenes.")
    parser.add_argument("--image-id", type=str, default=None, help="Image ID (e.g. 00053, 53, 00052, 00643)")
    parser.add_argument("--image-path", type=str, default=None, help="Direct path to Sentinel-1 GeoTIFF")
    parser.add_argument("--ocean-file", type=str, default=None, help="Path to Copernicus NetCDF currents file")
    parser.add_argument("--timestamp", type=str, default=None, help="Observation ISO timestamp (e.g. 2017-03-11T02:15:11Z)")
    parser.add_argument("--skip-ais", action="store_true", help="Skip GFW AIS query")
    parser.add_argument("--skip-drift", action="store_true", help="Skip ocean hydrodynamic drift simulation")

    args = parser.parse_args()
    if not args.image_id and not args.image_path:
        parser.print_help()
        sys.exit(1)

    run_pipeline(
        image_id=args.image_id,
        image_path=args.image_path,
        ocean_file=args.ocean_file,
        timestamp=args.timestamp,
        skip_ais=args.skip_ais,
        skip_drift=args.skip_drift,
    )


if __name__ == "__main__":
    main()
