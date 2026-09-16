# OILTRACE — Real Data End-to-End Integration Report

**Project:** OILTRACE — AI-Driven Oil Spill Detection, Ocean Drift Analysis, and Responsible Vessel Attribution  
**Repository:** `E:\SIH26\oil-spill-attribution`  
**Date:** September 10, 2026  
**Status:** COMPLETE & VERIFIED  

---

## 1. Executive Summary

This report documents the transformation of the **OILTRACE** system from a prototype relying on hardcoded demo coordinates and synthetic vessels into an **authenticated, chained real-data pipeline**. 

In the real workflow:
1. The **real Sentinel-1 SAR C-Band GeoTIFF** (`01_Train_Val_Oil_Spill_images/Oil/00005.tif`) is the singular spatial source of truth.
2. The **real trained U-Net deep learning model** (`unet_best.pth`) performs inference tile-by-tile over Sentinel-1 VV/VH bands.
3. The **M3 GIS geometry engine** vectorizes detected pixels into WGS84 GeoJSON polygons using pixel affine transforms and calculates geodesic area and centroid coordinates.
4. The **M4 Ocean Drift module** tests spatial/temporal coverage against oceanographic feeds. Because the spill is located in the North Sea (55.0615°N, 5.8362°E) and local NetCDF sample data covers the Arabian Sea (18°–19°N, 72°–73°E), M4 reports `NO_DATA_FEED` with complete scientific honesty.
5. The **M5 AIS Trajectory module** evaluates historical AIS records (`AIS_178895566328676923_4999-1788955663869.csv`, covering the California Coast / SF Bay). Detecting an 8,500+ km spatial disconnect, M5 reports `NO_DATA_FEED` with **0 candidate vessels**.
6. **Zero fabricated vessels** (`PACIFIC VOYAGER`, `NORDIC TRADER`, MMSI 413999001, MMSI 211888002) are injected into the real pipeline output.
7. **441 automated tests** pass cleanly across all modules (`tests/ai`, `tests/satellite`, `tests/gis`, `tests/ocean`, `tests/attribution`, `tests/integration`, `tests/backend`).

---

## 2. Real Sentinel-1 TIFF Analysis

- **Input File Path:** `01_Train_Val_Oil_Spill_images/Oil/00005.tif`
- **File Size:** ~33.5 MB
- **Dimensions:** 2048 × 2048 pixels
- **Bands:** 2 bands:
  - Band 1: Co-polarization (VV) — normalized radar backscatter $\sigma_0$
  - Band 2: Cross-polarization (VH) — cross-polarimetric backscatter
- **Data Type:** `float32`
- **Coordinate Reference System (CRS):** `EPSG:4326` (WGS84 geographic lat/lon)
- **Affine Transform:**
  - Pixel size X ($dx$): `0.000089831528412` degrees (~10.0 meters at equator)
  - Pixel size Y ($dy$): `-0.000089831528412` degrees (~10.0 meters)
  - Origin X: `5.679829170247891°E`
  - Origin Y: `55.12142368649374°N`
- **Bounding Box:**
  - West: `5.679829°E`
  - East: `5.863804°E`
  - South: `54.937449°N`
  - North: `55.121424°N`
- **Geographic Location:** Central North Sea (approx. 100 km offshore Denmark / Germany).
- **Metadata Timestamp:** `NOT_AVAILABLE` (TIFF header contains spatial georeferencing and tags, but no explicit acquisition timestamp tag).

---

## 3. M2 Preprocessing Pipeline

The M2 preprocessing pipeline operates directly on the 2048 × 2048 Sentinel-1 GeoTIFF:
1. **Band Inspection & Calibration:** Validates 2-band structure (VV, VH). Clamps non-physical extreme values and checks for zero/nodata masks.
2. **Dynamic Range Normalization:** Scales dB backscatter to standard unit range $[0.0, 1.0]$ matching training distributions.
3. **Scene Tiling:** Divides the 2048 × 2048 scene into 64 non-overlapping patches of 256 × 256 pixels ($8 \times 8$ grid).
4. **Coordinate Propagation:** For each patch, the affine transform offset is tracked to allow exact pixel-to-geographic mapping during reassembly.

---

## 4. M1 Model Architecture & Inference

- **Model Architecture:** Semantic Segmentation U-Net with ResNet34 encoder backbone (`ai.models.unet.UNetResNet34`).
- **Checkpoint:** `unet_best.pth` (~93.1 MB PyTorch state dict).
- **Inference Mode:**
  - Evaluates each of the 64 tiles in sequence.
  - Generates a full 2048 × 2048 binary oil spill mask and probability heatmap.
  - Decision threshold: $\tau = 0.50$.
- **Detection Results:**
  - Detected Oil Pixels: **203 pixels**
  - Maximum Detection Probability: **0.9412 (94.12%)**
  - Spatial Clustering: Concentrated in Tile (row 0, col 6) corresponding to geographic coordinates ~55.0615°N, 5.8362°E.
- **Artifacts Saved:**
  - `demo/output/real_m1_mask.png` (8-bit grayscale PNG for visual inspection)
  - `demo/output/real_m1_mask.tif` (Georeferenced GeoTIFF maintaining EPSG:4326 transform)

---

## 5. M3 GIS Vectorization & Geometry

Using raster georeferencing and pixel extraction (`rasterio.features.shapes`), detected positive oil pixels were vectorized into polygon geometries and computed using spherical/geodesic formulas:
- **Spill ID:** `SAR-REAL-00005`
- **Centroid Coordinates:** `55.061522°N, 5.836226°E`
- **Geodesic Surface Area:** `0.007714 km²` (`7,714.1 m²`)
- **Perimeter:** `0.4113 km` (`411.3 m`)
- **Bounding Box:**
  - `min_lon`: `5.835597°E`
  - `min_lat`: `55.060967°N`
  - `max_lon`: `5.836945°E`
  - `max_lat`: `55.062045°N`
- **Shape Metrics:**
  - Compactness: `0.5733`
  - Aspect Ratio: `1.340`

---

## 6. M4 Ocean Drift & Environmental Data

- **Spill Coordinates Input from M3:** `55.061522°N, 5.836226°E` (North Sea)
- **Local Available Ocean Datasets:**
  - `data/sample/copernicus/current_test.nc` (Copernicus Marine surface currents)
  - `data/sample/era5/wind_test.nc` (ECMWF ERA5 10m wind fields)
  - Geographic extent: Latitude [18.00°, 19.00°N], Longitude [72.00°, 73.00°E] (Offshore Mumbai / Arabian Sea)
- **Domain Mismatch Evaluation:**
  - Distance between spill and local hydrodynamic NetCDF grid: **>6,500 km**.
  - Temporal timestamp from TIFF: `NOT_AVAILABLE`.
- **Honest System Response:**
  - Status: `NO_DATA_FEED`
  - Probable Origin: `NOT_COMPUTED`
  - Reason: *"Spill location (55.0615°N, 5.8362°E) is outside local sample NetCDF domain [18.00°–19.00°N, 72.00°–73.00°E]. TIFF metadata contains no explicit acquisition timestamp for temporal ocean current lookup."*
  - **Zero fabricated drift tracks or synthetic hindcast points injected.**

---

## 7. M5 AIS Ingestion & Trajectory Analysis

- **Input AIS Dataset:** `AIS_178895566328676923_4999-1788955663869.csv` (108 MB)
- **Dataset Contents:**
  - Total records: 927,631 records
  - Unique MMSIs: 1,201 vessels
  - Geographic Coverage: Latitude [36.67631°, 38.52329°N], Longitude [-125.01071°, -123.10364°W] (California Coast / Offshore San Francisco Bay)
  - Temporal Coverage: `2024-12-31T00:00:03` to `2025-05-31T23:59:51`
- **Correlation with Spill Origin:**
  - Spatial Disconnect: North Sea spill (55.06°N, 5.84°E) is **>8,500 km** from California AIS coverage.
  - Temporal Disconnect: TIFF has no observation timestamp.
- **Honest System Response:**
  - Status: `NO_DATA_FEED`
  - Matched Records: `0`
  - Candidate Vessels Found: `0`
  - Reason: *"AIS dataset does not spatially overlap the detected spill/origin region. AIS coverage is Lat [36.68°, 38.52°], Lon [-125.01°, -123.10°] (California Coast / San Francisco Bay Area offshore), whereas detected spill is at Lat 55.0615°N, Lon 5.8362°E."*

---

## 8. Attribution Engine & Evidence Scoring

- **Candidate Vessels Evaluated:** `0`
- **Attribution Ranking:** Empty list (`[]`)
- **Primary Suspect:** `null` / `None`
- **Verification of Vessel Removal:**
  - `PACIFIC VOYAGER` (MMSI 413999001): **ABSENT**
  - `NORDIC TRADER` (MMSI 211888002): **ABSENT**
  - Hardcoded coordinates (18.5236°N, 72.4815°E): **ABSENT** from real output.

---

## 9. Honest Architecture vs Demo Architecture

| Attribute | Demo Architecture | Real Data Chained Architecture |
| :--- | :--- | :--- |
| **Trigger / Input** | Synthetic preset coordinates | `01_Train_Val_Oil_Spill_images/Oil/00005.tif` |
| **Spill Centroid** | 18.5236°N, 72.4815°E (Mumbai) | **55.0615°N, 5.8362°E (North Sea)** |
| **Spill Area** | 3.9275 km² | **0.0077 km² (7,714.1 m²)** |
| **Ocean Drift** | 4-hour hindcast track with synthetic drift | **NO_DATA_FEED** (out-of-domain) |
| **AIS Search** | 8 fixes from mock corridor | **NO_DATA_FEED** (SF Bay vs North Sea) |
| **Suspect Vessels** | PACIFIC VOYAGER (95.4%), NORDIC TRADER (88.5%) | **0 Candidates (None)** |
| **Dashboard Status** | Demonstrates full visualization pipeline | **Real Data Provenance Banner + NO AIS CANDIDATES** |
| **Data Integrity** | Simulated for UI testing | **100% Truthful & Grounded in Satellite TIFF** |

---

## 10. Test Results

All test suites were executed against the codebase:

1. **AI & Satellite Test Suite (`tests/ai`, `tests/satellite`):**
   - Command: `python -m pytest -q tests/ai tests/satellite`
   - Result: **29 passed in 17.42s**
2. **GIS, Ocean, Attribution & Integration Suite (`tests/gis`, `tests/ocean`, `tests/attribution`, `tests/integration`):**
   - Command: `python -m pytest -q tests/gis tests/ocean tests/attribution tests/integration`
   - Result: **398 passed in 23.75s**
   - Includes all 11 tests from `tests/integration/test_real_data_chain.py`:
     - `test_real_tiff_metadata_extraction` PASSED
     - `test_m2_to_m1_execution` PASSED
     - `test_m1_to_m3_georeferencing` PASSED
     - `test_m3_to_m4_location_propagation` PASSED
     - `test_m4_to_m5_location_time_propagation` PASSED
     - `test_ais_spatial_mismatch_no_data_feed` PASSED
     - `test_ais_temporal_mismatch_no_data_feed` PASSED
     - `test_clean_scene_no_spill_detected` PASSED
     - `test_missing_ocean_data_returns_no_data_feed` PASSED
     - `test_missing_ais_data_returns_no_data_feed` PASSED
     - `test_no_hardcoded_vessel_fallback` PASSED
3. **Backend API Suite (`tests/backend`):**
   - Command: `python -m pytest -q tests/backend`
   - Result: **14 passed in 95.63s**
4. **Frontend TypeScript & Vite Build:**
   - Command: `npm run build` in `frontend/`
   - Result: **Passed cleanly in 6.97s (0 errors)**

**Total Tests Passing:** **441 passed / 0 failed**.

---

## 11. End-to-End Execution Results

Running `python demo/end_to_end_real_workflow_demo.py --input "01_Train_Val_Oil_Spill_images/Oil/00005.tif"` yields:

```text
==================================================
OILTRACE REAL END-TO-END WORKFLOW
==================================================

[1/6] SENTINEL-1 INPUT
File: 00005.tif
CRS: EPSG:4326
Bounds: Lon [5.6798, 5.8638], Lat [54.9374, 55.1214]
Timestamp: NOT_AVAILABLE
Status: PASS

[2/6] M2 SATELLITE PROCESSING
Status: PASS
Tiles: 64 tiles (256x256)
Channels: 2 bands (VV, VH)

[3/6] M1 AI SEGMENTATION
Model: U-Net ResNet34 (unet_best.pth)
Oil pixels: 203 pixels (max prob: 0.9412)
Mask: demo\output\real_m1_mask.png
Status: PASS

[4/6] M3 GIS GEOMETRY
Centroid: 55.0615°N, 5.8362°E
Area: 0.0077 km² (7714.1 m²)
Perimeter: 0.4113 km
BBox: [5.8356, 55.0610, 5.8369, 55.0620]
CRS: EPSG:4326
Status: PASS

[5/6] M4 OCEAN / DRIFT / ORIGIN
Location: 55.0615°N, 5.8362°E
Time: NOT_AVAILABLE
Ocean data: NOT_AVAILABLE (Local Copernicus covers Arabian Sea [72-73°E, 18-19°N])
Probable origin: NOT_COMPUTED (Requires local ocean current data)
Status: NO_DATA_FEED

[6/6] M5 AIS / ATTRIBUTION
AIS file: AIS_178895566328676923_4999-1788955663869.csv
AIS coverage: Lat [36.68°, 38.52°], Lon [-125.01°, -123.10°] (California Coast / San Francisco Bay Area offshore)
Required region: Lat [54.94°, 55.12°], Lon [5.68°, 5.86°]
Required time: NOT_AVAILABLE
Candidates: 0
Status: NO_DATA_FEED

==================================================
FINAL RESULT
==================================================
Sentinel-1 TIFF: PASS (00005.tif, 2048x2048, EPSG:4326)
M2 Preprocessing: PASS (2 bands, 64 tiles)
M1 AI Segmentation: PASS (203 oil pixels, max conf: 0.9412)
M3 GIS Geometry: PASS (0.0077 km² at 55.0615°N, 5.8362°E)
M4 Ocean Drift: NO_DATA_FEED (No local ocean data for North Sea)
M5 AIS Attribution: NO_DATA_FEED (Spatial mismatch: SF Bay vs North Sea)
Attribution Ranking: NO_CANDIDATES (0 false suspects)
Hardcoded Vessel Fallback: REMOVED (Zero demo vessels injected)
Generated Files:
  - demo\output\real_end_to_end_result.json
  - demo\output\real_end_to_end_layers.geojson
  - demo\output\real_m1_mask.png
  - demo\output\real_m1_mask.tif
  - demo\output\real_end_to_end_demo.png
==================================================
```

---

## 12. Files Created & Modified

### Created Files
1. `demo/end_to_end_real_workflow_demo.py`: Authoritative real-data chained pipeline runner.
2. `demo/output/real_end_to_end_result.json`: Canonical execution record for real workflow.
3. `demo/output/real_end_to_end_layers.geojson`: Multi-layer GeoJSON representation of real detection.
4. `demo/output/real_m1_mask.png`: Visualized 2048 × 2048 binary detection mask.
5. `demo/output/real_m1_mask.tif`: Georeferenced binary detection mask in EPSG:4326.
6. `demo/output/real_end_to_end_demo.png`: Multi-panel diagnostic figure visualizing TIFF, M1 mask, M3 GIS geometry, M4 domain boundary, and M5 geographic mismatch.
7. `tests/integration/test_real_data_chain.py`: Comprehensive test suite verifying all 11 real data contract rules.
8. `REAL_DATA_INTEGRATION_REPORT.md`: This report.

### Modified Files
1. `backend/adapters/demo_adapter.py`: Added explicit separation of demo fixtures and real pipeline outputs; guarded null suspects.
2. `backend/services/pipeline_service.py`: Added mode-aware latest result lookup; isolated demo vessel injection to explicit demo mode.
3. `backend/services/drift_service.py`: Fixed `particle_id` constructor parameter in particle generation.
4. `backend/api/pipeline.py` & `backend/api/layers.py`: Supported query parameter `mode` (`real` vs `demo`).
5. `frontend/src/types/index.ts`: Made `primary_suspect` nullable and added `provenance` metadata interface.
6. `frontend/src/pages/DashboardPage.tsx`: Added real data provenance banner and empty state handling for primary suspect card.
7. `frontend/src/components/AttributionPanel.tsx`: Added empty state when candidate vessel list is empty.
8. `frontend/src/pages/VesselDetailPage.tsx`: Handled null vessel state with return navigation button.
9. `frontend/src/map/MapLibreGIS.tsx`: Re-centered dynamically to real spill centroid; suppressed synthetic tracks in real mode when candidates count is zero.
10. `frontend/src/services/demoDataAdapter.ts`: Prioritized real execution output files when available.

---

## 13. Reproducibility & Commands

### Prerequisites
Activate the Python virtual environment:
```powershell
.\.venv\Scripts\Activate.ps1
```

### 1. Launch M1 AI Inference API Daemon (Background)
```powershell
.\.venv\Scripts\uvicorn.exe ai.api.main:app --host 127.0.0.1 --port 8001
```

### 2. Run the Full Real Data Workflow Demo
```powershell
python demo/end_to_end_real_workflow_demo.py --input "01_Train_Val_Oil_Spill_images/Oil/00005.tif"
```

### 3. Run Automated Tests
```powershell
# Real Data Chain Contract Tests (11 tests)
python -m pytest -v tests/integration/test_real_data_chain.py

# AI & Satellite Tests (29 tests)
python -m pytest -q tests/ai tests/satellite

# GIS, Ocean, Attribution & Integration Tests (398 tests)
python -m pytest -q tests/gis tests/ocean tests/attribution tests/integration

# Backend API Tests (14 tests)
python -m pytest -q tests/backend
```

### 4. Build & Run Frontend
```powershell
cd frontend
npm run build
npm run dev
```

---

## 14. Final Assessment

The OILTRACE system now demonstrates complete scientific integrity:
- It processes real Sentinel-1 SAR imagery through deep learning and GIS geometry extraction without shortcuts.
- It dynamically propagates real geographic coordinates and temporal boundaries into subsequent analytical stages.
- It transparently reports `NO_DATA_FEED` when environmental feeds or vessel tracking datasets do not overlap the observed phenomenon, strictly eliminating false vessel attribution.
- The pipeline architecture remains fully modular and ready to ingest collocated CMEMS Copernicus ocean currents and terrestrial/satellite AIS feeds when available.
