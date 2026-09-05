# Data Guide

## Oil Spill Attribution System

This document defines how project data is acquired, stored, processed, documented,
and consumed by different modules.

The main principle is:

> Raw data is never modified directly. Processing creates reproducible derived
> data that downstream modules can consume through defined interfaces.

---

## 1. Data Categories

The project uses four major data categories:

| Data | Purpose | Main Module |
|---|---|---|
| Sentinel-1 SAR | Oil-spill detection | `satellite/`, `ai/` |
| Sentinel-2 / EO | Supporting optical information | `satellite/` |
| Oceanographic + Meteorological | Drift modelling | `ocean/`, `drift/` |
| AIS | Vessel trajectory and attribution | `ais/`, `attribution/` |

Additional derived data includes:

- Segmentation masks
- Spill polygons
- Spill measurements
- Origin probability regions
- Drift trajectories
- Candidate vessel trajectories
- Attribution scores

---

## 2. Data Storage

Large datasets must not be committed to Git.

Use:

```text
data/
├── raw/
├── processed/
└── sample/