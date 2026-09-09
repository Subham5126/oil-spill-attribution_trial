"""Unified preprocessing pipeline for Sentinel-1 dual-polarized SAR imagery.

Converts raw calibrated Sigma0 dB arrays into model-ready tensors for the
AI/U-Net segmentation module while preserving geospatial integrity and
scientific reproducibility.
"""

from dataclasses import dataclass, field
from typing import Any, Literal
import numpy as np

from satellite.sentinel1.exceptions import Sentinel1DataError
from .invalid_values import InvalidValueStats, handle_invalid_values
from .normalization import normalize_sar_channels
from .resizing import resize_sar_image
from .scaling import scale_sar_channels


@dataclass
class PreprocessingConfig:
    """Configuration for Sentinel-1 SAR preprocessing pipeline.

    Default settings preserve original physical Sigma0 dB values and spatial
    dimensions without applying destructive smoothing or per-image normalization.
    """

    # 1. Invalid value handling
    handle_invalid: bool = True
    invalid_strategy: Literal["constant", "clip_bounds", "raise"] = "constant"
    invalid_fill_value: float = -50.0
    min_bound: float = -50.0
    max_bound: float = 5.0

    # 2. Speckle / smoothing hook
    # Default is 'none': SNAP preprocessing already applied Lee speckle filtering.
    speckle_filter: Literal["none", "median"] = "none"
    speckle_kernel_size: int = 3

    # 3. Scaling / clipping
    # Default is False: raw physical Sigma0 dB values are preserved.
    clip_values: bool = False
    clip_min: tuple[float, float] | float = -50.0
    clip_max: tuple[float, float] | float = 5.0
    scale_range: tuple[float, float] | None = None

    # 4. Normalization
    # Default is 'none': identity passthrough.
    # When enabled, requires externally supplied dataset-wide parameters.
    normalization: Literal["none", "zscore", "minmax"] = "none"
    mean: tuple[float, float] | None = None  # (mean_vv, mean_vh)
    std: tuple[float, float] | None = None   # (std_vv, std_vh)
    min_val: tuple[float, float] | None = None  # (min_vv, min_vh)
    max_val: tuple[float, float] | None = None  # (max_vv, max_vh)
    eps: float = 1e-6

    # 5. Optional spatial resizing
    # Default is None: original 2048x2048 scene dimensions are strictly preserved.
    target_size: tuple[int, int] | None = None
    resize_interpolation: Literal["bilinear", "nearest", "area", "bicubic"] = "bilinear"


@dataclass(frozen=True)
class PreprocessingReport:
    """Execution metadata and statistics generated during preprocessing."""

    input_shape: tuple[int, ...]
    output_shape: tuple[int, ...]
    input_dtype: str
    output_dtype: str
    invalid_stats: InvalidValueStats
    channel_order: list[str] = field(default_factory=lambda: ["VV", "VH"])
    normalization_applied: str = "none"
    clipping_applied: bool = False
    resizing_applied: bool = False


class Sentinel1Preprocessor:
    """Configurable, deterministic preprocessor for Sentinel-1 VV/VH imagery."""

    def __init__(self, config: PreprocessingConfig | None = None):
        """Initialize the preprocessor.

        Args:
            config: Pipeline configuration. If None, default PreprocessingConfig is used.
        """
        self.config = config or PreprocessingConfig()

    def process(
        self,
        image: np.ndarray,
    ) -> tuple[np.ndarray, PreprocessingReport]:
        """Execute the preprocessing pipeline on a dual-channel SAR array.

        Pipeline Stages:
            1. Channel validation: Verifies shape (2, H, W) and float32 conversion.
            2. Invalid-value handling: Cleans NaN and +/- inf using configured strategy.
            3. Optional speckle hook: Applies optional filter if explicitly configured.
            4. Scaling/Clipping: Applies bounds clamping or range mapping if enabled.
            5. Normalization: Standardizes channels using dataset statistics if enabled.
            6. Optional Resizing: Adjusts dimensions if target_size is specified.

        Args:
            image: NumPy array of shape (2, H, W) with channel 0=VV and channel 1=VH.

        Returns:
            Tuple of (model_ready_image, report) where model_ready_image is a
            float32 NumPy array of shape (2, H', W').

        Raises:
            Sentinel1DataError: If array is malformed or parameters are invalid.
        """
        if not isinstance(image, np.ndarray):
            raise Sentinel1DataError(f"Input must be a numpy.ndarray; got {type(image)}.")

        if image.ndim != 3 or image.shape[0] != 2:
            raise Sentinel1DataError(
                f"Expected array of shape (2, H, W) for (VV, VH); got shape {image.shape}."
            )

        input_shape = image.shape
        input_dtype = str(image.dtype)
        out = image.astype(np.float32, copy=True)

        # 1. Invalid value handling
        if self.config.handle_invalid:
            out, invalid_stats = handle_invalid_values(
                out,
                strategy=self.config.invalid_strategy,
                fill_value=self.config.invalid_fill_value,
                min_bound=self.config.min_bound,
                max_bound=self.config.max_bound,
            )
        else:
            invalid_stats = InvalidValueStats(0, 0, 0, 0, int(image.size))

        # 2. Optional speckle hook (Default: none)
        if self.config.speckle_filter == "median":
            import cv2
            ksize = self.config.speckle_kernel_size
            out[0] = cv2.medianBlur(out[0], ksize)
            out[1] = cv2.medianBlur(out[1], ksize)
        elif self.config.speckle_filter != "none":
            raise Sentinel1DataError(
                f"Unsupported speckle_filter '{self.config.speckle_filter}'. "
                f"Supported: 'none', 'median'."
            )

        # 3. Scaling / Clipping
        if self.config.clip_values or self.config.scale_range is not None:
            out = scale_sar_channels(
                out,
                clip=self.config.clip_values,
                clip_min=self.config.clip_min,
                clip_max=self.config.clip_max,
                scale_range=self.config.scale_range,
            )

        # 4. Normalization
        if self.config.normalization != "none":
            out = normalize_sar_channels(
                out,
                strategy=self.config.normalization,
                mean=self.config.mean,
                std=self.config.std,
                min_val=self.config.min_val,
                max_val=self.config.max_val,
                eps=self.config.eps,
            )

        # 5. Optional Resizing (Default: None, preserves 2048x2048)
        resizing_applied = False
        if self.config.target_size is not None:
            out = resize_sar_image(
                out,
                target_size=self.config.target_size,
                interpolation=self.config.resize_interpolation,
            )
            resizing_applied = True

        report = PreprocessingReport(
            input_shape=input_shape,
            output_shape=out.shape,
            input_dtype=input_dtype,
            output_dtype=str(out.dtype),
            invalid_stats=invalid_stats,
            channel_order=["VV", "VH"],
            normalization_applied=self.config.normalization,
            clipping_applied=self.config.clip_values,
            resizing_applied=resizing_applied,
        )

        return out, report

    def process_scene(
        self,
        image: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any] | None, PreprocessingReport]:
        """Execute the preprocessing pipeline and synchronize scene metadata.

        If resizing is applied, updates spatial metadata (dimensions, transform,
        pixel_spacing) to maintain geospatial accuracy. If resizing is not applied
        (the default), metadata is preserved cleanly.

        Args:
            image: NumPy array of shape (2, H, W).
            metadata: Optional scene metadata dictionary from the loader.

        Returns:
            Tuple of (preprocessed_image, updated_metadata, report).
        """
        out, report = self.process(image)

        if metadata is None:
            return out, None, report

        updated_meta = dict(metadata)

        if report.resizing_applied and self.config.target_size is not None:
            from satellite.sentinel1.coordinates import update_transform_for_resizing

            orig_h, orig_w = report.input_shape[1], report.input_shape[2]
            new_h, new_w = self.config.target_size
            updated_meta["dimensions"] = [new_h, new_w]
            updated_meta["height"] = new_h
            updated_meta["width"] = new_w

            if "transform" in updated_meta and updated_meta["transform"]:
                updated_meta["transform"] = update_transform_for_resizing(
                    updated_meta["transform"], (orig_h, orig_w), (new_h, new_w)
                )

            if "pixel_spacing" in updated_meta and updated_meta["pixel_spacing"]:
                sx = float(orig_w) / float(new_w)
                sy = float(orig_h) / float(new_h)
                old_rx, old_ry = updated_meta["pixel_spacing"]
                new_spacing = (old_rx * sx, old_ry * sy)
                updated_meta["pixel_spacing"] = new_spacing
                updated_meta["pixel_resolution"] = new_spacing

        if report.normalization_applied != "none":
            updated_meta["unit"] = "normalized"

        return out, updated_meta, report

    def __call__(self, image: np.ndarray) -> np.ndarray:
        """Callable interface returning only the model-ready array.

        Args:
            image: Input array of shape (2, H, W).

        Returns:
            Preprocessed array of shape (2, H', W') and float32 dtype.
        """
        output_image, _ = self.process(image)
        return output_image


def process_scene(
    image: np.ndarray,
    metadata: dict[str, Any] | None = None,
    config: PreprocessingConfig | None = None,
) -> tuple[np.ndarray, dict[str, Any] | None, PreprocessingReport]:
    """Convenience function to preprocess a SAR scene and synchronize metadata.

    Args:
        image: NumPy array of shape (2, H, W).
        metadata: Optional scene metadata dictionary from the loader.
        config: Optional PreprocessingConfig; defaults to default configuration.

    Returns:
        Tuple of (preprocessed_image, updated_metadata, report).
    """
    preprocessor = Sentinel1Preprocessor(config)
    return preprocessor.process_scene(image, metadata)

