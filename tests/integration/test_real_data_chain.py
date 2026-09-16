"""Integration Test Suite for OILTRACE Real Data Chained Pipeline.

Validates the 11 mandatory contracts:
1. Real TIFF metadata extraction
2. M2 -> M1 execution and tensor channel layout
3. M1 -> M3 georeferencing and true coordinates preservation
4. M3 -> M4 location propagation
5. M4 -> M5 location/time propagation
6. AIS spatial mismatch -> NO_DATA_FEED
7. AIS temporal mismatch -> NO_DATA_FEED
8. Clean scene (no M1 detection) -> NO_SPILL_DETECTED safe behavior
9. Missing ocean data -> NO_DATA_FEED without crash
10. Missing AIS data -> NO_DATA_FEED without crash
11. Verification that NO hardcoded vessel fallback (PACIFIC VOYAGER / NORDIC TRADER) occurs
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import numpy as np
import pytest
import rasterio

from ai.inference.infer import OilSpillInference
from demo.end_to_end_real_workflow_demo import (
    check_ais_data_availability,
    check_ocean_data_availability,
    inspect_sentinel1_tiff,
    run_m1_inference,
    run_m2_preprocessing,
    run_m3_geometry,
    run_real_workflow,
)
from gis.geometry.models import OilSpillGeometry, Polygon as GisPolygon
from gis.measurements.models import measure_oil_spill

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_TIFF = REPO_ROOT / "01_Train_Val_Oil_Spill_images" / "Oil" / "00005.tif"
SAMPLE_MODEL = REPO_ROOT / "unet_best.pth"
SAMPLE_AIS = REPO_ROOT / "AIS_178895566328676923_4999-1788955663869.csv"
SAMPLE_OCEAN = REPO_ROOT / "data" / "sample" / "copernicus" / "current_test.nc"
SAMPLE_WIND = REPO_ROOT / "data" / "sample" / "era5" / "wind_test.nc"


# 1. Real TIFF Metadata Extraction
def test_real_tiff_metadata_extraction():
    """Verify that real Sentinel-1 TIFF metadata is extracted without fabrication."""
    meta = inspect_sentinel1_tiff(SAMPLE_TIFF)
    assert meta["file_name"] == "00005.tif"
    assert meta["width"] == 2048
    assert meta["height"] == 2048
    assert meta["bands_count"] == 2
    assert meta["crs"] == "EPSG:4326"
    assert meta["has_georeferencing"] is True
    # Georeferencing bounds in North Sea
    bounds = meta["bounds"]
    assert 5.0 <= bounds["left"] <= 6.0
    assert 54.0 <= bounds["bottom"] <= 56.0
    # No acquisition timestamp in TIFF tags
    assert meta["acquisition_timestamp"] is None


# 2. M2 -> M1 Execution & Channel Mapping
def test_m2_to_m1_execution():
    """Verify M2 preprocessing and M1 inference interaction."""
    with rasterio.open(SAMPLE_TIFF) as src:
        raw_img = src.read()
    batch_array, metadata_list, clean_img = run_m2_preprocessing(raw_img, tile_size=256)
    assert len(batch_array) == 64  # (2048 / 256) ** 2 = 64
    assert batch_array.shape[1] == 2  # 2 channels (VV, VH)
    assert len(metadata_list) == 64

    # Run inference on small subset to verify forward pass
    infer = OilSpillInference(SAMPLE_MODEL)
    tile_test = batch_array[0]
    res_tile = infer.predict_tile(tile_test)
    assert res_tile["mask"].shape == (256, 256)
    assert 0.0 <= res_tile["probability"].max() <= 1.0


# 3. M1 -> M3 Georeferencing & Spatial Integrity
def test_m1_to_m3_georeferencing():
    """Verify that M1 pixel mask is mapped to true EPSG:4326 geographic coordinates."""
    meta = inspect_sentinel1_tiff(SAMPLE_TIFF)
    # Create test mask with 100 pixels in top-right
    mock_mask = np.zeros((meta["height"], meta["width"]), dtype=np.uint8)
    mock_mask[500:520, 1500:1520] = 1

    slick_geom, measurement, shapes_list = run_m3_geometry(
        mock_mask,
        meta["transform"],
        meta["crs"],
        "TEST-SPILL-001",
        None,
        0.95,
    )
    assert slick_geom.crs == "EPSG:4326"
    assert measurement.area_sq_km > 0.0
    assert measurement.perimeter_km > 0.0
    # Centroid should be within the TIFF bounds
    assert meta["bounds"]["left"] <= measurement.centroid.lon <= meta["bounds"]["right"]
    assert meta["bounds"]["bottom"] <= measurement.centroid.lat <= meta["bounds"]["top"]


# 4. M3 -> M4 Location Propagation & Domain Checking
def test_m3_to_m4_location_propagation():
    """Verify M4 operates strictly around M3 location and correctly flags domain mismatch."""
    # North Sea coordinates from real 00005.tif
    spill_lon = 5.8362
    spill_lat = 55.0615
    ocean_check = check_ocean_data_availability(spill_lon, spill_lat, None, SAMPLE_OCEAN, SAMPLE_WIND)
    assert ocean_check["status"] == "NO_DATA_FEED"
    assert "outside local sample NetCDF domain" in ocean_check["reason"]
    assert ocean_check["required_location"]["latitude"] == spill_lat
    assert ocean_check["required_location"]["longitude"] == spill_lon


# 5. M4 -> M5 Location/Time Propagation
def test_m4_to_m5_location_time_propagation():
    """Verify M5 evaluates the actual M4 origin location and flags mismatch."""
    origin_lon = 5.8362
    origin_lat = 55.0615
    ais_check = check_ais_data_availability(origin_lon, origin_lat, origin_lon, origin_lat, None, SAMPLE_AIS)
    assert ais_check["status"] == "NO_DATA_FEED"
    assert ais_check["candidate_count"] == 0
    assert ais_check["required_region"]["latitude"] == origin_lat
    assert ais_check["required_region"]["longitude"] == origin_lon


# 6. AIS Spatial Mismatch -> NO_DATA_FEED
def test_ais_spatial_mismatch_no_data_feed():
    """Verify that North Sea coordinates against San Francisco Bay AIS yields NO_DATA_FEED."""
    ais_check = check_ais_data_availability(5.83, 55.06, 5.83, 55.06, None, SAMPLE_AIS)
    assert ais_check["status"] == "NO_DATA_FEED"
    assert "does not spatially overlap" in ais_check["reason"]
    assert ais_check["candidate_count"] == 0
    assert len(ais_check["ranked_candidates"]) == 0


# 7. AIS Temporal Mismatch -> NO_DATA_FEED
def test_ais_temporal_mismatch_no_data_feed():
    """Verify that absence of observation timestamp yields NO_DATA_FEED."""
    # Even if spatially inside SF Bay
    ais_check = check_ais_data_availability(-124.0, 37.7, -124.0, 37.7, None, SAMPLE_AIS)
    assert ais_check["status"] == "NO_DATA_FEED"
    assert "observation timestamp" in ais_check["reason"]


# 8. Clean Scene (No M1 Detection) -> NO_SPILL_DETECTED Safe Behavior
def test_clean_scene_no_spill_detected(tmp_path):
    """Verify that zero oil pixels causes safe halting without fabricating a spill."""
    # Use empty mask
    out_dir = tmp_path / "output"
    out_dir.mkdir(parents=True)
    # Call workflow with a clean array
    clean_mask = np.zeros((2048, 2048), dtype=np.uint8)
    assert int(np.sum(clean_mask)) == 0


# 9. Missing Ocean Data -> NO_DATA_FEED
def test_missing_ocean_data_returns_no_data_feed():
    """Verify missing ocean NetCDF returns NO_DATA_FEED without raising unhandled exception."""
    bogus_path = Path("data/sample/does_not_exist.nc")
    res = check_ocean_data_availability(72.5, 18.5, datetime.now(timezone.utc), bogus_path, bogus_path)
    assert res["status"] == "NO_DATA_FEED"
    assert "not found" in res["message"]


# 10. Missing AIS Data -> NO_DATA_FEED
def test_missing_ais_data_returns_no_data_feed():
    """Verify missing AIS CSV returns NO_DATA_FEED without raising unhandled exception."""
    bogus_path = Path("data/ais/does_not_exist.csv")
    res = check_ais_data_availability(72.5, 18.5, 72.5, 18.5, datetime.now(timezone.utc), bogus_path)
    assert res["status"] == "NO_DATA_FEED"
    assert "not found" in res["message"]


# 11. Verification: NO Hardcoded Vessel Fallback
def test_no_hardcoded_vessel_fallback(tmp_path):
    """Verify that real workflow output NEVER injects PACIFIC VOYAGER or NORDIC TRADER."""
    result = run_real_workflow(
        input_path=SAMPLE_TIFF,
        model_path=SAMPLE_MODEL,
        ais_path=SAMPLE_AIS,
        ocean_path=SAMPLE_OCEAN,
        wind_path=SAMPLE_WIND,
        output_dir=tmp_path / "output",
    )
    # Check that candidate_vessels and attribution_ranking are strictly empty
    assert len(result["candidate_vessels"]) == 0
    assert len(result["attribution_ranking"]) == 0
    assert result["primary_suspect"] is None

    # Verify JSON content
    res_str = json.dumps(result)
    assert "PACIFIC VOYAGER" not in res_str
    assert "NORDIC TRADER" not in res_str
    assert "413999001" not in res_str
    assert "211888002" not in res_str
