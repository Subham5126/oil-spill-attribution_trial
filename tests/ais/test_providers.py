"""Comprehensive unit and integration tests for AIS Provider Layer (AIS-09).

Tests cover:
A. AISProvider Abstract Base Class and Exception Hierarchy
B. LocalAISProvider Configuration and Health Checks
C. Spatial and Temporal Filtering correctness
D. Temporal filtering with and without source_timestamp (no origin timestamp fabrication)
E. Multi-file aggregation, deduplication, and caching
F. Canonical schema compliance and empty result handling
G. Integration with real local NOAA dataset
H. Integration with Member 4 Drift Adapter (AIS-08 -> AIS-09 pipeline)
"""

from pathlib import Path
from typing import Generator

import numpy as np
import pandas as pd
import pytest

from ais.data_loader.schema import REQUIRED_COLUMNS
from ais.integration.adapter import adapt_drift_origin_result
from ais.integration.search_request import AISSearchRequest
from ais.providers import (
    AISProvider,
    AISProviderConfigError,
    AISProviderConnectionError,
    AISProviderError,
    AISProviderNotFoundError,
    LocalAISProvider,
)


# ---------------------------------------------------------------------------
# Test Fixtures & Synthetic Data Helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_ais_csv(tmp_path: Path) -> Path:
    """Create a temporary synthetic AIS CSV file in canonical NOAA format."""
    csv_file = tmp_path / "test_ais_sample.csv"
    data = """MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft
111222333,2025-01-08T00:00:00Z,28.0000,-90.0000,10.5,180.0,180.0,CARGO A,IMO1234567,WDC1234,70,0,150,25,8.5
111222333,2025-01-08T00:15:00Z,28.0200,-90.0000,10.2,180.0,180.0,CARGO A,IMO1234567,WDC1234,70,0,150,25,8.5
111222333,2025-01-08T00:30:00Z,28.0400,-90.0000,10.0,180.0,180.0,CARGO A,IMO1234567,WDC1234,70,0,150,25,8.5
222333444,2025-01-08T00:15:00Z,28.0100,-90.0100,5.0,90.0,90.0,TANKER B,IMO7654321,WDC5678,80,0,200,32,11.0
333444555,2025-01-08T02:00:00Z,28.0000,-90.0000,12.0,0.0,0.0,TUGBOAT C,IMO9999999,WDC9999,52,0,40,10,4.0
444555666,2025-01-08T00:15:00Z,35.0000,-75.0000,8.0,45.0,45.0,FAR AWAY,IMO1111111,WDC0000,70,0,100,20,6.0
"""
    csv_file.write_text(data, encoding="utf-8")
    return csv_file


# ---------------------------------------------------------------------------
# Group A: AISProvider ABC and Exception Hierarchy
# ---------------------------------------------------------------------------
def test_cannot_instantiate_abstract_provider():
    """AISProvider cannot be instantiated directly."""
    with pytest.raises(TypeError):
        AISProvider()  # type: ignore[abstract]


def test_concrete_subclass_must_implement_all_methods():
    """Subclass without all abstract methods raises TypeError."""

    class IncompleteProvider(AISProvider):
        @property
        def name(self) -> str:
            return "incomplete"

    with pytest.raises(TypeError):
        IncompleteProvider()  # type: ignore[abstract]


def test_exception_hierarchy():
    """All custom provider exceptions inherit from AISProviderError."""
    assert issubclass(AISProviderNotFoundError, AISProviderError)
    assert issubclass(AISProviderConfigError, AISProviderError)
    assert issubclass(AISProviderConnectionError, AISProviderError)
    assert issubclass(AISProviderError, Exception)


# ---------------------------------------------------------------------------
# Group B: LocalAISProvider Configuration and Health Checks
# ---------------------------------------------------------------------------
def test_provider_init_invalid_data_path():
    """Invalid data_path types or empty arguments raise AISProviderConfigError."""
    with pytest.raises(AISProviderConfigError, match="data_path must be provided"):
        LocalAISProvider(data_path=None)  # type: ignore[arg-type]

    with pytest.raises(AISProviderConfigError, match="cannot be empty"):
        LocalAISProvider(data_path="")

    with pytest.raises(AISProviderConfigError, match="cannot be empty"):
        LocalAISProvider(data_path=[])

    with pytest.raises(AISProviderConfigError, match="must be a str, Path"):
        LocalAISProvider(data_path=12345)  # type: ignore[arg-type]


def test_provider_name_property(sample_ais_csv: Path):
    """LocalAISProvider reports correct name."""
    provider = LocalAISProvider(sample_ais_csv)
    assert provider.name == "local"


def test_health_check_non_existent_path(tmp_path: Path):
    """health_check returns False when path does not exist, without raising."""
    non_existent = tmp_path / "does_not_exist.csv"
    provider = LocalAISProvider(non_existent)
    assert provider.health_check() is False


def test_health_check_empty_directory(tmp_path: Path):
    """health_check returns False when directory has no data files."""
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    provider = LocalAISProvider(empty_dir)
    assert provider.health_check() is False


def test_health_check_valid_file(sample_ais_csv: Path):
    """health_check returns True for existing readable file."""
    provider = LocalAISProvider(sample_ais_csv)
    assert provider.health_check() is True


def test_health_check_valid_directory(sample_ais_csv: Path):
    """health_check returns True for directory containing data files."""
    provider = LocalAISProvider(sample_ais_csv.parent)
    assert provider.health_check() is True


# ---------------------------------------------------------------------------
# Group C: Spatial and Temporal Filtering Correctness
# ---------------------------------------------------------------------------
def test_fetch_ais_data_type_check(sample_ais_csv: Path):
    """Passing a non-AISSearchRequest object raises TypeError."""
    provider = LocalAISProvider(sample_ais_csv)
    with pytest.raises(TypeError, match="request must be an instance of AISSearchRequest"):
        provider.fetch_ais_data("not_a_search_request")  # type: ignore[arg-type]


def test_fetch_ais_data_non_existent_path(tmp_path: Path):
    """fetch_ais_data raises AISProviderNotFoundError when files are missing."""
    provider = LocalAISProvider(tmp_path / "ghost.csv")
    req = AISSearchRequest(
        latitude=28.0,
        longitude=-90.0,
        radius_km=10.0,
        start_time=pd.Timestamp("2025-01-08T00:00:00Z"),
        end_time=pd.Timestamp("2025-01-08T01:00:00Z"),
    )
    with pytest.raises(AISProviderNotFoundError, match="Configured AIS data path"):
        provider.fetch_ais_data(req)


def test_fetch_ais_data_spatial_and_temporal(sample_ais_csv: Path):
    """fetch_ais_data matches vessels within both spatial radius and time window."""
    provider = LocalAISProvider(sample_ais_csv)
    req = AISSearchRequest(
        latitude=28.0,
        longitude=-90.0,
        radius_km=10.0,
        start_time=pd.Timestamp("2025-01-08T00:00:00Z"),
        end_time=pd.Timestamp("2025-01-08T00:30:00Z"),
        source_timestamp=pd.Timestamp("2025-01-08T00:15:00Z"),
    )

    df = provider.fetch_ais_data(req)

    assert not df.empty
    assert "distance_km" in df.columns
    # MMSI 111222333 and 222333444 are within 10km and within 00:00 to 00:30
    assert set(df["mmsi"].unique()) == {111222333, 222333444}
    # 444555666 is far away (Atlantic), 333444555 is at 02:00 (outside window)
    assert 444555666 not in df["mmsi"].values
    assert 333444555 not in df["mmsi"].values

    # Check all distances are within radius
    assert (df["distance_km"] <= req.radius_km).all()


# ---------------------------------------------------------------------------
# Group D: Temporal Filtering without source_timestamp (No Timestamp Invention)
# ---------------------------------------------------------------------------
def test_temporal_filtering_without_source_timestamp(sample_ais_csv: Path):
    """When source_timestamp is None, authoritative boundaries [start_time, end_time] apply exactly."""
    provider = LocalAISProvider(sample_ais_csv)

    # Window covers only 00:00:00 to 00:15:00
    req = AISSearchRequest(
        latitude=28.0,
        longitude=-90.0,
        radius_km=20.0,
        start_time=pd.Timestamp("2025-01-08T00:00:00Z"),
        end_time=pd.Timestamp("2025-01-08T00:15:00Z"),
        source_timestamp=None,  # No source timestamp!
    )

    df = provider.fetch_ais_data(req)

    assert not df.empty
    assert df["timestamp"].min() >= req.start_time
    assert df["timestamp"].max() <= req.end_time

    # Observation at 00:30:00 must be excluded
    timestamps = set(df["timestamp"].dt.strftime("%H:%M:%S"))
    assert "00:00:00" in timestamps
    assert "00:15:00" in timestamps
    assert "00:30:00" not in timestamps


def test_temporal_filtering_boundary_inclusivity(sample_ais_csv: Path):
    """Exact boundary timestamps (start_time and end_time) are inclusive."""
    provider = LocalAISProvider(sample_ais_csv)

    # Query exactly spanning 00:15:00 to 00:15:00
    req = AISSearchRequest(
        latitude=28.0,
        longitude=-90.0,
        radius_km=10.0,
        start_time=pd.Timestamp("2025-01-08T00:15:00Z"),
        end_time=pd.Timestamp("2025-01-08T00:15:00Z"),
        source_timestamp=None,
    )

    df = provider.fetch_ais_data(req)
    assert not df.empty
    assert len(df) == 2  # 111222333 at 00:15:00 and 222333444 at 00:15:00
    assert (df["timestamp"] == pd.Timestamp("2025-01-08T00:15:00Z")).all()


# ---------------------------------------------------------------------------
# Group E: Multi-File Aggregation, Deduplication, and Caching
# ---------------------------------------------------------------------------
def test_multi_file_aggregation_and_deduplication(tmp_path: Path):
    """Provider correctly aggregates multiple files and deduplicates overlapping records."""
    file1 = tmp_path / "day1.csv"
    file2 = tmp_path / "day2.csv"

    # Common record in both files (duplicate)
    dup_record = "111222333,2025-01-08T00:10:00Z,28.0,-90.0,10.0,180.0,180.0,SHIP,IMO1,C1,70,0,100,20,5\n"

    file1.write_text(
        "MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft\n"
        "111222333,2025-01-08T00:05:00Z,28.0,-90.0,10.0,180.0,180.0,SHIP,IMO1,C1,70,0,100,20,5\n"
        + dup_record,
        encoding="utf-8",
    )

    file2.write_text(
        "MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft\n"
        + dup_record
        + "111222333,2025-01-08T00:20:00Z,28.0,-90.0,10.0,180.0,180.0,SHIP,IMO1,C1,70,0,100,20,5\n",
        encoding="utf-8",
    )

    provider = LocalAISProvider([file1, file2])
    req = AISSearchRequest(
        latitude=28.0,
        longitude=-90.0,
        radius_km=10.0,
        start_time=pd.Timestamp("2025-01-08T00:00:00Z"),
        end_time=pd.Timestamp("2025-01-08T01:00:00Z"),
    )

    df = provider.fetch_ais_data(req)
    assert len(df) == 3  # 00:05, 00:10 (deduplicated), 00:20
    assert (df["timestamp"] == pd.Timestamp("2025-01-08T00:10:00Z")).sum() == 1


def test_provider_caching(sample_ais_csv: Path):
    """Raw data caching accelerates repeated queries and clear_cache resets it."""
    provider = LocalAISProvider(sample_ais_csv, cache_raw=True)
    req = AISSearchRequest(
        latitude=28.0,
        longitude=-90.0,
        radius_km=10.0,
        start_time=pd.Timestamp("2025-01-08T00:00:00Z"),
        end_time=pd.Timestamp("2025-01-08T01:00:00Z"),
    )

    assert len(provider._file_cache) == 0
    res1 = provider.fetch_ais_data(req)
    assert len(provider._file_cache) == 1

    # Second fetch reuses cached raw DataFrame
    res2 = provider.fetch_ais_data(req)
    pd.testing.assert_frame_equal(res1, res2)

    # Clear cache
    provider.clear_cache()
    assert len(provider._file_cache) == 0


# ---------------------------------------------------------------------------
# Group F: Canonical Schema Compliance and Empty Result Handling
# ---------------------------------------------------------------------------
def test_empty_query_result_schema(sample_ais_csv: Path):
    """Query with no matches returns an empty DataFrame preserving canonical columns + distance_km."""
    provider = LocalAISProvider(sample_ais_csv)
    # Search in an empty ocean region
    req = AISSearchRequest(
        latitude=0.0,
        longitude=0.0,
        radius_km=5.0,
        start_time=pd.Timestamp("2025-01-08T00:00:00Z"),
        end_time=pd.Timestamp("2025-01-08T01:00:00Z"),
    )

    df = provider.fetch_ais_data(req)
    assert df.empty
    assert len(df) == 0
    assert "distance_km" in df.columns
    for req_col in REQUIRED_COLUMNS:
        assert req_col in df.columns


def test_corrupt_file_raises_ais_provider_error(tmp_path: Path):
    """Corrupted CSV file raises AISProviderError."""
    bad_file = tmp_path / "corrupt.csv"
    # Header missing required columns
    bad_file.write_text("random_col1,random_col2\nval1,val2\n", encoding="utf-8")

    provider = LocalAISProvider(bad_file)
    req = AISSearchRequest(
        latitude=28.0,
        longitude=-90.0,
        radius_km=10.0,
        start_time=pd.Timestamp("2025-01-08T00:00:00Z"),
        end_time=pd.Timestamp("2025-01-08T01:00:00Z"),
    )

    with pytest.raises(AISProviderError):
        provider.fetch_ais_data(req)


# ---------------------------------------------------------------------------
# Group G: Integration with Real Local NOAA Dataset
# ---------------------------------------------------------------------------
def test_real_local_noaa_dataset_sf_bay():
    """Query real local NOAA uncompressed dataset in San Francisco Bay."""
    local_path = Path("data/ais/2025/AIS_178881322085076878_1697-1788813221032.csv")
    if not local_path.exists():
        pytest.skip("Local NOAA SF Bay dataset not present")

    provider = LocalAISProvider(local_path)
    assert provider.health_check() is True

    # SF Bay coordinates around 37.8°N, -122.4°W at 2025-01-07 00:00 to 00:30 UTC
    req = AISSearchRequest(
        latitude=37.80,
        longitude=-122.40,
        radius_km=15.0,
        start_time=pd.Timestamp("2025-01-07T00:00:00Z"),
        end_time=pd.Timestamp("2025-01-07T00:30:00Z"),
    )

    df = provider.fetch_ais_data(req)
    assert not df.empty
    assert "distance_km" in df.columns
    assert (df["distance_km"] <= req.radius_km).all()
    assert (df["timestamp"] >= req.start_time).all()
    assert (df["timestamp"] <= req.end_time).all()
    assert len(df["mmsi"].unique()) >= 1


# ---------------------------------------------------------------------------
# Group H: End-to-End Integration with Member 4 Drift Adapter (AIS-08 -> AIS-09)
# ---------------------------------------------------------------------------
def test_e2e_drift_adapter_to_local_provider(sample_ais_csv: Path):
    """End-to-end integration: Member 4 output -> Drift Adapter -> LocalAISProvider."""
    # Synthetic Member 4 origin dictionary
    member4_origin = {
        "status": "success",
        "best_candidate": {
            "timestamp": "2025-01-08T00:15:00Z",
            "region": {
                "centroid_lat": 28.005,
                "centroid_lon": -90.005,
                "radius_km": 5.0,
            },
        },
    }

    # Adapt Member 4 origin using AIS-08 adapter
    adapter_result = adapt_drift_origin_result(
        member4_origin,
        before_minutes=15.0,
        after_minutes=15.0,
        buffer_km=1.0,
    )

    req = adapter_result.search_request

    # Feed search request into LocalAISProvider
    provider = LocalAISProvider(sample_ais_csv)
    df = provider.fetch_ais_data(req)

    assert not df.empty
    assert "distance_km" in df.columns
    # Both 111222333 and 222333444 are within the 6.0km effective radius
    assert 111222333 in df["mmsi"].values
    assert 222333444 in df["mmsi"].values
    assert (df["distance_km"] <= req.effective_radius_km).all()
