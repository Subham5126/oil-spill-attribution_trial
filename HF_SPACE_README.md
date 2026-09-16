# OILTRACE Hugging Face Space (ML Inference Engine)

This subproject packages the PyTorch deep learning and SAR GIS preprocessing pipeline for free deployment on Hugging Face Spaces.

## Capabilities
- M2 SAR Preprocessing: Dual-polarization (VV/VH) band extraction, percentile contrast normalization, tiled sliding-window inference.
- M1 PyTorch U-Net Segmentation: Deep learning segmentation with ResNet-34 backbone trained for marine oil spill detection.
- M3 GIS Geometry Vectorization: Vectorizes binary masks into GeoJSON Polygons/MultiPolygons and computes geodesic surface area in km2.

## Space Configuration
- SDK: Docker
- Hardware: CPU Basic (2 vCPU, 16 GB RAM, Free)
- Base Image: python:3.11-slim

## Directory Contents
- Dockerfile: Container environment configuration with libgl1 and libgdal dependencies.
- requirements.txt: Minimal PyTorch, TorchVision, smp, rasterio, fastapi, uvicorn stack.
- app.py: FastAPI server exposing GET /health and POST /predict.
- inference/adapters.py: Pure-Python M1/M2/M3 execution adapters.
- model/unet_best.pth: Model weights checkpoint (copy from repository root).

## Deploy to Hugging Face Spaces
1. Create a new Space at https://huggingface.co/new-space.
2. Choose Space Name (e.g. oiltrace-ml) and select Docker SDK.
3. Copy the contents of this folder hf_space/ into your Hugging Face Space repository.
4. Copy unet_best.pth into model/unet_best.pth. Ensure Git LFS is enabled for files > 10MB.
5. Hugging Face Space will build and serve the API at https://<username>-oiltrace-ml.hf.space.
