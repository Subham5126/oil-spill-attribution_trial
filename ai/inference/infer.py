from pathlib import Path
import logging

import json
import numpy as np
import rasterio
import torch
import segmentation_models_pytorch as smp

_logger = logging.getLogger("oiltrace.ai.inference")


PATCH_SIZE = 512
STRIDE = 512
THRESHOLD = 0.5

# M1 Specific Model Constants
M1_PATCH_SIZE = 256
M1_STRIDE = 256
M1_THRESHOLD = 0.5


class OilSpillInference:
    def __init__(self, model_path, device=None, model_provider="current"):
        """Initialize OilSpillInference engine.

        Parameters
        ----------
        model_path : str | Path
            Filesystem path to the PyTorch checkpoint.
        device : torch.device | str | None
            Execution device ('cpu' or 'cuda').
        model_provider : str
            Model specification provider: 'current' (default) or 'm1'.
        """
        self.model_path = Path(model_path)
        self.model_provider = str(model_provider).strip().lower()

        if self.model_provider not in ("current", "m1"):
            raise ValueError(
                f"Unknown model_provider '{model_provider}'. Expected 'current' or 'm1'."
            )

        self.device = torch.device(
            device if device else
            ("cuda" if torch.cuda.is_available() else "cpu")
        )

        self.model = smp.Unet(
            encoder_name="resnet34",
            encoder_weights=None,
            in_channels=2,
            classes=1,
            activation=None
        )

        checkpoint = torch.load(
            self.model_path,
            map_location=self.device
        )

        ckpt_type = "training_checkpoint" if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint else "raw_state_dict"
        if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
            self.model.load_state_dict(
                checkpoint["model_state_dict"]
            )
        else:
            self.model.load_state_dict(checkpoint)

        self.model.to(self.device)
        self.model.eval()

        # Diagnostic logging — emitted on every M2 inference engine instantiation
        _logger.info(
            "[M2] Model provider: %s | Checkpoint: %s | Architecture: U-Net ResNet34, 2-channel input | "
            "Device: %s | Checkpoint type: %s | File size: %s bytes",
            self.model_provider.upper(),
            self.model_path,
            self.device,
            ckpt_type,
            f"{self.model_path.stat().st_size:,}" if self.model_path.exists() else "N/A",
        )

    @staticmethod
    def normalize_band(band):
        """Current production dynamic 2nd-98th percentile scaling."""
        band = band.astype(np.float32)

        p2 = np.percentile(band, 2)
        p98 = np.percentile(band, 98)

        if p98 <= p2:
            return np.zeros_like(band, dtype=np.float32)

        band = (band - p2) / (p98 - p2)

        return np.clip(
            band, 0, 1
        ).astype(np.float32)

    @staticmethod
    def normalize_band_m1(band):
        """M1 dedicated fixed decibel clipping and linear scaling: [-35.0, 5.0] dB -> [0, 1]."""
        band = band.astype(np.float32)
        band = np.clip(band, -35.0, 5.0)
        return ((band + 35.0) / 40.0).astype(np.float32)

    def _predict_current(self, image):
        """Execute inference using current production parameters (512x512, percentile scaling, edge padding)."""
        _, height, width = image.shape

        probability_map = np.zeros((height, width), dtype=np.float32)
        count_map = np.zeros((height, width), dtype=np.float32)

        for y in range(0, height, STRIDE):
            for x in range(0, width, STRIDE):
                y2 = min(y + PATCH_SIZE, height)
                x2 = min(x + PATCH_SIZE, width)

                patch = image[:, y:y2, x:x2]

                original_h = patch.shape[1]
                original_w = patch.shape[2]

                pad_h = PATCH_SIZE - original_h
                pad_w = PATCH_SIZE - original_w

                if pad_h > 0 or pad_w > 0:
                    patch = np.pad(
                        patch,
                        (
                            (0, 0),
                            (0, pad_h),
                            (0, pad_w)
                        ),
                        mode="edge"
                    )

                patch = patch.astype(np.float32)

                patch[0] = self.normalize_band(patch[0])
                patch[1] = self.normalize_band(patch[1])

                tensor = torch.from_numpy(patch).unsqueeze(0).to(self.device)

                with torch.no_grad():
                    logits = self.model(tensor)
                    probability = torch.sigmoid(logits)

                prediction = probability[0, 0].cpu().numpy()
                prediction = prediction[:original_h, :original_w]

                probability_map[y:y2, x:x2] += prediction
                count_map[y:y2, x:x2] += 1

        probability_map /= np.maximum(count_map, 1)
        predicted_mask = (probability_map >= THRESHOLD).astype(np.uint8)
        return predicted_mask, probability_map

    def _predict_m1(self, image):
        """Execute inference using validated Member 1 pipeline (256x256, [-35, 5] dB norm, zero padding)."""
        # Step 1: Clean invalid/NaN values
        if not np.all(np.isfinite(image)):
            image = np.nan_to_num(image, nan=0.0, posinf=0.0, neginf=0.0)

        _, height, width = image.shape
        probability_sum = np.zeros((height, width), dtype=np.float32)
        count_map = np.zeros((height, width), dtype=np.float32)

        with torch.no_grad():
            for y in range(0, height, M1_PATCH_SIZE):
                for x in range(0, width, M1_PATCH_SIZE):
                    y_end = min(y + M1_PATCH_SIZE, height)
                    x_end = min(x + M1_PATCH_SIZE, width)
                    actual_h = y_end - y
                    actual_w = x_end - x

                    patch = image[:, y:y_end, x:x_end]

                    vv_norm = self.normalize_band_m1(patch[0])
                    vh_norm = self.normalize_band_m1(patch[1])
                    norm_patch = np.stack([vv_norm, vh_norm], axis=0)

                    # Zero-padding for boundary patches
                    padded_patch = np.zeros((2, M1_PATCH_SIZE, M1_PATCH_SIZE), dtype=np.float32)
                    padded_patch[:, :actual_h, :actual_w] = norm_patch

                    tensor = torch.from_numpy(padded_patch).unsqueeze(0).to(self.device)
                    logits = self.model(tensor)
                    prob = torch.sigmoid(logits)[0, 0].cpu().numpy()

                    # Remove boundary padding
                    prediction = prob[:actual_h, :actual_w]

                    probability_sum[y:y_end, x:x_end] += prediction
                    count_map[y:y_end, x:x_end] += 1.0

        probability_map = probability_sum / np.maximum(count_map, 1.0)
        predicted_mask = (probability_map >= M1_THRESHOLD).astype(np.uint8)
        return predicted_mask, probability_map

    def predict(self, image_path):
        image_path = Path(image_path)

        with rasterio.open(image_path) as src:
            image = src.read()
            profile = src.profile.copy()

        if image.shape[0] != 2:
            raise ValueError(
                f"Expected 2-band SAR image, "
                f"found {image.shape[0]} bands."
            )

        if self.model_provider == "m1":
            _logger.info(
                "[M2] Inference dispatch: M1 pipeline (256x256, dB norm [-35,5], zero-pad) on %s (%dx%d)",
                image_path.name, image.shape[2], image.shape[1],
            )
            predicted_mask, probability_map = self._predict_m1(image)
        else:
            _logger.info(
                "[M2] Inference dispatch: CURRENT pipeline (512x512, percentile norm, edge-pad) on %s (%dx%d)",
                image_path.name, image.shape[2], image.shape[1],
            )
            predicted_mask, probability_map = self._predict_current(image)

        oil_pixel_count = int(predicted_mask.sum())
        total_pixels = predicted_mask.size
        oil_percentage = (oil_pixel_count / total_pixels) * 100.0

        _logger.info(
            "[M2] Result: %d oil pixels (%.3f%%), max prob %.4f, provider=%s",
            oil_pixel_count, oil_percentage,
            float(np.max(probability_map)) if probability_map.size > 0 else 0.0,
            self.model_provider.upper(),
        )

        return {
            "mask": predicted_mask,
            "probability": probability_map,
            "oil_pixel_count": oil_pixel_count,
            "oil_percentage": oil_percentage,
            "profile": profile
        }

    def predict_tile(self, tile):
        """
        Run oil-spill segmentation on one M2 tile.

        Expected input:
            tile.shape = (2, 256, 256)
            tile[0] = VV
            tile[1] = VH

        Returns:
            mask:        (256, 256) uint8
            probability: (256, 256) float32
            oil_pixel_count
            oil_percentage
        """

        tile = np.asarray(tile, dtype=np.float32)

        if tile.ndim != 3:
            raise ValueError(
                f"Expected tile with 3 dimensions (2,H,W), got {tile.shape}"
            )

        if tile.shape[0] != 2:
            raise ValueError(
                f"Expected 2 channels (VV,VH), got {tile.shape[0]}"
            )

        # Normalize VV and VH using the same method as normal inference
        tile[0] = self.normalize_band(tile[0])
        tile[1] = self.normalize_band(tile[1])

        tensor = torch.from_numpy(tile).unsqueeze(0).to(self.device)

        with torch.no_grad():
            logits = self.model(tensor)
            probability = torch.sigmoid(logits)

        probability = (
            probability[0, 0]
            .cpu()
            .numpy()
            .astype(np.float32)
        )

        predicted_mask = (
            probability >= THRESHOLD
        ).astype(np.uint8)

        oil_pixel_count = int(predicted_mask.sum())

        total_pixels = predicted_mask.size

        oil_percentage = (
            oil_pixel_count / total_pixels
        ) * 100

        return {
            "mask": predicted_mask,
            "probability": probability,
            "oil_pixel_count": oil_pixel_count,
            "oil_percentage": oil_percentage
    }

    def save_outputs(self, result, output_dir, input_metadata=None):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        profile = result["profile"].copy()

        # Binary mask GeoTIFF
        mask_profile = profile.copy()
        mask_profile.update(
            count=1,
            dtype="uint8",
            compress="lzw"
        )

        mask_path = output_dir / "predicted_mask.tif"

        with rasterio.open(mask_path, "w", **mask_profile) as dst:
            dst.write(result["mask"], 1)

        # Probability GeoTIFF
        probability_profile = profile.copy()
        probability_profile.update(
            count=1,
            dtype="float32",
            compress="lzw"
        )

        probability_path = output_dir / "probability.tif"

        with rasterio.open(probability_path, "w", **probability_profile) as dst:
            dst.write(
                result["probability"].astype(np.float32),
                1
            )

        metadata = {
            "source": input_metadata or {},

            "prediction": {
                "oil_pixel_count": result["oil_pixel_count"],
                "oil_percentage": result["oil_percentage"],
                "threshold": THRESHOLD
            },

            "image": {
                "width": profile["width"],
                "height": profile["height"],
                "count": profile["count"],
                "dtype": profile["dtype"]
            },

            "geospatial": {
                "crs": str(profile["crs"]) if profile.get("crs") else None,
                "transform": list(profile["transform"])
            }
        }

        metadata_path = output_dir / "metadata.json"

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return {
            "mask_path": str(mask_path),
            "probability_path": str(probability_path),
            "metadata_path": str(metadata_path)
        }


def predict_oil_spill(
    image_path,
    model_path
):
    """
    Run oil-spill segmentation on a 2-band SAR TIFF.
    """

    predictor = OilSpillInference(
        model_path=model_path
    )

    return predictor.predict(
        image_path
    )