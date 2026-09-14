# OILTRACE Application User & Operator Guide

This guide details how to launch, operate, and manage the **OILTRACE Satellite Oil Spill Attribution & Investigation System**.

---

## 1. Quick Start: Launching the Services

The application consists of a FastAPI Python backend and a React/Vite/Tailwind frontend.

### Step 1: Start the Backend Server

Open a terminal in the repository root:
```powershell
cd E:\SIH26\oil-spill-attribution
.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
- **Backend API URL**: `http://127.0.0.1:8000`
- **Interactive OpenAPI Documentation**: `http://127.0.0.1:8000/docs`
- **Database**: SQLite database automatically initialized at `data/oiltrace.db`.

### Step 2: Start the Frontend Application

Open a second terminal:
```powershell
cd E:\SIH26\oil-spill-attribution\frontend
npm run dev
```
- **Web Interface URL**: `http://localhost:5173`

---

## 2. Investigation Lifecycle & Workflow

### 1. Launching a New Investigation
1. In the sidebar, click **New Incident** (`/new-investigation`).
2. Select a Sentinel-1 SAR scene from the available scenes list (e.g., `00052.tif` or `00053.tif`).
3. Enter an investigation title and operational notes.
4. Click **Launch Investigation**.
5. The pipeline automatically runs the 6 core stages:
   - SAR radiometric calibration & speckle filtering
   - U-Net deep learning dark slick inference
   - WGS-84 geodesic polygonization and measurement
   - Copernicus CMEMS hydrodynamic Lagrangian reverse drift hindcasting
   - AIS candidate trajectory correlation and multi-criteria scoring
   - Forensic dossier packaging

### 2. Monitoring Execution & Real-Time Telemetry
- Navigate to **Live Pipeline** (`/live-investigations`) to watch the progress of active runs.
- Use **Pipeline Stream** (`/analysis-process`) to view detailed log outputs, intermediate confidence maps, and particle coordinates as they compute.

### 3. Reviewing Attribution on the Dashboard
- In **Dashboard** (`/dashboard`):
  - View high-level metrics (Recorded Incidents, Cumulative Spill Area, AIS Profiled Vessels, Top Ranked Suspect).
  - Use the **Recent Forensic Incidents** cards to quickly switch between investigated cases.
  - Interact with the **GIS Evidence Canvas**: toggle layers (Slick Polygons, Origin Points, Dispersion Ellipses, Vessel Paths).
  - Inspect the **Multi-Criteria Radar Chart** showing spatial, temporal, trajectory, and behavioral scores.
  - Review the **Member 3 GIS Measurements** panel for geodesic area ($\text{km}^2$), perimeter, compactness, and centroid.

### 4. Managing Investigations
- In **Investigations** (`/investigations`):
  - **Search**: Search by ID, region, vessel, or keyword.
  - **Filter**: Filter by status (Completed, Active, Failed), star favorite incidents, or include soft-deleted items.
  - **Sort**: Sort by date (newest/oldest), spill area, or title.
  - **Actions**:
    - Click **Star** to bookmark critical cases.
    - Click **Re-run** to spawn an identical or updated investigation run linked to the parent case.
    - Click **Delete** to move the case to trash (soft delete).
    - In the delete modal, check **Permanent Purge** to erase the database entry and incident-specific output files (`real_{id}_*`, `OILTRACE_Report_{id}.md`) while strictly preserving shared satellite scenes and model weights.
    - Click **Restore** on deleted cases to return them to the active registry.

### 5. Compliance & Audit History
- In **History Log** (`/investigation-history`):
  - Review the complete chronological log of all cases, timestamps, and status changes.
  - Click **Export Audit Log (JSON)** to download a complete cryptographic JSON audit file for regulatory compliance or maritime court submission.

### 6. Vessel Intelligence Registry
- In **Vessel Intelligence** (`/vessel-intelligence`):
  - Inspect all AIS candidate vessels detected across all incident release corridors.
  - Filter by high-score suspects ($\ge 60\%$) or multi-incident candidates.
  - Expand any vessel row to see all past incidents where the vessel was in proximity.

### 7. Evidence Custody & File Download
- In **Evidence Library** (`/evidence-library`):
  - Select any incident case to inspect its physical artifacts on disk.
  - Verify file size, availability status (`AVAILABLE` vs `UNAVAILABLE`), and provenance.
  - Download raw GeoTIFFs, mask PNGs, vector GeoJSONs, candidate CSVs, and markdown reports.

### 8. System Health Diagnostics
- In **System Status** (`/system-status`):
  - Check the health of the FastAPI engine, SQLite database, PyTorch ML models, GDAL/Rasterio drivers, Copernicus grids, and GFW AIS tokens.
  - Click **Run Self-Test Diagnostics** to verify that all drivers and dependencies are operational.

---

## 3. Manual Configuration Steps (External APIs)

To enable live data downloading from third-party services, perform the following optional configuration steps:

### 1. Global Fishing Watch (GFW) AIS API Key
To query live vessel positions outside the local historical scenes:
1. Register for a free API token at [globalfishingwatch.org](https://globalfishingwatch.org/).
2. In the project root, open `.env` (or create one from `.env.example`).
3. Set your token:
   ```env
   GFW_API_TOKEN=your_token_here
   ```
4. Verify in the web UI under **System Status** (`/system-status`) that the GFW subsystem shows `OPERATIONAL`.

### 2. Copernicus Marine Service (CMEMS) Credentials
To download live NetCDF hydrodynamic ocean current grids dynamically:
1. Register at [marine.copernicus.eu](https://marine.copernicus.eu/).
2. Set your credentials in `.env`:
   ```env
   COPERNICUS_USERNAME=your_username
   COPERNICUS_PASSWORD=your_password
   ```
3. Existing NetCDF grids (such as `persian_gulf_current_2017.nc` in `data/copernicus/`) will continue to work offline without credentials.

### 3. Model Weights (`models/unet_best.pth`)
- Trained PyTorch model checkpoints are stored in `models/unet_best.pth`.
- When training a new model or updating weights, place the `.pth` file into the `models/` directory; the system will automatically detect and load it upon startup.
