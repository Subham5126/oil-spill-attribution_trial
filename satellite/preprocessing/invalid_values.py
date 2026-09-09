"""Invalid value detection, reporting, and replacement for SAR data."""

from dataclasses import dataclass
from typing import Literal
import numpy as np

from satellite.sentinel1.exceptions import Sentinel1DataError


@dataclass(frozen=True)
class InvalidValueStats:
    """Summary of non-finite values detected in an array."""

    nan_count: int
    pos_inf_count: int
    neg_inf_count: int
    total_invalid: int
    total_pixels: int

    @property
    def has_invalid(self) -> bool:
        """True if any non-finite values were detected."""
        return self.total_invalid > 0

    @property
    def invalid_ratio(self) -> float:
        """Ratio of invalid pixels to total pixels."""
        if self.total_pixels == 0:
            return 0.0
        return self.total_invalid / self.total_pixels


def detect_invalid_values(image: np.ndarray) -> InvalidValueStats:
    """Scan a SAR array and return statistics on non-finite values (NaN, +inf, -inf).

    Args:
        image: NumPy array of any shape (typically (C, H, W)).

    Returns:
        InvalidValueStats with counts of NaN, +inf, -inf, and total invalid pixels.
    """
    nan_mask = np.isnan(image)
    pos_inf_mask = np.isposinf(image)
    neg_inf_mask = np.isneginf(image)

    nan_count = int(np.count_nonzero(nan_mask))
    pos_inf_count = int(np.count_nonzero(pos_inf_mask))
    neg_inf_count = int(np.count_nonzero(neg_inf_mask))
    total_invalid = nan_count + pos_inf_count + neg_inf_count
    total_pixels = int(image.size)

    return InvalidValueStats(
        nan_count=nan_count,
        pos_inf_count=pos_inf_count,
        neg_inf_count=neg_inf_count,
        total_invalid=total_invalid,
        total_pixels=total_pixels,
    )


def handle_invalid_values(
    image: np.ndarray,
    strategy: Literal["constant", "clip_bounds", "raise"] = "constant",
    fill_value: float = -50.0,
    min_bound: float = -50.0,
    max_bound: float = 5.0,
) -> tuple[np.ndarray, InvalidValueStats]:
    """Detect and handle non-finite values (NaN, +inf, -inf) according to strategy.

    Strategies:
        - "constant": Replaces all non-finite values with ``fill_value``.
                      Default fill_value is -50.0 dB (representing the SAR radar
                      noise floor where signal is below detection limits).
        - "clip_bounds": Replaces -inf with ``min_bound``, +inf with ``max_bound``,
                         and NaN with ``min_bound``.
        - "raise": Raises Sentinel1DataError if any non-finite value is present.

    Args:
        image: NumPy float array of shape (C, H, W) or (H, W).
        strategy: Strategy for handling invalid pixels ('constant', 'clip_bounds', 'raise').
        fill_value: Value used when strategy='constant'. Default -50.0 dB.
        min_bound: Lower bound used when strategy='clip_bounds'. Default -50.0 dB.
        max_bound: Upper bound used when strategy='clip_bounds'. Default 5.0 dB.

    Returns:
        Tuple of (cleaned_array, stats). The returned array is guaranteed finite.

    Raises:
        Sentinel1DataError: If strategy is 'raise' and non-finite values are found,
                            or if strategy is unrecognized.
    """
    stats = detect_invalid_values(image)

    if not stats.has_invalid:
        return image.copy(), stats

    if strategy == "raise":
        raise Sentinel1DataError(
            f"Array contains non-finite values: {stats.nan_count} NaN, "
            f"{stats.pos_inf_count} +inf, {stats.neg_inf_count} -inf "
            f"(total: {stats.total_invalid}/{stats.total_pixels})."
        )

    out = image.copy()

    if strategy == "constant":
        invalid_mask = ~np.isfinite(out)
        out[invalid_mask] = fill_value
    elif strategy == "clip_bounds":
        out[np.isneginf(out)] = min_bound
        out[np.isposinf(out)] = max_bound
        out[np.isnan(out)] = min_bound
    else:
        raise Sentinel1DataError(
            f"Unknown invalid-value handling strategy '{strategy}'. "
            f"Supported: 'constant', 'clip_bounds', 'raise'."
        )

    return out.astype(np.float32), stats
