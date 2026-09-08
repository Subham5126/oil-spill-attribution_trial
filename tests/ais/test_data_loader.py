"""Unit tests for the AIS Data Loader (AIS-02).

Tests decompression detection (zstd, gzip, zip, uncompressed), misleading file extensions,
canonical schema mapping, UTC timestamp parsing, coordinate validation, sentinel replacement,
suspicious zero quality-flagging, MMSI validation, deduplication, deterministic sorting,
nrows, and chunked streaming.
"""

import gzip
import io
import zipfile
from pathlib import Path
from typing import Generator

import numpy as np
import pandas as pd
import pytest
import zstandard as zstd

from ais.data_loader import (
    AISDataLoaderError,
    AISInvalidFileError,
    AISMissingRequiredColumnError,
    clean_ais_dataframe,
    detect_compression,
    load_ais_csv,
    resolve_column_mapping,
)


@pytest.fixture
def sample_csv_content() -> str:
    """Standard NOAA-style CSV sample content."""
    return (
        "MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft\n"
        "367793030,2025-01-08T00:00:00,-12.40506,-77.12345,12.5,180.0,180.0,PACIFIC VOYAGER,IMO9123456,WDC1234,70,0,180,30,10.5\n"
        "338160209,2025-01-08T00:01:00,34.12345,-119.69199,8.0,90.0,90.0,OCEAN EXPLORER,IMO9654321,WDE5678,80,0,150,25,8.0\n"
    )


# ---------------------------------------------------------------------------
# 1. Compression and Magic-Byte Detection Tests
# ---------------------------------------------------------------------------

def test_detect_compression_zstd(tmp_path: Path):
    """Verify Zstandard magic-byte detection (0x28 0xb5 0x2f 0xfd)."""
    file_path = tmp_path / "test.zst"
    compressed = zstd.ZstdCompressor().compress(b"col1,col2\nval1,val2\n")
    file_path.write_bytes(compressed)

    assert detect_compression(file_path) == "zstd"


def test_detect_compression_misleading_tgz_extension(tmp_path: Path):
    """Verify that a zstd file with a misleading .tgz extension is detected as zstd."""
    file_path = tmp_path / "ais-2025-01-08.tgz"
    compressed = zstd.ZstdCompressor().compress(b"col1,col2\nval1,val2\n")
    file_path.write_bytes(compressed)

    assert detect_compression(file_path) == "zstd"


def test_detect_compression_gzip(tmp_path: Path):
    """Verify gzip magic-byte detection (0x1f 0x8b)."""
    file_path = tmp_path / "test.csv.gz"
    compressed = gzip.compress(b"col1,col2\nval1,val2\n")
    file_path.write_bytes(compressed)

    assert detect_compression(file_path) == "gzip"


def test_detect_compression_zip(tmp_path: Path):
    """Verify zip magic-byte detection (PK 0x03 0x04)."""
    file_path = tmp_path / "test.zip"
    with zipfile.ZipFile(file_path, "w") as zf:
        zf.writestr("test.csv", "col1,col2\nval1,val2\n")

    assert detect_compression(file_path) == "zip"


def test_detect_compression_uncompressed(tmp_path: Path):
    """Verify uncompressed CSV returns None."""
    file_path = tmp_path / "test.csv"
    file_path.write_text("col1,col2\nval1,val2\n", encoding="utf-8")

    assert detect_compression(file_path) is None


# ---------------------------------------------------------------------------
# 2. Loading with Misleading .tgz Extension & Formats
# ---------------------------------------------------------------------------

def test_load_zstandard_with_misleading_tgz(tmp_path: Path, sample_csv_content: str):
    """Verify load_ais_csv correctly reads a Zstandard file named .tgz."""
    file_path = tmp_path / "ais-2025-01-08.tgz"
    compressed = zstd.ZstdCompressor().compress(sample_csv_content.encode("utf-8"))
    file_path.write_bytes(compressed)

    df = load_ais_csv(file_path)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert "mmsi" in df.columns
    assert "timestamp" in df.columns
    assert "latitude" in df.columns
    assert "longitude" in df.columns
    assert df["mmsi"].iloc[0] == 338160209  # Sorted deterministically
    assert df["mmsi"].iloc[1] == 367793030


def test_load_gzip_csv(tmp_path: Path, sample_csv_content: str):
    """Verify load_ais_csv reads a gzip-compressed CSV."""
    file_path = tmp_path / "sample.csv.gz"
    file_path.write_bytes(gzip.compress(sample_csv_content.encode("utf-8")))

    df = load_ais_csv(file_path)
    assert len(df) == 2


def test_load_zip_csv(tmp_path: Path, sample_csv_content: str):
    """Verify load_ais_csv reads a zip-compressed CSV."""
    file_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(file_path, "w") as zf:
        zf.writestr("ais.csv", sample_csv_content)

    df = load_ais_csv(file_path)
    assert len(df) == 2


def test_load_uncompressed_csv(tmp_path: Path, sample_csv_content: str):
    """Verify load_ais_csv reads an uncompressed CSV."""
    file_path = tmp_path / "sample.csv"
    file_path.write_text(sample_csv_content, encoding="utf-8")

    df = load_ais_csv(file_path)
    assert len(df) == 2


# ---------------------------------------------------------------------------
# 3. Schema & Column Alias Mapping
# ---------------------------------------------------------------------------

def test_noaa_column_alias_normalization():
    """Verify resolution of NOAA-specific headers to canonical columns."""
    noaa_cols = [
        "MMSI",
        "BaseDateTime",
        "LAT",
        "LON",
        "SOG",
        "COG",
        "Heading",
        "VesselName",
        "IMO",
        "CallSign",
        "VesselType",
        "Status",
        "Length",
        "Width",
        "Draft",
    ]
    mapping = resolve_column_mapping(noaa_cols)
    assert mapping["MMSI"] == "mmsi"
    assert mapping["BaseDateTime"] == "timestamp"
    assert mapping["LAT"] == "latitude"
    assert mapping["LON"] == "longitude"
    assert mapping["SOG"] == "sog"
    assert mapping["COG"] == "cog"
    assert mapping["Heading"] == "heading"
    assert mapping["VesselName"] == "vessel_name"
    assert mapping["IMO"] == "imo"
    assert mapping["CallSign"] == "callsign"
    assert mapping["VesselType"] == "vessel_type"
    assert mapping["Status"] == "nav_status"
    assert mapping["Length"] == "length"
    assert mapping["Width"] == "width"
    assert mapping["Draft"] == "draught"


def test_dma_column_alias_normalization():
    """Verify resolution of Danish Maritime Authority headers to canonical columns."""
    dma_cols = [
        "MMSI",
        "# Timestamp",
        "Latitude",
        "Longitude",
        "SOG",
        "COG",
        "Heading",
        "Name",
        "Ship type",
        "Navigational status",
        "Draught",
    ]
    mapping = resolve_column_mapping(dma_cols)
    assert mapping["MMSI"] == "mmsi"
    assert mapping["# Timestamp"] == "timestamp"
    assert mapping["Latitude"] == "latitude"
    assert mapping["Longitude"] == "longitude"
    assert mapping["Name"] == "vessel_name"
    assert mapping["Ship type"] == "vessel_type"
    assert mapping["Navigational status"] == "nav_status"
    assert mapping["Draught"] == "draught"


def test_xy_columns_not_treated_as_lat_lon(tmp_path: Path):
    """Verify generic 'x' and 'y' columns are NOT assumed to be longitude and latitude."""
    content = "mmsi,timestamp,x,y\n123456789,2025-01-01T00:00:00,10.0,20.0\n"
    file_path = tmp_path / "ambiguous.csv"
    file_path.write_text(content, encoding="utf-8")

    with pytest.raises(AISMissingRequiredColumnError) as exc_info:
        load_ais_csv(file_path)

    err_msg = str(exc_info.value)
    assert "latitude" in err_msg
    assert "longitude" in err_msg


def test_missing_required_columns_raises_error(tmp_path: Path):
    """Verify exception is raised when required columns (e.g. latitude) are absent."""
    content = "mmsi,timestamp,longitude\n123456789,2025-01-01T00:00:00,10.0\n"
    file_path = tmp_path / "missing_col.csv"
    file_path.write_text(content, encoding="utf-8")

    with pytest.raises(AISMissingRequiredColumnError) as exc_info:
        load_ais_csv(file_path)

    assert "latitude" in exc_info.value.missing_columns


# ---------------------------------------------------------------------------
# 4. UTC Timestamp Normalization
# ---------------------------------------------------------------------------

def test_utc_timestamp_parsing(tmp_path: Path):
    """Verify timestamps across formats are normalized to timezone-aware UTC."""
    content = (
        "mmsi,timestamp,latitude,longitude\n"
        "200000001,2025-01-08T12:30:00,10.0,20.0\n"
        "200000002,2025-01-08 14:00:00+02:00,10.0,20.0\n"
        "200000003,invalid-date,10.0,20.0\n"
    )
    file_path = tmp_path / "dates.csv"
    file_path.write_text(content, encoding="utf-8")

    df = load_ais_csv(file_path)
    # Row 3 with invalid date should be dropped
    assert len(df) == 2
    # Verify timezone-aware UTC
    assert str(df["timestamp"].dt.tz) == "UTC"
    # Row 2 (14:00+02:00) should be converted to 12:00:00 UTC
    row2 = df[df["mmsi"] == 200000002].iloc[0]
    assert row2["timestamp"].hour == 12


# ---------------------------------------------------------------------------
# 5. Coordinate Bounds & Sentinel Handling
# ---------------------------------------------------------------------------

def test_coordinate_bounds_and_sentinels(tmp_path: Path):
    """Verify invalid physical coordinates and ITU sentinels (91.0, 181.0) are rejected."""
    content = (
        "mmsi,timestamp,latitude,longitude\n"
        "200000001,2025-01-08T00:00:00,45.0,-120.0\n"       # Valid
        "200000002,2025-01-08T00:00:00,91.0,-120.0\n"       # Lat Sentinel 91.0 -> Rejected
        "200000003,2025-01-08T00:00:00,45.0,181.0\n"        # Lon Sentinel 181.0 -> Rejected
        "200000004,2025-01-08T00:00:00,95.0,-120.0\n"       # Lat > 90 -> Rejected
        "200000005,2025-01-08T00:00:00,-95.0,-120.0\n"      # Lat < -90 -> Rejected
        "200000006,2025-01-08T00:00:00,45.0,190.0\n"        # Lon > 180 -> Rejected
        "200000007,2025-01-08T00:00:00,45.0,-190.0\n"       # Lon < -180 -> Rejected
        "200000008,2025-01-08T00:00:00,NaN,-120.0\n"        # NaN coord -> Rejected
    )
    file_path = tmp_path / "coords.csv"
    file_path.write_text(content, encoding="utf-8")

    df = load_ais_csv(file_path)
    assert len(df) == 1
    assert df["mmsi"].iloc[0] == 200000001


def test_suspicious_zero_coordinates_preserved_and_flagged(tmp_path: Path):
    """Verify (0.0, 0.0) coordinates are preserved with quality flag is_suspicious_zero=True."""
    content = (
        "mmsi,timestamp,latitude,longitude\n"
        "200000001,2025-01-08T00:00:00,0.0,0.0\n"           # Null Island (0,0) -> Preserved + Flagged
        "200000002,2025-01-08T00:00:00,25.0,-80.0\n"        # Regular coordinate -> Not Flagged
    )
    file_path = tmp_path / "null_island.csv"
    file_path.write_text(content, encoding="utf-8")

    df = load_ais_csv(file_path)
    assert len(df) == 2
    assert "is_suspicious_zero" in df.columns

    row_zero = df[df["mmsi"] == 200000001].iloc[0]
    assert row_zero["latitude"] == 0.0
    assert row_zero["longitude"] == 0.0
    assert row_zero["is_suspicious_zero"] is True or row_zero["is_suspicious_zero"] == 1

    row_normal = df[df["mmsi"] == 200000002].iloc[0]
    assert row_normal["is_suspicious_zero"] is False or row_normal["is_suspicious_zero"] == 0


# ---------------------------------------------------------------------------
# 6. SOG, COG, and Heading Sentinel Handling
# ---------------------------------------------------------------------------

def test_kinematic_sentinels_converted_to_nan(tmp_path: Path):
    """Verify SOG=102.3, COG=360.0, Heading=511 are converted to NaN."""
    content = (
        "mmsi,timestamp,latitude,longitude,sog,cog,heading\n"
        "200000001,2025-01-08T00:00:00,10.0,20.0,102.3,360.0,511.0\n"  # All sentinels
        "200000002,2025-01-08T00:00:00,10.0,20.0,-5.0,400.0,-1.0\n"     # Out of bounds
        "200000003,2025-01-08T00:00:00,10.0,20.0,15.2,180.5,180.0\n"   # Valid
    )
    file_path = tmp_path / "sentinels.csv"
    file_path.write_text(content, encoding="utf-8")

    df = load_ais_csv(file_path)
    assert len(df) == 3

    # Row 1: sentinels converted to NaN
    row1 = df[df["mmsi"] == 200000001].iloc[0]
    assert np.isnan(row1["sog"])
    assert np.isnan(row1["cog"])
    assert np.isnan(row1["heading"])

    # Row 2: out-of-bounds converted to NaN
    row2 = df[df["mmsi"] == 200000002].iloc[0]
    assert np.isnan(row2["sog"])
    assert np.isnan(row2["cog"])
    assert np.isnan(row2["heading"])

    # Row 3: valid values preserved
    row3 = df[df["mmsi"] == 200000003].iloc[0]
    assert row3["sog"] == 15.2
    assert row3["cog"] == 180.5
    assert row3["heading"] == 180.0


# ---------------------------------------------------------------------------
# 7. MMSI Validation
# ---------------------------------------------------------------------------

def test_mmsi_validation(tmp_path: Path):
    """Verify non-numeric, zero, negative, and sentinel invalid MMSIs are rejected."""
    content = (
        "mmsi,timestamp,latitude,longitude\n"
        "200000001,2025-01-08T00:00:00,10.0,20.0\n"       # Valid
        "0,2025-01-08T00:00:00,10.0,20.0\n"               # Zero MMSI -> Rejected
        "-100,2025-01-08T00:00:00,10.0,20.0\n"            # Negative MMSI -> Rejected
        "111111111,2025-01-08T00:00:00,10.0,20.0\n"       # Default invalid test sentinel -> Rejected
        "not_a_number,2025-01-08T00:00:00,10.0,20.0\n"   # Non-numeric -> Rejected
    )
    file_path = tmp_path / "mmsi.csv"
    file_path.write_text(content, encoding="utf-8")

    df = load_ais_csv(file_path)
    assert len(df) == 1
    assert df["mmsi"].iloc[0] == 200000001
    assert df["mmsi"].dtype == np.int64


# ---------------------------------------------------------------------------
# 8. Deduplication & Deterministic Sorting
# ---------------------------------------------------------------------------

def test_duplicate_removal(tmp_path: Path):
    """Verify duplicate records with identical (mmsi, timestamp) are deduplicated."""
    content = (
        "mmsi,timestamp,latitude,longitude,sog\n"
        "200000001,2025-01-08T00:00:00,10.0,20.0,12.0\n"
        "200000001,2025-01-08T00:00:00,10.0,20.0,14.0\n"  # Duplicate (mmsi, timestamp)
        "200000001,2025-01-08T00:05:00,10.1,20.1,12.5\n"
    )
    file_path = tmp_path / "dups.csv"
    file_path.write_text(content, encoding="utf-8")

    df = load_ais_csv(file_path)
    assert len(df) == 2
    assert df["sog"].iloc[0] == 12.0  # Kept first duplicate


def test_deterministic_sorting(tmp_path: Path):
    """Verify output DataFrame is sorted deterministically by MMSI, then timestamp."""
    content = (
        "mmsi,timestamp,latitude,longitude\n"
        "300000001,2025-01-08T05:00:00,10.0,20.0\n"
        "200000001,2025-01-08T04:00:00,10.0,20.0\n"
        "200000001,2025-01-08T01:00:00,10.0,20.0\n"
    )
    file_path = tmp_path / "sort.csv"
    file_path.write_text(content, encoding="utf-8")

    df = load_ais_csv(file_path)
    assert df["mmsi"].tolist() == [200000001, 200000001, 300000001]
    assert df["timestamp"].iloc[0] < df["timestamp"].iloc[1]


# ---------------------------------------------------------------------------
# 9. Parameters (nrows and chunksize)
# ---------------------------------------------------------------------------

def test_nrows_parameter(tmp_path: Path):
    """Verify nrows parameter restricts the loaded records."""
    content = (
        "mmsi,timestamp,latitude,longitude\n"
        "200000001,2025-01-08T00:00:00,10.0,20.0\n"
        "200000002,2025-01-08T00:00:00,10.0,20.0\n"
        "200000003,2025-01-08T00:00:00,10.0,20.0\n"
    )
    file_path = tmp_path / "nrows.csv"
    file_path.write_text(content, encoding="utf-8")

    df = load_ais_csv(file_path, nrows=2)
    assert len(df) == 2


def test_chunksize_generator(tmp_path: Path):
    """Verify chunksize parameter returns a generator yielding cleaned DataFrame chunks."""
    content = (
        "mmsi,timestamp,latitude,longitude\n"
        "200000001,2025-01-08T00:00:00,10.0,20.0\n"
        "200000002,2025-01-08T00:00:00,10.0,20.0\n"
        "200000003,2025-01-08T00:00:00,10.0,20.0\n"
        "200000004,2025-01-08T00:00:00,10.0,20.0\n"
    )
    file_path = tmp_path / "chunks.csv"
    file_path.write_text(content, encoding="utf-8")

    gen = load_ais_csv(file_path, chunksize=2)
    assert isinstance(gen, Generator)

    chunks = list(gen)
    assert len(chunks) == 2
    assert len(chunks[0]) == 2
    assert len(chunks[1]) == 2
    assert all(isinstance(c, pd.DataFrame) for c in chunks)


# ---------------------------------------------------------------------------
# 10. File Error Handling
# ---------------------------------------------------------------------------

def test_empty_file_raises_invalid_file_error(tmp_path: Path):
    """Verify empty 0-byte file raises AISInvalidFileError."""
    file_path = tmp_path / "empty.csv"
    file_path.touch()

    with pytest.raises(AISInvalidFileError):
        load_ais_csv(file_path)


def test_nonexistent_file_raises_file_not_found():
    """Verify non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_ais_csv("non_existent_file_path_12345.csv")


# ---------------------------------------------------------------------------
# 11. Local NOAA Real-Data Smoke Test (Optional / Skipped if File Absent)
# ---------------------------------------------------------------------------

def test_real_noaa_file_preview_smoke_test():
    """Smoke test on local NOAA daily file if present, loading only 50 rows.

    This test never fails CI if the large raw file is absent.
    """
    raw_path = Path("data/raw/ais/noaa/ais-2025-01-08.tgz")
    if not raw_path.exists():
        pytest.skip("Local NOAA raw file not present (as expected in CI/clean repos)")

    # Read a tiny preview slice without loading the entire 160MB archive
    df = load_ais_csv(raw_path, nrows=50)
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    assert "mmsi" in df.columns
    assert "timestamp" in df.columns
    assert "latitude" in df.columns
    assert "longitude" in df.columns
    assert "is_suspicious_zero" in df.columns
    assert str(df["timestamp"].dt.tz) == "UTC"
    assert df["mmsi"].dtype == np.int64
