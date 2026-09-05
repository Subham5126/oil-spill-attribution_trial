# Database Design

## Oil Spill Attribution System

PostgreSQL + PostGIS is the primary database for structured, searchable and
geospatial project data.

Large raster datasets, raw satellite products, AIS archives and model weights
must remain in external/file storage rather than PostgreSQL.

---

## Architecture

```text
Satellite / AI / GIS / Drift / AIS
              ↓
          Backend
              ↓
      PostgreSQL + PostGIS
              ↓
           Frontend