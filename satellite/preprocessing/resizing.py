"""Explicit spatial resizing utility for dual-channel SAR data.

Note:
    By default, the pipeline does NOT resize the 2048x2048 SAR scenes.
    This utility is provided solely for models requiring specific input sizes
    (e.g., downscaled evaluation architectures) and must be explicitly enabled.
"""

from typing import Literal
import cv2
import numpy as np

from satellite.sentinel1.exceptions import Sentinel1DataError


def resize_sar_image(
    image: np.ndarray,
    target_size: tuple[int, int],
    interpolation: Literal["bilinear", "nearest", "area", "bicubic"] = "bilinear",
) -> np.ndarray:
    """Resize a dual-channel (2, H, W) SAR image to target (target_H, target_W).

    Args:
        image: NumPy array of shape (2, H, W) where channel 0=VV and channel 1=VH.
        target_size: Desired output dimensions as (target_height, target_width).
        interpolation: Resampling method ('bilinear', 'nearest', 'area', 'bicubic').

    Returns:
        Resized float32 NumPy array of shape (2, target_height, target_width).

    Raises:
        Sentinel1DataError: If image shape is invalid or target dimensions are non-positive.
    """
    if image.ndim != 3 or image.shape[0] != 2:
        raise Sentinel1DataError(
            f"Expected array of shape (2, H, W) for (VV, VH) channels; got shape {image.shape}."
        )

    if len(target_size) != 2:
        raise Sentinel1DataError(
            f"target_size must be a 2-element tuple (height, width); got {target_size}."
        )

    target_h, target_w = int(target_size[0]), int(target_size[1])
    if target_h <= 0 or target_w <= 0:
        raise Sentinel1DataError(
            f"Target dimensions must be strictly positive; got ({target_h}, {target_w})."
        )

    # If already target size, return copy
    if image.shape[1] == target_h and image.shape[2] == target_w:
        return image.astype(np.float32, copy=True)

    interp_map = {
        "bilinear": cv2.INTER_LINEAR,
        "nearest": cv2.INTER_NEAREST,
        "area": cv2.INTER_AREA,
        "bicubic": cv2.INTER_CUBIC,
    }

    if interpolation not in interp_map:
        raise Sentinel1DataError(
            f"Unknown interpolation method '{interpolation}'. "
            f"Supported: {list(interp_map.keys())}."
        )

    cv2_flag = interp_map[interpolation]

    # OpenCV takes (width, height) for dsize
    dsize = (target_w, target_h)

    # Resize each channel independently to preserve float32 precision
    vv_resized = cv2.resize(image[0], dsize, interpolation=cv2_flag)
    vh_resized = cv2.resize(image[1], dsize, interpolation=cv2_flag)

    return np.stack([vv_resized, vh_resized], axis=0).astype(np.float32)
