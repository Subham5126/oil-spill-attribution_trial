# AGENTS.md

## Oil Spill Attribution System — AI Agent Instructions

This file defines the rules that AI coding agents must follow when working inside
this repository.

The repository is a high-end, research-oriented system for detecting marine oil
spills from satellite imagery, estimating spill geometry and probable origin,
modelling spill drift using oceanographic and meteorological data, correlating
the probable origin and time window with AIS vessel trajectories, and ranking
potential responsible vessels.

This project combines:

- Remote sensing
- Synthetic Aperture Radar (SAR)
- Computer vision
- Deep learning
- GIS
- Oceanographic modelling
- Meteorological data
- AIS trajectory analysis
- Geospatial databases
- Backend APIs
- Interactive GIS visualization

The system is intended to support research, analysis, and decision support.
AI-generated code must therefore prioritize scientific correctness, reproducibility,
geospatial correctness, maintainability, and explainability over speed of
implementation.

---

# 1. Instruction Priority

When deciding how to implement a change, follow this priority:

1. Explicit user/developer instructions for the current task
2. This `AGENTS.md`
3. `docs/architecture/ARCHITECTURE.md`
4. Relevant documentation under `docs/`
5. Existing project interfaces and data contracts
6. Existing implementation patterns
7. General engineering conventions

If two project documents appear to conflict, do not silently choose one.

Stop and report the conflict before making a major architectural decision.

---

# 2. Mandatory First Step: Inspect Before Coding

Before modifying code, inspect the repository.

At minimum, inspect:

- `AGENTS.md`
- `docs/architecture/ARCHITECTURE.md`
- `README.md` if relevant
- Relevant module directories
- Existing tests
- `requirements.txt`
- `.gitignore`
- `.github/workflows/`
- Existing implementation related to the task

Do not immediately start generating code based only on the user's description.

First determine:

- What already exists
- What is missing
- Which module owns the requested functionality
- Whether an existing implementation can be reused
- Whether a similar function/class already exists
- Which interfaces will be affected
- Which tests already cover the area
- Whether the requested change crosses module boundaries

Never create duplicate functionality simply because an existing implementation
was not inspected.

---

# 3. Read the Architecture Before Making Architectural Changes

The authoritative architecture document is:

`docs/architecture/ARCHITECTURE.md`

Do not redesign the project architecture casually.

The architecture is intentionally modular:

```text
Sentinel-1
    ↓
Satellite Processing
    ↓
AI Segmentation
    ↓
GIS Geometry
    ↓
Oceanographic / Meteorological Data
    ↓
Drift Hindcasting / Forecasting
    ↓
Probable Spill Origin
    ↓
AIS Filtering
    ↓
Vessel Attribution
    ↓
Backend / Database
    ↓
GIS Dashboard