"""Sentinel-1 GeoTIFF Upload & Geospatial Validation Service.

Provides chunked and direct upload management for Sentinel-1 GeoTIFF scenes (up to 1 GiB),
enforcing strict server-side file type and size limits, path traversal prevention,
authoritative rasterio GeoTIFF validation, and real raster metadata extraction.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, Optional, Set
import uuid

from fastapi import HTTPException, UploadFile, status
import rasterio

from backend.core.config import settings
from backend.core.logging import logger
from backend.services.temporal_service import (
    resolve_sar_temporal_anchor,
    resolve_sar_acquisition_time,
    validate_user_utc_timestamp,
    to_utc_iso,
)

ALLOWED_EXTENSIONS = {".tif", ".tiff"}
MAX_FILE_SIZE = settings.MAX_UPLOAD_SIZE_BYTES  # 1 GiB = 1073741824 bytes
DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024  # 5 MB


class UploadSession:
    """In-memory state for an in-progress chunked upload."""

    def __init__(
        self,
        upload_id: str,
        original_filename: str,
        safe_filename: str,
        file_path: Path,
        expected_size: int,
        total_chunks: int,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        content_type: Optional[str] = None,
        investigation_id: Optional[str] = None,
    ):
        self.upload_id = upload_id
        self.original_filename = original_filename
        self.safe_filename = safe_filename
        self.file_path = file_path
        self.expected_size = expected_size
        self.total_chunks = total_chunks
        self.chunk_size = chunk_size
        self.content_type = content_type
        self.investigation_id = investigation_id
        self.received_chunks: Set[int] = set()
        self.received_bytes: int = 0
        self.created_at: float = time.time()


class UploadService:
    """Service handling secure GeoTIFF upload, verification, and metadata extraction."""

    _active_sessions: Dict[str, UploadSession] = {}

    @classmethod
    def _ensure_upload_dir(cls) -> Path:
        """Ensure the upload destination directory exists."""
        upload_dir = settings.UPLOAD_DIR
        upload_dir.mkdir(parents=True, exist_ok=True)
        return upload_dir

    @classmethod
    def validate_file_extension(cls, filename: str) -> str:
        """Validate that the file extension is strictly .tif or .tiff."""
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type. Please upload a Sentinel-1 GeoTIFF (.tif or .tiff).",
            )
        return ext

    @classmethod
    def sanitize_filename(cls, original_name: str, upload_id: str) -> str:
        """Generate a safe, collision-resistant server-side filename preventing path traversal."""
        clean_name = Path(original_name).name.strip()
        stem = Path(clean_name).stem
        ext = Path(clean_name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            ext = ".tif"

        safe_stem = re.sub(r"[^a-zA-Z0-9_\-]", "_", stem)[:60]
        if not safe_stem:
            safe_stem = "sentinel1_scene"

        short_id = upload_id[:8]
        return f"s1_{short_id}_{safe_stem}{ext}"

    @classmethod
    def init_chunked_upload(
        cls,
        filename: str,
        file_size: int,
        total_chunks: Optional[int] = None,
        content_type: Optional[str] = None,
        investigation_id: Optional[str] = None,
        chunk_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Initialize a new chunked upload session for a Sentinel-1 GeoTIFF."""
        if not filename or not filename.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename is required for upload initialization.",
            )

        cls.validate_file_extension(filename)

        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="File exceeds the 1 GB maximum size.",
            )

        if file_size <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is empty or has invalid size.",
            )

        eff_chunk_size = chunk_size if (chunk_size and chunk_size > 0) else DEFAULT_CHUNK_SIZE
        if total_chunks is None or total_chunks <= 0:
            total_chunks = max(1, math.ceil(file_size / eff_chunk_size))

        try:
            upload_dir = cls._ensure_upload_dir()
            upload_id = uuid.uuid4().hex
            safe_name = cls.sanitize_filename(filename, upload_id)
            target_path = upload_dir / safe_name

            # Create empty placeholder file
            with open(target_path, "wb") as f:
                pass
        except Exception as err:
            logger.error(f"[UPLOAD] Failed to initialize upload storage on disk: {err}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Storage initialization failed. Unable to allocate upload session on server.",
            )

        session = UploadSession(
            upload_id=upload_id,
            original_filename=Path(filename).name,
            safe_filename=safe_name,
            file_path=target_path,
            expected_size=file_size,
            total_chunks=total_chunks,
            chunk_size=eff_chunk_size,
            content_type=content_type,
            investigation_id=investigation_id,
        )
        cls._active_sessions[upload_id] = session

        logger.info(
            f"[UPLOAD] Initialized chunked upload {upload_id} for '{filename}' "
            f"({file_size} bytes, {total_chunks} chunks, chunk_size={eff_chunk_size}) -> {safe_name}"
        )

        return {
            "upload_id": upload_id,
            "filename": session.original_filename,
            "safe_filename": safe_name,
            "chunk_size": eff_chunk_size,
            "total_chunks": total_chunks,
            "max_file_size": MAX_FILE_SIZE,
            "investigation_id": investigation_id,
        }

    @classmethod
    def append_chunk(
        cls,
        upload_id: str,
        chunk_index: int,
        chunk_bytes: bytes,
    ) -> Dict[str, Any]:
        """Write an uploaded binary chunk to the target file."""
        session = cls._active_sessions.get(upload_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upload session not found or has expired.",
            )

        chunk_len = len(chunk_bytes)
        if session.received_bytes + chunk_len > MAX_FILE_SIZE:
            cls.cancel_upload(upload_id)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File exceeds the 1 GB maximum size during upload.",
            )

        # Write chunk at the expected offset
        offset = chunk_index * DEFAULT_CHUNK_SIZE
        try:
            with open(session.file_path, "r+b") as f:
                f.seek(offset)
                f.write(chunk_bytes)
        except Exception as e:
            logger.error(f"[UPLOAD] Failed to write chunk {chunk_index} for {upload_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to write upload chunk to disk.",
            )

        session.received_chunks.add(chunk_index)
        session.received_bytes = os.path.getsize(session.file_path)

        pct = int((len(session.received_chunks) / session.total_chunks) * 100)
        return {
            "upload_id": upload_id,
            "chunk_index": chunk_index,
            "chunks_received": len(session.received_chunks),
            "total_chunks": session.total_chunks,
            "received_bytes": session.received_bytes,
            "progress_percentage": pct,
        }

    @classmethod
    def complete_chunked_upload(cls, upload_id: str) -> Dict[str, Any]:
        """Finalize chunked upload, validate GeoTIFF integrity, and extract metadata."""
        session = cls._active_sessions.get(upload_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upload session not found or has expired.",
            )

        if not session.file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Uploaded file missing on disk.",
            )

        actual_size = session.file_path.stat().st_size
        if actual_size > MAX_FILE_SIZE:
            cls.cancel_upload(upload_id)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File exceeds the 1 GB maximum size.",
            )

        # Validate with rasterio and extract metadata
        metadata = cls.validate_and_extract_metadata(
            file_path=session.file_path,
            original_filename=session.original_filename,
            upload_id=upload_id,
        )

        # Clean session from active tracker
        cls._active_sessions.pop(upload_id, None)
        return metadata

    @classmethod
    def cancel_upload(cls, upload_id: str) -> None:
        """Cancel and purge an upload session and delete any uploaded file from disk."""
        session = cls._active_sessions.pop(upload_id, None)
        if session and session.file_path.exists():
            try:
                session.file_path.unlink()
                logger.info(f"[UPLOAD] Cleaned up cancelled upload file {session.file_path}")
            except Exception as e:
                logger.warning(f"[UPLOAD] Failed to delete file {session.file_path}: {e}")

    @classmethod
    def direct_upload(cls, file: UploadFile) -> Dict[str, Any]:
        """Perform a single-shot streaming upload for a Sentinel-1 GeoTIFF."""
        cls.validate_file_extension(file.filename or "")

        upload_dir = cls._ensure_upload_dir()
        upload_id = uuid.uuid4().hex
        safe_name = cls.sanitize_filename(file.filename or "uploaded.tif", upload_id)
        target_path = upload_dir / safe_name

        total_bytes = 0
        try:
            with open(target_path, "wb") as buffer:
                while chunk := file.file.read(1024 * 1024):  # 1 MB blocks
                    total_bytes += len(chunk)
                    if total_bytes > MAX_FILE_SIZE:
                        buffer.close()
                        if target_path.exists():
                            target_path.unlink()
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="File exceeds the 1 GB maximum size.",
                        )
                    buffer.write(chunk)
        except HTTPException:
            raise
        except Exception as e:
            if target_path.exists():
                target_path.unlink()
            logger.error(f"[UPLOAD] Direct upload streaming failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store uploaded file on server.",
            )

        return cls.validate_and_extract_metadata(
            file_path=target_path,
            original_filename=Path(file.filename or "uploaded.tif").name,
            upload_id=upload_id,
        )

    @classmethod
    def validate_and_extract_metadata(
        cls,
        file_path: Path,
        original_filename: str,
        upload_id: str,
    ) -> Dict[str, Any]:
        """Inspect and validate that the file is an authentic, readable Sentinel-1 GeoTIFF."""
        if not file_path.exists() or file_path.stat().st_size == 0:
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty or corrupted.",
            )

        try:
            with rasterio.open(str(file_path)) as src:
                width = src.width
                height = src.height
                num_bands = src.count
                crs = str(src.crs) if src.crs else "EPSG:4326"
                bounds = src.bounds
                tags = src.tags()
                res = src.res

                # Ensure minimal raster validity
                if width <= 0 or height <= 0 or num_bands <= 0:
                    raise ValueError("Raster has invalid dimensions or no bands.")

        except Exception as e:
            # Delete corrupted or non-GeoTIFF file immediately
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass
            logger.warning(f"[UPLOAD] GeoTIFF validation failed for {file_path}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid GeoTIFF. The uploaded file could not be read as a valid Sentinel-1 raster.",
            )

        # Calculate bounding box and centroid
        min_lon, min_lat, max_lon, max_lat = bounds.left, bounds.bottom, bounds.right, bounds.top
        c_lat = float((min_lat + max_lat) / 2.0)
        c_lon = float((min_lon + max_lon) / 2.0)

        # Authoritative SAR acquisition timestamp resolution
        anchor = resolve_sar_temporal_anchor(
            filename=original_filename,
            image_path=str(file_path),
            metadata=tags,
            coordinates=(c_lat, c_lon) if (c_lat != 0 or c_lon != 0) else None,
        )
        acquisition_time_iso = anchor.get("sar_acquisition_time")

        # Determine marine region from coordinates or anchors
        region = cls._detect_region(c_lat, c_lon)

        # Generate a clean image ID for the scene
        clean_stem = Path(original_filename).stem
        digits = re.search(r"\d+", clean_stem)
        if digits and len(digits.group(0)) >= 4:
            image_id = f"{int(digits.group(0)):05d}"
        else:
            image_id = f"UPL-{upload_id[:8]}"

        file_size = file_path.stat().st_size

        metadata: Dict[str, Any] = {
            "status": "SUCCESS",
            "upload_id": upload_id,
            "image_id": image_id,
            "filename": original_filename,
            "safe_filename": file_path.name,
            "file_path": str(file_path),
            "file_size": file_size,
            "file_size_formatted": cls._format_bytes(file_size),
            "width": width,
            "height": height,
            "num_bands": num_bands,
            "crs": crs,
            "pixel_res_m": float(res[0]) if res else 10.0,
            "bounds": {
                "min_lon": min_lon,
                "min_lat": min_lat,
                "max_lon": max_lon,
                "max_lat": max_lat,
            },
            "centroid_lat": c_lat,
            "centroid_lon": c_lon,
            "region": region,
            "acquisition_time": acquisition_time_iso,
            "temporal_anchor": anchor,
            "source_file": str(file_path),
            "is_uploaded": True,
        }

        logger.info(
            f"[UPLOAD] Validated GeoTIFF '{original_filename}': "
            f"{width}x{height}, {num_bands} bands, CRS={crs}, "
            f"AcqTime={acquisition_time_iso or 'UNAVAILABLE'} "
            f"AnchorStatus={anchor.get('status')}"
        )
        return metadata

    @classmethod
    def confirm_temporal_anchor(
        cls,
        upload_id: str,
        sar_acquisition_time: Optional[str] = None,
        date: Optional[str] = None,
        time: Optional[str] = None,
        source: str = "user_provided",
    ) -> Dict[str, Any]:
        """Confirm or manually set the SAR acquisition temporal anchor for an upload."""
        payload_val: Any = sar_acquisition_time
        if not payload_val and date:
            t = time or "00:00:00"
            payload_val = f"{date}T{t}Z"

        if not payload_val:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A valid UTC SAR acquisition date/time must be provided.",
            )

        try:
            dt = validate_user_utc_timestamp(payload_val)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )

        iso_str = to_utc_iso(dt)

        return {
            "status": "resolved",
            "sar_acquisition_time": iso_str,
            "source": source or "user_provided",
            "verified": False,
            "provenance_badge": "USER PROVIDED — MANUAL TEMPORAL ANCHOR",
            "description": "Manual UTC temporal anchor confirmed by operator.",
            "candidates": [
                {
                    "source": "user_provided",
                    "timestamp": iso_str,
                    "confidence": "HIGH",
                    "description": "Operator supplied UTC acquisition timestamp",
                }
            ],
            "conflicts": [],
            "requires_user_action": False,
        }

    @staticmethod
    def _detect_region(lat: float, lon: float) -> str:
        """Identify geographic marine region from coordinates."""
        if 23.0 <= lat <= 30.0 and 48.0 <= lon <= 57.0:
            return "Persian Gulf (Sirri / UAE Corridor)"
        if 12.0 <= lat <= 28.0 and 32.0 <= lon <= 44.0:
            return "Red Sea (Jeddah Marine Corridor)"
        if 50.0 <= lat <= 62.0 and -4.0 <= lon <= 10.0:
            return "North Sea"
        if 5.0 <= lat <= 25.0 and 65.0 <= lon <= 78.0:
            return "Arabian Sea (Mumbai High EEZ)"
        if -10.0 <= lat <= 15.0 and 95.0 <= lon <= 110.0:
            return "Strait of Malacca"
        if lat == 0.0 and lon == 0.0:
            return "Offshore Waters"
        return f"Maritime Domain ({lat:.2f}°, {lon:.2f}°)"

    @staticmethod
    def _format_bytes(num_bytes: int) -> str:
        """Format byte count to readable string."""
        if num_bytes < 1024:
            return f"{num_bytes} B"
        elif num_bytes < 1024 * 1024:
            return f"{num_bytes / 1024:.1f} KB"
        elif num_bytes < 1024 * 1024 * 1024:
            return f"{num_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"
