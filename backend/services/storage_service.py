"""Storage Service & Abstraction for OILTRACE Artifacts.

Provides uniform file persistence, integrity verification (SHA-256), MIME detection,
path sanitization, and ZIP evidence bundling across local and production deployment environments.
"""

from __future__ import annotations

import hashlib
import io
import mimetypes
import os
import shutil
import zipfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from backend.core.config import settings
from backend.core.logging import logger


class BaseStorageService(ABC):
    """Abstract base class for investigation artifact storage."""

    @abstractmethod
    def store_file(self, relative_path: str, source_path: Path) -> Path:
        """Store a file into the storage backend."""
        pass

    @abstractmethod
    def get_file_path(self, relative_path: str) -> Optional[Path]:
        """Resolve a storage reference to a readable path."""
        pass

    @abstractmethod
    def compute_sha256(self, file_path: Path) -> Optional[str]:
        """Calculate SHA-256 hash of a file."""
        pass

    @abstractmethod
    def get_file_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Return existence, byte size, SHA-256, and MIME type."""
        pass


class LocalStorageService(BaseStorageService):
    """Local filesystem storage implementation with path sanitization."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir or (settings.DATA_DIR / "artifacts")).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.demo_output_dir = settings.DEMO_OUTPUT_DIR.resolve()
        self.demo_output_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_path(self, relative_path: Union[str, Path]) -> Path:
        """Ensure path does not escape the storage base directory."""
        clean = Path(str(relative_path).replace("\\", "/")).as_posix().lstrip("/")
        target = (self.base_dir / clean).resolve()
        if not str(target).startswith(str(self.base_dir)) and not str(target).startswith(str(self.demo_output_dir)):
            # If pointing into REPO_ROOT data or demo output, allow if inside REPO_ROOT
            repo_root = settings.REPO_ROOT.resolve()
            if not str(target).startswith(str(repo_root)):
                raise ValueError(f"Path traversal detected: {relative_path}")
        return target

    def compute_sha256(self, file_path: Path) -> Optional[str]:
        """Compute SHA-256 checksum from file."""
        if not file_path or not file_path.exists() or not file_path.is_file():
            return None
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def get_file_metadata(self, file_path: Optional[Path]) -> Dict[str, Any]:
        """Retrieve real file metrics and compute cryptographic hash."""
        if not file_path or not file_path.exists() or not file_path.is_file():
            return {
                "exists": False,
                "byte_size": 0,
                "sha256": None,
                "mime_type": "application/octet-stream",
                "modified_at": None,
            }

        stat = file_path.stat()
        byte_size = stat.st_size
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            if file_path.suffix.lower() in (".tif", ".tiff"):
                mime_type = "image/tiff"
            elif file_path.suffix.lower() == ".geojson":
                mime_type = "application/geo+json"
            elif file_path.suffix.lower() == ".csv":
                mime_type = "text/csv"
            elif file_path.suffix.lower() == ".json":
                mime_type = "application/json"
            elif file_path.suffix.lower() == ".png":
                mime_type = "image/png"
            elif file_path.suffix.lower() == ".pdf":
                mime_type = "application/pdf"
            else:
                mime_type = "application/octet-stream"

        sha256_hash = self.compute_sha256(file_path) if byte_size > 0 else None

        return {
            "exists": True,
            "byte_size": byte_size,
            "sha256": sha256_hash,
            "mime_type": mime_type,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        }

    def store_file(self, relative_path: str, source_path: Path) -> Path:
        """Copy a source file into managed storage."""
        target = self._sanitize_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
        return target

    def get_file_path(self, relative_path: str) -> Optional[Path]:
        """Resolve a stored relative key to an existing Path."""
        try:
            target = self._sanitize_path(relative_path)
            if target.exists() and target.is_file():
                return target
        except Exception:
            pass
        return None

    def create_evidence_bundle(
        self,
        investigation_id: str,
        artifacts: List[Dict[str, Any]],
        manifest: Dict[str, Any],
    ) -> io.BytesIO:
        """Create a clean, isolated in-memory ZIP bundle containing all available artifacts."""
        buffer = io.BytesIO()

        # Category to subfolder mapping
        folder_map = {
            "SATELLITE": "01_sar",
            "DETECTION": "02_detection",
            "SEGMENTATION": "03_segmentation",
            "GIS": "04_geometry",
            "OCEAN_DRIFT": "05_ocean_drift",
            "AIS_ATTRIBUTION": "06_ais",
            "LEGAL_REPORT": "07_reports",
        }

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1. Write manifest.json
            import json
            manifest_json = json.dumps(manifest, indent=2)
            zf.writestr("manifest.json", manifest_json)

            # 2. Write each available artifact
            for art in artifacts:
                p_str = art.get("file_path")
                if not p_str:
                    continue
                p = Path(p_str)
                if not p.exists() or not p.is_file() or p.stat().st_size == 0:
                    continue

                category = art.get("category", "OTHER")
                subfolder = folder_map.get(category, "08_metadata")
                file_name = art.get("file_name") or p.name
                archive_name = f"{subfolder}/{file_name}"

                zf.write(p, arcname=archive_name)

        buffer.seek(0)
        return buffer


# Global storage service instance
storage = LocalStorageService()
