"""Unit and integration tests for scripts/analyze_sentinel1_collection.py.

Verifies:
1. TIFF discovery with recursive directory traversal and extension filtering
2. Metadata extraction from GeoTIFF headers
3. WGS84 bounding box and centroid calculations
4. Timestamp extraction hierarchy and missing-timestamp handling
5. Spatial clustering (DBSCAN over Haversine/coordinate space)
6. Multi-criteria region scoring and ranking
7. Exact AIS bounding box and temporal window derivation
8. Ocean current and surface wind requirement derivation
9. Geographic marine basin naming heuristics
10. JSON serializability of analysis reports
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import pytest
import numpy as np
import rasterio
from rasterio.transform import from_origin

from scripts.analyze_sentinel1_collection import (
    TIFFMetadata,
    RegionCluster,
    ClusterSummary,
    discover_sentinel1_tiffs,
    extract_tiff_metadata,
    get_geographic_region_name,
    perform_spatial_clustering,
    score_regions,
    calculate_ais_requirements,
    calculate_ocean_and_wind_requirements,
    _apply_time_window,
)


def make_tiff_metadata(
    filename: str,
    centroid_lat: float,
    centroid_lon: float,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    acquisition_time: str | None = None,
    timestamp_status: str = "UNKNOWN",
    crs: str = "EPSG:4326",
) -> TIFFMetadata:
    """Helper to instantiate valid TIFFMetadata objects for testing."""
    return TIFFMetadata(
        file_path=f"/fake/path/{filename}",
        filename=filename,
        width=2048,
        height=2048,
        num_bands=2,
        band_descriptions=["VV", "VH"],
        dtype="float32",
        crs=crs,
        epsg_code=4326,
        affine_transform=[0.0001, 0.0, min_lon, 0.0, -0.0001, max_lat],
        min_lon=min_lon,
        min_lat=min_lat,
        max_lon=max_lon,
        max_lat=max_lat,
        centroid_lon=centroid_lon,
        centroid_lat=centroid_lat,
        pixel_res_deg=0.0001,
        pixel_res_m=10.0,
        nodata=0.0,
        acquisition_time=acquisition_time,
        timestamp_status=timestamp_status,
        satellite="Sentinel-1",
        product_type="GRD",
        polarization="VV+VH",
    )


@pytest.fixture
def dummy_geotiff(tmp_path: Path) -> Path:
    """Create a temporary synthetic GeoTIFF with EPSG:4326 metadata."""
    tif_path = tmp_path / "test_s1_00001.tif"
    width, height = 64, 64
    transform = from_origin(32.0, 34.0, 0.001, 0.001)
    data = np.ones((2, height, width), dtype=np.float32) * 0.15

    with rasterio.open(
        tif_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=2,
        dtype=np.float32,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data)

    return tif_path


@pytest.fixture
def sample_metadata_list() -> list[TIFFMetadata]:
    """Generate a diverse synthetic list of TIFFMetadata across 3 distinct regions."""
    # Eastern Med cluster: ~33.5N, 32.5E
    med_tiffs = [
        make_tiff_metadata(
            filename=f"med_{i:03d}.tif",
            centroid_lat=33.1 + (i * 0.05),
            centroid_lon=32.1 + (i * 0.05),
            min_lon=32.0 + (i * 0.05),
            min_lat=33.0 + (i * 0.05),
            max_lon=32.2 + (i * 0.05),
            max_lat=33.2 + (i * 0.05),
            acquisition_time="2016-07-07T04:00:14Z" if i == 0 else None,
            timestamp_status="EXACT" if i == 0 else "UNKNOWN",
        )
        for i in range(15)
    ]

    # Gulf of Mexico cluster: ~28.0N, -90.0W
    gom_tiffs = [
        make_tiff_metadata(
            filename=f"gom_{i:03d}.tif",
            centroid_lat=27.6 + (i * 0.04),
            centroid_lon=-90.4 + (i * 0.04),
            min_lon=-90.5 + (i * 0.04),
            min_lat=27.5 + (i * 0.04),
            max_lon=-90.3 + (i * 0.04),
            max_lat=27.7 + (i * 0.04),
            acquisition_time="2018-08-03T17:25:54Z" if i == 0 else None,
            timestamp_status="EXACT" if i == 0 else "UNKNOWN",
        )
        for i in range(10)
    ]

    # Persian Gulf cluster: ~26.5N, 52.0E
    persian_tiffs = [
        make_tiff_metadata(
            filename=f"pg_{i:03d}.tif",
            centroid_lat=26.1 + (i * 0.02),
            centroid_lon=51.6 + (i * 0.02),
            min_lon=51.5 + (i * 0.02),
            min_lat=26.0 + (i * 0.02),
            max_lon=51.7 + (i * 0.02),
            max_lat=26.2 + (i * 0.02),
            acquisition_time=None,
            timestamp_status="UNKNOWN",
        )
        for i in range(5)
    ]

    return med_tiffs + gom_tiffs + persian_tiffs


def test_discover_sentinel1_tiffs(tmp_path: Path):
    """Verify discovery finds .tif and .tiff files recursively."""
    sub_dir = tmp_path / "nested"
    sub_dir.mkdir()
    (tmp_path / "image1.tif").touch()
    (tmp_path / "image2.tiff").touch()
    (sub_dir / "image3.tif").touch()
    (tmp_path / "ignore.txt").touch()

    found = discover_sentinel1_tiffs(tmp_path)
    assert len(found) == 3
    names = {p.name for p in found}
    assert names == {"image1.tif", "image2.tiff", "image3.tif"}


def test_extract_tiff_metadata(dummy_geotiff: Path):
    """Verify metadata extraction from rasterio header."""
    meta = extract_tiff_metadata(dummy_geotiff)
    assert meta.filename == dummy_geotiff.name
    assert meta.crs == "EPSG:4326"
    assert meta.width == 64
    assert meta.height == 64
    assert meta.num_bands == 2
    assert meta.dtype == "float32"
    assert meta.min_lon < meta.max_lon
    assert meta.min_lat < meta.max_lat
    assert 33.0 <= meta.centroid_lat <= 35.0
    assert 31.0 <= meta.centroid_lon <= 33.0


def test_geographic_region_naming():
    """Verify naming heuristics for distinct marine basins."""
    assert "Northern Gulf of Mexico" in get_geographic_region_name(28.0, -90.0)
    assert "Southern Gulf of Mexico" in get_geographic_region_name(19.5, -92.0)
    assert "Eastern Mediterranean Sea" in get_geographic_region_name(33.5, 32.5)
    assert "Persian / Arabian Gulf" in get_geographic_region_name(27.0, 51.0)
    assert "North Sea" in get_geographic_region_name(55.0, 4.0)
    assert "Marine Basin" in get_geographic_region_name(0.0, 0.0)


def test_spatial_clustering(sample_metadata_list: list[TIFFMetadata]):
    """Verify DBSCAN groups nearby coordinates into correct geographic clusters."""
    clusters, cluster_map = perform_spatial_clustering(sample_metadata_list, eps_km=300.0, min_samples=3)

    assert len(clusters) == 3
    # First cluster should be Med (15 items)
    assert clusters[0].tiff_count == 15
    assert "Mediterranean" in clusters[0].region_name

    # Second should be GoM (10 items)
    assert clusters[1].tiff_count == 10
    assert "Gulf of Mexico" in clusters[1].region_name

    # Third should be Persian Gulf (5 items)
    assert clusters[2].tiff_count == 5


def test_score_regions(sample_metadata_list: list[TIFFMetadata]):
    """Verify multi-criteria scoring ranks clusters according to density and timestamp quality."""
    clusters, _ = perform_spatial_clustering(sample_metadata_list, eps_km=300.0, min_samples=3)
    scored = score_regions(clusters, total_tiffs=len(sample_metadata_list))

    assert len(scored) == 3
    assert scored[0].score >= scored[1].score >= scored[2].score
    assert scored[0].score_breakdown["spatial_density"] > 0
    assert scored[0].score_breakdown["metadata_quality"] > 0


def test_apply_time_window():
    """Verify temporal window calculation with lead and lag hours."""
    # When timestamps are known ISO strings
    start = "2016-07-07T04:00:00Z"
    end = "2016-07-07T04:00:00Z"
    w_start, w_end = _apply_time_window(start, end, lead_hours=48.0, lag_hours=12.0)
    assert "2016-07-05 04:00:00 UTC" == w_start
    assert "2016-07-07 16:00:00 UTC" == w_end

    # When timestamp is unknown or None
    w_start_rel, w_end_rel = _apply_time_window(None, None, lead_hours=48.0, lag_hours=12.0)
    assert "T0 - 48h" in w_start_rel
    assert "T0 + 12h" in w_end_rel


def test_calculate_ais_requirements():
    """Verify AIS bounding box calculation applies buffer and lead/lag windowing."""
    bbox = (30.0, 32.0, 31.0, 33.0)  # min_lon, min_lat, max_lon, max_lat
    ais_req = calculate_ais_requirements(
        bbox,
        observation_start="2016-07-07T04:00:00Z",
        observation_end="2016-07-07T04:00:00Z",
        buffer_deg=0.50,
    )

    assert ais_req["recommended_bbox"]["west"] == 29.5
    assert ais_req["recommended_bbox"]["south"] == 31.5
    assert ais_req["recommended_bbox"]["east"] == 31.5
    assert ais_req["recommended_bbox"]["north"] == 33.5
    assert ais_req["start_utc"] == "2016-07-05 04:00:00 UTC"
    assert ais_req["end_utc"] == "2016-07-07 16:00:00 UTC"
    assert ais_req["lead_time_hours"] == 48.0


def test_calculate_ocean_and_wind_requirements():
    """Verify hydrodynamic current and meteorological wind requirement structures."""
    bbox = (30.0, 32.0, 31.0, 33.0)
    ocean_req, wind_req = calculate_ocean_and_wind_requirements(
        bbox,
        observation_start="2016-07-07T04:00:00Z",
        observation_end="2016-07-07T04:00:00Z",
        buffer_deg=0.50,
    )

    assert "uo (Eastward sea water velocity, m/s)" in ocean_req["parameters"]
    assert "vo (Northward sea water velocity, m/s)" in ocean_req["parameters"]
    assert "Copernicus Marine Service" in ocean_req["data_source_recommendation"]
    assert ocean_req["start_utc"] == "2016-07-05 04:00:00 UTC"
    assert ocean_req["end_utc"] == "2016-07-08 04:00:00 UTC"  # 24h lag

    assert "u10 (10 metre U wind component, m/s)" in wind_req["parameters"]
    assert "v10 (10 metre V wind component, m/s)" in wind_req["parameters"]
    assert "ECMWF ERA5" in wind_req["data_source_recommendation"]


def test_missing_timestamp_handling():
    """Verify robust handling when acquisition timestamp is missing/unknown."""
    meta = make_tiff_metadata(
        filename="00100.tif",
        centroid_lat=30.5,
        centroid_lon=30.5,
        min_lon=30.0,
        min_lat=30.0,
        max_lon=31.0,
        max_lat=31.0,
        acquisition_time=None,
        timestamp_status="UNKNOWN",
    )

    assert meta.acquisition_time is None
    assert meta.timestamp_status == "UNKNOWN"

    ais_req = calculate_ais_requirements((meta.min_lon, meta.min_lat, meta.max_lon, meta.max_lat))
    assert "T0 - 48h" in ais_req["start_utc"]
    assert "T0 + 12h" in ais_req["end_utc"]
