"""Consistent per-channel normalization for Sentinel-1 Sigma0 dB data.

This module provides reproducible normalization across training, validation,
testing, and inference splits. Rather than normalizing each scene independently
(which distorts physical backscatter differences), normalization parameters
should be calculated strictly on the training partition and applied consistently.
"""

from typing import Literal
import numpy as np

from satellite.sentinel1.exceptions import Sentinel1DataError


def normalize_sar_channels(
    image: np.ndarray,
    strategy: Literal["none", "zscore", "minmax"] = "none",
    mean: tuple[float, float] | None = None,
    std: tuple[float, float] | None = None,
    min_val: tuple[float, float] | None = None,
    max_val: tuple[float, float] | None = None,
    eps: float = 1e-6,
) -> np.ndarray:
    """Normalize a dual-channel (VV, VH) Sentinel-1 array consistently.

    Args:
        image: NumPy array of shape (2, H, W) where channel 0=VV and channel 1=VH.
        strategy: Normalization approach:
            - "none": Identity passthrough. Preserves raw Sigma0 dB backscatter.
            - "zscore": Standardizes each channel using externally supplied (mean, std):
                        (x_c - mean_c) / (std_c + eps).
            - "minmax": Scales each channel into [0, 1] using externally supplied (min_val, max_val):
                        (x_c - min_c) / (max_c - min_c + eps).
        mean: Tuple of (mean_vv, mean_vh) in dB. Required when strategy='zscore'.
        std: Tuple of (std_vv, std_vh) in dB. Required when strategy='zscore'.
        min_val: Tuple of (min_vv, min_vh) in dB. Required when strategy='minmax'.
        max_val: Tuple of (max_vv, max_vh) in dB. Required when strategy='minmax'.
        eps: Small positive epsilon to prevent division by zero. Default 1e-6.

    Returns:
        Normalized NumPy float32 array of shape (2, H, W).

    Raises:
        Sentinel1DataError: If array does not have exactly 2 channels, or if required
                            statistics are missing for the chosen strategy.
    """
    if image.ndim != 3 or image.shape[0] != 2:
        raise Sentinel1DataError(
            f"Expected array of shape (2, H, W) for (VV, VH) channels; got shape {image.shape}."
        )

    if strategy == "none":
        return image.astype(np.float32, copy=True)

    if strategy == "zscore":
        if mean is None or std is None:
            raise Sentinel1DataError(
                "zscore normalization requires dataset-wide 'mean' and 'std' parameters "
                "as (vv_stat, vh_stat) tuples to maintain consistency across dataset splits."
            )
        if len(mean) != 2 or len(std) != 2:
            raise Sentinel1DataError(
                f"Expected 2-element tuples for mean and std; got len(mean)={len(mean)}, len(std)={len(std)}."
            )
        if std[0] <= 0 or std[1] <= 0:
            raise Sentinel1DataError(
                f"Standard deviations must be strictly positive; got std={std}."
            )

        norm_vv = (image[0] - mean[0]) / (std[0] + eps)
        norm_vh = (image[1] - mean[1]) / (std[1] + eps)
        return np.stack([norm_vv, norm_vh], axis=0).astype(np.float32)

    if strategy == "minmax":
        if min_val is None or max_val is None:
            raise Sentinel1DataError(
                "minmax normalization requires dataset-wide 'min_val' and 'max_val' parameters "
                "as (vv_stat, vh_stat) tuples to maintain consistency across dataset splits."
            )
        if len(min_val) != 2 or len(max_val) != 2:
            raise Sentinel1DataError(
                f"Expected 2-element tuples for min_val and max_val; "
                f"got len(min_val)={len(min_val)}, len(max_val)={len(max_val)}."
            )
        if max_val[0] <= min_val[0] or max_val[1] <= min_val[1]:
            raise Sentinel1DataError(
                f"max_val must be strictly greater than min_val; got min_val={min_val}, max_val={max_val}."
            )

        norm_vv = (image[0] - min_val[0]) / (max_val[0] - min_val[0] + eps)
        norm_vh = (image[1] - min_val[1]) / (max_val[1] - min_val[1] + eps)
        return np.stack([norm_vv, norm_vh], axis=0).astype(np.float32)

    raise Sentinel1DataError(
        f"Unknown normalization strategy '{strategy}'. Supported: 'none', 'zscore', 'minmax'."
    )
