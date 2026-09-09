import json
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine
from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ai.inference.infer import OilSpillInference


router = APIRouter()


def register_tile_router(predictor: OilSpillInference, api_key: str):
    @router.post("/predict-tiles")
    async def predict_tiles(
        tiles: UploadFile = File(...),
        metadata: UploadFile = File(...),
        x_api_key: str | None = Header(default=None)
    ):
        # API-key authentication
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="M1 API key is not configured on the server."
            )

        if x_api_key != api_key:
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing API key."
            )

        # Validate files
        if not tiles.filename.lower().endswith(".npy"):
            raise HTTPException(
                status_code=400,
                detail="Tiles must be a .npy file."
            )

        if not metadata.filename.lower().endswith(".json"):
            raise HTTPException(
                status_code=400,
                detail="Metadata must be a JSON file."
            )

        temp_dir = Path(tempfile.mkdtemp(prefix="m1_tiles_"))

        try:
            tiles_path = temp_dir / tiles.filename
            metadata_path = temp_dir / metadata.filename

            with open(tiles_path, "wb") as f:
                f.write(await tiles.read())

            with open(metadata_path, "wb") as f:
                f.write(await metadata.read())

            # Read M2 metadata
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    raw_input_metadata = json.load(f)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid metadata JSON."
                )

            if isinstance(raw_input_metadata, list):
                tile_metadata_list = raw_input_metadata
                input_metadata = {"tiles": raw_input_metadata}
            elif isinstance(raw_input_metadata, dict):
                tile_metadata_list = raw_input_metadata.get("tiles")
                if not isinstance(tile_metadata_list, list):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Metadata JSON must be either a root list of "
                            "per-tile metadata objects or an object with a "
                            "'tiles' list."
                        )
                    )
                input_metadata = raw_input_metadata
            else:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Metadata JSON must be either a root list of "
                        "per-tile metadata objects or an object with a "
                        "'tiles' list."
                    )
                )

            # Load M2 tiles
            try:
                tile_array = np.load(tiles_path)
            except Exception as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Could not read .npy tiles: {exc}"
                )

            if len(tile_metadata_list) != len(tile_array):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Metadata tile count does not match the number of "
                        f"tiles in the .npy file ({len(tile_array)})."
                    )
                )

            # Validate shape
            if tile_array.ndim != 4:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Expected tiles with shape "
                        "(N, 2, 256, 256). "
                        f"Received {tile_array.shape}."
                    )
                )

            if tile_array.shape[1:] != (2, 256, 256):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Expected tiles with shape "
                        "(N, 2, 256, 256). "
                        f"Received {tile_array.shape}."
                    )
                )

            if tile_array.dtype != np.float32:
                tile_array = tile_array.astype(np.float32)

            masks_dir = temp_dir / "predicted_masks"
            probabilities_dir = temp_dir / "probabilities"

            masks_dir.mkdir()
            probabilities_dir.mkdir()

            tile_results = []

            for index, tile in enumerate(tile_array):

                result = predictor.predict_tile(tile)

                tile_metadata = tile_metadata_list[index]
                tile_id = str(tile_metadata.get("tile_id") or f"tile_{index:04d}")

                transform = Affine(*tile_metadata["transform"])
                crs = tile_metadata["crs"]

                mask_path = masks_dir / f"{tile_id}.tif"
                probability_path = probabilities_dir / f"{tile_id}.tif"

                profile = {
                    "driver": "GTiff",
                    "height": 256,
                    "width": 256,
                    "count": 1,
                    "dtype": "uint8",
                    "crs": crs,
                    "transform": transform,
                    "compress": "lzw"
                }

                with rasterio.open(mask_path, "w", **profile) as dst:
                    dst.write(result["mask"], 1)

                probability_profile = profile.copy()
                probability_profile["dtype"] = "float32"

                with rasterio.open(
                    probability_path,
                    "w",
                    **probability_profile
                ) as dst:
                    dst.write(
                        result["probability"].astype(np.float32),
                        1
                    )

                tile_result = dict(tile_metadata)
                tile_result.update({
                    "tile_id": tile_id,
                    "index": index,
                    "shape": list(tile.shape),
                    "prediction": {
                        "oil_pixel_count": result["oil_pixel_count"],
                        "oil_percentage": result["oil_percentage"],
                        "threshold": 0.5
                    }
                })

                tile_results.append(tile_result)

            output_metadata = {
                "source": input_metadata,
                "tile_count": len(tile_array),
                "tile_shape": [2, 256, 256],
                "channel_mapping": {
                    "channel_0": "VV",
                    "channel_1": "VH"
                },
                "tiles": tile_results
            }

            metadata_output = temp_dir / "metadata.json"

            with open(
                metadata_output,
                "w",
                encoding="utf-8"
            ) as f:
                json.dump(
                    output_metadata,
                    f,
                    indent=2
                )

            zip_path = temp_dir / "m1_tiles_result.zip"

            with zipfile.ZipFile(
                zip_path,
                "w",
                compression=zipfile.ZIP_DEFLATED
            ) as zip_file:

                for path in masks_dir.glob("*.tif"):
                    zip_file.write(
                        path,
                        arcname=f"predicted_masks/{path.name}"
                    )

                for path in probabilities_dir.glob("*.tif"):
                    zip_file.write(
                        path,
                        arcname=f"probabilities/{path.name}"
                    )

                zip_file.write(
                    metadata_output,
                    arcname="metadata.json"
                )

            return FileResponse(
                path=zip_path,
                media_type="application/zip",
                filename="m1_tiles_result.zip"
            )

        except HTTPException:
            raise

        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Tile inference failed: {exc}"
            )

    return router