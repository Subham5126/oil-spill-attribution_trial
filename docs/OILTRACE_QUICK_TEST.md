# OILTRACE — Quick Testing Guide

A practical, copy-paste-ready guide for running unit tests and real end-to-end Sentinel-1 pipeline cases.

---

## 1. Prerequisites

- Windows PowerShell
- Working directory: `E:\SIH26\oil-spill-attribution`
- Virtual environment: `.venv`
- Configured `.env` file containing:
  ```ini
  GFW_API_TOKEN=your_token_here
  M1_MODEL_PATH=unet_best.pth
  ```

---

## 2. Environment Activation

Open PowerShell and activate the environment:

```powershell
cd E:\SIH26\oil-spill-attribution
.venv\Scripts\Activate.ps1
```

Verify dependencies:
```powershell
.venv\Scripts\python -c "import torch, rasterio, xarray, shapely, requests; print('All core dependencies OK')"
```

---

## 3. Fast Automated Unit Tests

Run the core offline test suites:

```powershell
# GIS Geometry & Measurements (81 tests, ~0.1s)
.venv\Scripts\pytest tests/gis -q

# Ocean Hydrodynamics & Drift (142 tests, ~3s)
.venv\Scripts\pytest tests/ocean -q

# AIS Filters & GFW Client Logic (211 passed, ~4s)
.venv\Scripts\pytest tests/ais -q

# Attribution Scoring & Correlators (153 tests, ~6.5s)
.venv\Scripts\pytest tests/attribution -q

# Satellite Ingestion & Tiling (29 tests, ~4.8s)
.venv\Scripts\pytest tests/satellite -q

# End-to-End Integration Contracts (22 tests, ~21s)
.venv\Scripts\pytest tests/integration -q
```

---

## 4. Run the Real End-to-End Pipeline

Use the universal runner [`scripts/run_pipeline.py`](file:///E:/SIH26/oil-spill-attribution/scripts/run_pipeline.py).

### Option A: Fresh Random Case — `00053.tif` (Persian Gulf)
*Uses local Copernicus current file `persian_gulf_current_2017.nc` with live GFW AIS.*

```powershell
.venv\Scripts\python scripts/run_pipeline.py --image-id 00053
```

### Option B: Benchmark Case — `00052.tif` (Persian Gulf)

```powershell
.venv\Scripts\python scripts/run_pipeline.py --image-id 00052
```

### Option C: Benchmark Case — `00643.tif` (Red Sea)

```powershell
.venv\Scripts\python scripts/run_pipeline.py --image-id 00643
```

### Option D: Fast Offline Test (Skip GFW API)

```powershell
.venv\Scripts\python scripts/run_pipeline.py --image-id 00053 --skip-ais
```

---

## 5. Expected Outputs

All run deliverables are generated under `demo/output/`:

| Output File | Description |
|---|---|
| `real_<id>_result.json` | Machine-readable investigation summary |
| `real_<id>_layers.geojson` | MapLibre vector layers (slick, centroid, origin, vessels) |
| `real_<id>_drift_trajectory.csv` | 72h hindcast & 24h forecast coordinates |
| `real_<id>_drift_trajectory.json` | Drift trajectory summary metadata |
| `real_<id>_mask.png` | 8-bit binary segmentation mask |
| `real_<id>_mask.tif` | Georeferenced GeoTIFF segmentation mask |
| `real_<id>_demo.png` | High-resolution 6-panel analytical figure |

---

## 6. How to Verify PASS

A successful run terminates with:
```text
==================================================
<id> REAL PIPELINE EXECUTION COMPLETED: ALL PASS
==================================================
```

Verify the generated outputs:
```powershell
Get-ChildItem demo\output\real_00053_* | Select-Object Name, Length
```

---

## 7. Common Errors and Fixes

1. **`GFW health check failed` or `GFW_API_TOKEN is not configured`**
   - *Fix:* Ensure `GFW_API_TOKEN` is set in `.env` without surrounding quotes.
2. **`HTTPConnectionPool: port 8001 actively refused` during `test_step15`**
   - *Fix:* `test_step15` tests the remote HTTP microservice. Start Uvicorn first:
     ```powershell
     .venv\Scripts\python -m uvicorn ai.api.main:app --host 127.0.0.1 --port 8001
     ```
3. **`WARNING: No local Copernicus current file covers centroid`**
   - *Fix:* The scene is located in a geographic region without a downloaded NetCDF file. Pass a local file via `--ocean-file <path>` or use `--skip-drift`.
