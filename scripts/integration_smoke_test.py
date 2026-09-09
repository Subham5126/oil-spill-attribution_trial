import json
from pathlib import Path
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import rasterio
from rasterio.transform import Affine

from satellite.sentinel1.pipeline import run_sentinel1_pipeline
from satellite.preprocessing.m1_client import M1Client

DEFAULT_TIFF = r"D:\sih_26_info\Oil\00009.tif"
BASE_OUTPUT_DIR = Path("data/processed/m1_smoke_test")


def main():
    if len(sys.argv) > 1 and sys.argv[1].strip():
        input_image = Path(sys.argv[1].strip())
    else:
        input_image = Path(DEFAULT_TIFF)

    print(f"Input image: {input_image}")

    if not input_image.exists():
        print(f"Error: Input TIFF file does not exist: {input_image}", file=sys.stderr)
        sys.exit(1)

    output_dir = BASE_OUTPUT_DIR / input_image.stem
    if output_dir.exists():
        shutil.rmtree(output_dir)

    print("\n--- Step 1: Running M2 Sentinel-1 Pipeline ---")
    pipeline_result = run_sentinel1_pipeline(str(input_image))

    print(f"Batch images shape: {pipeline_result.batch_images.shape}")
    print(f"Batch images dtype: {pipeline_result.batch_images.dtype}")
    print(f"Number of metadata records: {len(pipeline_result.batch_metadata)}")

    assert pipeline_result.batch_images.shape == (64, 2, 256, 256)
    assert pipeline_result.batch_images.dtype.name == "float32"
    assert len(pipeline_result.batch_metadata) == 64

    first_m2_tile_id = pipeline_result.batch_metadata[0]["tile_id"]
    print(f"First M2 tile_id: {first_m2_tile_id}")

    print("\n--- Step 2: Sending M2 batch to M1 U-Net Inference via M1Client ---")
    client = M1Client()
    print(f"Client endpoint: {client.endpoint_url}")

    inference_result = client.predict_pipeline_result(
        pipeline_result,
        output_dir=output_dir,
        extract=True,
    )

    print(f"HTTP Status: {inference_result.status_code}")
    print(f"ZIP path: {inference_result.zip_path}")
    print(f"Extracted dir: {inference_result.extracted_dir}")
    print(f"Total tiles sent: {inference_result.num_tiles}")
    print(f"Total masks received: {inference_result.num_masks}")
    print(f"Total probabilities received: {inference_result.num_probabilities}")

    assert inference_result.status_code == 200
    assert inference_result.num_tiles == 64
    assert inference_result.num_masks == 64
    assert inference_result.num_probabilities == 64

    print("\n--- Step 3: Verifying Original Tile ID Preservation ---")
    m2_tile_ids = [m["tile_id"] for m in pipeline_result.batch_metadata]
    assert inference_result.tile_ids == m2_tile_ids, "Tile IDs mismatch!"

    for tid in m2_tile_ids:
        assert tid in inference_result.predicted_mask_paths, f"Missing mask for tile_id: {tid}"
        assert tid in inference_result.probability_paths, f"Missing probability for tile_id: {tid}"
        mask_path = inference_result.predicted_mask_paths[tid]
        prob_path = inference_result.probability_paths[tid]
        assert mask_path.exists(), f"Mask file does not exist: {mask_path}"
        assert prob_path.exists(), f"Probability file does not exist: {prob_path}"

    print("All 64 original M2 tile IDs preserved and matched perfectly!")

    print("\n--- Step 4: Verifying GeoTIFF Geospatial Attributes ---")
    sample_mask_path = inference_result.predicted_mask_paths[first_m2_tile_id]
    sample_meta = pipeline_result.batch_metadata[0]

    with rasterio.open(sample_mask_path) as src:
        print(f"Mask dimensions: {src.width}x{src.height}, count: {src.count}, dtype: {src.dtypes[0]}")
        print(f"Mask CRS: {src.crs}")
        print(f"Mask Transform: {src.transform}")
        assert src.width == 256
        assert src.height == 256
        assert src.count == 1
        assert src.dtypes[0] == "uint8"
        assert str(src.crs) == sample_meta["crs"]
        expected_transform = Affine(*sample_meta["transform"])
        assert src.transform == expected_transform

    sample_prob_path = inference_result.probability_paths[first_m2_tile_id]
    with rasterio.open(sample_prob_path) as src:
        print(f"Prob dimensions: {src.width}x{src.height}, count: {src.count}, dtype: {src.dtypes[0]}")
        assert src.dtypes[0] == "float32"
        assert str(src.crs) == sample_meta["crs"]

    print("\n--- Step 5: Prediction Statistics across ALL Probability Tiles ---")
    assert "tiles" in inference_result.metadata
    print(f"Metadata tile records count: {len(inference_result.metadata['tiles'])}")

    prob_dir = inference_result.extracted_dir / "probabilities"
    discovered_prob_files = sorted(list(prob_dir.glob("*.tif")))
    num_prob_files = len(discovered_prob_files)

    expected_tile_ids = set(m2_tile_ids)
    discovered_tile_ids = {p.stem for p in discovered_prob_files}

    if num_prob_files != len(m2_tile_ids) or discovered_tile_ids != expected_tile_ids:
        missing = expected_tile_ids - discovered_tile_ids
        unexpected = discovered_tile_ids - expected_tile_ids
        print(
            f"Error: Probability TIFF count mismatch! Expected {len(m2_tile_ids)}, found {num_prob_files}",
            file=sys.stderr,
        )
        if missing:
            print(f"Missing tile IDs: {sorted(list(missing))}", file=sys.stderr)
        if unexpected:
            print(f"Unexpected tile IDs: {sorted(list(unexpected))}", file=sys.stderr)
        sys.exit(1)

    all_probs = []
    tile_stats = []

    for prob_file in discovered_prob_files:
        with rasterio.open(prob_file) as src:
            arr = src.read(1)
        all_probs.append(arr)
        max_p = float(arr.max())
        oil_px = int(np.sum(arr >= 0.5))
        tile_stats.append({
            "filename": prob_file.name,
            "tile_id": prob_file.stem,
            "max_prob": max_p,
            "oil_pixels": oil_px,
        })

    stacked_probs = np.stack(all_probs)
    total_pixels = stacked_probs.size
    px_ge_01 = int(np.sum(stacked_probs >= 0.1))
    px_ge_03 = int(np.sum(stacked_probs >= 0.3))
    px_ge_05 = int(np.sum(stacked_probs >= 0.5))
    px_ge_07 = int(np.sum(stacked_probs >= 0.7))
    global_oil_pct = (px_ge_05 / total_pixels) * 100
    tiles_with_oil = sum(1 for t in tile_stats if t["oil_pixels"] > 0)

    print("Step 5: Prediction statistics")
    print(f"Probability tiles: {num_prob_files}")
    print(f"Total pixels: {total_pixels}")
    print(f"Global min: {float(stacked_probs.min()):.7f}")
    print(f"Global max: {float(stacked_probs.max()):.7f}")
    print(f"Global mean: {float(stacked_probs.mean()):.7f}")
    print(f"Pixels >= 0.1: {px_ge_01}")
    print(f"Pixels >= 0.3: {px_ge_03}")
    print(f"Pixels >= 0.5: {px_ge_05}")
    print(f"Pixels >= 0.7: {px_ge_07}")
    print(f"Global oil percentage: {global_oil_pct:.4f}%")
    print(f"Tiles with >=0.5 prediction: {tiles_with_oil}")

    top_tile = max(tile_stats, key=lambda t: t["max_prob"])
    first_tile = tile_stats[0]
    print(f"\nSample tile (first tile - single tile only, not overall scene):")
    print(f"  File: {first_tile['filename']}")
    print(f"  Max probability: {first_tile['max_prob']:.6f}")
    print(f"  Pixels >= 0.5: {first_tile['oil_pixels']}")

    if top_tile["oil_pixels"] > 0:
        print(f"\nPeak oil detection tile (single tile with highest activation):")
        print(f"  File: {top_tile['filename']}")
        print(f"  Max probability: {top_tile['max_prob']:.6f}")
        print(f"  Pixels >= 0.5: {top_tile['oil_pixels']}")

    print("\n>>> SMOKE TEST PASSED COMPLETELY! <<<")


if __name__ == "__main__":
    main()
