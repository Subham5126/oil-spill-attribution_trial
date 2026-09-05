# Data Contracts

## Oil Spill Attribution System

This document defines the standard data exchanged between project modules.

The purpose is to ensure that six developers can implement modules independently
without breaking downstream components.

> Module implementations may change internally, but their agreed inputs and
> outputs must remain stable.

---

## 1. Pipeline

```text
Sentinel-1
    ↓
Satellite Processing
    ↓
AI Segmentation
    ↓
GIS Geometry
    ↓
Ocean / Weather
    ↓
Drift Modelling
    ↓
Probable Origin
    ↓
AIS Filtering
    ↓
Attribution
    ↓
Backend / Database
    ↓
Frontend