import json
import os
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env")

API_URL = "http://127.0.0.1:8001/predict-tiles"

API_KEY = os.getenv("M1_API_KEY")

OUTPUT_ZIP = Path(os.getenv("M1_OUTPUT_ZIP", str(Path(__file__).parent / "m1_tiles_result.zip")))


def main():

    # --------------------------------------------------
    # 1. Create mock M2 tiles
    # --------------------------------------------------

    N = 3

    tiles = np.random.rand(
        N, 2, 256, 256
    ).astype(np.float32)

    tiles_path = Path(__file__).parent / "m2_tiles.npy"
    np.save(tiles_path, tiles)

    # --------------------------------------------------
    # 2. Create mock M2 metadata
    # --------------------------------------------------

    sample_transform = [
        8.983152841195215e-05,
        0.0,
        29.198322133239117,
        0.0,
        -8.983152841195215e-05,
        32.63479208299711
    ]

    metadata = {
        "scene_id": "subset_33_of_S1A_IW_GRDH_1SDV_20160707T040004_20160707T040024_012037_0129A1_A38C_Orb_NR_Cal_Spk_TC_dB.dim",
        "tile_count": N,
        "tile_shape": [2, 256, 256],

        "channel_mapping": {
            "channel_0": "VV",
            "channel_1": "VH"
        },

        "tiles": [
            {
                "scene_id": "subset_33_of_S1A_IW_GRDH_1SDV_20160707T040004_20160707T040024_012037_0129A1_A38C_Orb_NR_Cal_Spk_TC_dB.dim",
                "tile_id": f"tile_{i:04d}",
                "row_idx": 0,
                "col_idx": i,
                "pixel_row_start": 0,
                "pixel_row_end": 256,
                "pixel_col_start": i * 256,
                "pixel_col_end": (i + 1) * 256,
                "tile_height": 256,
                "tile_width": 256,
                "scene_dimensions": [2048, 2048],
                "tile_size": 256,
                "stride": 256,
                "overlap": 0,
                "is_padded": False,
                "valid_region": [0, 256, 0, 256],
                "crs": "EPSG:4326",
                "transform": sample_transform,
                "bounds": [
                    29.198322133239117,
                    32.611795211723646,
                    29.221319004512576,
                    32.63479208299711
                ],
                "acquisition_time": "2016-07-07 04:00:14.019949+00:00",
                "pixel_spacing": [
                    8.983152841195215e-05,
                    8.983152841195215e-05
                ],
                "pixel_resolution": [
                    8.983152841195215e-05,
                    8.983152841195215e-05
                ],
                "bands": ["VV", "VH"],
                "polarization_order": ["VV", "VH"],
                "unit": "dB",
                "dtype": "float32",
                "tile_dimensions": [256, 256],
                "index": i
            }
            for i in range(N)
        ]
    }

    metadata_path = (
        Path(__file__).parent /
        "m2_metadata.json"
    )

    with open(
        metadata_path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            metadata,
            f,
            indent=2
        )

    # --------------------------------------------------
    # 3. Send M2 output to M1
    # --------------------------------------------------

    headers = {
        "X-API-Key": API_KEY
    }

    with open(tiles_path, "rb") as tiles_file, \
         open(metadata_path, "rb") as metadata_file:

        files = {
            "tiles": (
                "m2_tiles.npy",
                tiles_file,
                "application/octet-stream"
            ),

            "metadata": (
                "m2_metadata.json",
                metadata_file,
                "application/json"
            )
        }

        response = requests.post(
            API_URL,
            headers=headers,
            files=files
        )

    # --------------------------------------------------
    # 4. Check response
    # --------------------------------------------------

    print("HTTP status:", response.status_code)

    if response.status_code != 200:
        print("M1 error:")
        print(response.text)
        return

    with open(OUTPUT_ZIP, "wb") as f:
        f.write(response.content)

    print("M1 response received.")
    print("Output:", OUTPUT_ZIP)

    # --------------------------------------------------
    # 5. Validation of ZIP and GeoTIFF outputs
    # --------------------------------------------------
    import zipfile
    import rasterio
    from rasterio.transform import Affine

    with zipfile.ZipFile(OUTPUT_ZIP, "r") as zip_ref:
        zip_contents = zip_ref.namelist()
        print("ZIP contents:", zip_contents)
        
        extract_dir = Path(__file__).parent / "extracted_result"
        zip_ref.extractall(extract_dir)

    mask_tif = extract_dir / "predicted_masks" / "tile_0000.tif"
    prob_tif = extract_dir / "probabilities" / "tile_0000.tif"
    out_meta_json = extract_dir / "metadata.json"

    assert mask_tif.exists(), "Mask TIF missing!"
    assert prob_tif.exists(), "Probability TIF missing!"
    assert out_meta_json.exists(), "Metadata JSON missing!"

    with rasterio.open(mask_tif) as src:
        print(f"Mask TIF size: {src.width}x{src.height}, count: {src.count}, dtype: {src.dtypes[0]}, crs: {src.crs}")
        assert src.width == 256
        assert src.height == 256
        assert src.count == 1
        assert src.dtypes[0] == "uint8"
        assert str(src.crs) == "EPSG:4326"
        expected_transform = Affine(*sample_transform)
        assert src.transform == expected_transform, f"Transform mismatch: {src.transform} vs {expected_transform}"

    with rasterio.open(prob_tif) as src:
        print(f"Prob TIF size: {src.width}x{src.height}, count: {src.count}, dtype: {src.dtypes[0]}, crs: {src.crs}")
        assert src.width == 256
        assert src.height == 256
        assert src.count == 1
        assert src.dtypes[0] == "float32"
        assert str(src.crs) == "EPSG:4326"
        assert src.transform == expected_transform

    with open(out_meta_json, "r", encoding="utf-8") as f:
        res_meta = json.load(f)

    assert "source" in res_meta, "Metadata 'source' missing!"
    assert "tiles" in res_meta, "Metadata 'tiles' missing!"
    print("Validation successful!")


if __name__ == "__main__":
    main()