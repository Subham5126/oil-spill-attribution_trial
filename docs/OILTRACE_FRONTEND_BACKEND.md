# OILTRACE — Frontend & Backend Integration Architecture

## Overview
This document describes the complete integration between the **OILTRACE FastAPI Backend** and the **React + Vite + MapLibre GL Frontend**. All mock and hardcoded fixtures have been decommissioned in favor of an end-to-end, data-driven architecture powered by real Sentinel-1 SAR imagery, U-Net segmentation, GIS geodesic vectorization, Copernicus Marine hydrodynamic drift, and AIS vessel correlation.

---

## Architecture Diagram

```text
+-----------------------------------------------------------------------------------+
|                            React Frontend (Port 5173)                             |
|                                                                                   |
|  [Scene Selector]      [Live Progress Stream]     [MapLibre GL GIS]  [MARPOL Rep] |
|   (1,200 Scenes)        (6 Lifecycle Stages)      (Spill + Drift + AIS) (Markdown)|
+-----------------------------------------------------------------------------------+
                                         │
                   REST & GeoJSON via fetch() [VITE_API_URL]
                                         ▼
+-----------------------------------------------------------------------------------+
|                            FastAPI Backend (Port 8000)                            |
|                                                                                   |
|  /api/health               — Health & DB Liveness                                 |
|  /api/images               — Real Sentinel-1 Inventory Discovery                  |
|  /api/investigations       — Incident Lifecycle CRUD & Persistence                |
|  /api/investigations/{id}/run   — Real Pipeline Orchestrator                      |
|  /api/investigations/{id}/status— Live Lifecycle Stage Poller                     |
|  /api/investigations/{id}/map   — Real GeoJSON Vector Features                    |
|  /api/investigations/{id}/report— 11-Section MARPOL Annex I Forensic Report       |
|  /api/investigations/{id}/report/download — Markdown Dossier Attachment           |
+-----------------------------------------------------------------------------------+
       │                         │                           │                │
       ▼                         ▼                           ▼                ▼
[SQLite / Postgres]   [M1/M2: U-Net Model]   [M4: Copernicus Marine]   [M5: GFW AIS]
 data/oiltrace.db      weights/unet_best.pth   NetCDF Surface Velocity  Spatial/Temporal
```

---

## 1. Backend REST Endpoints

### 1.1 Image Discovery
- `GET /api/images`
  - Scans `reports/sentinel1_inventory.csv` and `01_Train_Val_Oil_Spill_images/Oil/`.
  - Returns metadata including geographic coordinates, acquisition timestamp, region, and local Copernicus NetCDF compatibility.
- `GET /api/images/{image_id}`
  - Returns detailed bounds, polarization, dimensions, and path for a specific scene.

### 1.2 Investigation Lifecycle
- `GET /api/investigations`
  - Lists all registered incidents from SQLite (`data/oiltrace.db`).
- `POST /api/investigations`
  - Creates a new investigation record with auto-assigned ID (`INV-YYYY-XXXXX`).
  - Auto-extracts centroid and region from Sentinel-1 image registry.
- `GET /api/investigations/{id}`
  - Fetches complete metadata for an investigation.
- `GET /api/investigations/{id}/status`
  - Returns live processing stage (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`), percentage progress, stage statuses dictionary, and audit log trace.
- `POST /api/investigations/{id}/run`
  - Triggers the real attribution pipeline synchronously or in a background task:
    1. **M1**: Ingestion & validation of Sentinel-1 GeoTIFF.
    2. **M2**: Radiometric preprocessing & PyTorch U-Net inference (`unet_best.pth`).
    3. **M3**: Vectorization, polygonization, and WGS-84 geodesic measurements (area, perimeter, centroid, aspect ratio, compactness).
    4. **M4**: Automated Copernicus NetCDF matching (`persian_gulf_current_2017.nc` / `red_sea_current_2019.nc`), 72-hour backward Lagrangian particle drift hindcasting, and 24-hour forward dispersion forecasting.
    5. **M5**: Spatial-temporal AIS filtering and candidate vessel attribution ranking.
    6. **REPORT**: 11-section MARPOL Annex I dossier generation and cryptographic SHA-256 seal.

### 1.3 GeoJSON & Reports
- `GET /api/investigations/{id}/map`
  - Returns dynamic GeoJSON FeatureCollection:
    - Detected oil slick polygon
    - Spill centroid point
    - Backward drift hindcast trajectory & probable origin point
    - Forward drift forecast trajectory
    - Correlated AIS candidate vessel positions & track segments
- `GET /api/investigations/{id}/report`
  - Returns structured JSON containing all 11 IMO MARPOL Annex I evidentiary sections.
- `GET /api/investigations/{id}/report/download`
  - Downloads the complete forensic dossier as a formatted Markdown (`.md`) file.

---

## 2. Frontend Application Workflow

### 2.1 Starting an Investigation (`NewInvestigationPage.tsx`)
1. The user navigates to **New Incident Investigation**.
2. The UI queries `GET /api/images` and populates the scene dropdown with real GeoTIFF scenes (e.g. `00052.tif`, `00643.tif`).
3. Scene metadata (file, region, coordinates, Copernicus compatibility) is displayed in real-time.
4. Clicking **Execute Real Pipeline**:
   - Calls `POST /api/investigations` to register the case.
   - Calls `POST /api/investigations/{id}/run` to start execution.
   - Automatically navigates to **Analysis Process**.

### 2.2 Monitoring Live Progress (`AnalysisProcessPage.tsx`)
1. The page polls `GET /api/investigations/{id}/status` every 1.5 seconds.
2. Animated progress bar tracks overall percentage (0% to 100%).
3. Stage badges display real-time statuses (`RUNNING`, `COMPLETED`, `PASS`, `BLOCKED`, `FAILED`).
4. Live terminal log renders real execution notes from the pipeline.
5. Upon completion, direct links allow inspecting candidate vessels, viewing the GIS map, or downloading the MARPOL report.

### 2.3 Operational Command Hub (`DashboardPage.tsx`)
1. Displays the active incident ID, region, and real SAR source file.
2. Renders the interactive MapLibre GL map centered on the spill centroid.
3. Provenance ribbon confirms model weights, CRS, and Copernicus dataset used.

### 2.4 MARPOL Legal Dossier (`ReportsPage.tsx`)
1. Renders the 11-section forensic report generated from actual pipeline outputs.
2. Shows cryptographic SHA-256 evidence digest.
3. Download button triggers `GET /api/investigations/{id}/report/download` for official documentation export.

---

## 3. How to Launch and Test

### Terminal 1: Backend
```powershell
cd E:\SIH26\oil-spill-attribution
.venv\Scripts\python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```
- API Docs: `http://127.0.0.1:8000/docs`
- Health Check: `http://127.0.0.1:8000/api/health`

### Terminal 2: Frontend
```powershell
cd E:\SIH26\oil-spill-attribution\frontend
npm run dev
```
- Web Application: `http://localhost:5173`
