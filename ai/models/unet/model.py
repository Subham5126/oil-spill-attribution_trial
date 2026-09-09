"""U-Net baseline model for two-channel SAR oil-spill segmentation."""

from __future__ import annotations

import segmentation_models_pytorch as smp


def build_unet(
    encoder_name: str = "resnet34",
    encoder_weights: str | None = None,
) -> smp.Unet:
    """Build the project baseline: VV + VH -> binary oil mask."""
    return smp.Unet(
        encoder_name=encoder_name,
        encoder_weights=encoder_weights,
        in_channels=2,
        classes=1,
        activation=None,
    )
