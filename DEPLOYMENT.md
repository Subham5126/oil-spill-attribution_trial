# OILTRACE Deployment Guide (Free Cloud Architecture)

This document provides step-by-step instructions for deploying OILTRACE to free cloud hosting tiers:
1. Frontend: Render Static Site (or Vercel / Netlify / GitHub Pages)
2. Backend: Render Web Service (Free Tier, 512 MB RAM limit)
3. ML Inference: Hugging Face Spaces (CPU Basic, 16 GB RAM, 2 vCPU, Free)

---

## 1. Zero-Data Cloud Deployment Philosophy
- NO pre-loaded satellite imagery is deployed.
- All 1,200 Sentinel-1 TIFFs, training masks, and raw AIS CSV dumps remain in .gitignore.
- All oil spill segmentation, geometry calculation, ocean drift hindcasting, and vessel correlation occur dynamically at runtime when an analyst uploads a Sentinel-1 TIFF through the web dashboard.
- The pipeline never fabricates candidate vessels or currents. If an uploaded scene falls outside Copernicus coverage or lacks AIS feeds, clear scientific status flags are displayed (NO_DATA_FEED, NO_COMPATIBLE_DATA, AUTHENTICATION_REQUIRED, TIMESTAMP_REQUIRED).

---

## 2. Component 1: Hugging Face Space (ML Inference Service)

The Hugging Face Space hosts M2 (SAR Preprocessing), M1 (PyTorch U-Net Model), and M3 (GIS Geometry Vectorization).

### Directory to Deploy:
Everything inside hf_space/:
hf_space/
├── Dockerfile
├── README.md
├── requirements.txt
├── app.py
├── inference/
│   ├── __init__.py
│   └── adapters.py
└── model/
    └── unet_best.pth   <-- (Copy unet_best.pth from repo root into model/)

### Steps to Deploy to Hugging Face Spaces:
1. Create a new Space on Hugging Face (https://huggingface.co/new-space).
2. Set Space Name: oiltrace-ml (or any unique name).
3. Select SDK: Docker (Blank).
4. Hardware: CPU Basic (2 vCPU, 16 GB RAM, Free).
5. Push hf_space/ contents to your Space Git repository.
6. Hugging Face will build the Docker container and expose: https://<username>-oiltrace-ml.hf.space
7. Verify health: GET https://<username>-oiltrace-ml.hf.space/health

---

## 3. Component 2: Render Web Service (FastAPI Backend)

The FastAPI backend orchestrates geospatial validation, database persistence, oceanographic querying (M4 Copernicus), and AIS attribution (M5). It does NOT load PyTorch at startup, keeping memory usage ~219 MB (safely under Render 512 MB free tier ceiling).

### Render Configuration:
- Environment: Python 3
- Build Command: pip install -r requirements-api.txt
- Start Command: uvicorn backend.main:app --host 0.0.0.0 --port 

### Environment Variables on Render:
- HF_ML_API_URL: https://<username>-oiltrace-ml.hf.space
- DATABASE_URL: sqlite:///./oiltrace.db (or external PostgreSQL)
- COPERNICUS_USERNAME: (Optional) Copernicus Marine Service username
- COPERNICUS_PASSWORD: (Optional) Copernicus Marine Service password
- GFW_API_TOKEN: (Optional) Global Fishing Watch API Token
- ALLOWED_ORIGINS: https://<frontend>.onrender.com,http://localhost:5173

---

## 4. Component 3: Render Static Site (React/Vite Frontend)

The React dashboard allows drag-and-drop TIFF uploading, acquisition timestamp entry, and interactive Leaflet GIS visualization.

### Render Configuration:
- Type: Static Site
- Build Command: npm install && npm run build
- Publish Directory: frontend/dist
- Root Directory: frontend

### Environment Variables on Frontend:
- VITE_API_URL: https://<backend>.onrender.com
- VITE_ML_API_URL: https://<username>-oiltrace-ml.hf.space
- VITE_MAPTILER_KEY: (Optional) MapTiler API Key

---

## 5. End-to-End Runtime Workflow Verification

1. Analyst opens the web dashboard.
2. Navigates to New Investigation.
3. Drags and drops a Sentinel-1 SAR GeoTIFF (.tif or .tiff).
4. Enters or confirms acquisition timestamp (UTC).
5. Clicks Run Full Attribution Pipeline.
6. Backend delegates M2/M1/M3 to Hugging Face Space, runs Copernicus/AIS analysis for that exact coordinate and timestamp, and presents results interactively on the GIS map.
