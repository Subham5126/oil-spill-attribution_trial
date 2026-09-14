# OILTRACE — Full System Technical Architecture & Operational Guide

## 1. Executive System Overview
OILTRACE is an operational, AI-driven oil spill detection, hydrodynamic drift hindcasting, and responsible vessel attribution platform. It integrates remote sensing satellite SAR imagery, deep learning semantic segmentation, WGS-84 geodesic GIS measurements, Copernicus Marine hydrodynamic ocean current modeling, and AIS maritime trajectory correlation.

---

## 2. Core Modules Architecture

### 2.1 M1: Satellite SAR Ingestion & Validation
- **Path**: `scripts/inspect_s1_tiff.py`, `backend/services/image_service.py`
- **Function**: Validates GeoTIFF headers, GDAL/Rasterio CRS tags (e.g. EPSG:4326 or UTM), radiometric bounds, dimensions (e.g., 2048x2048), pixel resolution, and observation timestamps.
- **Data Source**: 1,200 Sentinel-1 scenes registered from `reports/sentinel1_inventory.csv` and `01_Train_Val_Oil_Spill_images/Oil/`.

### 2.2 M2: Radiometric Preprocessing & U-Net Deep Learning Segmentation
- **Path**: `ai/inference/infer.py`, `ai/models/unet.py`
- **Model Weights**: `unet_best.pth`
- **Function**: Performs min-max intensity normalization, tiling/patching of SAR backscatter, applies PyTorch U-Net inference, thresholds probability maps (optimal threshold: 0.50), and outputs binary GeoTIFF and PNG masks.

### 2.3 M3: GIS Vectorization & Geodesic Measurements
- **Path**: `scripts/m3_geometry.py`, `backend/services/pipeline_service.py`
- **Function**: Extracts contours using OpenCV/Shapely, transforms raster pixel coordinates into geographic latitude/longitude (EPSG:4326), computes true ellipsoidal surface area (km² and m²) and perimeter using `pyproj.Geod` (WGS-84 ellipsoid), calculates center-of-mass centroid, aspect ratio (elongation), and compactness (Polsby-Popper score).

### 2.4 M4: Copernicus Oceanographic Drift Hindcasting & Forecasting
- **Path**: `ocean/currents.py`, `ocean/drift/hindcast.py`, `ocean/drift/particle.py`, `backend/adapters/ocean_adapter.py`
- **Forcing Data**: Copernicus Marine Service (CMEMS) Global Ocean Physics Reanalysis NetCDF files (`uo`, `vo` eastward/northward surface velocities):
  - Persian Gulf (2017): `data/sample/copernicus/persian_gulf_current_2017.nc`
  - Red Sea (2019): `data/sample/copernicus/red_sea_current_2019.nc`
- **Advection Engine**: 4th-order Runge-Kutta / Forward-Euler Lagrangian particle simulation:
  - 72-Hour Backward Hindcasting: Advects spill particles backward in time to locate the estimated release origin point and calculate spatial dispersion uncertainty envelope (95% radius).
  - 24-Hour Forward Forecasting: Advects particles forward in time to project slick trajectory and coastal impact zones.

### 2.5 M5: AIS Trajectory Filtering & Vessel Attribution Ranking
- **Path**: `ais/providers/gfw.py`, `ais/filtering/spatial.py`, `backend/services/pipeline_service.py`
- **Provider**: Global Fishing Watch (GFW) 4Wings API / Local AIS store.
- **Algorithm**: Queries all maritime vessels within the 95% spatial dispersion envelope and temporal hindcast window.
- **Attribution Criteria**: Multi-criteria weighted scoring:
  - Spatial proximity to discharge origin (40% weight)
  - Temporal alignment with discharge window (35% weight)
  - Vessel trajectory heading vs drift axis (15% weight)
  - Kinematic behaviour / speed abnormalities (10% weight)
- **Reporting Rule**: Vessels are categorized as "Candidate Vessels" or "Correlation Candidates", accompanied by scientific disclaimers in accordance with international maritime jurisprudence.

### 2.6 Forensic Reporting Engine
- **Path**: `backend/services/report_service.py`
- **Standard**: IMO MARPOL Annex I evidentiary standards.
- **Structure**: 11 mandatory sections:
  1. Executive Summary
  2. Incident Information
  3. Sentinel-1 Observation Evidence
  4. Spill Characterization & GIS Measurements
  5. Oceanographic Current & Drift Hindcast Analysis
  6. AIS Vessel Traffic Correlation
  7. Evidentiary Confidence Assessment
  8. Candidate Vessel Assessment
  9. Scientific & Observational Limitations
  10. Recommended Operational Next Steps
  11. Technical Provenance & Cryptographic SHA-256 Digest

---

## 3. Database Schema (`data/oiltrace.db`)
- **Table `investigations`**:
  - `investigation_id`: Primary key (e.g. `INV-2026-40662`)
  - `title`: User-facing title
  - `image_id`: Referenced Sentinel-1 scene
  - `pipeline_status`: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`
  - `spill_area_km2`: Geodesic surface area in square kilometers
  - `centroid_lat`, `centroid_lon`: Spatial center of mass
  - `suspect_vessel`: Attributed primary candidate vessel
  - `result_json`: Full end-to-end serialized result JSON
  - `geojson_layers`: MapLibre GL FeatureCollection with polygons, points, and tracks
  - `pipeline_stages_json`: Stage-by-stage status dictionary

---

## 4. Operational Instructions

### Prerequisites
- Python 3.10+ in `.venv` with `rasterio`, `torch`, `torchvision`, `xarray`, `netCDF4`, `fastapi`, `uvicorn`, `sqlalchemy`, `shapely`, `pyproj`.
- Node.js 18+ in `frontend/`.

### Starting the Backend
```powershell
cd E:\SIH26\oil-spill-attribution
.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### Starting the Frontend
```powershell
cd E:\SIH26\oil-spill-attribution\frontend
npm run dev
```

### Running Automated Test Suite
```powershell
.venv\Scripts\python -c "
from fastapi.testclient import TestClient
from backend.main import app
c = TestClient(app)
assert c.get('/api/health').status_code == 200
assert c.get('/api/images').status_code == 200
assert c.get('/api/investigations').status_code == 200
print('Full test suite passed!')
"
```
