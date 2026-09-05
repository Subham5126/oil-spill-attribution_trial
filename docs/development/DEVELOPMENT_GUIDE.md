# Development Guide

## Oil Spill Attribution System

This document defines the standard development workflow for the Oil Spill
Attribution System.

The project is a six-member collaborative research and software engineering
project involving:

- Satellite imagery
- Sentinel-1 SAR processing
- Deep learning
- Image segmentation
- GIS
- Oceanographic data
- Meteorological data
- Spill drift modelling
- AIS vessel trajectory analysis
- Vessel attribution
- Backend APIs
- Geospatial databases
- Interactive GIS visualization

The purpose of this document is to ensure that all six team members can work
simultaneously without creating unnecessary conflicts, duplicated code,
broken interfaces, or inconsistent implementations.

---

# 1. Development Philosophy

The project follows these principles:

1. `main` must remain stable.
2. No direct feature development on `main`.
3. Every meaningful feature should use a separate branch.
4. One logical task should normally correspond to one branch and one PR.
5. Code must be placed in the correct module.
6. AI coding agents may assist development but do not define architecture.
7. Every meaningful change must be tested.
8. Large datasets and model weights must stay outside Git.
9. Shared interfaces must be documented.
10. Cross-module changes require coordination.
11. Small, reviewable PRs are preferred over giant changes.
12. Scientific correctness is more important than quickly producing code.

---

# 2. Team Structure

The project has six primary development areas.

| Member | Area | Main Directories |
|---|---|---|
| Member 1 | AI / Segmentation | `ai/` |
| Member 2 | Sentinel-1 / Satellite Processing | `satellite/` |
| Member 3 | GIS / Spill Geometry | `gis/` |
| Member 4 | Ocean / Drift Modelling | `ocean/`, `drift/` |
| Member 5 | AIS / Vessel Attribution | `ais/`, `attribution/` |
| Member 6 | Backend / Frontend / Integration | `backend/`, `frontend/`, `database/` |

Ownership means primary responsibility, not exclusive access.

Any team member may inspect or modify another module when required, but
cross-module changes should be communicated to the relevant owner.

---

# 3. Source of Truth

Different tools serve different purposes.

## GitHub

GitHub is the source of truth for:

- Source code
- Branches
- Issues
- Pull requests
- Code reviews
- CI/CD
- Documentation
- Project development history

## Google Drive

Use Google Drive for:

- Research papers
- Large datasets
- Presentations
- Reports
- Large model files
- Supporting project documents

## WhatsApp / Discord

Use team communication tools for:

- Quick discussions
- Coordination
- Questions
- Meeting communication

Important technical decisions should eventually be documented in GitHub.

Do not allow critical project knowledge to exist only inside chat messages.

---

# 4. Repository Architecture

The main repository structure is:

```text
oil-spill-attribution/
│
├── README.md
├── AGENTS.md
├── .gitignore
├── .env.example
├── requirements.txt
├── docker-compose.yml
│
├── docs/
│   ├── architecture/
│   ├── research/
│   ├── datasets/
│   └── api/
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── sample/
│
├── ai/
│   ├── models/
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
│   └── attribution/
│
└── scripts/
    ├── setup/
    ├── data/
    └── utilities/