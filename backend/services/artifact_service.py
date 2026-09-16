"""Investigation Artifact Management & Rendering Service.

Provides authoritative resolution, dynamic on-demand rendering, and caching of
Sentinel-1 SAR detection overlays, AI segmentation masks, and source GeoTIFFs
per investigation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np
import rasterio
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import logger
from backend.repositories.investigations import InvestigationRepository
from backend.services.image_service import ImageService

OUTPUT_DIR = settings.DEMO_OUTPUT_DIR
IMAGES_DIR = settings.REPO_ROOT / "01_Train_Val_Oil_Spill_images" / "Oil"
MODEL_PATH = settings.OILTRACE_MODEL_PATH


class ArtifactService:
    """Service providing access and on-demand rendering for investigation artifacts."""

    @staticmethod
    def normalize_image_id(raw_id: Optional[str]) -> Optional[str]:
        """Normalize an image ID or filename to a clean 5-digit string (e.g. '00052')."""
        if not raw_id:
            return None
        clean = Path(str(raw_id)).stem.strip()
        match = re.search(r"\d+", clean)
        if match:
            return f"{int(match.group(0)):05d}"
        return clean

    @classmethod
    def resolve_investigation_image(
        cls,
        investigation_id: str,
        db: Optional[Session] = None,
        explicit_image_id: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[Path]]:
        """Resolve the normalized image ID and source TIFF path for an investigation."""
        norm_id: Optional[str] = None
        source_path: Optional[Path] = None

        if explicit_image_id:
            norm_id = cls.normalize_image_id(explicit_image_id)

        if not norm_id and db is not None:
            repo = InvestigationRepository(db)
            inv = repo.get_by_id(investigation_id, include_deleted=True)
            if inv:
                if inv.source_image_path and Path(inv.source_image_path).exists():
                    source_path = Path(inv.source_image_path)
                    norm_id = cls.normalize_image_id(inv.image_id or source_path.stem)
                elif inv.image_id:
                    norm_id = cls.normalize_image_id(inv.image_id)
                elif inv.metadata_json and isinstance(inv.metadata_json, dict):
                    prop_id = inv.metadata_json.get("image_id") or inv.metadata_json.get("properties", {}).get("image_id")
                    if prop_id:
                        norm_id = cls.normalize_image_id(prop_id)

        # If still not found, check known demo investigation IDs
        if not norm_id:
            if "00643" in investigation_id:
                norm_id = "00643"
            elif "00052" in investigation_id:
                norm_id = "00052"

        # Resolve filesystem path for TIFF if not already set
        if norm_id and not source_path:
            meta = ImageService.get_image_metadata(norm_id)
            if meta and meta.get("file_path") and Path(meta["file_path"]).exists():
                source_path = Path(meta["file_path"])
            else:
                candidate = IMAGES_DIR / f"{norm_id}.tif"
                if candidate.exists():
                    source_path = candidate

        return norm_id, source_path

    @classmethod
    def get_segmentation_mask_path(
        cls,
        investigation_id: str,
        db: Optional[Session] = None,
        explicit_image_id: Optional[str] = None,
    ) -> Optional[Path]:
        """Retrieve or generate the AI segmentation mask PNG for the current investigation."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        norm_id, source_path = cls.resolve_investigation_image(
            investigation_id, db=db, explicit_image_id=explicit_image_id
        )

        if not norm_id:
            logger.warning(f"[ARTIFACT] Could not resolve image_id for investigation '{investigation_id}'")
            return None

        mask_png = OUTPUT_DIR / f"real_{norm_id}_mask.png"
        if mask_png.exists() and mask_png.stat().st_size > 0:
            return mask_png

        # Check for GeoTIFF mask
        mask_tif = OUTPUT_DIR / f"real_{norm_id}_mask.tif"
        if mask_tif.exists() and mask_tif.stat().st_size > 0:
            try:
                with rasterio.open(mask_tif) as src:
                    arr = src.read(1)
                binary = (arr > 0).astype(np.uint8) * 255
                cv2.imwrite(str(mask_png), binary)
                logger.info(f"[ARTIFACT] Converted mask GeoTIFF to PNG: {mask_png}")
                return mask_png
            except Exception as e:
                logger.warning(f"[ARTIFACT] Failed to convert mask GeoTIFF {mask_tif}: {e}")

        # If source TIFF exists, run U-Net inference on the fly
        if source_path and source_path.exists() and MODEL_PATH.exists():
            try:
                logger.info(f"[ARTIFACT] Running U-Net inference on {source_path.name} to generate mask artifact...")
                from ai.inference.infer import OilSpillInference

                infer = OilSpillInference(MODEL_PATH, model_provider=settings.OILTRACE_MODEL_PROVIDER)
                res = infer.predict(source_path)
                mask = res["mask"]
                binary = (mask * 255).astype(np.uint8)
                cv2.imwrite(str(mask_png), binary)
                logger.info(f"[ARTIFACT] Generated segmentation mask PNG: {mask_png} (spill pixels: {int(mask.sum())})")
                return mask_png
            except Exception as e:
                logger.error(f"[ARTIFACT] On-demand U-Net inference failed on {source_path}: {e}", exc_info=True)

        return None

    @classmethod
    def get_detection_overlay_path(
        cls,
        investigation_id: str,
        db: Optional[Session] = None,
        explicit_image_id: Optional[str] = None,
    ) -> Optional[Path]:
        """Retrieve or generate the high-contrast SAR Detection Overlay PNG for the investigation."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        norm_id, source_path = cls.resolve_investigation_image(
            investigation_id, db=db, explicit_image_id=explicit_image_id
        )

        if not norm_id:
            return None

        overlay_png = OUTPUT_DIR / f"real_{norm_id}_overlay.png"
        if overlay_png.exists() and overlay_png.stat().st_size > 0:
            return overlay_png

        # Need source TIFF to render overlay
        if not source_path or not source_path.exists():
            logger.warning(f"[ARTIFACT] Source TIFF not found for scene '{norm_id}'")
            return None

        # Ensure segmentation mask exists (or generate it)
        mask_path = cls.get_segmentation_mask_path(
            investigation_id, db=db, explicit_image_id=explicit_image_id
        )

        try:
            logger.info(f"[ARTIFACT] Rendering SAR Detection Overlay for scene {norm_id} from {source_path.name}...")
            # 1. Read calibrated SAR Band 1 (VV backscatter)
            with rasterio.open(source_path) as src:
                b1 = src.read(1)

            valid = np.isfinite(b1)
            if np.any(valid):
                p2, p98 = np.percentile(b1[valid], (2, 98))
                if p98 > p2:
                    norm = np.clip((b1 - p2) / (p98 - p2), 0.0, 1.0)
                else:
                    norm = np.zeros_like(b1, dtype=np.float32)
            else:
                norm = np.zeros_like(b1, dtype=np.float32)

            gray = (norm * 255.0).astype(np.uint8)
            rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)

            # 2. Overlay segmentation highlight if mask available
            if mask_path and mask_path.exists():
                mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
                if mask is not None:
                    if mask.shape != rgb.shape[:2]:
                        mask = cv2.resize(mask, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_NEAREST)
                    slick = mask > 0

                    if np.any(slick):
                        # High-contrast Rose/Red detection overlay: #f43f5e (RGB 244, 63, 94)
                        rgb[slick, 0] = np.clip(rgb[slick, 0] * 0.55 + 244 * 0.45, 0, 255).astype(np.uint8)
                        rgb[slick, 1] = np.clip(rgb[slick, 1] * 0.55 + 63 * 0.45, 0, 255).astype(np.uint8)
                        rgb[slick, 2] = np.clip(rgb[slick, 2] * 0.55 + 94 * 0.45, 0, 255).astype(np.uint8)

                        # Draw boundary contour
                        contours, _ = cv2.findContours(
                            (slick.astype(np.uint8) * 255), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                        )
                        cv2.drawContours(rgb, contours, -1, (255, 40, 80), 2)

            # Save as BGR for OpenCV
            cv2.imwrite(str(overlay_png), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            logger.info(f"[ARTIFACT] Saved SAR Detection Overlay to {overlay_png}")
            return overlay_png

        except Exception as e:
            logger.error(f"[ARTIFACT] Failed to render detection overlay for {source_path}: {e}", exc_info=True)
            return None

    @classmethod
    def get_source_tiff_path(
        cls,
        investigation_id: str,
        db: Optional[Session] = None,
        explicit_image_id: Optional[str] = None,
    ) -> Optional[Path]:
        """Retrieve path to the raw Sentinel-1 GeoTIFF for an investigation."""
        _, source_path = cls.resolve_investigation_image(
            investigation_id, db=db, explicit_image_id=explicit_image_id
        )
        if source_path and source_path.exists():
            return source_path
        return None

    @classmethod
    def get_georeferenced_mask_tif_path(
        cls,
        investigation_id: str,
        db: Optional[Session] = None,
        explicit_image_id: Optional[str] = None,
    ) -> Optional[Path]:
        """Retrieve or generate the Georeferenced Oil Slick GeoTIFF."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        norm_id, source_path = cls.resolve_investigation_image(
            investigation_id, db=db, explicit_image_id=explicit_image_id
        )

        # Check candidate stems
        stems = [norm_id]
        if db is not None:
            repo = InvestigationRepository(db)
            inv = repo.get_by_id(investigation_id, include_deleted=True)
            if inv and inv.source_image_path:
                stems.insert(0, Path(inv.source_image_path).stem)

        for s in stems:
            if not s:
                continue
            cand = OUTPUT_DIR / f"real_{s}_mask.tif"
            if cand.exists() and cand.stat().st_size > 0:
                return cand

        # If mask_png exists and source_tiff exists, create valid GeoTIFF
        mask_png = cls.get_segmentation_mask_path(investigation_id, db=db, explicit_image_id=explicit_image_id)
        if mask_png and mask_png.exists() and source_path and source_path.exists():
            try:
                with rasterio.open(source_path) as src:
                    crs = src.crs
                    transform = src.transform
                    width = src.width
                    height = src.height

                mask_arr = cv2.imread(str(mask_png), cv2.IMREAD_GRAYSCALE)
                if mask_arr is not None:
                    if mask_arr.shape != (height, width):
                        mask_arr = cv2.resize(mask_arr, (width, height), interpolation=cv2.INTER_NEAREST)
                    bin_arr = (mask_arr > 0).astype(np.uint8)

                    target_tif = OUTPUT_DIR / f"real_{norm_id or 'mask'}_mask.tif"
                    with rasterio.open(
                        target_tif,
                        "w",
                        driver="GTiff",
                        height=height,
                        width=width,
                        count=1,
                        dtype=np.uint8,
                        crs=crs,
                        transform=transform,
                        compress="lzw",
                    ) as dst:
                        dst.write(bin_arr, 1)

                    logger.info(f"[ARTIFACT] Created georeferenced GeoTIFF mask at {target_tif}")
                    return target_tif
            except Exception as e:
                logger.error(f"[ARTIFACT] Failed to generate GeoTIFF mask: {e}")

        return None

    @classmethod
    def get_drift_trajectory_paths(
        cls,
        investigation_id: str,
        db: Optional[Session] = None,
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """Retrieve or generate the Lagrangian drift trajectory CSV and JSON files."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        norm_id, _ = cls.resolve_investigation_image(investigation_id, db=db)
        clean_id = norm_id or "drift"

        csv_path = OUTPUT_DIR / f"real_{clean_id}_drift_trajectory.csv"
        json_path = OUTPUT_DIR / f"real_{clean_id}_drift_trajectory.json"

        if csv_path.exists() and csv_path.stat().st_size > 0 and json_path.exists() and json_path.stat().st_size > 0:
            return csv_path, json_path

        # If missing, reconstruct from persisted investigation result_json / geojson_layers
        if db is not None:
            repo = InvestigationRepository(db)
            inv = repo.get_by_id(investigation_id, include_deleted=True)
            if inv and inv.result_json and isinstance(inv.result_json, dict):
                ocean = inv.result_json.get("ocean_drift", {})
                layers = inv.geojson_layers or {}
                features = layers.get("features", []) if isinstance(layers, dict) else []

                hindcast_coords = []
                forecast_coords = []
                for f in features:
                    props = f.get("properties", {})
                    lt = props.get("layer_type")
                    if lt == "drift_hindcast":
                        hindcast_coords = f.get("geometry", {}).get("coordinates", [])
                    elif lt == "drift_forecast":
                        forecast_coords = f.get("geometry", {}).get("coordinates", [])

                if hindcast_coords or ocean.get("probable_origin"):
                    import pandas as pd
                    rows = []
                    u_vel = ocean.get("surface_velocity", {}).get("u_eastward_m_s", 0.0)
                    v_vel = ocean.get("surface_velocity", {}).get("v_northward_m_s", 0.0)
                    speed = ocean.get("surface_velocity", {}).get("speed_m_s", 0.0)

                    # Hindcast points
                    for idx, pt in enumerate(hindcast_coords):
                        rows.append({
                            "timestamp": inv.observation_timestamp.isoformat() if inv.observation_timestamp else "",
                            "latitude": pt[1],
                            "longitude": pt[0],
                            "step_hours": -idx,
                            "trajectory_type": "HINDCAST",
                            "u_current_m_s": u_vel,
                            "v_current_m_s": v_vel,
                            "current_speed_m_s": speed,
                        })

                    # Forecast points
                    for idx, pt in enumerate(forecast_coords):
                        rows.append({
                            "timestamp": inv.observation_timestamp.isoformat() if inv.observation_timestamp else "",
                            "latitude": pt[1],
                            "longitude": pt[0],
                            "step_hours": idx + 1,
                            "trajectory_type": "FORECAST",
                            "u_current_m_s": u_vel,
                            "v_current_m_s": v_vel,
                            "current_speed_m_s": speed,
                        })

                    if rows:
                        df_t = pd.DataFrame(rows)
                        df_t.to_csv(csv_path, index=False)

                    summary = {
                        "investigation_id": investigation_id,
                        "model_type": ocean.get("model_type", "Lagrangian RK4 Hydrodynamic Advection"),
                        "dataset_id": ocean.get("dataset_id", "Copernicus Marine CMEMS"),
                        "product_id": ocean.get("product_id", "Copernicus Marine CMEMS"),
                        "reference_timestamp": inv.observation_timestamp.isoformat() if inv.observation_timestamp else "",
                        "probable_origin": ocean.get("probable_origin", {}),
                        "forecast_endpoint": ocean.get("forecast_endpoint", {}),
                        "surface_velocity": ocean.get("surface_velocity", {}),
                        "uncertainty": ocean.get("uncertainty", {}),
                        "hindcast_coordinates": hindcast_coords,
                        "forecast_coordinates": forecast_coords,
                    }
                    import json
                    with open(json_path, "w", encoding="utf-8") as jf:
                        json.dump(summary, jf, indent=2)

                    return csv_path if csv_path.exists() else None, json_path if json_path.exists() else None

        return None, None

    @classmethod
    def get_ais_evidence_paths(
        cls,
        investigation_id: str,
        db: Optional[Session] = None,
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """Retrieve or generate the AIS evidence CSV and JSON files."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        json_path = OUTPUT_DIR / f"ais_attribution_{investigation_id}.json"
        csv_path = OUTPUT_DIR / f"ais_candidates_{investigation_id}.csv"

        if json_path.exists() and json_path.stat().st_size > 0 and csv_path.exists() and csv_path.stat().st_size > 0:
            return json_path, csv_path

        if db is not None:
            repo = InvestigationRepository(db)
            inv = repo.get_by_id(investigation_id, include_deleted=True)
            if inv and inv.result_json and isinstance(inv.result_json, dict):
                candidates = inv.result_json.get("candidate_vessels", [])
                if candidates:
                    import json
                    import pandas as pd

                    payload = {
                        "investigation_id": investigation_id,
                        "pipeline_run_id": inv.result_json.get("pipeline_execution", {}).get("pipeline_run_id"),
                        "observation_timestamp": inv.observation_timestamp.isoformat() if inv.observation_timestamp else "",
                        "provider": "Global Fishing Watch 4Wings AIS API / Space-Time Ranker",
                        "total_candidates": len(candidates),
                        "primary_suspect": inv.result_json.get("primary_suspect"),
                        "candidates": candidates,
                    }
                    with open(json_path, "w", encoding="utf-8") as jf:
                        json.dump(payload, jf, indent=2)

                    rows = []
                    for c in candidates:
                        scores = c.get("scores", {})
                        factors = c.get("confidence_factors", {})
                        rows.append({
                            "rank": c.get("rank"),
                            "mmsi": c.get("mmsi"),
                            "vessel_name": c.get("vessel_name"),
                            "imo": c.get("imo"),
                            "callsign": c.get("callsign"),
                            "flag": c.get("flag"),
                            "vessel_type": c.get("vessel_type"),
                            "latitude": c.get("latitude"),
                            "longitude": c.get("longitude"),
                            "distance_to_spill_km": c.get("distance_to_spill_km"),
                            "distance_to_track_km": c.get("distance_to_track_km"),
                            "min_distance_km": c.get("min_distance_km"),
                            "presence_hours": c.get("presence_hours", 1.0),
                            "timestamp": c.get("timestamp"),
                            "attribution_score": scores.get("overall"),
                            "confidence_score": c.get("confidence_score"),
                            "confidence_level": c.get("confidence_level"),
                            "spatial_factor": factors.get("spatial_proximity"),
                            "temporal_factor": factors.get("temporal_overlap"),
                            "trajectory_factor": factors.get("drift_consistency"),
                            "behaviour_factor": factors.get("track_consistency"),
                        })
                    pd.DataFrame(rows).to_csv(csv_path, index=False)
                    return json_path, csv_path

        return None, None

    @classmethod
    def get_forensic_report_pdf_path(
        cls,
        investigation_id: str,
        db: Optional[Session] = None,
    ) -> Optional[Path]:
        """Retrieve or generate the authoritative forensic PDF report."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        pdf_path = OUTPUT_DIR / f"OILTRACE_{investigation_id}_Forensic_Report.pdf"

        if pdf_path.exists() and pdf_path.stat().st_size > 1000:
            return pdf_path

        if db is not None:
            try:
                from backend.services.report_service import ReportService
                svc = ReportService(db)
                pdf_bytes = svc.generate_report_pdf(investigation_id)
                with open(pdf_path, "wb") as pf:
                    pf.write(pdf_bytes)
                return pdf_path
            except Exception as e:
                logger.warning(f"[ARTIFACT] Could not pre-generate PDF report: {e}")

        return None

    @classmethod
    def compile_investigation_evidence(
        cls,
        investigation_id: str,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """Compile verified forensic evidence library for an investigation."""
        from backend.services.storage_service import storage

        repo = InvestigationRepository(db) if db else None
        inv = repo.get_by_id(investigation_id, include_deleted=True) if repo else None
        if not inv:
            return []

        clean_id = cls.normalize_image_id(inv.image_id) or "00052"

        # Resolve all artifact file paths
        source_tiff = cls.get_source_tiff_path(investigation_id, db=db)
        overlay_png = cls.get_detection_overlay_path(investigation_id, db=db)
        mask_png = cls.get_segmentation_mask_path(investigation_id, db=db)
        mask_tif = cls.get_georeferenced_mask_tif_path(investigation_id, db=db)
        drift_csv, drift_json = cls.get_drift_trajectory_paths(investigation_id, db=db)
        ais_json, ais_csv = cls.get_ais_evidence_paths(investigation_id, db=db)
        report_pdf = cls.get_forensic_report_pdf_path(investigation_id, db=db)

        # GIS GeoJSON layers
        layers_path = OUTPUT_DIR / f"real_{clean_id}_layers.geojson"
        if not layers_path.exists() and inv.geojson_layers:
            import json
            with open(layers_path, "w", encoding="utf-8") as lf:
                json.dump(inv.geojson_layers, lf, indent=2)

        def _art(
            artifact_type: str,
            name: str,
            category: str,
            path: Optional[Path],
            provenance: str,
            preview_type: str,
            unavailable_reason: Optional[str] = None,
        ) -> Dict[str, Any]:
            meta = storage.get_file_metadata(path)
            is_avail = meta["exists"] and meta["byte_size"] > 0
            return {
                "artifact_type": artifact_type,
                "name": name,
                "category": category,
                "status": "AVAILABLE" if is_avail else "UNAVAILABLE",
                "file_name": path.name if is_avail else f"{artifact_type.lower()}.dat",
                "file_path": str(path) if is_avail else None,
                "file_size_bytes": meta["byte_size"],
                "sha256": meta["sha256"],
                "mime_type": meta["mime_type"],
                "generated_at": meta["modified_at"] or (inv.observation_timestamp.isoformat() if inv.observation_timestamp else None),
                "provenance_source": provenance,
                "download_url": f"/api/investigations/{investigation_id}/artifacts/{artifact_type}/download" if is_avail else None,
                "preview_type": preview_type if is_avail else "none",
                "unavailable_reason": None if is_avail else (unavailable_reason or "Artifact file not yet generated or not found on disk"),
            }

        return [
            _art(
                "SOURCE_SAR_TIFF",
                "Sentinel-1 SAR C-Band Calibrated GeoTIFF",
                "SATELLITE",
                source_tiff,
                "European Space Agency (ESA) / Copernicus Open Access Hub",
                "none",
                "Raw Sentinel-1 GeoTIFF scene missing from storage",
            ),
            _art(
                "SAR_DETECTION_OVERLAY",
                "High-Contrast SAR Detection Overlay (PNG)",
                "DETECTION",
                overlay_png,
                "OILTRACE Radiometric VV Equalizer & Slick Boundary Vectorizer",
                "image",
            ),
            _art(
                "SEGMENTATION_MASK_PNG",
                "U-Net Deep Learning Oil Slick Mask (PNG)",
                "SEGMENTATION",
                mask_png,
                "OILTRACE U-Net ResNet34 Inference (unet_best.pth)",
                "image",
            ),
            _art(
                "GEOREFERENCED_MASK_TIFF",
                "Georeferenced Oil Slick GeoTIFF (EPSG:4326)",
                "SEGMENTATION",
                mask_tif,
                "Rasterio Spatial Affine Transform (EPSG:4326 / WGS-84)",
                "none",
            ),
            _art(
                "GIS_LAYERS_GEOJSON",
                "Multi-Layer GIS GeoJSON FeatureCollection",
                "GIS",
                layers_path if layers_path.exists() else None,
                "Shapely / Geodesic WGS-84 Polygon Vectorizer",
                "geojson",
            ),
            _art(
                "DRIFT_TRAJECTORY_CSV",
                "Lagrangian Ocean Drift Advection Coordinates (CSV)",
                "OCEAN_DRIFT",
                drift_csv,
                "Copernicus Marine CMEMS Hydrodynamic Currents (Euler/RK4 Advection)",
                "table",
                "Copernicus currents unavailable for temporal window" if not drift_csv else None,
            ),
            _art(
                "DRIFT_TRAJECTORY_JSON",
                "Drift Trajectory Time-Stepped Vectors (JSON)",
                "OCEAN_DRIFT",
                drift_json,
                "Copernicus CMEMS 72h Hindcast & 24h Forecast Predictor",
                "json",
            ),
            _art(
                "AIS_ATTRIBUTION_JSON",
                "AIS Vessel Candidate Attribution Matrix (JSON)",
                "AIS_ATTRIBUTION",
                ais_json,
                "Global Fishing Watch 4Wings AIS API / Space-Time Ranker",
                "table",
            ),
            _art(
                "AIS_CANDIDATES_CSV",
                "Ranked Candidate AIS Telemetry & Proximity Log (CSV)",
                "AIS_ATTRIBUTION",
                ais_csv,
                "GFW 4Wings Telemetry / Multi-Criteria Scoring Calibration",
                "table",
            ),
            _art(
                "FORENSIC_REPORT_PDF",
                "IMO MARPOL 73/78 Annex I Legal Evidence Dossier (PDF)",
                "LEGAL_REPORT",
                report_pdf,
                "OILTRACE Automated Forensic Report Generator",
                "pdf",
            ),
        ]

