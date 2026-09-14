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

OUTPUT_DIR = settings.REPO_ROOT / "demo" / "output"
IMAGES_DIR = settings.REPO_ROOT / "01_Train_Val_Oil_Spill_images" / "Oil"
MODEL_PATH = settings.REPO_ROOT / "unet_best.pth"


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

                infer = OilSpillInference(MODEL_PATH)
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
