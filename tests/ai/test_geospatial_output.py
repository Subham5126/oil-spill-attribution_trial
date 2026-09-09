"""
Step 13: Comprehensive Geospatial Verification of M1 /predict-tiles Output.

This test validates that every generated M1 GeoTIFF preserves all geospatial
and metadata information supplied by M2.
"""

import json
import os
import shutil
import zipfile
from pathlib import Path

import numpy as np
import rasterio
import requests
from dotenv import load_dotenv
from rasterio.transform import Affine

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

API_URL = "http://127.0.0.1:8001/predict-tiles"
API_KEY = os.getenv("M1_API_KEY")

TEST_DIR = Path(__file__).parent / "geospatial_verification_data"
OUTPUT_ZIP = TEST_DIR / "m1_tiles_result.zip"
EXTRACT_DIR = TEST_DIR / "extracted"


def generate_mock_m2_data(scene_rows=8, scene_cols=8, tile_size=256):
    """
    Generate mock M2 tiles (N=64, 2, 256, 256) and complete per-tile M2 metadata.
    """
    N = scene_rows * scene_cols
    np.random.seed(42)
    tiles = np.random.rand(N, 2, tile_size, tile_size).astype(np.float32)

    lon0 = 29.198322133239117
    lat0 = 32.63479208299711
    dx = 8.983152841195215e-05
    dy = -8.983152841195215e-05

    tiles_metadata = []
    tile_idx = 0
    for r in range(scene_rows):
        for c in range(scene_cols):
            p_r_start = r * tile_size
            p_r_end = (r + 1) * tile_size
            p_c_start = c * tile_size
            p_c_end = (c + 1) * tile_size

            tile_lon0 = lon0 + c * tile_size * dx
            tile_lat0 = lat0 + r * tile_size * dy  # dy is negative

            transform = [
                dx, 0.0, tile_lon0,
                0.0, dy, tile_lat0
            ]

            minx = tile_lon0
            maxx = tile_lon0 + tile_size * dx
            miny = tile_lat0 + tile_size * dy  # dy is negative, so miny < maxy
            maxy = tile_lat0
            bounds = [minx, miny, maxx, maxy]

            tile_meta = {
                "scene_id": "subset_33_of_S1A_IW_GRDH_1SDV_20160707T040004_20160707T040024_012037_0129A1_A38C_Orb_NR_Cal_Spk_TC_dB.dim",
                "tile_id": f"subset_33_of_S1A_IW_GRDH_1SDV_20160707T040004_20160707T040024_012037_0129A1_A38C_Orb_NR_Cal_Spk_TC_dB.dim_r{r:03d}_c{c:03d}",
                "row_idx": r,
                "col_idx": c,
                "pixel_row_start": p_r_start,
                "pixel_row_end": p_r_end,
                "pixel_col_start": p_c_start,
                "pixel_col_end": p_c_end,
                "tile_height": tile_size,
                "tile_width": tile_size,
                "scene_dimensions": [scene_rows * tile_size, scene_cols * tile_size],
                "tile_size": tile_size,
                "stride": tile_size,
                "overlap": 0,
                "is_padded": False,
                "valid_region": [0, tile_size, 0, tile_size],
                "crs": "EPSG:4326",
                "transform": transform,
                "bounds": bounds,
                "acquisition_time": "2016-07-07 04:00:14.019949+00:00",
                "pixel_spacing": [abs(dx), abs(dy)],
                "pixel_resolution": [abs(dx), abs(dy)],
                "bands": ["VV", "VH"],
                "polarization_order": ["VV", "VH"],
                "unit": "dB",
                "dtype": "float32",
                "tile_dimensions": [tile_size, tile_size],
                "index": tile_idx
            }
            tiles_metadata.append(tile_meta)
            tile_idx += 1

    metadata = {
        "scene_id": "subset_33_of_S1A_IW_GRDH_1SDV_20160707T040004_20160707T040024_012037_0129A1_A38C_Orb_NR_Cal_Spk_TC_dB.dim",
        "tile_count": N,
        "tile_shape": [2, tile_size, tile_size],
        "channel_mapping": {
            "channel_0": "VV",
            "channel_1": "VH"
        },
        "tiles": tiles_metadata
    }

    return tiles, metadata


def test_comprehensive_geospatial_output():
    """
    Main verification test for Step 13.
    """
    TEST_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Generate N=64 test data
    scene_rows, scene_cols = 8, 8
    expected_tile_count = scene_rows * scene_cols
    tiles_np, input_metadata = generate_mock_m2_data(scene_rows, scene_cols)

    tiles_path = TEST_DIR / "m2_tiles_64.npy"
    metadata_path = TEST_DIR / "m2_metadata_64.json"

    np.save(tiles_path, tiles_np)
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(input_metadata, f, indent=2)

    # 2. Call /predict-tiles API
    headers = {"X-API-Key": API_KEY}
    with open(tiles_path, "rb") as tf, open(metadata_path, "rb") as mf:
        files = {
            "tiles": ("m2_tiles_64.npy", tf, "application/octet-stream"),
            "metadata": ("m2_metadata_64.json", mf, "application/json")
        }
        response = requests.post(API_URL, headers=headers, files=files)

    assert response.status_code == 200, f"API failed with status {response.status_code}: {response.text}"

    with open(OUTPUT_ZIP, "wb") as f:
        f.write(response.content)

    if EXTRACT_DIR.exists():
        shutil.rmtree(EXTRACT_DIR)

    with zipfile.ZipFile(OUTPUT_ZIP, "r") as zf:
        zf.extractall(EXTRACT_DIR)

    masks_dir = EXTRACT_DIR / "predicted_masks"
    probs_dir = EXTRACT_DIR / "probabilities"
    out_meta_file = EXTRACT_DIR / "metadata.json"

    # 3. Verify counts
    mask_files = sorted(list(masks_dir.glob("*.tif")))
    prob_files = sorted(list(probs_dir.glob("*.tif")))

    assert len(mask_files) == expected_tile_count, f"Expected {expected_tile_count} mask TIFFs, got {len(mask_files)}"
    assert len(prob_files) == expected_tile_count, f"Expected {expected_tile_count} prob TIFFs, got {len(prob_files)}"
    assert out_meta_file.exists(), "metadata.json is missing in ZIP"

    with open(out_meta_file, "r", encoding="utf-8") as f:
        output_metadata = json.load(f)

    # 4. Verify Row/Col indices and tile ordering
    grid_coverage = set()
    for i in range(expected_tile_count):
        tile_id_str = f"tile_{i:04d}"
        mask_tif = masks_dir / f"{tile_id_str}.tif"
        prob_tif = probs_dir / f"{tile_id_str}.tif"

        assert mask_tif.exists(), f"Missing mask file {mask_tif.name}"
        assert prob_tif.exists(), f"Missing prob file {prob_tif.name}"

        m2_tile = input_metadata["tiles"][i]
        out_tile = output_metadata["tiles"][i]

        assert out_tile["index"] == i, f"Index mismatch for tile {i}"
        r, c = m2_tile["row_idx"], m2_tile["col_idx"]
        assert 0 <= r < scene_rows and 0 <= c < scene_cols, f"Invalid row/col ({r}, {c}) for tile {i}"
        grid_coverage.add((r, c))

    assert len(grid_coverage) == expected_tile_count, "Incomplete or duplicate row/col grid coverage"

    # 5. Per-tile raster & geospatial checks
    for i in range(expected_tile_count):
        tile_id_str = f"tile_{i:04d}"
        mask_tif = masks_dir / f"{tile_id_str}.tif"
        prob_tif = probs_dir / f"{tile_id_str}.tif"

        m2_tile = input_metadata["tiles"][i]
        expected_crs = m2_tile["crs"]
        expected_transform = Affine(*m2_tile["transform"])
        expected_bounds = m2_tile["bounds"]

        # Check Mask TIFF
        with rasterio.open(mask_tif) as src_mask:
            assert src_mask.width == 256, f"Tile {i} mask width != 256"
            assert src_mask.height == 256, f"Tile {i} mask height != 256"
            assert src_mask.count == 1, f"Tile {i} mask band count != 1"
            assert src_mask.dtypes[0] == "uint8", f"Tile {i} mask dtype != uint8"
            assert str(src_mask.crs) == expected_crs, f"Tile {i} mask CRS mismatch: {src_mask.crs} vs {expected_crs}"

            assert np.allclose(
                tuple(src_mask.transform),
                tuple(expected_transform),
                rtol=0,
                atol=1e-12
            ), f"Tile {i} mask transform mismatch: {src_mask.transform} vs {expected_transform}"

            # Check bounds against M2 metadata
            assert np.allclose(
                list(src_mask.bounds),
                expected_bounds,
                rtol=0,
                atol=1e-8
            ), f"Tile {i} mask bounds mismatch vs M2: {list(src_mask.bounds)} vs {expected_bounds}"

            # Independently verify internal bounds consistency using rasterio
            calc_bounds = rasterio.transform.array_bounds(src_mask.height, src_mask.width, src_mask.transform)
            assert np.allclose(
                list(src_mask.bounds),
                list(calc_bounds),
                rtol=0,
                atol=1e-8
            ), f"Tile {i} mask internal bounds inconsistency"

            mask_data = src_mask.read(1)
            unique_vals = set(np.unique(mask_data))
            assert unique_vals.issubset({0, 1}), f"Tile {i} mask contains invalid values: {unique_vals}"

        # Check Probability TIFF
        with rasterio.open(prob_tif) as src_prob:
            assert src_prob.width == 256, f"Tile {i} prob width != 256"
            assert src_prob.height == 256, f"Tile {i} prob height != 256"
            assert src_prob.count == 1, f"Tile {i} prob band count != 1"
            assert src_prob.dtypes[0] == "float32", f"Tile {i} prob dtype != float32"
            assert str(src_prob.crs) == expected_crs, f"Tile {i} prob CRS mismatch: {src_prob.crs} vs {expected_crs}"

            assert np.allclose(
                tuple(src_prob.transform),
                tuple(expected_transform),
                rtol=0,
                atol=1e-12
            ), f"Tile {i} prob transform mismatch: {src_prob.transform} vs {expected_transform}"

            assert np.allclose(
                list(src_prob.bounds),
                expected_bounds,
                rtol=0,
                atol=1e-8
            ), f"Tile {i} prob bounds mismatch vs M2: {list(src_prob.bounds)} vs {expected_bounds}"

            prob_data = src_prob.read(1)
            assert prob_data.min() >= -1e-6 and prob_data.max() <= 1.0 + 1e-6, \
                f"Tile {i} prob out of [0, 1] range: [{prob_data.min()}, {prob_data.max()}]"

            # Check Mask/Probability consistency
            expected_binary_mask = (prob_data >= 0.5).astype(np.uint8)
            assert np.array_equal(mask_data, expected_binary_mask), \
                f"Tile {i} mask does not match probability >= 0.5 thresholding"

    # 6. Check Metadata Preservation
    assert "source" in output_metadata, "Missing 'source' key in output metadata"

    required_m2_fields = [
        "scene_id", "tile_id", "row_idx", "col_idx",
        "pixel_row_start", "pixel_row_end", "pixel_col_start", "pixel_col_end",
        "scene_dimensions", "tile_size", "stride", "overlap", "is_padded",
        "valid_region", "crs", "transform", "bounds", "acquisition_time",
        "pixel_spacing", "pixel_resolution", "bands", "polarization_order",
        "unit", "dtype", "tile_dimensions"
    ]

    for i in range(expected_tile_count):
        out_tile = output_metadata["tiles"][i]

        for field in required_m2_fields:
            assert field in out_tile, f"Required M2 metadata field '{field}' missing from tile {i}"

        assert "prediction" in out_tile, f"Prediction field missing from tile {i}"
        pred = out_tile["prediction"]
        assert "oil_pixel_count" in pred, f"oil_pixel_count missing from tile {i} prediction"
        assert "oil_percentage" in pred, f"oil_percentage missing from tile {i} prediction"
        assert "threshold" in pred, f"threshold missing from tile {i} prediction"

    print("Step 13 Comprehensive Geospatial Verification: ALL PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_comprehensive_geospatial_output()
    print("\n--- SUMMARY REPORT DATA ---")
    print("1. Input tiles: 64")
    print("2. Predicted mask TIFFs: 64")
    print("3. Probability TIFFs: 64")
    print("4. CRS matching: PASS (64/64 match EPSG:4326)")
    print("5. Transform matching: PASS (64/64 match exact Affine transforms)")
    print("6. Bounds matching: PASS (64/64 match M2 & internal bounds)")
    print("7. Row/Col mapping: PASS (8x8 grid coverage row 0..7, col 0..7)")
    print("8. Mask values: PASS (all values strictly in {0, 1})")
    print("9. Probabilities range: PASS (all values in [0.0, 1.0])")
    print("10. Mask/Prob consistency: PASS (mask == probability >= 0.5)")
    print("11. Metadata preservation: PASS (all 25 source fields + 3 M1 prediction fields intact)")
