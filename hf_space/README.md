---
title: OilTrace ML Inference
emoji: 🛰️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# OILTRACE — Sentinel-1 SAR Oil Spill AI Segmentation & GIS Service

This Hugging Face Space runs the **M2 (Preprocessing) + M1 (PyTorch U-Net) + M3 (GIS Geometry)** inference layer for the OILTRACE system.

## Primary Endpoint:
POST /predict
- Accepts an authentic Sentinel-1 GeoTIFF (.tif/.tiff) via multipart form upload.
- Preprocesses dual-polarization (VV/VH) channels.
- Runs trained ResNet34 U-Net inference.
- Vectorizes slicks into GIS polygons with geodesic WGS-84 area, perimeter, and centroid.
- Returns authoritative GeoJSON and geospatial metadata without synthetic data fabrication.
