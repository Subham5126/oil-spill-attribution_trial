# OILTRACE System & Testing Documentation

**Document Version:** 1.0.0  
**Repository:** `E:\SIH26\oil-spill-attribution`  
**Audit & Verification Date:** September 10, 2026  
**Status:** FULL AUDIT & DUAL-CASE VERIFICATION COMPLETED (Cases `00052` and `00053` Verified)

---

## 1. Current System Overview

The **OILTRACE** system is a scientific decision-support platform designed to detect marine oil slicks from satellite Synthetic Aperture Radar (SAR) imagery, calculate geodesic GIS geometry, reconstruct backward and forward trajectory drift using hydrodynamic ocean current models, correlate spatio-temporal probable origin zones with historical Automatic Identification System (AIS) vessel presence data, and rank potential suspect vessels.

The system is organized into five core scientific and engineering stages:
- **M1:** Sentinel-1 GeoTIFF Ingestion, SAR metadata extraction, and geographic georeferencing.
- **M2:** Radiometric calibration, tiling, dynamic range normalization, and deep learning semantic segmentation via U-Net (ResNet34 backbone).
- **M3:** GIS polygonization, geodesic surface area and perimeter calculations, compactness/aspect ratio shape indices, and GeoJSON export.
- **M3/M4:** Oceanographic validation using Copernicus Marine hydrodynamic surface current datasets (`uo`, `vo`) and Lagrangian particle advection (backward hindcasting to find probable spill origin and forward forecasting to predict slick dispersion).
- **M5:** AIS vessel ingestion via Global Fishing Watch (GFW) 4Wings API (`public-global-presence:latest`), spatio-temporal distance calculations to spill centroid and drift trajectory, and suspect attribution ranking.
- **Backend & Frontend:** FastAPI REST backend serving spatial investigation endpoints, and a React 18 / MapLibre GL / Vite web dashboard for interactive cartographic analysis.

---

## 2. Repository Architecture

```text
E:\SIH26\oil-spill-attribution
├── 01_Train_Val_Oil_Spill_images/
│   └── Oil/                            # 1,200 Sentinel-1 SAR GeoTIFFs (00000.tif - 01316.tif)
├── ai/
│   ├── api/
│   │   ├── main.py                     # M1 FastAPI microservice (/predict, /predict-tiles)
│   │   └── tile_predict.py             # Tile inference serialization
│   ├── inference/
│   │   └── infer.py                    # OilSpillInference class (direct local PyTorch model loader)
│   └── models/
│       ├── unet.py                     # U-Net architecture definitions
│       └── dataset.py                  # PyTorch Dataset wrappers
├── ais/
│   ├── filtering/
│   │   └── spatial.py                  # Haversine distance, bounding box filters
│   ├── integration/
│   │   └── search_request.py           # AISSearchRequest canonical dataclass
│   └── providers/
│       ├── base.py                     # BaseAISProvider abstract class
│       ├── gfw.py                      # GlobalFishingWatchAISProvider (GFW 4Wings API client)
│       └── local.py                    # Local CSV provider for offline testing
├── attribution/
│   ├── models.py                       # Attribution data models, ranking schemas
│   └── scoring/                        # Multi-criteria scoring logic
├── backend/
│   ├── api/v1/                         # FastAPI REST endpoints
│   ├── core/                           # Database engine, configuration
│   └── main.py                         # Application entrypoint
├── data/
│   ├── ais/                            # Historical AIS sample datasets
│   └── sample/
│       └── copernicus/                 # Local Copernicus Marine NetCDF current files
│           ├── current_test.nc         # Synthetic/mini current test file (33 KB)
│           ├── persian_gulf_current_2017.nc # Real Copernicus currents for Persian Gulf (2.19 MB)
│           └── red_sea_current_2019.nc      # Real Copernicus currents for Red Sea (1.98 MB)
├── demo/
│   ├── output/                         # Investigation JSON, GeoJSON, CSV, masks, figures
│   ├── end_to_end_real_workflow_demo.py # Offline workflow utilities
│   └── run_00643_integration.py        # Dedicated 00643 integration script
├── frontend/                           # React 18, MapLibre GL, TailwindCSS, Vite dashboard
├── gis/
│   ├── geometry/models.py              # Coordinate, Polygon, BoundingBox models
│   ├── measurements/models.py          # Geodesic area, perimeter, shape indices
│   ├── polygonizer.py                  # Raster-to-vector polygonizer
│   └── layers.py                       # Multi-layer GeoJSON constructors
├── ocean/
│   ├── currents/
│   │   └── loader.py                   # load_currents() with multi-level surface slice support
│   ├── drift/
│   │   ├── hindcast.py                 # hindcast_particles() (backward Lagrangian Euler)
│   │   ├── particle.py                 # simulate_particles() (forward Lagrangian Euler)
│   │   └── origin.py                   # Probable origin density and uncertainty
│   ├── interpolation/
│   │   └── environment.py              # interpolate_currents() (bilinear xarray interpolation)
│   └── time/
│       └── synchronization.py          # UTC normalization
├── reports/
│   ├── sentinel1_inventory.csv         # Full 1,200-scene inventory with coordinates & clusters
│   └── sentinel1_region_analysis.json  # DBSCAN regional cluster analysis
├── scripts/
│   ├── analyze_sentinel1_collection.py # Regional cluster analysis tool
│   ├── run_pipeline.py                 # Universal CLI runner (--image-id 00XXX)
│   ├── test_case_00052.py              # 00052 evaluation script
│   └── data/copernicus_download_test.py# Copernicus subset download utility
├── tests/                              # PyTest test suites (667 collected tests)
└── unet_best.pth                       # Real trained PyTorch U-Net model weights (293.5 MB)
```

---

## 3. End-to-End Pipeline

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. Sentinel-1 SAR GeoTIFF (2048x2048, VV/VH, EPSG:4326)     │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ M1 Ingestion & M2 Preprocessing                             │
│ Module: demo.end_to_end_real_workflow_demo / satellite      │
│ Functions: inspect_sentinel1_tiff(), run_m2_preprocessing() │
│ Transforms: Radiometric dB clamp, 256x256 non-overlapping   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ M2 Deep Learning Semantic Segmentation                      │
│ Module: ai.inference.infer / OilSpillInference              │
│ Model: unet_best.pth (ResNet34 U-Net)                       │
│ Output: 8-bit binary mask (mask.png) & GeoTIFF (mask.tif)   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ M3 GIS Vectorization & Geodesic Measurements                │
│ Module: demo.end_to_end_real_workflow_demo / gis            │
│ Functions: run_m3_geometry(), measure_oil_spill()           │
│ Output: WGS84 Polygons, Geodesic Area (km²), Centroid       │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ M3/M4 Ocean Currents & Lagrangian Drift                     │
│ Module: ocean.currents.loader, ocean.drift.hindcast         │
│ Functions: load_currents(), interpolate_currents()          │
│ Drift: 72h Backward Hindcast (Origin) & 24h Forecast        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ M5 Historical AIS Attribution                               │
│ Module: ais.providers.gfw / GlobalFishingWatchAISProvider   │
│ Endpoint: POST /v3/4wings/report (public-global-presence)   │
│ Processing: Geodesic proximity to centroid and drift track  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Artifact Generation (demo/output/)                          │
│ Deliverables: result.json, layers.geojson, trajectory.csv/   │
│ json, mask.png, mask.tif, and 6-panel scientific figure     │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Stage-by-Stage Implementation Matrix

| Stage | Input | Primary File & Function | Processing | Output | Dependencies | Status |
|---|---|---|---|---|---|---|
| **M1 Ingestion** | Local `.tif` in `01_Train_Val_Oil_Spill_images/Oil/` | `demo/end_to_end_real_workflow_demo.py` -> `inspect_sentinel1_tiff()` | Reads raster metadata, CRS, affine transform, band statistics | Metadata dictionary | `rasterio`, `numpy` | **VERIFIED / PASS** |
| **M2 Preprocessing** | Raw 2-band image array (`float32`) | `demo/end_to_end_real_workflow_demo.py` -> `run_m2_preprocessing()` | Clamps non-physical dB, tiles into 64 patches of 256x256 | Tile tensor batch, tile metadata | `numpy`, `torch` | **VERIFIED / PASS** |
| **M2 Segmentation** | TIFF file path or tile tensor batch | `ai/inference/infer.py` -> `OilSpillInference.predict()` | Passes tiles through ResNet34 U-Net, stitches full probability map, thresholds at 0.5 | Binary mask (`np.ndarray`), probability heatmap | `torch`, `torchvision`, `cv2`, `rasterio` | **VERIFIED / PASS** |
| **M3 GIS Geometry** | Binary mask & raster affine transform | `demo/end_to_end_real_workflow_demo.py` -> `run_m3_geometry()` | Extracts polygon contours using `rasterio.features.shapes`, transforms to WGS84, calculates Karney geodesic area/perimeter | `GisPolygon`, `OilSpillMeasurement` | `shapely`, `pyproj`, `rasterio` | **VERIFIED / PASS** |
| **M3 Ocean Currents** | Copernicus Marine NetCDF file (`.nc`) | `ocean/currents/loader.py` -> `load_currents()`, `ocean/interpolation/environment.py` -> `interpolate_currents()` | Validates dimensions, extracts surface level (`depth=0`), interpolates $u, v$ velocities at spill centroid | Eastward $u$, northward $v$, speed, heading | `xarray`, `scipy`, `pandas` | **VERIFIED / PASS** |
| **M4 Drift Simulation** | Observed centroid, current dataset, zero/ERA5 wind | `ocean/drift/hindcast.py` -> `hindcast_particles()`, `ocean/drift/particle.py` -> `simulate_particles()` | Backward Euler advection ($\Delta t = -3600\text{s}$, 72h) and Forward Euler advection ($\Delta t = +3600\text{s}$, 24h) | Chronological trajectory DataFrame, probable origin coordinate | `xarray`, `pandas`, `numpy` | **VERIFIED / PASS** |
| **M5 AIS Ingestion** | Spatial AOI & time window | `ais/providers/gfw.py` -> `GlobalFishingWatchAISProvider.fetch_ais_data()` | Queries GFW 4Wings API, normalizes vessel presence cells to canonical schema | Canonical pandas DataFrame with MMSI, vessel name, type, coordinates | `requests`, `pandas`, `.env` token | **VERIFIED / PASS** |
| **M5 Vessel Ranking** | AIS DataFrame, spill centroid, drift track coordinates | `scripts/run_pipeline.py` / `demo/run_00643_integration.py` | Computes minimum Haversine distance from vessel locations to spill centroid and to the 72h hindcast track | Sorted candidate vessel list with rank, MMSI, IMO, distances | `pandas`, `numpy` | **VERIFIED / PASS** |

---

## 5. Ocean Data Workflow (Copernicus Marine)

### Implementation Audit & Data Handling Truths

1. **Does the system download ocean data for every Sentinel image?**
   **NO.** The current implementation contains **no automatic background downloader**. The pipeline expects an existing local NetCDF file.
2. **Does it reuse existing NetCDF files?**
   **YES.** For example, all scenes in the Persian Gulf 2017 cluster (`00051`, `00052`, `00053`) reuse `data/sample/copernicus/persian_gulf_current_2017.nc`. Scenes in the Red Sea cluster (`00643`, `00644`) reuse `data/sample/copernicus/red_sea_current_2019.nc`.
3. **Is there currently a cache mechanism?**
   **NO.** There is no automated spatial/temporal SQLite or file-hash cache index. Matching is currently coordinated by folder lookup and regional boundary checks in the runner script.
4. **What determines the AOI?**
   The spatial AOI is derived from the detected spill centroid: standard bounding box is buffered by $\pm 1.25^\circ$ latitude and $\pm 1.0^\circ$ longitude (approximately $140\text{ km}$ radius).
5. **What determines the temporal range?**
   At least 72 hours prior to observation (for hindcasting) and at least 24 hours post-observation (for forecasting), typically downloaded as a 14-day window (7 days prior to 7 days post).
6. **What Copernicus dataset is used?**
   - **Multi-Year Historical Reanalysis:** `cmems_mod_glo_phy_my_0.083deg_P1D-m` (Global Ocean Physics Reanalysis, 1/12° daily).
   - **Near-Real-Time Analysis & Forecast:** `cmems_mod_glo_phy_anfc_merged-uv_PT1H-i` (Global Ocean Hourly Surface Currents).
7. **Which variables are used?**
   `uo` (eastward surface current velocity, $\text{m/s}$) and `vo` (northward surface current velocity, $\text{m/s}$).
8. **Which depth level is used?**
   The uppermost surface level: depth index `0` (depth $\approx 0.494\text{ m}$). Handled by `load_currents(..., select_surface=True)`.
9. **How is velocity interpolated?**
   Via `ocean/interpolation/environment.py`: bilinear spatial interpolation across latitude/longitude and linear interpolation across time using xarray / SciPy.
10. **What happens if NetCDF is missing?**
    The pipeline raises `FileNotFoundError` or cleanly skips the hydrodynamic step with `SKIPPED_NO_LOCAL_DATA`, warning that local data is absent for the scene coordinates.
11. **Deduplication for the 1,200-image dataset:**
    The 1,200 Sentinel-1 scenes fall into **35 spatial clusters** globally (per `reports/sentinel1_inventory.csv`). If ocean data is downloaded on a per-cluster basis, only **35 regional NetCDF files** are required, completely preventing 1,200 duplicate downloads.

---

## 6. AIS / Global Fishing Watch (GFW) Workflow

### GFW 4Wings Provider Specifications

- **API Endpoint:** `POST https://gateway.api.globalfishingwatch.org/v3/4wings/report`
- **Official Dataset:** `public-global-presence:latest`
- **Request Parameters:**
  - `datasets[0]=public-global-presence:latest`
  - `format=JSON`
  - `group-by=VESSEL_ID` (enforces uppercase enum)
  - `temporal-resolution=HOURLY`
  - `spatial-resolution=LOW` (~0.1° grid)
  - `spatial-aggregation=false`
  - `date-range=<start>,<end>` (ISO-8601 UTC)
- **AOI Request Body:** GeoJSON Polygon with 5 closed coordinates: `[[min_lon, min_lat], [max_lon, min_lat], [max_lon, max_lat], [min_lon, max_lat], [min_lon, min_lat]]`.
- **Response Normalization:** Parses JSON records into canonical pandas DataFrame columns: `mmsi`, `vessel_name`, `imo`, `callsign`, `flag`, `vessel_type`, `latitude`, `longitude`, `timestamp`, `presence_hours`, `provenance="gfw_grid_center"`.
- **Concurrency & Rate Limits:** Concurrency lock permits only 1 concurrent report request per API key. Bounded HTTP timeout `(10.0, 105.0)`. HTTP 524 recovery polls `GET /v3/4wings/last-report` with a bounded timeout (`max_recovery_timeout=120.0s`).
- **Token Security:** Bearer token is strictly loaded from `GFW_API_TOKEN` in `.env` and sanitized via `_sanitize()` to prevent exposure in logs or exceptions.

### Critical Scientific AIS Distinction

> [!IMPORTANT]
> **GFW 4Wings Vessel Presence $\ne$ Raw Sensor Trajectories**
> GFW 4Wings provides vessel presence activity aggregated into discrete spatial grid cells over time windows. The coordinates returned represent the **center of the grid cell** where a vessel was detected, not continuous transponder pings. Suspect attribution ranks vessels by proximity to the spill and drift track; ranking #1 indicates highest spatial-temporal correlation, **not proven legal culpability**.

---

## 7. Dual Verified Test Cases: 00052 & 00053

Both test cases were executed and verified against real Sentinel-1 SAR imagery, real Copernicus currents, and the live GFW 4Wings API.

| Parameter | Case 00052 (Verified Benchmark) | Case 00053 (Fresh Validation Run) |
|---|---|---|
| **GeoTIFF File** | `01_Train_Val_Oil_Spill_images/Oil/00052.tif` | `01_Train_Val_Oil_Spill_images/Oil/00053.tif` |
| **Marine Region** | Persian Gulf (offshore UAE) | Persian Gulf (offshore UAE) |
| **Observation Timestamp** | `2017-03-11 02:15:11 UTC` | `2017-03-11 02:15:11 UTC` |
| **M1 Status** | **PASS** (2048x2048, EPSG:4326) | **PASS** (2048x2048, EPSG:4326) |
| **M2 Oil Pixels** | 1,424,572 pixels (33.96% of scene) | 1,732,368 pixels (41.30% of scene) |
| **M2 Confidence** | Max: 1.0000, Mean: 0.9767 | Max: 1.0000, Mean: 0.9666 |
| **M3 Centroid** | **25.567163°N, 54.634578°E** | **25.592503°N, 54.652472°E** |
| **M3 Spill Area** | **71.0808 km²** ($71,080,806.9\text{ m}^2$) | **91.2548 km²** ($91,254,779.9\text{ m}^2$) |
| **M3 Perimeter** | 112.2843 km | 125.5204 km |
| **Slick Components** | 214 connected components | 141 connected components |
| **Copernicus Dataset** | `persian_gulf_current_2017.nc` | `persian_gulf_current_2017.nc` |
| **Surface Current Velocity** | $u=-0.0046\text{ m/s}, v=-0.0212\text{ m/s}$ (0.02 m/s, 192.2°) | $u=-0.0227\text{ m/s}, v=-0.0206\text{ m/s}$ (0.03 m/s, 227.8°) |
| **72h Hindcast Origin** | **25.654030°N, 54.739283°E** (14.27 km drift) | **25.683052°N, 54.825753°E** (20.08 km drift) |
| **24h Forecast Endpoint** | **25.541479°N, 54.637228°E** (2.87 km drift) | **25.567517°N, 54.647673°E** (2.82 km drift) |
| **M5 AIS Records Tracked** | 1,736 vessel presence records (1,736 vessels) | 1,636 vessel presence records (1,636 vessels) |
| **Top Suspect Vessel** | `DIAMOND QUEST` (MMSI: 353287000, 5.04 km) | `NAVIGATOR MAGELLAN` (MMSI: 636015937, 11.34 km) |
| **#2 Suspect Vessel** | `DHT LEOPARD` (MMSI: 477730700, 13.98 km) | `AL DURRAH` (MMSI: 374510000, 11.55 km) |
| **#3 Suspect Vessel** | `PASARGAD 100` (MMSI: 422033700, 15.17 km) | `QATAR SADIQ 2` (MMSI: 373632000, 12.87 km) |
| **Overall Pipeline Status**| **ALL PASS** | **ALL PASS** |

---

## 8. Automated Test Suite Reference

All tests run from the repository root `E:\SIH26\oil-spill-attribution`:

| Test Command | Module Covered | Test Count | Runtime | External Dependency | Expected Result |
|---|---|---|---|---|---|
| `.venv\Scripts\pytest tests/gis -q` | GIS geometry & measurements | 81 tests | ~0.10s | None (Offline) | 81 passed |
| `.venv\Scripts\pytest tests/ocean -q` | Copernicus loaders & drift models | 142 tests | ~3.0s | None (Offline NetCDF fixtures) | 142 passed |
| `.venv\Scripts\pytest tests/ais -q` | AIS filters, adapters & GFW client | 216 tests | ~4.0s | None (Live tests skipped) | 211 passed, 5 skipped |
| `.venv\Scripts\pytest tests/attribution -q`| Suspect scoring & correlators | 153 tests | ~6.5s | None (Offline) | 153 passed |
| `.venv\Scripts\pytest tests/satellite -q` | Ingestion, tiling, normalization | 29 tests | ~4.8s | None (Offline) | 29 passed |
| `.venv\Scripts\pytest tests/integration -q`| End-to-end integration contracts | 22 tests | ~21.0s | None (Offline) | 22 passed |
| `.venv\Scripts\pytest tests/backend -q` | FastAPI backend endpoints | 14 tests | ~95.0s | Local PostgreSQL fallback | 14 passed |

> [!NOTE]
> `tests/ai/test_step15_production_validation.py` requires starting the M1 microservice first:  
> `python -m uvicorn ai.api.main:app --host 127.0.0.1 --port 8001`

---

## 9. Reusable CLI Runner Guide

The universal pipeline runner [`scripts/run_pipeline.py`](file:///E:/SIH26/oil-spill-attribution/scripts/run_pipeline.py) accepts arbitrary image IDs or paths:

```powershell
# Run arbitrary image by ID (auto-detects zero-padding and matching local Copernicus file)
.venv\Scripts\python scripts/run_pipeline.py --image-id 00053

# Run with custom Copernicus NetCDF currents file
.venv\Scripts\python scripts/run_pipeline.py --image-id 00643 --ocean-file data/sample/copernicus/red_sea_current_2019.nc

# Run offline without querying GFW API
.venv\Scripts\python scripts/run_pipeline.py --image-id 00052 --skip-ais
```

### Outputs Generated

For every scene `<image_id>`, artifacts are written to `demo/output/`:
- `real_<image_id>_result.json`: Machine-readable structured investigation record.
- `real_<image_id>_layers.geojson`: MapLibre / GIS layers (spill polygon, centroid, origin, drift track, suspect vessels).
- `real_<image_id>_drift_trajectory.csv`: Timestep coordinates for 72h hindcast and 24h forecast.
- `real_<image_id>_drift_trajectory.json`: Detailed trajectory summary.
- `real_<image_id>_mask.png`: 8-bit binary segmentation raster.
- `real_<image_id>_mask.tif`: Georeferenced GeoTIFF segmentation raster.
- `real_<image_id>_demo.png`: 6-panel publication-quality analytical figure.

---

## 10. Known Limitations & Troubleshooting

1. **GFW 4Wings Gateway Timeout (HTTP 524):** Large spatial areas or date windows >7 days can trigger Cloudflare 524 timeouts. The provider handles bounded recovery via `/last-report`.
2. **Missing Local Ocean Currents for Uncached Clusters:** If testing an image outside the Persian Gulf or Red Sea (e.g. North Sea `00001.tif` or Mediterranean `00009.tif`), the runner reports `SKIPPED_NO_LOCAL_DATA` unless a matching NetCDF file is provided via `--ocean-file`.
3. **M1 Microservice Port Refusal:** If running `test_step15_production_validation.py`, ensure Uvicorn is launched on port 8001 first. Direct local inference (`OilSpillInference` / `run_pipeline.py`) does not require Uvicorn.
