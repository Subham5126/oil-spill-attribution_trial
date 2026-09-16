"""AI Segmentation Adapter (Member 1 Contract).

Defines the normalized segmentation output contract and adapter interface.
Tomorrow Member 1's deep learning segmentation model will plug in here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import numpy as np


@dataclass
class SegmentationResult:
    """Normalized segmentation inference output."""

    mask_raster_path: Optional[Path] = None
    mask_array: Optional[np.ndarray] = None
    confidence: float = 0.94
    detection_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    model_name: str = "DeepLabV3+_ResNet50_SAR_Oil"
    model_version: str = "1.0.0"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mask_raster_path": str(self.mask_raster_path) if self.mask_raster_path else None,
            "confidence": self.confidence,
            "detection_timestamp": self.detection_timestamp.isoformat(),
            "model_name": self.model_name,
            "model_version": self.model_version,
            "metadata": self.metadata,
        }


class AIAdapterInterface(ABC):
    """Abstract interface to be implemented by Member 1 deep learning module."""

    @abstractmethod
    def segment(self, raster_path: Path, **kwargs) -> SegmentationResult:
        """Run deep learning segmentation inference on preprocessed SAR raster."""
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Return metadata about the segmentation neural network architecture and weights."""
        pass


class DemoAIAdapter(AIAdapterInterface):
    """Placeholder adapter for demo execution before Member 1 integrates."""

    def segment(self, raster_path: Path, **kwargs) -> SegmentationResult:
        return SegmentationResult(
            mask_raster_path=raster_path,
            confidence=0.94,
            detection_timestamp=datetime(2025, 1, 1, 5, 0, 0, tzinfo=timezone.utc),
            model_name="OilTrace-SAR-DeepLabV3+",
            model_version="1.0-demo",
            metadata={"analyst_notes": "Continuous linear sheen with heavy core patch offshore Mumbai shipping corridor."},
        )

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "architecture": "DeepLabV3+",
            "backbone": "ResNet50",
            "weights": "Sentinel-1 Marine Oil Benchmark v1",
            "status": "AWAITING_MEMBER_1_INTEGRATION",
        }
