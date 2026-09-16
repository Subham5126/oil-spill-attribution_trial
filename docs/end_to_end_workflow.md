# OilTrace: End-to-End Oil Spill Attribution Workflow

## 1. Executive Summary

The **OilTrace Spill Attribution System** is a high-precision, research-grade operational pipeline designed for the detection, hydrodynamic hindcasting, and forensic vessel attribution of marine oil spills. Developed for the Smart India Hackathon (SIH 2026), the system automates the complete intelligence sequence from satellite synthetic aperture radar (SAR) observations to ranked, explainable vessel culpability profiles.

The architecture integrates three specialized engineering subsystems:
- **Member 3 (GIS & Spatial Geometry)**: Ingests SAR oil spill segmentations, calculates geodesic area, perimeter, centroid, and shape indices, handles coordinate reference systems (CRS), and exports styled vector GeoJSON layers.
- **Member 4 (Oceanographic & Drift Modelling)**: Ingests Copernicus Marine Service hydrodynamic currents (`uo`, `vo`) and ERA5 surface atmospheric wind vectors (`u10`, `v10`). Executes forward Lagrangian particle dispersion (forecast) and backward advection (hindcast) to identify probable release points and empirical spatial dispersion envelopes.
- **Member 5 (AIS & Vessel Attribution)**: Queries historical Automatic Identification System (AIS) vessel traffic within the spatio-temporal uncertainty envelope, reconstructs continuous vessel trajectories via kinematic interpolation, applies spatio-temporal filters, and executes a 4-tier multi-criteria evidence scoring and ranking engine with explainable narrative reporting.

---

## 2. Integrated System Architecture

```text
================================================================================================
                                 OILTRACE INTEGRATED WORKFLOW
================================================================================================

 [ Sentinel-1 SAR C-Band ]
            │
            ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ MEMBER 3: GIS & SPATIAL GEOMETRY (gis/)                                                      │
│  - OilSpillGeometry (WGS84 EPSG:4326 Polygon / MultiPolygon)                                  │
│  - Geodesic Measurements: calculate_spill_area(), calculate_perimeter()                      │
│  - Morphological Indices: Compactness (Isoperimetric Quotient), Bounding Aspect Ratio        │
│  - Geodesic Centroid: calculate_spill_centroid()                                              │
└──────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                       │
                         SpillObservation & SpillMeasurement
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ INTEGRATION LAYER: GIS -> OCEAN ADAPTER (integration/adapters/gis_ocean_adapter.py)          │
│  - initialize_particles_from_spill():                                                        │
│      * Particle 1 positioned at exact geodesic centroid                                      │
│      * Particles 2..N sampled deterministically inside polygon via point_in_polygon()        │
└──────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                       │
                         List[Particle] (lon, lat, timestamp, active)
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ MEMBER 4: OCEANOGRAPHIC & DRIFT MODELLING (ocean/ & drift/)                                   │
│  - Environmental Ingestion: Copernicus CMEMS Currents (uo, vo) + ERA5 Surface Wind (u10, v10)│
│  - Forward Advection (Forecast): simulate_particles() -> +2h dispersion                      │
│  - Backward Advection (Hindcast): hindcast_particles() -> -4h trajectory reconstruction      │
│  - Probable Origin Detection (OCEAN-08): analyze_origin() -> relative heuristic score        │
│  - Spatial Uncertainty (DRIFT-06): calculate_uncertainty() -> 95% empirical dispersion radius│
└──────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                       │
                         OceanDriftResult -> AISSearchRequest
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ INTEGRATION LAYER: OCEAN -> AIS ADAPTER (integration/adapters/ocean_ais_adapter.py)          │
│  - adapt_ocean_drift_to_ais():                                                               │
│      * Center = Origin centroid (lat, lon)                                                   │
│      * Effective Search Radius = Uncertainty radius + Search buffer (km)                     │
│      * Time Window = Origin timestamp +/- query buffer minutes                               │
│      * OriginMetadata & search_direction_deg extraction                                      │
└──────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                       │
                         AISSearchRequest & OriginMetadata
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ MEMBER 5: AIS TRAJECTORY & VESSEL ATTRIBUTION (ais/ & attribution/)                          │
│  - Data Ingestion: LocalAISProvider / Historical AIS CSV (NOAA / Marine Traffic schema)      │
│  - Trajectory Reconstruction: reconstruct_trajectories() -> segment sorting & validation    │
│  - Kinematic Interpolation: interpolate_trajectories() (300s step, cubic Hermite/linear)     │
│  - Spatial & Temporal Filtering: filter_spatial() -> filter_temporal()                       │
│  - 4-Tier Evidence Scoring (ATTR-02): score_candidates()                                     │
│      * Tier 1: Spatial Proximity (w = 0.40)                                                  │
│      * Tier 2: Temporal Coincidence (w = 0.35)                                               │
│      * Tier 3: Trajectory & Course Alignment (w = 0.15)                                      │
│      * Tier 4: Vessel Type & Speed Behaviour (w = 0.10)                                      │
│  - Explainable Audit (ATTR-03): explain_attribution() -> primary suspect narrative          │
└──────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                       │
                         PipelineResult (Consolidated Data Container)
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ MEMBER 6 PREVIEW: GIS DASHBOARD & FORENSIC EXPORT                                            │
│  - GeoJSON FeatureCollection: Spill Polygon, Bounding Box, Hindcast Drift, Vessel Tracks     │
│  - Map View Configuration: Center, Bounding Envelopes, Zoom Level                            │
│  - High-Resolution Multi-Panel Visual Plot: end_to_end_oil_spill_demo.png                     │
│  - Machine-Readable Forensic JSON: end_to_end_result.json                                    │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Subsystem Overviews & Data Contracts

### 3.1 Member 3 — GIS & Spatial Geometry Subsystem (`gis/`)
Member 3 establishes the spatial foundation using strictly validated WGS84 geographic coordinate objects:
- **`Coordinate(x, y, z)`**: Longitude $x \in [-180, 180]$, Latitude $y \in [-90, 90]$.
- **`BoundingBox(min_x, min_y, max_x, max_y)`**: 2D envelope bounds.
- **`LinearRing` & `Polygon`**: Exterior and interior rings validated for closure, non-self-intersection, and Shoelace signed area.
- **`OilSpillGeometry`**: Strongly typed domain container bundling `geometry`, `detection_timestamp` (strictly UTC), `source_sensor`, `confidence`, and descriptive properties.
- **`measure_oil_spill(spill)`**: Computes physical metrics without planar projection distortion using geodesic approximations:
  - Surface area ($m^2$ and $km^2$)
  - Total perimeter ($m$ and $km$)
  - Geodesic centroid (`Coordinate.lon`, `Coordinate.lat`)
  - Compactness / Isoperimetric Quotient ($4\pi \cdot \text{Area} / \text{Perimeter}^2$)
  - Bounding envelope aspect ratio

### 3.2 Member 4 — Oceanographic & Drift Modelling Subsystem (`ocean/`, `drift/`)
Member 4 executes Lagrangian transport physics using hydrodynamic and meteorological forcings:
- **`interpolate_currents` & `interpolate_wind`**: Bivariate / trilinear spatio-temporal interpolation on regular lat-lon grids for Copernicus Marine Service (`uo`, `vo`) and ERA5 (`u10`, `v10`).
- **`simulate_particles`**: Explicit forward Euler numerical advection:
  $$\vec{V}_{\text{oil}} = \vec{V}_{\text{current}} + \alpha \cdot \vec{V}_{\text{wind}}$$
  where $\alpha = 0.03$ (3% standard windage drift factor).
- **`hindcast_particles`**: Explicit backward Euler numerical advection reversing particle trajectories backwards in time:
  $$\vec{X}(t - \Delta t) = \vec{X}(t) - \vec{V}_{\text{oil}}(t, \vec{X}) \cdot \Delta t$$
- **`analyze_origin`**: Identifies highest density convergence regions from backward particles over time, producing `best_candidate` with heuristic density score.
- **`calculate_uncertainty`**: Evaluates particle cluster dispersion around the probable origin at the selected release time, outputting uncertainty radius $R_{\text{unc}}$ and spread metric.

> [!IMPORTANT]
> **Scientific Terminology Constraint**: Member 4's `calculate_uncertainty()` provides an **empirical spatial dispersion estimate**, NOT a calibrated statistical probability. Its 0.95 confidence parameter represents a 95% spatial particle coverage level. Similarly, origin scores represent **relative heuristic likelihood scores**, not absolute statistical probabilities.

### 3.3 Member 5 — AIS Trajectory & Attribution Subsystem (`ais/`, `attribution/`)
Member 5 ingests historical AIS streams, filters relevant candidates, reconstructs paths, and ranks suspects:
- **`AISSearchRequest`**: Bounding search definition (`latitude`, `longitude`, `effective_radius_km`, `start_time`, `end_time`).
- **`reconstruct_trajectories` & `interpolate_trajectories`**: Cleans noisy AIS fixes, partitions into MMSI tracks, and interpolates position fixes at 300-second intervals using cubic Hermite splines.
- **`filter_spatial` & `filter_temporal`**: Filters out vessel segments outside the origin uncertainty buffer or outside the estimated release time window.
- **`score_candidates`**: Evaluates every surviving vessel against the probable release envelope using four weighted evidence tiers:
  1. **Spatial Proximity ($w_s = 0.40$)**: Exponential / linear decay function based on closest point of approach (CPA) to release center.
  2. **Temporal Coincidence ($w_t = 0.35$)**: Closeness of CPA timestamp to estimated release time.
  3. **Trajectory Alignment ($w_{tr} = 0.15$)**: Cosine similarity between vessel heading/course vector and the computed hindcast drift axis.
  4. **Vessel Behaviour ($w_b = 0.10$)**: Vessel type risk weighting (Tanker > Cargo > Container > Fishing > Tug) and transit speed consistency.
- **`explain_attribution`**: Produces natural language forensic audit reports summarizing supporting and contradicting evidence.

---

## 4. Integration Architecture & Contracts

The integration layer lives in `integration/` and connects all three subsystems without modifying any internal Member algorithms:

```text
integration/
├── contracts/
│   ├── __init__.py
│   └── spill_contract.py         <-- SpillObservation & OceanDriftResult
├── adapters/
│   ├── __init__.py
│   ├── gis_ocean_adapter.py      <-- Member 3 -> Member 4 bridge
│   └── ocean_ais_adapter.py      <-- Member 4 -> Member 5 bridge
└── pipeline.py                   <-- Unified End-to-End Orchestrator
```

### 4.1 Member 3 -> Member 4 Contract
Defined in `integration/contracts/spill_contract.py` and `integration/adapters/gis_ocean_adapter.py`:
- `SpillObservation`: Carries centroid latitude, longitude, UTC timestamp, area, perimeter, bounding box, compactness, aspect ratio, and polygon geometry.
- `initialize_particles_from_spill(spill, num_particles, random_seed)`:
  - Particle 1 is pinned to the exact Member 3 geodesic centroid.
  - Particles 2..N are deterministically sampled within the spill polygon boundary using ray-casting point-in-polygon testing.
  - Fallback dispersion preserves physical area dimensions if the geometry is narrow.

### 4.2 Member 4 -> Member 5 Contract
Defined in `integration/contracts/spill_contract.py` and `integration/adapters/ocean_ais_adapter.py`:
- `OceanDriftResult`: Encapsulates `best_candidate` origin, `ranked_candidates` list, `uncertainty` dispersion result, backward hindcast trajectories DataFrame, and forward forecast trajectories DataFrame.
- `adapt_ocean_drift_to_ais(ocean_result, spill_observation, buffer_km, before_minutes, after_minutes)`:
  - Generates `AISSearchRequest` with `effective_radius_km = uncertainty_radius_km + buffer_km`.
  - Generates `OriginMetadata` for Member 5 scoring containing release coordinates, uncertainty radius, time window, and drift direction.

---

## 5. End-to-End Demonstration (`demo/end_to_end_oil_spill_demo.py`)

### 5.1 Running the Demo
```bash
python demo/end_to_end_oil_spill_demo.py
```

### 5.2 Generated Output Artifacts
Running the demo executes all stages in ~5 seconds and generates:
1. **Cartographic Plot**: `demo/output/end_to_end_oil_spill_demo.png`
   - High-resolution (220 DPI) multi-panel visualization.
   - Panel 1: Synoptic geospatial map with observed spill polygon, centroid, forward drift (+2h), backward hindcast tracks (-4h), 95% empirical dispersion circle, AIS search buffer, candidate vessel tracks, and top suspect callout annotation.
   - Panel 2: Multi-tier attribution score breakdown bar chart comparing candidates.
   - Panel 3: Forensic attribution ranking audit table.
2. **Forensic JSON**: `demo/output/end_to_end_result.json`
   - Complete machine-readable results including spill metadata, GIS measurements, ocean drift parameters, AIS search parameters, candidate vessels, attribution rankings, primary suspect summary, and map view configuration.
3. **GeoJSON Vector Layers**: `demo/output/end_to_end_layers.geojson`
   - Standard GeoJSON `FeatureCollection` with styled vector features ready for Leaflet / Mapbox frontend rendering.

---

## 6. Testing Strategy & Verification

The repository test suite verifies each subsystem independently and end-to-end:

| Test Suite | Path | Tests | Coverage Scope | Status |
|---|---|---|---|---|
| Member 3 GIS | `tests/gis/` | 81 | Geometry models, measurements, CRS transformation, GeoJSON styling | PASS |
| Member 4 Ocean | `tests/ocean/` | 74 | CMEMS interpolation, ERA5 wind, time synchronization | PASS |
| Member 4 Drift | `tests/drift/` | 27 | Particle advection, backward hindcasting, origin clustering, uncertainty | PASS |
| Member 5 AIS | `tests/ais/` | 89 | Providers, trajectory reconstruction, interpolation, filtering | PASS* |
| Member 5 Attribution | `tests/attribution/` | 42 | Multi-criteria scoring, candidate ranking, factor explanations | PASS |
| End-to-End Integration | `tests/integration/` | 11 | Complete M3 -> M4 -> M5 pipeline, GIS adaptation, cases A-F | PASS |

*\*Note: 1 pre-existing unit test in `tests/ais/test_temporal_filtering.py::test_non_datetime_dtype_string_parsing` fails due to pandas 3.0 string dtype assertion differences; all core functionality is unaffected.*

Run all integration tests:
```bash
python -m pytest tests/integration/ -v
```

---

## 7. Handoff Guide for Member 6 (Backend / API / Dashboard)

### 7.1 Python Pipeline Entry Point
To execute the attribution pipeline programmatically in FastAPI:
```python
from integration.pipeline import run_spill_attribution_pipeline
from gis.geometry.models import OilSpillGeometry, Polygon
from ocean.currents import load_currents
from ocean.wind import load_wind

# Ingest spill geometry
spill = OilSpillGeometry(spill_id="SAR-001", geometry=poly, detection_timestamp=ts)

# Execute pipeline
result = run_spill_attribution_pipeline(
    spill=spill,
    current_ds=load_currents("data/sample/copernicus/current_test.nc"),
    wind_ds=load_wind("data/sample/era5/wind_test.nc"),
    ais_source="data/ais/...",
    num_particles=50,
    hindcast_duration_hours=4.0,
)

# Access outputs
primary_suspect = result.attribution_result.ranked_candidates[0]
geojson_layers = result.gis_layers
```

### 7.2 Frontend Map Integration
The `result.gis_layers` output is a standard GeoJSON `FeatureCollection` where every feature includes Leaflet/Mapbox vector style properties (`color`, `weight`, `fillColor`, `fillOpacity`, `popup_html`). The frontend dashboard can render it directly onto an interactive map using `L.geoJSON(data).addTo(map)`.
