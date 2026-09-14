# OILTRACE Operational Investigation Platform — Feature Specification

This document provides a comprehensive overview of all operational features, interfaces, scientific data contracts, and management workflows in the **OILTRACE Satellite Oil Spill Attribution & Investigation System**.

---

## 1. System Overview & Scientific Architecture

OILTRACE connects Copernicus Sentinel-1 Synthetic Aperture Radar (SAR) remote sensing, deep learning segmentation, geodesic vector polygonization, hydrodynamic Lagrangian drift hindcasting, and Automatic Identification System (AIS) vessel spatiotemporal correlation into an end-to-end maritime forensic investigation platform.

```
┌─────────────────────────────────────────────────────────────┐
│                   SENTINEL-1 SAR (C-BAND)                   │
└──────────────────────────────┬──────────────────────────────┘
                               │ Radiometric calibration & speckle filtering
                               ▼
┌─────────────────────────────────────────────────────────────┐
│          M1/M2: U-NET DEEP LEARNING SEGMENTATION             │
└──────────────────────────────┬──────────────────────────────┘
                               │ Binary probability mask & contour extraction
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              M3: GIS VECTORIZATION & METRICS                │
└──────────────────────────────┬──────────────────────────────┘
                               │ Geodesic WGS-84 area, perimeter, centroid
                               ▼
┌─────────────────────────────────────────────────────────────┐
│          M4: COPERNICUS CMEMS DRIFT HINDCASTING             │
└──────────────────────────────┬──────────────────────────────┘
                               │ Reverse Lagrangian hydrodynamic particle tracking
                               ▼
┌─────────────────────────────────────────────────────────────┐
│          M5: AIS VESSEL CORRELATION & ATTRIBUTION           │
└──────────────────────────────┬──────────────────────────────┘
                               │ Multi-criteria weighting: Spatial, Temporal, Trajectory, Behaviour
                               ▼
┌─────────────────────────────────────────────────────────────┐
│             FORENSIC DOSSIER & LEGAL PROSECUTION            │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Complete 12-Route Operational Navigation

The platform provides a sidebar organized into three operational tiers without decorative placeholders:

### Tier 1: Operational
1. **Dashboard (`dashboard`)**:
   - Aggregate statistics: Total incidents, completed cases, active runs, cumulative spill footprint ($\text{km}^2$), AIS candidate vessels profiled.
   - Active sector quick switcher with live status badges and measured areas.
   - Interactive MapLibre GL JS GIS canvas with layer toggles (Observed Slick, Probable Origin, Dispersion Ellipse, Backward Drift, Vessel Tracks).
   - Multi-criteria radar chart (Spatial 40%, Temporal 35%, Trajectory 15%, Behaviour 10%).
   - Member 3 GIS measurement panel & ranked suspect cards.
   - Zero-state onboarding widget when no investigations are registered.

2. **Investigations (`investigations`)**:
   - Multi-criteria search input (incident ID, region, title, suspect vessel).
   - Status filter chips: All, Completed, Active, Failed.
   - Quick toggles: "Starred Only" and "Include Trash / Deleted".
   - Dynamic sorting: Newest First, Oldest First, Largest Area, Title (A-Z).
   - Action controls: Open Dossier, View Report, View Map, Re-run Pipeline, Star/Unstar, Soft Delete, Restore, and Permanent Purge.

3. **New Investigation (`new-investigation`)**:
   - Ingest real Sentinel-1 GeoTIFF scenes (`00052.tif`, `00053.tif`, etc.).
   - Scene metadata inspection, CRS detection (`EPSG:4326`), and automatic sector naming.
   - Priority selection (High, Medium, Low) and execution parameter configuration.

4. **Investigation History (`investigation-history`)**:
   - Chronological audit log of all registered incident cases.
   - Search, status filtering, and soft-delete inclusion.
   - Pagination controls with total record counts.
   - Single-click "Export Audit Log (JSON)" for compliance reporting and regulatory submission.

5. **Live Pipeline (`live-investigations`)**:
   - In-flight execution monitoring of pipeline stages (SAR Ingestion, Segmentation, GIS Extraction, CMEMS Drift, AIS Attribution, Report Packaging).
   - Auto-polling telemetry (4-second interval).
   - Concluded pipeline summary table.

### Tier 2: Analysis & Evidence
6. **Map Explorer (`map-explorer`)**:
   - Multi-incident GIS command center.
   - Incident sector selector panel displaying all registered cases.
   - Full-screen hardware-accelerated MapLibre canvas with vector polygons, backward drift paths, and candidate AIS positions.

7. **Vessel Intelligence (`vessel-intelligence`)**:
   - Cross-incident AIS vessel correlation registry.
   - Candidate vessel identity: MMSI, IMO, Vessel Name, Callsign, Flag, Vessel Type.
   - Appearance frequency count across different incident release corridors.
   - Expandable incident history showing every incident where the vessel was detected.
   - Statutory Evidentiary Disclaimer: Neutral legal framing emphasizing proximity correlation vs proven culpability.

8. **Evidence Library (`evidence-library`)**:
   - Verified physical custody chain of files on disk.
   - Real file status: `AVAILABLE` vs `UNAVAILABLE`.
   - File size verification in KB/MB.
   - Supported artifacts: Raw SAR GeoTIFF, U-Net Segmentation Mask PNG, Vector Spill GeoJSON, CMEMS Drift Particles GeoJSON, Candidate Vessels CSV, Multi-Criteria Matrix JSON, Forensic Report Markdown.
   - Direct download actions for available artifacts.

9. **Forensic Reports (`reports`)**:
   - Comprehensive legal prosecution dossier generator.
   - Executive summary, MARPOL Annex I violation risk assessment, mathematical confidence breakdowns.
   - Real-time markdown rendering and single-click legal export.

### Tier 3: Platform & Data
10. **Datasets (`datasets`)**:
    - Physical repository inventory: Sentinel-1 GeoTIFF scenes, PyTorch `unet_best.pth` weights, Copernicus NetCDF hydrodynamic files, Global Fishing Watch AIS caches.
    - Verification status (`VERIFIED` vs `CHECK REQUIRED`), record counts, and local filesystem paths.

11. **System Status (`system-status`)**:
    - Live health verification of subsystems:
      - FastAPI Backend Core Engine
      - SQLAlchemy SQLite Database (`data/oiltrace.db`)
      - AI/ML Segmentation Models
      - Rasterio & GDAL Geospatial Drivers
      - Copernicus CMEMS Marine Current Grids
      - Global Fishing Watch API Key status (securely masked)
    - One-click "Run Self-Test Diagnostics".

12. **Settings (`settings`)**:
    - System configuration, spatial CRS parameters, drift model tolerances, and AIS API credentials.

---

## 3. Data Integrity & Safety Guardrails

- **Zero Mock Data in Production Mode**: All statistics, spill geometries, hydrodynamic drift particles, and AIS vessels are derived from real pipeline executions, database records, and Copernicus/GFW datasets.
- **Protected Datasets**: Soft deletion and permanent purge operations strictly protect shared resources (Sentinel-1 TIFFs, `unet_best.pth`, and Copernicus `.nc` files). Only incident-specific outputs (`real_{id}_*`, `OILTRACE_Report_{id}.md`) and database records are removed upon confirmed purge.
- **Two-Phase Deletion**: Incidents are soft-deleted (`is_deleted=1`) by default and can be restored at any time. Permanent purge requires explicit analyst confirmation via the destructive confirmation modal.
