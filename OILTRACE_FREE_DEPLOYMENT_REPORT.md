# OILTRACE Free Cloud Deployment Report

## 1. Executive Summary
The OILTRACE Oil Spill Attribution System has been fully prepared for 100% free cloud deployment. The architecture decouples the memory-intensive PyTorch deep learning segmentation from the FastAPI backend orchestration, enabling hosting across free tiers without operational cost.

## 2. Cloud Architecture Topology
- **Frontend UI**: Hosted on Render Static Site (or Vercel / Netlify) via React + TypeScript + Vite + Tailwind CSS + Leaflet.
- **API Gateway & Orchestrator**: Hosted on Render Web Service (Free Tier, 512 MB RAM limit). Runs FastAPI, SQLite, geospatial validation, Copernicus ocean current acquisition, and Global Fishing Watch AIS attribution. Startup memory is ~219 MB without PyTorch.
- **ML Inference Engine (M2 + M1 + M3)**: Hosted on Hugging Face Spaces (Docker SDK, CPU Basic, 2 vCPU, 16 GB RAM, Free). Runs Sentinel-1 preprocessing, tiled U-Net inference, and GeoJSON polygonization.

## 3. Zero-Data Cloud Strategy
- 0 pre-loaded Sentinel-1 scenes deployed.
- 0 training masks deployed.
- 0 raw AIS historical dumps deployed.
- All data processed is uploaded at runtime by the user via GeoTIFF drag-and-drop.

## 4. Decoupled Memory Profiling Results
- Initial monolith backend memory: ~501.8 MB RSS (exceeded Render 512 MB free tier ceiling).
- Decoupled backend memory: 219.4 MB RSS (57% reduction).
- torch loaded at API startup: False.

## 5. Hugging Face Space Package (hf_space/)
- Isolated Docker environment with Python 3.11.
- Exposes GET /health and POST /predict.
- Accepts multi-band Sentinel-1 SAR TIFF, extracts geospatial metadata, runs sliding-window U-Net segmentation, and outputs geodesic WGS-84 GeoJSON geometry.

## 6. Scientific Truthfulness Contract
- Zero synthetic vessels or fake drift vectors are produced in real uploads.
- If an uploaded TIFF coordinate or acquisition timestamp lacks Copernicus coverage or AIS data, the system reports explicit codes: SPATIAL_UNAVAILABLE, TEMPORAL_UNAVAILABLE, NO_DATA_FEED, or AUTHENTICATION_REQUIRED.

## 7. Verification and Test Results
- tests/test_deployment_architecture.py: 6/6 tests passed.
- tests/test_geotiff_upload.py, test_copernicus_selection.py, test_copernicus_temporal_anchor.py: 22/22 tests passed.
- Frontend Vite production build: built successfully in 7.92s with zero TypeScript errors.
- Local TIFF inference on scene 00009.tif: 55,414 oil pixels detected, area 4.6568 km2, 1 unified polygon feature produced.

## 8. Deployment Checklist for Maintainer
1. Create Hugging Face Space (Docker Blank), push hf_space/ and model/unet_best.pth.
2. Deploy FastAPI to Render Web Service using requirements-api.txt and set HF_ML_API_URL.
3. Deploy frontend to Render Static Site using frontend/dist and set VITE_API_URL.
