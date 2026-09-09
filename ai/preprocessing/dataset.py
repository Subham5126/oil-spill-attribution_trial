"""Dataset utilities for two-channel Sentinel-1 oil-spill segmentation."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
import rasterio
import torch
from torch.utils.data import Dataset


class OilSpillPatchDataset(Dataset):
    """Read paired SAR/mask GeoTIFFs and expose fixed-size patches.

    Assumptions for the current SIH dataset:
    - image band 1 = VV
    - image band 2 = VH
    - mask values > 0 represent oil
    - images are normally 2048 x 2048

    The dataset does not perform train/validation/test splitting. Splitting is
    done by the training script at the scene level so that patches from one
    scene cannot leak across splits.
    """

    def __init__(
        self,
        image_paths: Sequence[str | Path],
        mask_paths: Sequence[str | Path],
        patch_size: int = 512,
        stride: int | None = None,
        normalize: bool = True,
        filter_background: bool = False,
        bg_keep_ratio: float = 0.3,
        min_oil_pixels: int = 1,
        seed: int = 42,
    ) -> None:
        if len(image_paths) != len(mask_paths):
            raise ValueError("image_paths and mask_paths must have equal length")
        if not image_paths:
            raise ValueError("No image/mask pairs were supplied")
        if patch_size <= 0:
            raise ValueError("patch_size must be positive")

        self.image_paths = [Path(p) for p in image_paths]
        self.mask_paths = [Path(p) for p in mask_paths]
        self.patch_size = patch_size
        self.stride = stride or patch_size
        self.normalize = normalize
        self.filter_background = filter_background
        self.bg_keep_ratio = bg_keep_ratio
        self.min_oil_pixels = min_oil_pixels
        self.seed = seed

        self._validate_pairs()
        self.patch_index = self._build_patch_index()

    def _validate_pairs(self) -> None:
        for image_path, mask_path in zip(self.image_paths, self.mask_paths):
            if not image_path.is_file():
                raise FileNotFoundError(image_path)
            if not mask_path.is_file():
                raise FileNotFoundError(mask_path)

    def _build_patch_index(self) -> list[tuple[int, int, int]]:
        positive_indices: list[tuple[int, int, int]] = []
        background_indices: list[tuple[int, int, int]] = []

        for scene_idx, (image_path, mask_path) in enumerate(zip(self.image_paths, self.mask_paths)):
            with rasterio.open(image_path) as src:
                if src.count != 2:
                    raise ValueError(
                        f"{image_path.name}: expected 2 bands (VV, VH), found {src.count}"
                    )
                height, width = src.height, src.width

            if height < self.patch_size or width < self.patch_size:
                raise ValueError(
                    f"{image_path.name}: image {width}x{height} is smaller than "
                    f"patch_size={self.patch_size}"
                )

            if self.filter_background:
                with rasterio.open(mask_path) as msrc:
                    mask_full = msrc.read(1)

            for top in range(0, height - self.patch_size + 1, self.stride):
                for left in range(0, width - self.patch_size + 1, self.stride):
                    if self.filter_background:
                        patch_mask = mask_full[top : top + self.patch_size, left : left + self.patch_size]
                        oil_count = int((patch_mask > 0).sum())
                        if oil_count >= self.min_oil_pixels:
                            positive_indices.append((scene_idx, top, left))
                        else:
                            background_indices.append((scene_idx, top, left))
                    else:
                        positive_indices.append((scene_idx, top, left))

        if not self.filter_background:
            return positive_indices

        # Subsample background patches to maintain balance while retaining negative examples
        import random
        rng = random.Random(self.seed)
        num_bg_to_keep = int(len(background_indices) * self.bg_keep_ratio)
        kept_bg_indices = rng.sample(background_indices, k=min(num_bg_to_keep, len(background_indices)))

        final_index = positive_indices + kept_bg_indices
        rng.shuffle(final_index)
        return final_index

    @staticmethod
    def _robust_normalize(image: np.ndarray) -> np.ndarray:
        """Per-patch 2nd/98th percentile scaling for VV and VH."""
        output = np.empty_like(image, dtype=np.float32)
        for band in range(image.shape[0]):
            values = image[band].astype(np.float32, copy=False)
            low, high = np.percentile(values, (2, 98))
            if not np.isfinite(low) or not np.isfinite(high) or high <= low:
                output[band] = 0.0
                continue
            output[band] = np.clip((values - low) / (high - low), 0.0, 1.0)
        return output

    def __len__(self) -> int:
        return len(self.patch_index)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        scene_idx, top, left = self.patch_index[index]
        image_path = self.image_paths[scene_idx]
        mask_path = self.mask_paths[scene_idx]
        window = rasterio.windows.Window(left, top, self.patch_size, self.patch_size)

        with rasterio.open(image_path) as src:
            image = src.read(window=window).astype(np.float32)
        with rasterio.open(mask_path) as src:
            mask = src.read(1, window=window)

        if image.shape != (2, self.patch_size, self.patch_size):
            raise ValueError(f"Unexpected image patch shape: {image.shape}")
        if mask.shape != (self.patch_size, self.patch_size):
            raise ValueError(f"Unexpected mask patch shape: {mask.shape}")
        if not np.isfinite(image).all():
            raise ValueError(f"Non-finite SAR value found in {image_path.name}")

        if self.normalize:
            image = self._robust_normalize(image)

        mask = (mask > 0).astype(np.float32)

        return (
            torch.from_numpy(image),
            torch.from_numpy(mask[None, ...]),
        )

