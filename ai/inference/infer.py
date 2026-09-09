from pathlib import Path

import json
import numpy as np
import rasterio
import torch
import segmentation_models_pytorch as smp


PATCH_SIZE = 512
STRIDE = 512
THRESHOLD = 0.5


class OilSpillInference:
    def __init__(self, model_path, device=None):
        self.model_path = Path(model_path)

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

        if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
            self.model.load_state_dict(
                checkpoint["model_state_dict"]
            )
        else:
            self.model.load_state_dict(checkpoint)

        self.model.to(self.device)
        self.model.eval()

    @staticmethod
    def normalize_band(band):
        band = band.astype(np.float32)

        p2 = np.percentile(band, 2)
        p98 = np.percentile(band, 98)

        if p98 <= p2:
            return np.zeros_like(band, dtype=np.float32)

        band = (band - p2) / (p98 - p2)

        return np.clip(
            band, 0, 1
        ).astype(np.float32)

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

        _, height, width = image.shape

        probability_map = np.zeros(
            (height, width),
            dtype=np.float32
        )

        count_map = np.zeros(
            (height, width),
            dtype=np.float32
        )

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

                tensor = torch.from_numpy(
                    patch
                ).unsqueeze(0).to(self.device)

                with torch.no_grad():
                    logits = self.model(tensor)
                    probability = torch.sigmoid(logits)

                prediction = (
                    probability[0, 0]
                    .cpu()
                    .numpy()
                )

                prediction = prediction[
                    :original_h,
                    :original_w
                ]

                probability_map[
                    y:y2,
                    x:x2
                ] += prediction

                count_map[
                    y:y2,
                    x:x2
                ] += 1

        probability_map /= np.maximum(
            count_map,
            1
        )

        predicted_mask = (
            probability_map >= THRESHOLD
        ).astype(np.uint8)

        oil_pixel_count = int(
            predicted_mask.sum()
        )

        total_pixels = predicted_mask.size

        oil_percentage = (
            oil_pixel_count /
            total_pixels
        ) * 100

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