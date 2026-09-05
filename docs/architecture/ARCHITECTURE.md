# Oil Spill Attribution System — Architecture

## 1. Document Purpose

This document defines the official software architecture of the Oil Spill Attribution System.

It establishes:

* the major system modules
* responsibility of each module
* directory ownership
* system data flow
* module boundaries
* communication between modules
* technology choices
* integration principles
* rules for AI-assisted development
* rules for adding new components
* rules for modifying existing architecture

This document is intended to be used by:

* all project developers
* AI coding assistants
* project integrators
* reviewers
* future contributors

This document is an architectural reference.

### Important Rule

No developer or AI coding agent should introduce a major architectural change without first discussing and approving the change with the project team.

---

# 2. Project Objective

The system is designed to detect marine oil spills using satellite imagery and assist in identifying the vessel that may be responsible for the spill by correlating:

1. Satellite observations
2. Image segmentation
3. Geographic information
4. Oceanographic conditions
5. Meteorological conditions
6. Spill drift modelling
7. Historical AIS vessel data
8. Vessel trajectories
9. Temporal and spatial relationships
10. Behavioural and contextual features

The final system should provide an explainable analytical workflow rather than simply producing an unexplained vessel prediction.

---

# 3. High-Level System

The system consists of the following major stages:

```text
Satellite Observation
        |
        v
Sentinel-1 Processing
        |
        v
Oil Spill Segmentation
        |
        v
Spill Geometry Extraction
        |
        v
Ocean + Meteorological Data
        |
        v
Drift Hindcasting / Forecasting
        |
        v
Probable Spill Origin
        |
        v
AIS Data Processing
        |
        v
Candidate Vessel Filtering
        |
        v
Attribution Scoring
        |
        v
Ranked Candidate Vessels
        |
        v
Backend / Database
        |
        v
GIS Dashboard
```

The system must preserve the provenance of important outputs so that a user can understand how a final attribution result was produced.

---

# 4. Core Architectural Principle

The project follows a modular architecture.

Each major scientific or software responsibility belongs to a dedicated module.

```text
ai/
satellite/
gis/
ocean/
drift/
ais/
attribution/
database/
backend/
frontend/
```

Each module should:

* have a clearly defined responsibility
* expose predictable inputs and outputs
* avoid duplicating functionality from another module
* avoid unnecessary dependencies on unrelated modules
* contain its own tests where appropriate
* document assumptions
* preserve reproducibility

---

# 5. Repository Architecture

The official repository structure is:

```text
oil-spill-attribution/
│
├── README.md
├── AGENTS.md
├── CONTRIBUTING.md
├── requirements.txt
├── environment.yml
├── .env.example
├── .gitignore
├── docker-compose.yml
│
├── .github/
│   ├── workflows/
│   │   └── tests.yml
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── CODEOWNERS
│
├── docs/
│   ├── architecture/
│   │   ├── ARCHITECTURE.md
│   │   ├── DATA_CONTRACTS.md
│   │   ├── DATABASE_DESIGN.md
│   │   └── SYSTEM_DIAGRAM.md
│   │
│   ├── research/
│   │   ├── satellite/
│   │   ├── ai/
│   │   ├── ocean/
│   │   ├── drift/
│   │   └── ais/
│   │
│   ├── datasets/
│   │   └── DATA_GUIDE.md
│   │
│   ├── api/
│   │   └── API_DESIGN.md
│   │
│   └── development/
│       ├── DEVELOPMENT_GUIDE.md
│       └── CODING_STANDARDS.md
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── sample/
│
├── ai/
│   ├── models/
│   │   ├── unet/
│   │   └── unetplusplus/
│   │
│   ├── preprocessing/
│   ├── training/
│   ├── evaluation/
│   └── inference/
│
├── satellite/
│   ├── sentinel1/
│   ├── sentinel2/
│   ├── download/
│   └── preprocessing/
│
├── gis/
│   ├── geometry/
│   ├── projection/
│   ├── measurements/
│   └── visualization/
│
├── ocean/
│   ├── currents/
│   ├── wind/
│   ├── weather/
│   └── data_loader/
│
├── drift/
│   ├── particle_model/
│   ├── hindcasting/
│   ├── forecasting/
│   └── probability/
│
├── ais/
│   ├── data_loader/
│   ├── preprocessing/
│   ├── trajectory/
│   └── filtering/
│
├── attribution/
│   ├── spatial/
│   ├── temporal/
│   ├── trajectory/
│   ├── behaviour/
│   ├── scoring/
│   └── explanation/
│
├── database/
│   ├── schema/
│   ├── migrations/
│   └── queries/
│
├── backend/
│   ├── api/
│   ├── services/
│   ├── schemas/
│   └── main.py
│
├── frontend/
│   ├── public/
│   └── src/
│       ├── components/
│       ├── pages/
│       ├── map/
│       ├── charts/
│       ├── services/
│       └── types/
│
├── tests/
│   ├── ai/
│   ├── satellite/
│   ├── gis/
│   ├── ocean/
│   ├── drift/
│   ├── ais/
│   ├── attribution/
│   ├── backend/
│   └── integration/
│
└── scripts/
    ├── setup/
    ├── data/
    └── utilities/
```

The exact structure may evolve, but major changes require team agreement.

---

# 6. Module Responsibilities

## 6.1 AI Module

Directory:

```text
ai/
```

Primary responsibility:

> Detect and segment oil-spill regions in satellite imagery.

Responsibilities include:

* dataset loading
* image preprocessing required by the model
* augmentation
* model implementation
* training
* validation
* evaluation
* inference
* model configuration
* model versioning metadata

The AI module should not be responsible for:

* calculating geographic area
* calculating geographic perimeter
* AIS processing
* ocean simulation
* database management
* frontend rendering

The AI module produces a segmentation result.

Conceptually:

```text
Satellite Image
       |
       v
AI Model
       |
       v
Segmentation Mask
       +
Confidence
       +
Model Metadata
```

---

# 7. Satellite Module

Directory:

```text
satellite/
```

Primary responsibility:

> Acquire, load, validate, and preprocess satellite imagery.

Responsibilities include:

* Sentinel-1 data handling
* image loading
* band handling
* metadata extraction
* acquisition timestamp extraction
* geospatial metadata
* preprocessing
* image tiling
* conversion into model-ready inputs

The satellite module should provide standardized inputs to the AI module.

It should not implement the segmentation model itself.

---

# 8. GIS Module

Directory:

```text
gis/
```

Primary responsibility:

> Convert image-space results into geographic information.

Responsibilities include:

* raster-to-vector conversion
* coordinate reference systems
* coordinate transformations
* polygon creation
* polygon cleaning
* geometry validation
* centroid calculation
* bounding boxes
* area
* perimeter
* GeoJSON generation
* map-ready geographic outputs

Example:

```text
AI Mask
   |
   v
Georeferenced Mask
   |
   v
Oil Spill Polygon
   |
   +---- Area
   |
   +---- Perimeter
   |
   +---- Centroid
   |
   +---- Bounding Box
```

GIS must use appropriate geographic projections when calculating physical measurements.

---

# 9. Ocean Module

Directory:

```text
ocean/
```

Primary responsibility:

> Load and prepare environmental data required for spill movement modelling.

Potential inputs include:

* ocean currents
* sea-surface velocity
* wind
* weather variables
* wave-related information where available
* environmental metadata

Responsibilities:

* downloading/loading environmental data
* temporal alignment
* spatial interpolation
* quality checking
* unit normalization
* handling missing values
* preparing model inputs

The ocean module does not itself determine vessel responsibility.

---

# 10. Drift Module

Directory:

```text
drift/
```

Primary responsibility:

> Model the probable movement of an oil spill through the marine environment.

The drift module contains:

```text
particle_model/
hindcasting/
forecasting/
probability/
```

### Hindcasting

Attempts to estimate where the spill may have originated by running the model backward from an observed spill.

```text
Observed Spill
      |
      v
Backward Simulation
      |
      v
Possible Origin Region
```

### Forecasting

Estimates possible future movement.

```text
Observed Spill
      |
      v
Forward Simulation
      |
      v
Future Spill Distribution
```

### Probability

Represents uncertainty rather than claiming one exact origin.

Output may include:

* probable origin region
* probability distribution
* time window
* uncertainty
* simulated trajectories

---

# 11. AIS Module

Directory:

```text
ais/
```

Primary responsibility:

> Load, clean, normalize, and reconstruct vessel movement from AIS data.

Responsibilities:

* AIS ingestion
* timestamp normalization
* coordinate validation
* duplicate removal
* invalid position filtering
* vessel identification
* trajectory construction
* interpolation where justified
* spatial filtering
* temporal filtering

AIS processing should not directly decide whether a vessel caused an oil spill.

It produces candidate vessel information for the attribution module.

---

# 12. Attribution Module

Directory:

```text
attribution/
```

Primary responsibility:

> Calculate evidence-based scores for candidate vessels.

Potential evidence dimensions include:

```text
Spatial proximity
Temporal compatibility
Trajectory compatibility
Movement direction
Speed
Presence in relevant area
Drift consistency
Behavioural indicators
Other contextual evidence
```

The attribution module should produce a ranked result.

Example:

```text
Candidate Vessel A
Score: 0.87

Candidate Vessel B
Score: 0.64

Candidate Vessel C
Score: 0.42
```

The score must be interpreted as an analytical ranking or confidence measure.

It must not be presented as definitive proof that a vessel caused the spill.

---

# 13. Explanation Module

Location:

```text
attribution/explanation/
```

The system should provide reasons behind a vessel's ranking.

For example:

```text
Vessel A

Overall Score: 0.87

Supporting factors:
- Strong temporal compatibility
- Passed through probable origin region
- High spatial proximity
- Trajectory compatible with hindcast
- AIS signal available during relevant period
```

This is important because the project should be explainable rather than acting as a black box.

---

# 14. Database Module

Directory:

```text
database/
```

Primary responsibility:

> Store structured application and geospatial information.

The database may contain entities such as:

```text
spills
spill_detections
spill_geometries
drift_runs
drift_results
vessels
ais_positions
candidate_vessels
attribution_results
```

PostgreSQL/PostGIS should be used for structured and spatial application data.

Large raw satellite datasets and large scientific datasets should not automatically be inserted into PostgreSQL.

---

# 15. Backend Module

Directory:

```text
backend/
```

Primary responsibility:

> Provide APIs connecting the scientific processing pipeline to the application.

Potential responsibilities:

* request validation
* API routing
* orchestration
* database interaction
* processing job management
* result retrieval
* authentication if required later
* error handling

The backend should not duplicate scientific algorithms that already belong to:

```text
ai/
gis/
drift/
ais/
attribution/
```

Instead, it should call the appropriate services/modules.

---

# 16. Frontend Module

Directory:

```text
frontend/
```

Primary responsibility:

> Provide the user-facing GIS dashboard.

The frontend may display:

* satellite imagery
* detected oil-spill polygon
* spill location
* spill area
* spill perimeter
* centroid
* drift simulation
* probable origin
* AIS vessel trajectories
* candidate vessel ranking
* attribution explanation
* timestamps
* uncertainty
* supporting evidence

The frontend must not implement core scientific calculations.

For example:

Bad:

```text
Frontend calculates oil-spill area
```

Good:

```text
GIS module calculates area
        |
        v
Backend API
        |
        v
Frontend displays area
```

---

# 17. Tests

Directory:

```text
tests/
```

Each major module should have corresponding tests.

```text
tests/
├── ai/
├── satellite/
├── gis/
├── ocean/
├── drift/
├── ais/
├── attribution/
├── backend/
└── integration/
```

Testing levels:

### Unit tests

Test individual functions.

Example:

```text
calculate_area()
```

### Module tests

Test an entire module.

Example:

```text
AIS trajectory reconstruction
```

### Integration tests

Test communication between modules.

Example:

```text
AI output
    |
    v
GIS
```

### End-to-end tests

Test the complete pipeline.

```text
Satellite
   ↓
AI
   ↓
GIS
   ↓
Drift
   ↓
AIS
   ↓
Attribution
```

---

# 18. Data Flow

The official conceptual data flow is:

```text
                 SENTINEL-1
                     |
                     v
             Satellite Processing
                     |
                     v
              Model Preparation
                     |
                     v
               AI Segmentation
                     |
                     v
                Oil Mask
                     |
                     v
               GIS Processing
                     |
             +-------+-------+
             |               |
             v               v
       Spill Geometry     Spill Metadata
             |               |
             +-------+-------+
                     |
                     v
          Ocean + Weather Data
                     |
                     v
              Drift Model
             /           \
            /             \
           v               v
      Hindcasting      Forecasting
           |
           v
   Probable Origin Region
           |
           v
         AIS Data
           |
           v
     Candidate Filtering
           |
           v
       Attribution
           |
           v
     Ranked Candidates
           |
           v
        Backend
           |
           v
        Database
           |
           v
       Frontend GIS
```

---

# 19. Module Dependency Rules

Dependencies should flow in a controlled direction.

Preferred conceptual dependency:

```text
Satellite
    ↓
AI
    ↓
GIS
    ↓
Drift
    ↓
AIS
    ↓
Attribution
    ↓
Backend
    ↓
Frontend
```

However, the actual implementation may use shared data contracts and service interfaces.

### Avoid circular dependencies.

Bad:

```text
AI → GIS
GIS → AI
AI → AIS
AIS → AI
```

Good:

```text
AI → standardized output
GIS consumes output
```

---

# 20. Shared Utilities

If multiple modules need the same functionality, do not duplicate it.

For example, if coordinate validation is needed by several modules, create an agreed shared utility rather than having:

```text
ai/utils/coordinates.py
ais/utils/coordinates.py
gis/utils/coordinates.py
```

with three different implementations.

Before creating a utility, developers must search the repository for an existing implementation.

---

# 21. Single Source of Truth

Each responsibility should have one primary implementation.

Examples:

```text
Segmentation
→ ai/

Geographic calculations
→ gis/

Ocean data preparation
→ ocean/

Drift simulation
→ drift/

AIS processing
→ ais/

Vessel scoring
→ attribution/

Database access
→ database/backend

UI rendering
→ frontend/
```

Do not implement the same functionality independently in multiple modules unless there is a documented reason.

---

# 22. AI-Assisted Development Rules

All team members may use AI coding assistants such as:

* Codex
* Antigravity
* AI Studio
* other approved coding assistants

AI assistance is encouraged.

However:

> AI-generated code is treated exactly like human-written code.

It must be:

* reviewed
* tested
* understood by the responsible developer
* placed in the correct module
* compatible with the existing architecture

AI must not independently redefine project architecture.

---

# 23. AI Coding Agent Rules

Before modifying code, an AI coding agent should:

1. Inspect the repository.
2. Read `AGENTS.md`.
3. Read relevant architecture documentation.
4. Identify the assigned module.
5. Inspect existing implementations.
6. Search for reusable functionality.
7. Determine affected files.
8. Avoid unrelated modifications.
9. Implement the requested task.
10. Run relevant tests.
11. Report what was changed.

AI agents should not:

* create a new architecture unnecessarily
* rename major folders
* move modules without approval
* introduce unnecessary frameworks
* duplicate existing functionality
* modify another team's module without reason
* remove existing code without understanding its purpose
* add dependencies unnecessarily
* commit secrets
* commit large datasets
* modify `.gitignore` casually
* modify CI configuration without understanding the impact

---

# 24. Dependency Rules

The project has an approved technology stack.

Primary technologies include:

```text
Python
PyTorch
segmentation-models-pytorch
NumPy
SciPy
OpenCV

Rasterio
GDAL
GeoPandas
Shapely
PyProj
xarray

PostgreSQL
PostGIS
SQLAlchemy

FastAPI
Pydantic

React
TypeScript
MapLibre GL JS
Apache ECharts

Docker
GitHub Actions
Pytest
```

A new dependency should only be introduced when:

1. the existing stack cannot reasonably solve the problem;
2. the dependency provides meaningful value;
3. the team understands its maintenance implications;
4. it is compatible with the project environment;
5. it does not unnecessarily duplicate an existing dependency.

Do not introduce a new framework simply because an AI assistant prefers it.

---

# 25. Configuration

Configuration should not be hardcoded throughout the codebase.

Use configuration files and environment variables where appropriate.

Sensitive values must be stored through environment variables.

Never commit:

```text
API keys
passwords
tokens
credentials
private access keys
```

`.env` files must remain ignored by Git.

Use:

```text
.env.example
```

to document required environment variables without exposing their values.

---

# 26. Data Storage Rules

GitHub is the source of truth for:

```text
source code
configuration
tests
documentation
small examples
schemas
```

Shared storage is used for:

```text
large datasets
satellite imagery
large AIS datasets
large NetCDF files
model weights
large experiment outputs
```

Do not commit large raw datasets to the normal Git repository.

The project should document where datasets are obtained and how they are prepared.

---

# 27. Model Management

Model weights should be treated separately from source code.

Source code:

```text
ai/
```

Model metadata should document:

```text
model architecture
training dataset
training configuration
input dimensions
input channels
preprocessing
training date
evaluation metrics
version
```

Example:

```text
Model:
U-Net++

Dataset:
Sentinel-1 oil-spill dataset

Input:
VV + VH

Output:
Oil-spill segmentation mask

Version:
v0.1
```

Large model weights should not be casually committed to Git.

---

# 28. Scientific Reproducibility

Because this is a scientific/geospatial project, every important result should be reproducible as far as practical.

Important experiments should record:

```text
Dataset
Dataset version
Model
Model version
Configuration
Preprocessing
Parameters
Input image
Environmental data
AIS data period
Software environment
Results
```

A result without sufficient provenance should not be treated as a final project result.

---

# 29. Time Handling

Time is critical throughout the system.

All internal timestamps should use a consistent standard.

Recommended:

```text
UTC
```

Store timestamps in an unambiguous format.

Example:

```text
2026-01-15T14:30:00Z
```

This is especially important because:

* satellite acquisition time
* AIS timestamps
* ocean data timestamps
* wind data timestamps
* drift simulation time

must be comparable.

Never silently mix local time and UTC.

---

# 30. Coordinate Handling

Geospatial coordinates must have an explicitly known CRS.

Do not assume that:

```text
x = longitude
y = latitude
```

without confirming the coordinate reference system.

All geographic transformations should be explicit.

The GIS module is responsible for coordinate transformation logic.

---

# 31. Error Handling

Modules should fail clearly.

Bad:

```text
return None
```

without explanation.

Better:

```text
raise a meaningful error
```

or return a structured result indicating:

```text
success
failure
reason
```

Errors should provide enough context to diagnose the problem.

---

# 32. Logging

Long-running scientific processes should provide useful logs.

Examples:

```text
Loading Sentinel-1 image
Loaded VV channel
Loaded VH channel
Running preprocessing
Running segmentation
Extracting geometry
Loading ocean data
Starting hindcast
Loading AIS candidates
Calculating attribution scores
```

Avoid excessive debug output in production.

---

# 33. Performance Principles

The project may eventually process large datasets.

Therefore:

* avoid loading unnecessary large datasets into memory
* process data in chunks where appropriate
* use vectorized NumPy operations where appropriate
* avoid repeated expensive disk reads
* avoid unnecessary model inference
* cache reusable results where appropriate
* separate development-scale data from production-scale data

Optimization should not come at the expense of correctness or scientific validity.

---

# 34. Security Principles

Never commit:

```text
API keys
database passwords
tokens
credentials
private keys
```

Never place secrets inside:

```text
Python source
React source
configuration committed to Git
notebooks
documentation
```

Use environment variables or approved secret-management mechanisms.

---

# 35. Branch Architecture

The repository uses:

```text
main
```

as the stable integration branch.

Feature development happens on branches such as:

```text
feature/unetplusplus
feature/sentinel1-preprocessing
feature/spill-geometry
feature/drift-hindcast
feature/ais-filtering
feature/attribution-scoring
feature/dashboard-map
```

Bug fixes:

```text
fix/sar-preprocessing
fix/ais-parser
fix/geometry-calculation
```

Documentation:

```text
docs/architecture
docs/dataset-guide
```

Branches should represent a focused task.

---

# 36. Pull Request Architecture

The normal development process is:

```text
Issue
  |
  v
Feature Branch
  |
  v
Implementation
  |
  v
Testing
  |
  v
Commit
  |
  v
Push
  |
  v
Pull Request
  |
  v
CI
  |
  v
Review
  |
  v
Merge
  |
  v
main
```

A pull request should normally address one focused task.

Large changes should be split where practical.

---

# 37. Module Ownership

Initial ownership:

```text
Member 1
AI / Segmentation
→ ai/

Member 2
Satellite Processing
→ satellite/

Member 3
GIS
→ gis/

Member 4
Ocean + Drift
→ ocean/
→ drift/

Member 5
AIS + Attribution
→ ais/
→ attribution/

Member 6
Backend + Frontend + Integration
→ backend/
→ frontend/
→ database/
```

Ownership means primary responsibility.

It does not mean other team members are forbidden from contributing.

Changes to another person's primary module should be coordinated with that module owner.

---

# 38. Integration Ownership

The project should have one person acting as the primary integration coordinator.

The integration coordinator is responsible for:

* maintaining architectural consistency
* coordinating cross-module changes
* resolving major conflicts
* checking interfaces
* coordinating releases
* ensuring the complete pipeline remains functional

This role does not mean the integrator writes everyone's code.

---

# 39. Architecture Change Policy

A developer must discuss a change before doing it if it:

* renames a major directory
* moves a module
* changes the database architecture
* changes the API contract
* replaces a major framework
* introduces a major dependency
* changes the data flow
* changes the model interface
* changes the output format used by another module
* changes the deployment architecture

Small implementation changes do not require architectural approval.

---

# 40. Definition of Done

A task is considered complete only when:

* implementation is complete
* code is in the correct directory
* tests are added or updated where appropriate
* existing tests pass
* documentation is updated where necessary
* no secrets are included
* no unnecessary files are included
* no unrelated modules were modified
* code has been self-reviewed
* pull request has been reviewed
* CI passes
* PR is merged

---

# 41. Definition of an Acceptable AI-Generated Change

AI-generated code is acceptable only if:

```text
Correct
+
Understandable
+
Tested
+
Architecturally compatible
+
Documented where necessary
+
Reviewed by a human
```

AI output should never be merged solely because:

> "The AI said it works."

---

# 42. Project Development Philosophy

The project prioritizes:

1. Correctness
2. Reproducibility
3. Scientific validity
4. Maintainability
5. Explainability
6. Testability
7. Security
8. Performance
9. Development speed

Development speed must not override correctness.

---

# 43. MVP vs Advanced Features

The project should first establish a working minimum viable pipeline:

```text
Sentinel-1
    ↓
Preprocessing
    ↓
Segmentation
    ↓
Spill Polygon
    ↓
Area / Location
    ↓
AIS Candidate Filtering
    ↓
Basic Attribution
    ↓
Map
```

After this works reliably, advanced capabilities can be added:

```text
Drift Hindcasting
Forecasting
Uncertainty
Advanced Attribution
Behaviour Analysis
Multi-source Satellite Data
Advanced Explainability
Large-scale Processing
```

This prevents the team from attempting the entire high-end system simultaneously.

---

# 44. Final Architectural Principle

The system should be built as a collection of cooperating scientific and software modules rather than one giant application.

The desired architecture is:

```text
                    ┌─────────────────┐
                    │   SENTINEL-1    │
                    └────────┬────────┘
                             │
                             v
                    ┌─────────────────┐
                    │    SATELLITE    │
                    └────────┬────────┘
                             │
                             v
                    ┌─────────────────┐
                    │       AI        │
                    │  SEGMENTATION   │
                    └────────┬────────┘
                             │
                             v
                    ┌─────────────────┐
                    │       GIS       │
                    │    GEOMETRY     │
                    └────────┬────────┘
                             │
                             v
               ┌─────────────┴─────────────┐
               │                           │
               v                           v
       ┌───────────────┐           ┌───────────────┐
       │ OCEAN/WEATHER │           │   SPILL DATA  │
       └───────┬───────┘           └───────┬───────┘
               │                           │
               └─────────────┬─────────────┘
                             v
                    ┌─────────────────┐
                    │      DRIFT      │
                    │  HINDCASTING    │
                    │  / FORECASTING  │
                    └────────┬────────┘
                             │
                             v
                    ┌─────────────────┐
                    │       AIS       │
                    │    FILTERING    │
                    └────────┬────────┘
                             │
                             v
                    ┌─────────────────┐
                    │  ATTRIBUTION    │
                    │     SCORING     │
                    └────────┬────────┘
                             │
                             v
                    ┌─────────────────┐
                    │    DATABASE     │
                    └────────┬────────┘
                             │
                             v
                    ┌─────────────────┐
                    │ BACKEND / API   │
                    └────────┬────────┘
                             │
                             v
                    ┌─────────────────┐
                    │ GIS DASHBOARD   │
                    └─────────────────┘
```

This architecture is the baseline for the project.

Any future architectural change should preserve the core principles of modularity, clear interfaces, scientific reproducibility, testability, and explainability.
