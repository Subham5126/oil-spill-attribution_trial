# API Design

## Oil Spill Attribution System

The backend exposes the project's scientific results to the frontend through
FastAPI.

The API is responsible for orchestration, validation, database access and
result delivery. Core scientific computation remains inside its respective
modules.

---

## Architecture

```text
Frontend
   ↓
FastAPI
   ↓
Services
   ↓
AI / GIS / Drift / AIS / Attribution
   ↓
PostgreSQL + PostGIS
   ↓
External Data Storage