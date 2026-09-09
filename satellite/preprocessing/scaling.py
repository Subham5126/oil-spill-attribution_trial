"""Configurable clipping and range scaling for SAR model inputs.

Note:
    Clipping and scaling parameters are model-training hyperparameters,
    NOT physical Sentinel-1 radiometric calibration values. They are designed
    to bound extreme outliers (e.g., strong metallic point reflections from vessels)
    and condition inputs for deep neural networks.
"""

import numpy as np

from satellite.sentinel1.exceptions import Sentinel1DataError


def scale_sar_channels(
    image: np.ndarray,
    clip: bool = False,
    clip_min: tuple[float, float] | float = -50.0,
    clip_max: tuple[float, float] | float = 5.0,
    scale_range: tuple[float, float] | None = None,
) -> np.ndarray:
    """Apply configurable clipping and optional linear range scaling to SAR data.

    Args:
        image: NumPy array of shape (2, H, W) with channel 0=VV and channel 1=VH.
        clip: If True, values outside [clip_min, clip_max] are clamped.
        clip_min: Lower bound for clipping (scalar applied to both or tuple of (vv, vh)).
        clip_max: Upper bound for clipping (scalar applied to both or tuple of (vv, vh)).
        scale_range: Optional tuple of (out_min, out_max) to linearly map clipped
                     values into [out_min, out_max]. If None, no scaling is performed.

    Returns:
        Float32 NumPy array of shape (2, H, W).

    Raises:
        Sentinel1DataError: If array dimensions are invalid or parameter bounds are inverted.
    """
    if image.ndim != 3 or image.shape[0] != 2:
        raise Sentinel1DataError(
            f"Expected array of shape (2, H, W) for (VV, VH) channels; got shape {image.shape}."
        )

    out = image.astype(np.float32, copy=True)

    min_vv = clip_min[0] if isinstance(clip_min, (tuple, list)) else float(clip_min)
    min_vh = clip_min[1] if isinstance(clip_min, (tuple, list)) else float(clip_min)
    max_vv = clip_max[0] if isinstance(clip_max, (tuple, list)) else float(clip_max)
    max_vh = clip_max[1] if isinstance(clip_max, (tuple, list)) else float(clip_max)

    if min_vv >= max_vv or min_vh >= max_vh:
        raise Sentinel1DataError(
            f"clip_min must be strictly less than clip_max; "
            f"got vv=({min_vv}, {max_vv}), vh=({min_vh}, {max_vh})."
        )

    if clip:
        out[0] = np.clip(out[0], min_vv, max_vv)
        out[1] = np.clip(out[1], min_vh, max_vh)

    if scale_range is not None:
        if len(scale_range) != 2:
            raise Sentinel1DataError(
                f"scale_range must be a 2-element tuple (out_min, out_max); got {scale_range}."
            )
        out_min, out_max = float(scale_range[0]), float(scale_range[1])
        if out_min >= out_max:
            raise Sentinel1DataError(
                f"out_min must be strictly less than out_max in scale_range; got ({out_min}, {out_max})."
            )

        # Scale VV channel
        range_vv = max_vv - min_vv
        if range_vv > 0:
            out[0] = out_min + (out[0] - min_vv) * (out_max - out_min) / range_vv

        # Scale VH channel
        range_vh = max_vh - min_vh
        if range_vh > 0:
            out[1] = out_min + (out[1] - min_vh) * (out_max - out_min) / range_vh

    return out
