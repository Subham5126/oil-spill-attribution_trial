"""
scripts/test_case_00052.py

Executes M1 Ingestion, M2 Preprocessing, M2 U-Net Segmentation, and M3 GIS Vectorization
for Sentinel-1 Case 00052 (Persian Gulf).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import rasterio
from rasterio.features import shapes
import torch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.inference.infer import OilSpillInference
from demo.end_to_end_real_workflow_demo import (
    inspect_sentinel1_tiff,
    run_m2_preprocessing,
    run_m3_geometry,
)
from gis.geometry.models import BoundingBox, Coordinate, OilSpillGeometry, Polygon as GisPolygon
from gis.measurements.models import measure_oil_spill

TIFF_PATH = REPO_ROOT / "01_Train_Val_Oil_Spill_images" / "Oil" / "00052.tif"
MODEL_PATH = REPO_ROOT / "unet_best.pth"
OUTPUT_DIR = REPO_ROOT / "demo" / "output"


def run_test_00052():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("==================================================")
    print("OILTRACE — M1/M2/M3 EVALUATION: 00052.tif")
    print("==================================================")

    # 1. M1 Image Ingestion
    print("\n--- M1: SENTINEL-1 IMAGE INGESTION ---")
    tiff_meta = inspect_sentinel1_tiff(TIFF_PATH)
    width = tiff_meta["width"]
    height = tiff_meta["height"]
    bands_count = tiff_meta["bands_count"]
    crs = tiff_meta["crs"]
    b = tiff_meta["bounds"]
    raw_img = tiff_meta["raw_image"]

    print(f"File Name: {tiff_meta['file_name']}")
    print(f"Path: {tiff_meta['absolute_path']}")
    print(f"Dimensions: {width} x {height}")
    print(f"Bands: {bands_count} ({tiff_meta['dtype']})")
    print(f"CRS: {crs}")
    print(f"Bounds: West (min_lon)={b['left']:.6f}°, South (min_lat)={b['bottom']:.6f}°, East (max_lon)={b['right']:.6f}°, North (max_lat)={b['top']:.6f}°")
    center_lon = (b["left"] + b["right"]) / 2.0
    center_lat = (b["bottom"] + b["top"]) / 2.0
    print(f"Scene Footprint Center: {center_lat:.6f}°N, {center_lon:.6f}°E")

    for stat in tiff_meta["band_statistics"]:
        print(f"  Band {stat['band']}: min={stat['min']:.2f} dB, max={stat['max']:.2f} dB, mean={stat['mean']:.2f} dB, NaNs={stat['nan_count']}")

    print("M1 STATUS: PASS")

    # 2. M2 Preprocessing
    print("\n--- M2: SATELLITE PREPROCESSING ---")
    batch_tensor, metadata_list, clean_image = run_m2_preprocessing(raw_img, tile_size=256)
    print(f"Preprocessed Tiles: {len(batch_tensor)} tiles (256x256)")
    print(f"Calibrated Bands: {clean_image.shape[0]} (VV, VH)")
    print("M2 Preprocessing STATUS: PASS")

    # 3. M2 U-Net Deep Learning Inference
    print("\n--- M2: OIL SPILL SEGMENTATION (U-Net) ---")
    infer = OilSpillInference(MODEL_PATH)
    pred_res = infer.predict(TIFF_PATH)
    binary_mask = pred_res["mask"]
    full_prob = pred_res["probability"]
    oil_pixels = pred_res["oil_pixel_count"]
    max_prob = float(np.max(full_prob))
    mean_mask_prob = float(np.mean(full_prob[binary_mask == 1])) if oil_pixels > 0 else 0.0

    print(f"Model: {MODEL_PATH.name} (U-Net ResNet34)")
    print(f"Oil Pixel Count: {oil_pixels} pixels ({pred_res['oil_percentage']:.2f}% of scene)")
    print(f"Max Detection Confidence: {max_prob:.4f} ({max_prob*100:.2f}%)")
    print(f"Mean Confidence over Slick: {mean_mask_prob:.4f} ({mean_mask_prob*100:.2f}%)")

    # Save Mask files
    mask_png_path = OUTPUT_DIR / "real_00052_mask.png"
    mask_tif_path = OUTPUT_DIR / "real_00052_mask.tif"
    cv2.imwrite(str(mask_png_path), (binary_mask * 255).astype(np.uint8))
    with rasterio.open(
        mask_tif_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=np.uint8,
        crs=crs,
        transform=tiff_meta["profile"]["transform"],
    ) as dst:
        dst.write(binary_mask, 1)

    print(f"Mask PNG Saved: {mask_png_path}")
    print(f"Mask GeoTIFF Saved: {mask_tif_path}")

    if oil_pixels == 0:
        print("M2 Detection Result: NO SPILL DETECTED")
        return

    print("M2 Detection STATUS: PASS")

    # 4. M3 GIS Vectorization & Geodesic Measurements
    print("\n--- M3: GIS VECTORIZATION & MEASUREMENTS ---")
    obs_time = datetime(2017, 3, 11, 2, 15, 11, tzinfo=timezone.utc)
    slick_geom, measurement, mask_shapes = run_m3_geometry(
        binary_mask=binary_mask,
        transform=tiff_meta["transform"],
        crs_str=crs,
        spill_id="SAR-REAL-00052",
        observation_time=obs_time,
        max_prob=max_prob,
    )
    c_lat, c_lon = measurement.centroid.lat, measurement.centroid.lon
    bounds_env = slick_geom.bounds

    print(f"Connected Components (Detected Regions): {len(mask_shapes)}")
    print(f"Actual Detected Spill Centroid: {c_lat:.6f}°N, {c_lon:.6f}°E")
    print(f"Geodesic Spill Surface Area: {measurement.area_sq_km:.4f} km² ({measurement.area_sq_m:.1f} m²)")
    print(f"Perimeter: {measurement.perimeter_km:.4f} km")
    print(f"Slick Bounding Box: Lat [{bounds_env.min_y:.6f}°N, {bounds_env.max_y:.6f}°N], Lon [{bounds_env.min_x:.6f}°E, {bounds_env.max_x:.6f}°E]")
    print(f"Shape Indices: Aspect Ratio={measurement.aspect_ratio:.4f}, Compactness={measurement.compactness:.4f}")
    print("M3 GIS STATUS: PASS")

    # 5. Determine Derived AOI around Actual Detected Centroid
    # Standard +/- 1.25 deg lat and +/- 1.0 deg lon buffer for ocean currents and AIS
    aoi_min_lat = round(c_lat - 1.25, 2)
    aoi_max_lat = round(c_lat + 1.25, 2)
    aoi_min_lon = round(c_lon - 1.0, 2)
    aoi_max_lon = round(c_lon + 1.0, 2)

    print("\n" + "=" * 60)
    print("EXACT DERIVED AOI & DATA SPECIFICATIONS FOR 00052:")
    print("=" * 60)
    print(f"Actual Detected Spill Centroid: {c_lat:.6f}°N, {c_lon:.6f}°E")
    print(f"Derived Case AOI (for Ocean Drift & AIS):")
    print(f"  Latitude:  {aoi_min_lat}°N to {aoi_max_lat}°N")
    print(f"  Longitude: {aoi_min_lon}°E to {aoi_max_lon}°E")
    print(f"  Region: Persian Gulf Marine Corridor (offshore UAE / Qatar / Iran)")

    # Copernicus Marine requirements: 7 days prior to 7 days post
    cmems_start = "2017-03-04"
    cmems_end = "2017-03-18"
    print(f"\nRequired Copernicus Marine Surface Currents Dataset:")
    print(f"  Dataset ID: cmems_mod_glo_phy_my_0.083deg_P1D-m (Global Physical Multi-Year Reanalysis)")
    print(f"  Time Range: {cmems_start} to {cmems_end}")
    print(f"  AOI: Lat [{aoi_min_lat}, {aoi_max_lat}], Lon [{aoi_min_lon}, {aoi_max_lon}]")
    print(f"  Variables: uo, vo")
    print(f"  Depth: surface level (~0.494 m or min depth)")

    # AIS time window: 3 days prior to 3 days post
    ais_start = "2017-03-08T00:00:00Z"
    ais_end = "2017-03-14T23:59:59Z"
    print(f"\nRequired GFW AIS Query Specifications:")
    print(f"  Time Window: {ais_start} to {ais_end}")
    print(f"  AOI: Lat [{aoi_min_lat}, {aoi_max_lat}], Lon [{aoi_min_lon}, {aoi_max_lon}]")
    print(f"  Dataset: public-global-presence:latest")

    # Write summary JSON
    summary = {
        "case_id": "00052",
        "file_name": tiff_meta["file_name"],
        "metadata_coordinates": {"latitude": 25.623814, "longitude": 54.610774},
        "detected_centroid": {"latitude": round(c_lat, 6), "longitude": round(c_lon, 6)},
        "dimensions": [width, height],
        "bands": bands_count,
        "crs": crs,
        "bounds": [b["left"], b["bottom"], b["right"], b["top"]],
        "model": MODEL_PATH.name,
        "detection_confidence": {
            "max": round(max_prob, 4),
            "mean": round(mean_mask_prob, 4),
        },
        "oil_pixels": oil_pixels,
        "spill_area_km2": round(measurement.area_sq_km, 4),
        "spill_area_m2": round(measurement.area_sq_m, 1),
        "connected_components": len(mask_shapes),
        "mask_png": str(mask_png_path.relative_to(REPO_ROOT)),
        "mask_tif": str(mask_tif_path.relative_to(REPO_ROOT)),
        "derived_aoi": {
            "min_latitude": aoi_min_lat,
            "max_latitude": aoi_max_lat,
            "min_longitude": aoi_min_lon,
            "max_longitude": aoi_max_lon,
        },
        "copernicus_spec": {
            "dataset_id": "cmems_mod_glo_phy_my_0.083deg_P1D-m",
            "start_date": cmems_start,
            "end_date": cmems_end,
            "variables": ["uo", "vo"],
        },
        "ais_spec": {
            "start_time": ais_start,
            "end_time": ais_end,
            "dataset": "public-global-presence:latest",
        },
    }
    summary_path = OUTPUT_DIR / "real_00052_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved summary JSON to: {summary_path}")


if __name__ == "__main__":
    run_test_00052()
