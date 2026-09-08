"""AIS Data Loader Implementation.

Provides robust ingestion and normalization for AIS datasets (such as NOAA MarineCadastre),
supporting magic-byte compression detection (zstd, gzip, zip, uncompressed), canonical
schema normalization, UTC timestamp validation, coordinate validation, sentinel replacement,
and chunked streaming.
"""

import io
import os
from pathlib import Path
from typing import Dict, Generator, Iterator, List, Optional, Union

import numpy as np
import pandas as pd

from ais.data_loader.schema import (
    AISDataLoaderError,
    AISInvalidFileError,
    AISMissingRequiredColumnError,
    COG_MAX,
    COG_MIN,
    COG_SENTINEL,
    COLUMN_ALIASES,
    HEADING_MAX,
    HEADING_MIN,
    HEADING_SENTINEL,
    LAT_MAX,
    LAT_MIN,
    LATITUDE_SENTINEL,
    LON_MAX,
    LON_MIN,
    LONGITUDE_SENTINEL,
    MMSI_MAX,
    MMSI_MIN,
    REQUIRED_COLUMNS,
    SOG_MAX,
    SOG_MIN,
    SOG_SENTINEL,
)


def detect_compression(source: Union[str, Path, io.BytesIO]) -> Optional[str]:
    """Detect compression format by inspecting magic bytes rather than trusting file extensions.

    Recognizes:
    - Zstandard (\\x28\\xb5\\x2f\\xfd) -> "zstd"
    - Gzip (\\x1f\\x8b) -> "gzip"
    - Zip (PK\\x03\\x04) -> "zip"
    - Bzip2 (BZh) -> "bz2"
    - XZ (\\xfd7zXZ\\x00) -> "xz"

    Args:
        source: Filepath as str/Path, or a readable binary buffer.

    Returns:
        Compression type string understood by pandas (e.g. "zstd", "gzip", "zip")
        or None if uncompressed.
    """
    magic_bytes: bytes = b""

    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"AIS file not found: {path}")
        if path.is_file() and path.stat().st_size == 0:
            return None
        with open(path, "rb") as f:
            magic_bytes = f.read(6)
    elif hasattr(source, "read") and hasattr(source, "seek"):
        pos = source.tell()
        magic_bytes = source.read(6)
        source.seek(pos)
    else:
        return None

    if len(magic_bytes) >= 4 and magic_bytes[:4] == b"\x28\xb5\x2f\xfd":
        return "zstd"
    if len(magic_bytes) >= 2 and magic_bytes[:2] == b"\x1f\x8b":
        return "gzip"
    if len(magic_bytes) >= 4 and magic_bytes[:4] == b"\x50\x4b\x03\x04":
        return "zip"
    if len(magic_bytes) >= 3 and magic_bytes[:3] == b"\x42\x5a\x68":
        return "bz2"
    if len(magic_bytes) >= 6 and magic_bytes[:6] == b"\xfd\x37\x7a\x58\x5a\x00":
        return "xz"

    return None


def _normalize_name(name: str) -> str:
    """Normalize a column header for alias lookup."""
    return (
        name.strip()
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
        .replace("#", "")
    )


def resolve_column_mapping(source_columns: List[str]) -> Dict[str, str]:
    """Resolve input dataset column names to canonical schema columns.

    Matches input columns against known alias dictionaries.
    Excludes generic 'x' and 'y' axis symbols.

    Args:
        source_columns: List of column names from the raw dataset.

    Returns:
        Dictionary mapping {raw_column_name: canonical_column_name}.

    Raises:
        AISMissingRequiredColumnError: If any required column cannot be resolved.
    """
    mapping: Dict[str, str] = {}
    assigned_canonical: set = set()

    for raw_col in source_columns:
        norm_raw = _normalize_name(str(raw_col))
        for canonical_name, aliases in COLUMN_ALIASES.items():
            if canonical_name in assigned_canonical:
                continue
            normalized_aliases = [_normalize_name(a) for a in aliases]
            if norm_raw in normalized_aliases or norm_raw == _normalize_name(canonical_name):
                mapping[raw_col] = canonical_name
                assigned_canonical.add(canonical_name)
                break

    # Verify all required columns are present
    missing = [req for req in REQUIRED_COLUMNS if req not in assigned_canonical]
    if missing:
        raise AISMissingRequiredColumnError(
            missing_columns=missing,
            available_columns=list(assigned_canonical),
        )

    return mapping


def clean_ais_dataframe(df: pd.DataFrame, col_map: Dict[str, str]) -> pd.DataFrame:
    """Normalize, validate, and clean an AIS DataFrame.

    Applies:
    - Column renaming to canonical names
    - MMSI positive integer validation
    - UTC timezone-aware datetime parsing
    - WGS84 coordinate bounds and sentinel filtering
    - Suspicious (0.0, 0.0) quality-flagging
    - SOG/COG/Heading sentinel conversion to NaN
    - Deduplication by (mmsi, timestamp)
    - Deterministic sorting by mmsi, timestamp

    Args:
        df: Raw pandas DataFrame.
        col_map: Mapping of raw column names to canonical names.

    Returns:
        Cleaned and normalized pandas DataFrame.
    """
    if df.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS + ["is_suspicious_zero"])

    # Rename mapped columns
    df = df.rename(columns=col_map).copy()

    # Retain only mapped canonical columns
    keep_cols = [col for col in df.columns if col in col_map.values()]
    df = df[keep_cols].copy()

    # 1. MMSI Validation
    df["mmsi"] = pd.to_numeric(df["mmsi"], errors="coerce")
    # Discard non-numeric, null, <= 0, or sentinel invalid patterns (e.g. 0, 111111111)
    valid_mmsi_mask = (
        df["mmsi"].notna()
        & (df["mmsi"] > 0)
        & (df["mmsi"] != 111111111)
        & (df["mmsi"] <= MMSI_MAX)
    )
    df = df[valid_mmsi_mask].copy()
    if df.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS + ["is_suspicious_zero"])
    df["mmsi"] = df["mmsi"].astype(np.int64)

    # 2. Timestamp Parsing (Strict UTC)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", utc=True, errors="coerce")
    df = df[df["timestamp"].notna()].copy()
    if df.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS + ["is_suspicious_zero"])

    # 3. Coordinate Parsing & Bounds Validation
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    # Drop NaNs
    df = df[df["latitude"].notna() & df["longitude"].notna()].copy()

    # Filter out ITU coordinate sentinels (91.0, 181.0) and out-of-range physical coordinates
    valid_coords = (
        (df["latitude"] >= LAT_MIN)
        & (df["latitude"] <= LAT_MAX)
        & (df["latitude"] != LATITUDE_SENTINEL)
        & (df["longitude"] >= LON_MIN)
        & (df["longitude"] <= LON_MAX)
        & (df["longitude"] != LONGITUDE_SENTINEL)
    )
    df = df[valid_coords].copy()
    if df.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS + ["is_suspicious_zero"])

    # 4. Flag Suspicious (0.0, 0.0) Coordinates (Preserve without dropping)
    df["is_suspicious_zero"] = (df["latitude"] == 0.0) & (df["longitude"] == 0.0)

    # 5. SOG Sentinel and Bounds Conversion
    if "sog" in df.columns:
        df["sog"] = pd.to_numeric(df["sog"], errors="coerce")
        invalid_sog = (df["sog"] < SOG_MIN) | (df["sog"] > SOG_MAX) | (df["sog"] == SOG_SENTINEL)
        df.loc[invalid_sog, "sog"] = np.nan

    # 6. COG Sentinel and Bounds Conversion
    if "cog" in df.columns:
        df["cog"] = pd.to_numeric(df["cog"], errors="coerce")
        invalid_cog = (df["cog"] < COG_MIN) | (df["cog"] >= COG_MAX) | (df["cog"] == COG_SENTINEL)
        df.loc[invalid_cog, "cog"] = np.nan

    # 7. Heading Sentinel and Bounds Conversion
    if "heading" in df.columns:
        df["heading"] = pd.to_numeric(df["heading"], errors="coerce")
        invalid_heading = (
            (df["heading"] < HEADING_MIN)
            | (df["heading"] > HEADING_MAX)
            | (df["heading"] == HEADING_SENTINEL)
        )
        df.loc[invalid_heading, "heading"] = np.nan

    # 8. Physical Dimensions (Length, Width, Draught) Conversion
    for dim_col in ["length", "width", "draught"]:
        if dim_col in df.columns:
            df[dim_col] = pd.to_numeric(df[dim_col], errors="coerce")
            df.loc[df[dim_col] <= 0.0, dim_col] = np.nan

    # 9. Deduplication on (mmsi, timestamp)
    df = df.drop_duplicates(subset=["mmsi", "timestamp"], keep="first")

    # 10. Deterministic Sorting
    df = df.sort_values(by=["mmsi", "timestamp"]).reset_index(drop=True)

    return df


def load_ais_csv(
    path: Union[str, Path],
    chunksize: Optional[int] = None,
    nrows: Optional[int] = None,
) -> Union[pd.DataFrame, Generator[pd.DataFrame, None, None]]:
    """Load, validate, and normalize an AIS CSV dataset.

    Supports uncompressed, gzip, zip, and zstandard (zstd) files.
    Automatically detects compression from file magic bytes, handling
    misleading file extensions (such as NOAA's zstd files named .tgz).

    Args:
        path: Path to the AIS data file.
        chunksize: If specified, returns a generator yielding cleaned DataFrames
            chunk by chunk for memory-efficient streaming.
        nrows: Number of rows of file to read (useful for testing and previews).

    Returns:
        Cleaned pd.DataFrame if chunksize is None, or a Generator of pd.DataFrame
        if chunksize is an integer.

    Raises:
        FileNotFoundError: If the file does not exist.
        AISInvalidFileError: If the file is empty or corrupted.
        AISMissingRequiredColumnError: If required canonical columns are missing.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"AIS file not found: {file_path}")

    if file_path.is_file() and file_path.stat().st_size == 0:
        raise AISInvalidFileError(f"AIS file is empty (0 bytes): {file_path}")

    compression = detect_compression(file_path)

    # Inspect header to resolve column mapping early
    try:
        header_df = pd.read_csv(file_path, compression=compression, nrows=0)
    except Exception as exc:
        raise AISInvalidFileError(f"Failed to read header from {file_path}: {exc}") from exc

    col_map = resolve_column_mapping(list(header_df.columns))

    if chunksize is not None:
        if chunksize <= 0:
            raise ValueError(f"chunksize must be a positive integer, got {chunksize}")

        def _chunk_generator() -> Generator[pd.DataFrame, None, None]:
            reader = pd.read_csv(
                file_path,
                compression=compression,
                chunksize=chunksize,
                nrows=nrows,
            )
            for raw_chunk in reader:
                cleaned = clean_ais_dataframe(raw_chunk, col_map)
                yield cleaned

        return _chunk_generator()

    # Load entire dataset
    try:
        raw_df = pd.read_csv(
            file_path,
            compression=compression,
            nrows=nrows,
        )
    except Exception as exc:
        raise AISInvalidFileError(f"Error parsing AIS data from {file_path}: {exc}") from exc

    return clean_ais_dataframe(raw_df, col_map)
