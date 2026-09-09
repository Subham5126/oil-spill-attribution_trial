"""
Step 15: Final Production Validation of the M1 API and ZIP Contract.

Tests:
  1. GET  /health                → 200, model_loaded=true
  2. POST /predict               → 200, valid ZIP
  3. POST /predict-tiles         → 200, valid ZIP
  4. Authentication (missing / invalid / correct key)
  5. Input validation (bad extension, bad JSON, bad shape)
  6. ZIP integrity
  7. ZIP path safety
"""

import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import rasterio
import requests
from dotenv import load_dotenv
from rasterio.transform import Affine

# ── Configuration ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("M1_API_KEY")
if not API_KEY:
    sys.exit("FATAL: M1_API_KEY not found in .env")

BASE_URL = os.getenv("M1_API_URL", "http://127.0.0.1:8001")
HEALTH_URL = f"{BASE_URL}/health"
PREDICT_URL = f"{BASE_URL}/predict"
PREDICT_TILES_URL = f"{BASE_URL}/predict-tiles"

TEST_DIR = Path(__file__).parent
OUTPUT_DIR = TEST_DIR / "step15_output"

# ── Counters ─────────────────────────────────────────────────────
_pass = 0
_fail = 0
_results = []


def record(name, passed, detail=""):
    global _pass, _fail
    status = "PASS" if passed else "FAIL"
    if passed:
        _pass += 1
    else:
        _fail += 1
    _results.append((name, status, detail))
    marker = "✓" if passed else "✗"
    print(f"  [{marker}] {name}" + (f"  ({detail})" if detail else ""))


# ── Helpers ──────────────────────────────────────────────────────
def make_mock_tiff(tmp: Path, width=256, height=256, bands=2):
    """Create a minimal 2-band GeoTIFF for /predict testing."""
    tiff_path = tmp / "test_input.tif"
    transform = Affine(
        8.983152841195215e-05, 0.0, 29.198322133239117,
        0.0, -8.983152841195215e-05, 32.63479208299711
    )
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": bands,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
    }
    data = np.random.rand(bands, height, width).astype(np.float32)
    with rasterio.open(tiff_path, "w", **profile) as dst:
        dst.write(data)
    return tiff_path, transform


def make_predict_metadata(tmp: Path):
    """Create metadata JSON for /predict."""
    meta = {
        "scene_id": "step15_validation_scene",
        "tile_id": "step15_tile_0000",
        "crs": "EPSG:4326",
        "transform": [
            8.983152841195215e-05, 0.0, 29.198322133239117,
            0.0, -8.983152841195215e-05, 32.63479208299711
        ],
    }
    meta_path = tmp / "test_metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return meta_path


def make_mock_tiles(tmp: Path, n_tiles=3):
    """Create mock M2 tile array and metadata for /predict-tiles."""
    tiles = np.random.rand(n_tiles, 2, 256, 256).astype(np.float32)
    tiles_path = tmp / "tiles.npy"
    np.save(tiles_path, tiles)

    sample_transform = [
        8.983152841195215e-05, 0.0, 29.198322133239117,
        0.0, -8.983152841195215e-05, 32.63479208299711
    ]
    bounds = [29.198322133239117, 32.611795211723646,
              29.221319004512576, 32.63479208299711]

    metadata = {
        "scene_id": "step15_scene",
        "tile_count": n_tiles,
        "tile_shape": [2, 256, 256],
        "channel_mapping": {"channel_0": "VV", "channel_1": "VH"},
        "tiles": [
            {
                "scene_id": "step15_scene",
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
                "bounds": bounds,
                "acquisition_time": "2016-07-07 04:00:14.019949+00:00",
                "pixel_spacing": [8.983152841195215e-05, 8.983152841195215e-05],
                "pixel_resolution": [8.983152841195215e-05, 8.983152841195215e-05],
                "bands": ["VV", "VH"],
                "polarization_order": ["VV", "VH"],
                "unit": "dB",
                "dtype": "float32",
                "tile_dimensions": [256, 256],
                "index": i
            }
            for i in range(n_tiles)
        ]
    }
    meta_path = tmp / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f)

    return tiles_path, meta_path, metadata


# ── 1. /health ───────────────────────────────────────────────────
def test_health():
    print("\n═══ 1. GET /health ═══")
    try:
        r = requests.get(HEALTH_URL, timeout=10)
        record("/health status code", r.status_code == 200, f"got {r.status_code}")
        body = r.json()
        record("/health status=ok", body.get("status") == "ok", f"got {body.get('status')}")
        record("/health model_loaded=true", body.get("model_loaded") is True,
               f"got {body.get('model_loaded')}")
    except Exception as e:
        record("/health reachable", False, str(e))


# ── 2. /predict ──────────────────────────────────────────────────
def test_predict():
    print("\n═══ 2. POST /predict ═══")
    tmp = Path(tempfile.mkdtemp(prefix="step15_predict_"))
    try:
        tiff_path, expected_transform = make_mock_tiff(tmp)
        meta_path = make_predict_metadata(tmp)

        with open(tiff_path, "rb") as img_f, open(meta_path, "rb") as meta_f:
            r = requests.post(
                PREDICT_URL,
                headers={"X-API-Key": API_KEY},
                files={
                    "image": ("test_input.tif", img_f, "image/tiff"),
                    "metadata": ("test_metadata.json", meta_f, "application/json")
                },
                timeout=60
            )

        record("/predict status code", r.status_code == 200, f"got {r.status_code}")

        if r.status_code != 200:
            record("/predict response", False, r.text[:200])
            return

        zip_path = tmp / "result.zip"
        zip_path.write_bytes(r.content)

        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
            record("/predict ZIP has predicted_mask.tif",
                   "predicted_mask.tif" in names, str(names))
            record("/predict ZIP has probability.tif",
                   "probability.tif" in names, str(names))
            record("/predict ZIP has metadata.json",
                   "metadata.json" in names, str(names))

            # ZIP integrity
            record("/predict ZIP integrity", zf.testzip() is None)

            extract = tmp / "extracted"
            zf.extractall(extract)

        # Mask validation
        mask_path = extract / "predicted_mask.tif"
        with rasterio.open(mask_path) as src:
            record("/predict mask bands=1", src.count == 1, f"got {src.count}")
            record("/predict mask dtype=uint8", src.dtypes[0] == "uint8", f"got {src.dtypes[0]}")
            record("/predict mask CRS=EPSG:4326", str(src.crs) == "EPSG:4326", f"got {src.crs}")
            data = src.read(1)
            unique = set(np.unique(data))
            record("/predict mask values ⊆ {0,1}", unique.issubset({0, 1}), f"got {unique}")

        # Probability validation
        prob_path = extract / "probability.tif"
        with rasterio.open(prob_path) as src:
            record("/predict prob bands=1", src.count == 1, f"got {src.count}")
            record("/predict prob dtype=float32", src.dtypes[0] == "float32", f"got {src.dtypes[0]}")
            record("/predict prob CRS=EPSG:4326", str(src.crs) == "EPSG:4326", f"got {src.crs}")
            data = src.read(1)
            record("/predict prob in [0,1]",
                   float(data.min()) >= -1e-6 and float(data.max()) <= 1.0 + 1e-6,
                   f"[{data.min():.6f}, {data.max():.6f}]")

        # Metadata validation
        with open(extract / "metadata.json", "r") as f:
            meta = json.load(f)
        record("/predict metadata has 'source'", "source" in meta)
        record("/predict metadata has 'prediction'", "prediction" in meta)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 3. /predict-tiles ───────────────────────────────────────────
def test_real_m2_root_list_metadata_format():
    print("\n═══ 3b. POST /predict-tiles with real M2 root-list metadata ═══")
    real_dir = Path(__file__).parent / "real_m2"
    tiles_path = real_dir / "tiles.npy"
    metadata_path = real_dir / "metadata.json"

    assert tiles_path.exists(), f"Missing real M2 tiles file: {tiles_path}"
    assert metadata_path.exists(), f"Missing real M2 metadata file: {metadata_path}"

    with open(tiles_path, "rb") as tf, open(metadata_path, "rb") as mf:
        r = requests.post(
            PREDICT_TILES_URL,
            headers={"X-API-Key": API_KEY},
            files={
                "tiles": (tiles_path.name, tf, "application/octet-stream"),
                "metadata": (metadata_path.name, mf, "application/json")
            },
            timeout=120
        )

    assert r.status_code == 200, f"Real M2 root-list metadata request failed: {r.text}"

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
        mask_files = [n for n in names if n.startswith("predicted_masks/") and n.endswith(".tif")]
        prob_files = [n for n in names if n.startswith("probabilities/") and n.endswith(".tif")]

    assert len(mask_files) == 64, f"Expected 64 mask TIFFs, got {len(mask_files)}"
    assert len(prob_files) == 64, f"Expected 64 probability TIFFs, got {len(prob_files)}"
    assert "metadata.json" in names, "metadata.json missing from ZIP"


def test_predict_tiles():
    print("\n═══ 3. POST /predict-tiles ═══")
    tmp = Path(tempfile.mkdtemp(prefix="step15_tiles_"))
    N = 3
    try:
        tiles_path, meta_path, input_meta = make_mock_tiles(tmp, n_tiles=N)

        with open(tiles_path, "rb") as tf, open(meta_path, "rb") as mf:
            r = requests.post(
                PREDICT_TILES_URL,
                headers={"X-API-Key": API_KEY},
                files={
                    "tiles": ("tiles.npy", tf, "application/octet-stream"),
                    "metadata": ("metadata.json", mf, "application/json")
                },
                timeout=60
            )

        record("/predict-tiles status code", r.status_code == 200, f"got {r.status_code}")

        if r.status_code != 200:
            record("/predict-tiles response", False, r.text[:200])
            return

        zip_path = tmp / "result.zip"
        zip_path.write_bytes(r.content)

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()

            mask_files = [n for n in names if n.startswith("predicted_masks/") and n.endswith(".tif")]
            prob_files = [n for n in names if n.startswith("probabilities/") and n.endswith(".tif")]

            record(f"/predict-tiles {N} mask TIFFs", len(mask_files) == N,
                   f"got {len(mask_files)}")
            record(f"/predict-tiles {N} prob TIFFs", len(prob_files) == N,
                   f"got {len(prob_files)}")
            record("/predict-tiles metadata.json in ZIP", "metadata.json" in names)

            # ZIP integrity
            record("/predict-tiles ZIP integrity", zf.testzip() is None)

            extract = tmp / "extracted"
            zf.extractall(extract)

        # Per-tile GeoTIFF validation
        expected_transform = Affine(*input_meta["tiles"][0]["transform"])

        all_tiles_ok = True
        for i in range(N):
            tid = f"tile_{i:04d}"
            mask_tif = extract / "predicted_masks" / f"{tid}.tif"
            prob_tif = extract / "probabilities" / f"{tid}.tif"

            if not mask_tif.exists() or not prob_tif.exists():
                record(f"  tile {i} files exist", False)
                all_tiles_ok = False
                continue

            with rasterio.open(mask_tif) as src:
                ok = (src.width == 256 and src.height == 256
                      and src.count == 1 and src.dtypes[0] == "uint8"
                      and str(src.crs) == "EPSG:4326"
                      and src.transform == expected_transform)
                mask_data = src.read(1)
                ok = ok and set(np.unique(mask_data)).issubset({0, 1})

            with rasterio.open(prob_tif) as src:
                ok2 = (src.width == 256 and src.height == 256
                       and src.count == 1 and src.dtypes[0] == "float32"
                       and str(src.crs) == "EPSG:4326"
                       and src.transform == expected_transform)
                prob_data = src.read(1)
                ok2 = ok2 and float(prob_data.min()) >= -1e-6 and float(prob_data.max()) <= 1.0 + 1e-6

                # mask == (prob >= 0.5)
                expected_mask = (prob_data >= 0.5).astype(np.uint8)
                ok2 = ok2 and np.array_equal(mask_data, expected_mask)

            if not (ok and ok2):
                all_tiles_ok = False

        record("/predict-tiles all tile GeoTIFFs valid", all_tiles_ok)

        # Metadata preservation
        with open(extract / "metadata.json", "r") as f:
            out_meta = json.load(f)
        record("/predict-tiles output has 'source'", "source" in out_meta)
        record("/predict-tiles output has 'tiles'", "tiles" in out_meta)
        if "tiles" in out_meta:
            m2_fields = [
                "scene_id", "tile_id", "row_idx", "col_idx",
                "crs", "transform", "bounds", "acquisition_time"
            ]
            fields_ok = all(
                all(f in t for f in m2_fields)
                for t in out_meta["tiles"]
            )
            record("/predict-tiles M2 metadata preserved", fields_ok)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 4. Authentication ───────────────────────────────────────────
def test_authentication():
    print("\n═══ 4. Authentication ═══")
    tmp = Path(tempfile.mkdtemp(prefix="step15_auth_"))
    try:
        tiles_path, meta_path, _ = make_mock_tiles(tmp, n_tiles=1)

        def post_tiles(api_key_header):
            with open(tiles_path, "rb") as tf, open(meta_path, "rb") as mf:
                return requests.post(
                    PREDICT_TILES_URL,
                    headers=api_key_header,
                    files={
                        "tiles": ("tiles.npy", tf, "application/octet-stream"),
                        "metadata": ("metadata.json", mf, "application/json")
                    },
                    timeout=30
                )

        # Missing key
        r = post_tiles({})
        record("Missing API key → 401", r.status_code == 401, f"got {r.status_code}")

        # Invalid key
        r = post_tiles({"X-API-Key": "wrong_key_12345"})
        record("Invalid API key → 401", r.status_code == 401, f"got {r.status_code}")

        # Correct key
        r = post_tiles({"X-API-Key": API_KEY})
        record("Correct API key → 200", r.status_code == 200, f"got {r.status_code}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 5. Input validation ─────────────────────────────────────────
def test_input_validation():
    print("\n═══ 5. Input Validation ═══")
    headers = {"X-API-Key": API_KEY}
    tmp = Path(tempfile.mkdtemp(prefix="step15_inputval_"))
    try:
        _, meta_path, _ = make_mock_tiles(tmp, n_tiles=2)

        # 5a. Invalid tile extension (.csv instead of .npy)
        fake_csv = tmp / "bad.csv"
        fake_csv.write_text("not a numpy file")
        with open(fake_csv, "rb") as tf, open(meta_path, "rb") as mf:
            r = requests.post(PREDICT_TILES_URL, headers=headers, files={
                "tiles": ("tiles.csv", tf, "application/octet-stream"),
                "metadata": ("metadata.json", mf, "application/json")
            }, timeout=30)
        record("Invalid tile extension → 400", r.status_code == 400, f"got {r.status_code}")

        # 5b. Invalid metadata extension (.xml instead of .json)
        tiles_path, _, _ = make_mock_tiles(tmp, n_tiles=2)
        fake_xml = tmp / "bad.xml"
        fake_xml.write_text("<xml/>")
        with open(tiles_path, "rb") as tf, open(fake_xml, "rb") as mf:
            r = requests.post(PREDICT_TILES_URL, headers=headers, files={
                "tiles": ("tiles.npy", tf, "application/octet-stream"),
                "metadata": ("metadata.xml", mf, "application/json")
            }, timeout=30)
        record("Invalid metadata extension → 400", r.status_code == 400, f"got {r.status_code}")

        # 5c. Invalid JSON content
        bad_json = tmp / "bad.json"
        bad_json.write_text("{not valid json!!")
        with open(tiles_path, "rb") as tf, open(bad_json, "rb") as mf:
            r = requests.post(PREDICT_TILES_URL, headers=headers, files={
                "tiles": ("tiles.npy", tf, "application/octet-stream"),
                "metadata": ("bad.json", mf, "application/json")
            }, timeout=30)
        record("Invalid JSON content → 400", r.status_code == 400, f"got {r.status_code}")

        # 5d. Wrong tile shape: (2, 256, 256) — missing batch dim
        bad_tiles_3d = np.random.rand(2, 256, 256).astype(np.float32)
        bad_path = tmp / "bad_3d.npy"
        np.save(bad_path, bad_tiles_3d)
        with open(bad_path, "rb") as tf, open(meta_path, "rb") as mf:
            r = requests.post(PREDICT_TILES_URL, headers=headers, files={
                "tiles": ("bad_3d.npy", tf, "application/octet-stream"),
                "metadata": ("metadata.json", mf, "application/json")
            }, timeout=30)
        record("Shape (2,256,256) → 400", r.status_code == 400, f"got {r.status_code}")

        # 5e. Wrong channels: (N, 3, 256, 256)
        bad_tiles_3ch = np.random.rand(2, 3, 256, 256).astype(np.float32)
        bad_path2 = tmp / "bad_3ch.npy"
        np.save(bad_path2, bad_tiles_3ch)
        with open(bad_path2, "rb") as tf, open(meta_path, "rb") as mf:
            r = requests.post(PREDICT_TILES_URL, headers=headers, files={
                "tiles": ("bad_3ch.npy", tf, "application/octet-stream"),
                "metadata": ("metadata.json", mf, "application/json")
            }, timeout=30)
        record("Shape (N,3,256,256) → 400", r.status_code == 400, f"got {r.status_code}")

        # 5f. Wrong tile size: (N, 2, 128, 128)
        bad_tiles_128 = np.random.rand(2, 2, 128, 128).astype(np.float32)
        bad_path3 = tmp / "bad_128.npy"
        np.save(bad_path3, bad_tiles_128)
        with open(bad_path3, "rb") as tf, open(meta_path, "rb") as mf:
            r = requests.post(PREDICT_TILES_URL, headers=headers, files={
                "tiles": ("bad_128.npy", tf, "application/octet-stream"),
                "metadata": ("metadata.json", mf, "application/json")
            }, timeout=30)
        record("Shape (N,2,128,128) → 400", r.status_code == 400, f"got {r.status_code}")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 6. ZIP integrity (dedicated) ────────────────────────────────
def test_zip_integrity():
    print("\n═══ 6. ZIP Integrity ═══")
    tmp = Path(tempfile.mkdtemp(prefix="step15_zipint_"))
    try:
        tiles_path, meta_path, _ = make_mock_tiles(tmp, n_tiles=2)

        with open(tiles_path, "rb") as tf, open(meta_path, "rb") as mf:
            r = requests.post(
                PREDICT_TILES_URL,
                headers={"X-API-Key": API_KEY},
                files={
                    "tiles": ("tiles.npy", tf, "application/octet-stream"),
                    "metadata": ("metadata.json", mf, "application/json")
                },
                timeout=60
            )

        if r.status_code != 200:
            record("ZIP integrity test (tiles)", False, f"HTTP {r.status_code}")
            return

        zip_bytes = io.BytesIO(r.content)
        with zipfile.ZipFile(zip_bytes) as zf:
            bad = zf.testzip()
            record("ZIP testzip() is None (no corruption)", bad is None,
                   f"corrupted member: {bad}" if bad else "")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 7. ZIP path safety ──────────────────────────────────────────
def test_zip_path_safety():
    print("\n═══ 7. ZIP Path Safety ═══")
    tmp = Path(tempfile.mkdtemp(prefix="step15_zipsafe_"))
    try:
        tiles_path, meta_path, _ = make_mock_tiles(tmp, n_tiles=2)

        with open(tiles_path, "rb") as tf, open(meta_path, "rb") as mf:
            r = requests.post(
                PREDICT_TILES_URL,
                headers={"X-API-Key": API_KEY},
                files={
                    "tiles": ("tiles.npy", tf, "application/octet-stream"),
                    "metadata": ("metadata.json", mf, "application/json")
                },
                timeout=60
            )

        if r.status_code != 200:
            record("ZIP path safety test", False, f"HTTP {r.status_code}")
            return

        zip_bytes = io.BytesIO(r.content)
        allowed_prefixes = ("predicted_masks/", "probabilities/", "metadata.json")

        with zipfile.ZipFile(zip_bytes) as zf:
            names = zf.namelist()
            no_traversal = all(".." not in n for n in names)
            no_absolute = all(not n.startswith("/") and not n.startswith("\\") for n in names)
            all_expected = all(
                n.startswith(allowed_prefixes) for n in names
            )

            record("No path traversal (..)", no_traversal, str(names))
            record("No absolute paths", no_absolute, str(names))
            record("All paths are expected", all_expected, str(names))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Main ─────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  STEP 15: M1 API Production Validation")
    print("=" * 60)

    test_health()
    test_predict()
    test_predict_tiles()
    test_authentication()
    test_input_validation()
    test_zip_integrity()
    test_zip_path_safety()

    print("\n" + "=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)
    for name, status, detail in _results:
        marker = "✓" if status == "PASS" else "✗"
        line = f"  [{marker}] {status}: {name}"
        if detail:
            line += f"  — {detail}"
        print(line)

    print(f"\n  Total: {_pass + _fail}   Passed: {_pass}   Failed: {_fail}")
    print()
    if _fail == 0:
        print("  M1 API production validation: PASS")
    else:
        print("  M1 API production validation: FAIL")
    print("  Real M2 integration: NOT RUN — real M2 files unavailable")
    print("=" * 60)

    sys.exit(1 if _fail > 0 else 0)


if __name__ == "__main__":
    main()
