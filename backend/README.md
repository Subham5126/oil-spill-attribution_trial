# OilTrace Backend & Integration Layer

The OilTrace Backend is a production-grade FastAPI application that orchestrates the entire satellite oil spill detection, hydrodynamic drift modelling, AIS vessel correlation, and multi-criteria attribution pipeline.

It bridges the scientific modules developed by the domain teams, provides PostgreSQL + PostGIS spatial persistence, manages asynchronous background processing via Celery and Redis, and exposes RESTful and GeoJSON vector layer APIs for the React + MapLibre frontend.

---

## 1. Architecture

```text
                               ┌─────────────────────────┐
                               │  React + MapLibre UI    │
                               └────────────┬────────────┘
                                            │ HTTP / JSON / GeoJSON
                                            ▼
                               ┌─────────────────────────┐
                               │     FastAPI Backend     │
                               │    (backend/main.py)    │
                               └───────┬───────────┬─────┘
                                       │           │ Enqueue Task
                         Service Calls │           ▼
                                       │    ┌──────────────┐
                                       │    │ Celery Worker│
                                       │    └──────┬───────┘
                                       │           │
                                       ▼           ▼
                         ┌───────────────────────────────┐
                         │       Pipeline Service        │
                         └──────────────┬────────────────┘
                                        │
     ┌──────────────────────────────────┴──────────────────────────────────┐
     │                                                                     │
     ▼                                                                     ▼
[Member 2 Adapter: Satellite]                                 [Member 4 Adapter: Ocean/Drift]
  - SentinelObservation contract                                - Copernicus currents (.nc)
  - Awaiting tomorrow's module                                  - ERA5 wind fields (.nc)
     │                                                          - Lagrangian forward/backward
     ▼                                                          - Probable origin clustering
[Member 1 Adapter: AI Segmentation]                             - Empirical spatial dispersion (95%)
  - SegmentationResult contract                                            │
  - Awaiting tomorrow's module                                             ▼
     │                                                        [Member 5 Adapter: AIS]
     ▼                                                          - Temporal & spatial filtering
[Member 3 Adapter: GIS]                                         - Hermite trajectory interpolation
  - WGS84 geodesic area/perimeter                                          │
  - Centroid, bounding box, aspect ratio                                   ▼
  - Multi-layer GeoJSON export                                [Member 5 Adapter: Attribution]
     │                                                          - 4-Tier multi-criteria scoring
     └──────────────────────────────────┬───────────────────────- Forensic narrative dossiers
                                        │
                                        ▼
                         ┌───────────────────────────────┐
                         │     PostgreSQL + PostGIS      │
                         │    (SQLAlchemy + Alembic)     │
                         └───────────────────────────────┘
```

---

## 2. Environment Variables

All configuration is loaded from `.env` using `backend/core/config.py`. See `.env.example` for reference.

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | Runtime mode: `development`, `production`, `test` |
| `APP_NAME` | `OilTrace Attribution Backend` | Service identifier |
| `DEBUG` | `true` | Debug logging and reloading |
| `DEMO_MODE` | `true` | Serves authoritative demonstration results if external services are offline |
| `DATABASE_URL` | None | PostgreSQL+PostGIS connection string (e.g. `postgresql+psycopg://postgres:postgres@localhost:5432/oiltrace`) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis broker and backend URL |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker URL |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Celery result storage |
| `CELERY_TASK_ALWAYS_EAGER` | `false` | When `true`, executes Celery tasks locally/synchronously |
| `AIS_DATA_DIR` | `data/ais` | Directory containing NOAA historical AIS CSVs |
| `OCEAN_DATA_DIR` | `data/sample` | Directory containing Copernicus and ERA5 NetCDF files |
| `SATELLITE_DATA_DIR` | `data/satellite` | Directory containing Sentinel-1 SAR products |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed CORS origins for Vite frontend |
| `SECRET_KEY` | Development key | Cryptographic secret for production tokens |

---

## 3. PostgreSQL & PostGIS Setup

### Using Docker Compose (Recommended)
```bash
# Start PostgreSQL 16 with PostGIS 3.4 and Redis 7
docker compose up -d db redis
```

### Manual Installation
1. Install PostgreSQL 16+ and PostGIS extension.
2. Create database:
   ```sql
   CREATE DATABASE oiltrace;
   \c oiltrace
   CREATE EXTENSION IF NOT EXISTS postgis;
   ```
3. Set your connection URL in `.env`:
   ```bash
   DATABASE_URL=postgresql+psycopg://postgres:yourpassword@localhost:5432/oiltrace
   ```

---

## 4. Redis Setup

### Using Docker Compose
```bash
docker compose up -d redis
```

### Native / Local Service
- Linux/macOS: `sudo systemctl start redis-server`
- Windows: Run Redis via WSL or Docker Desktop.

---

## 5. Running FastAPI

Activate the Python virtual environment and launch Uvicorn:

```powershell
# Windows PowerShell
cd E:\SIH26\oil-spill-attribution
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

FastAPI OpenAPI documentation will be available at:
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

---

## 6. Running Celery Worker

Start the Celery worker to handle asynchronous pipeline executions:

```powershell
cd E:\SIH26\oil-spill-attribution
.\.venv\Scripts\Activate.ps1
celery -A backend.workers.celery_app worker --loglevel=info
```

*Note: If Redis is offline or not installed, the backend automatically executes pipeline jobs via local background tasks or synchronous execution without crashing.*

---

## 7. Alembic Migrations

Run database migrations to initialize all tables and spatial schemas:

```powershell
# Check current migration head
python -m alembic heads

# Apply all migrations to database
python -m alembic upgrade head

# Roll back migration
python -m alembic downgrade -1
```

All 8 core database tables are migrated automatically:
1. `investigations`
2. `spill_detections`
3. `drift_runs`
4. `origin_candidates`
5. `vessels`
6. `ais_tracks`
7. `attribution_results`
8. `reports`

---

## 8. Demo Mode vs. Real Mode

The backend implements a strict separation between **DEMO** and **REAL** execution:

### Demo Mode (`DEMO_MODE=true`)
- Serves the authoritative pre-computed end-to-end demo results (`demo/output/end_to_end_result.json`) and vector layers (`demo/output/end_to_end_layers.geojson`).
- Explicitly flags provenance as `data_source_mode: "DEMO"`.
- Allows full development and testing of all frontend pages and API consumers without requiring active database connections or external sensor feeds.

### Real Mode (`DEMO_MODE=false`)
- Directly runs the complete scientific workflow through `PipelineService`.
- Queries Copernicus currents, ERA5 wind, and historical AIS trajectories.
- Persists entities into PostgreSQL/PostGIS.
- Distinguishes real API failures from fallback behavior.

---

## 9. API Endpoints

### System & Health
- `GET /api/health` — Returns status of backend, PostgreSQL, Redis, and demo mode.

### Investigations
- `GET /api/investigations` — List all active and completed investigations.
- `POST /api/investigations` — Create a new oil spill investigation.
- `GET /api/investigations/{id}` — Fetch details for a specific incident.
- `GET /api/investigations/{id}/status` — Fetch lifecycle and progress status.
- `GET /api/investigations/{id}/result` — Fetch end-to-end attribution result for incident.

### Pipeline Orchestration
- `POST /api/pipeline/run` — Enqueue or trigger end-to-end pipeline run.
- `GET /api/pipeline/latest` — Fetch latest end-to-end result (consumed by Dashboard).
- `GET /api/pipeline/{id}` — Fetch result by investigation ID.
- `GET /api/pipeline/{id}/status` — Status tracker with stage-by-stage lifecycle.

### Spill Detection & Geometry (Member 3)
- `GET /api/spills/{id}` — Fetch spill measurements, area, perimeter, and shape metrics.
- `GET /api/spills/{id}/geometry` — Fetch GeoJSON polygon and bounding box.

### Ocean & Drift Simulation (Member 4)
- `GET /api/drift/{id}` — Fetch Lagrangian forward/backward trajectories & origin.
- `POST /api/drift/simulate` — Custom on-demand drift simulation (lat, lon, duration, timestep).

### Maritime Vessels & AIS (Member 5)
- `GET /api/vessels` — List vessels in maritime registry.
- `GET /api/vessels/{mmsi}` — Retrieve details of specific vessel by MMSI.

### Attribution & Suspect Ranking (Member 5)
- `GET /api/attribution/{id}` — Fetch multi-criteria tier scores and ranked suspect vessels.

### GIS Layers & GeoJSON
- `GET /api/layers/geojson` — Active multi-layer GeoJSON FeatureCollection for MapLibre.
- `GET /api/layers/{id}` — Investigation-specific GeoJSON FeatureCollection.

### Forensic Reports
- `GET /api/reports` — List all MARPOL Annex I forensic dossiers.
- `GET /api/reports/{id}` — Retrieve specific dossier with SHA-256 integrity hash.
- `POST /api/reports` — Generate and sign a new dossier for an investigation.

---

## 10. Integration Flow

1. **Investigation Created**: An incident record is initialized with UTC observation timestamp and initial coordinates.
2. **Satellite Observation**: Sentinel-1 SAR acquisition adapter resolves observation bounds and polarization.
3. **AI Segmentation**: Deep learning segmentation mask identifies dark slick morphology and confidence.
4. **GIS Extraction**: Member 3 geodesics calculate true WGS84 surface area, perimeter, centroid, aspect ratio, and compactness.
5. **Ocean/Drift Modelling**: Member 4 loads Copernicus currents and ERA5 wind datasets, executing 4h backward Lagrangian hindcasting and 2h forward forecasting.
6. **Probable Release Origin**: KDE clustering establishes the candidate origin point and 95% spatial dispersion uncertainty radius.
7. **AIS Spatiotemporal Search**: Member 5 queries historical AIS tracks within the dynamic uncertainty cone, interpolates via kinematic Hermite spline, and reconstructs vessel passages.
8. **Multi-Tier Attribution**: Member 5 evaluates Spatial (40%), Temporal (35%), Trajectory (15%), and Behaviour (10%) scores to identify and rank suspects.
9. **Persistence & Cartography**: Results and GeoJSON layers are written to PostgreSQL/PostGIS and exported for frontend MapLibre visualization.

---

## 11. Tomorrow's Member 1 & Member 2 Integration Points

The integration layer was engineered specifically so that Member 1 and Member 2 modules plug in tomorrow without altering the backend architecture:

### Member 2: Sentinel-1 Satellite Processing
- **Target File**: `backend/adapters/satellite_adapter.py`
- **Class to Implement**: `SatelliteAdapterInterface`
- **Required Methods**:
  - `acquire(product_id: str) -> SatelliteObservation`
  - `preprocess(observation: SatelliteObservation) -> Path`
- **Input Contract**: Product ID / safe archive path
- **Output Contract**: Normalized `SatelliteObservation` containing calibrated GeoTIFF path, acquisition timestamp, polarization, and WGS84 bounds.

### Member 1: AI Oil Spill Segmentation
- **Target File**: `backend/adapters/ai_adapter.py`
- **Class to Implement**: `AIAdapterInterface`
- **Required Methods**:
  - `segment(raster_path: Path) -> SegmentationResult`
- **Input Contract**: Path to preprocessed SAR raster from Member 2
- **Output Contract**: Normalized `SegmentationResult` containing 2D binary/probability mask, confidence score, and model architecture metadata.
