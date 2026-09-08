"""Local AIS Data Provider.

Implements the AISProvider contract for local datasets (uncompressed and compressed
CSVs, e.g. NOAA MarineCadastre historical files), executing spatial and temporal
filtering using AIS-02, AIS-06, and AIS-07 without external API dependencies.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

import pandas as pd

from ais.data_loader.loader import load_ais_csv
from ais.data_loader.schema import (
    AISDataLoaderError,
    AISInvalidFileError,
    REQUIRED_COLUMNS,
)
from ais.filtering.spatial import filter_by_radius
from ais.filtering.temporal import filter_by_time_window
from ais.integration.search_request import AISSearchRequest
from ais.providers.base import (
    AISProvider,
    AISProviderConfigError,
    AISProviderError,
    AISProviderNotFoundError,
)

# Standard file extensions recognized when scanning directories
SUPPORTED_FILE_EXTENSIONS: tuple[str, ...] = (
    ".csv",
    ".tsv",
    ".txt",
    ".zst",
    ".gz",
    ".zip",
    ".bz2",
    ".xz",
    ".tgz",
    ".tar.gz",
)


class LocalAISProvider(AISProvider):
    """AIS data provider querying locally stored AIS files or directories.

    Reuses existing AIS-02 loader (`load_ais_csv`), AIS-06 spatial filtering
    (`filter_by_radius`), and AIS-07 temporal filtering (`filter_by_time_window`).
    Strictly enforces search bounds from `AISSearchRequest` without inventing
    or shifting timestamps.
    """

    def __init__(
        self,
        data_path: Union[str, Path, Sequence[Union[str, Path]]],
        cache_raw: bool = False,
    ) -> None:
        """Initialize LocalAISProvider with one or more file or directory paths.

        Args:
            data_path: Single filepath, directory path, or sequence of paths
                pointing to AIS data files or directories.
            cache_raw: If True, caches parsed raw AIS DataFrames in memory
                by file path to accelerate repeated queries against the same files.

        Raises:
            AISProviderConfigError: If data_path is None, empty, or of invalid type.
        """
        if data_path is None:
            raise AISProviderConfigError("data_path must be provided and cannot be None.")

        if isinstance(data_path, (str, Path)):
            if isinstance(data_path, str) and not data_path.strip():
                raise AISProviderConfigError("data_path string cannot be empty.")
            self._paths: List[Path] = [Path(data_path)]
            self._raw_path_input: Union[str, List[str]] = str(data_path)
        elif isinstance(data_path, (list, tuple, Sequence)) and not isinstance(
            data_path, (str, bytes)
        ):
            if len(data_path) == 0:
                raise AISProviderConfigError("data_path sequence cannot be empty.")
            self._paths = [Path(p) for p in data_path]
            self._raw_path_input = [str(p) for p in data_path]
        else:
            raise AISProviderConfigError(
                f"data_path must be a str, Path, or sequence of str/Path, got {type(data_path).__name__}"
            )

        self.cache_raw: bool = bool(cache_raw)
        self._file_cache: Dict[Path, pd.DataFrame] = {}

    @property
    def name(self) -> str:
        """Unique provider identifier."""
        return "local"

    def clear_cache(self) -> None:
        """Clear the internal raw DataFrame cache."""
        self._file_cache.clear()

    def _resolve_files(self) -> List[Path]:
        """Resolve configured paths into a list of existing candidate files.

        Returns:
            Deterministic, sorted list of resolved file paths.
        """
        resolved: List[Path] = []
        for p in self._paths:
            if not p.exists():
                continue
            if p.is_file():
                resolved.append(p.resolve())
            elif p.is_dir():
                # Discover data files recursively
                for cand in p.rglob("*"):
                    if (
                        cand.is_file()
                        and not cand.name.startswith(".")
                        and not cand.name.endswith(".gitkeep")
                        and any(
                            cand.name.lower().endswith(ext)
                            for ext in SUPPORTED_FILE_EXTENSIONS
                        )
                    ):
                        resolved.append(cand.resolve())

        # Return unique and deterministically sorted paths
        return sorted(list(set(resolved)))

    def health_check(self) -> bool:
        """Verify that configured data path(s) exist and contain readable files.

        Returns:
            True if at least one accessible data file is found and readable, False otherwise.
        """
        try:
            files = self._resolve_files()
            if not files:
                return False
            for f in files:
                if not f.exists() or not f.is_file():
                    return False
                if not os.access(f, os.R_OK):
                    return False
            return True
        except Exception:
            return False

    def fetch_ais_data(self, request: AISSearchRequest) -> pd.DataFrame:
        """Query and retrieve canonical AIS observations matching search criteria.

        Reuses AIS-02 `load_ais_csv`, AIS-07 `filter_by_time_window`, and AIS-06
        `filter_by_radius`. Does not invent origin timestamps when source_timestamp
        is None, maintaining strict boundaries `[request.start_time, request.end_time]`.

        Args:
            request: An AISSearchRequest defining spatio-temporal query parameters.

        Returns:
            A pandas DataFrame adhering to the canonical AIS schema with 'distance_km'.
            Returns an empty DataFrame with canonical columns if no observations match.

        Raises:
            TypeError: If request is not an AISSearchRequest instance.
            AISProviderNotFoundError: If configured files/directories do not exist or no data files found.
            AISProviderError: If data loading or filtering fails.
        """
        if not isinstance(request, AISSearchRequest):
            raise TypeError(
                f"request must be an instance of AISSearchRequest, got {type(request).__name__}"
            )

        # Check if any configured path exists
        any_path_exists = any(p.exists() for p in self._paths)
        if not any_path_exists:
            raise AISProviderNotFoundError(
                f"Configured AIS data path(s) not found: {self._raw_path_input}"
            )

        files = self._resolve_files()
        if not files:
            raise AISProviderNotFoundError(
                f"No AIS data files found in configured data path(s): {self._raw_path_input}"
            )

        matched_dfs: List[pd.DataFrame] = []
        canonical_cols_template: Optional[List[str]] = None

        for file_path in files:
            try:
                if self.cache_raw and file_path in self._file_cache:
                    df = self._file_cache[file_path].copy()
                else:
                    df = load_ais_csv(file_path)
                    if self.cache_raw:
                        self._file_cache[file_path] = df.copy()
            except FileNotFoundError as exc:
                raise AISProviderNotFoundError(
                    f"AIS data file not found: {file_path}"
                ) from exc
            except (AISDataLoaderError, AISInvalidFileError) as exc:
                raise AISProviderError(
                    f"Error loading AIS data from {file_path}: {exc}"
                ) from exc
            except Exception as exc:
                raise AISProviderError(
                    f"Unexpected error loading AIS data from {file_path}: {exc}"
                ) from exc

            if canonical_cols_template is None and not df.empty:
                cols = list(df.columns)
                if "distance_km" not in cols:
                    cols.append("distance_km")
                canonical_cols_template = cols

            if df.empty:
                continue

            # 1. Temporal Filtering
            # Authoritative boundaries are request.start_time and request.end_time.
            if (
                request.source_timestamp is not None
                and request.start_time <= request.source_timestamp <= request.end_time
            ):
                before_minutes = (
                    request.source_timestamp - request.start_time
                ).total_seconds() / 60.0
                after_minutes = (
                    request.end_time - request.source_timestamp
                ).total_seconds() / 60.0
                df_temporal = filter_by_time_window(
                    data=df,
                    origin_timestamp=request.source_timestamp,
                    before_minutes=before_minutes,
                    after_minutes=after_minutes,
                    retain_full_segments=False,
                )
            else:
                # Calculate internal midpoint solely to satisfy filter_by_time_window's interface
                span_seconds = (request.end_time - request.start_time).total_seconds()
                midpoint = request.start_time + pd.Timedelta(seconds=span_seconds / 2.0)
                half_window_minutes = span_seconds / 120.0
                df_temporal = filter_by_time_window(
                    data=df,
                    origin_timestamp=midpoint,
                    window_minutes=half_window_minutes,
                    retain_full_segments=False,
                )

            # Authoritative exact boundary enforcement (inclusive)
            df_temporal = df_temporal[
                (df_temporal["timestamp"] >= request.start_time)
                & (df_temporal["timestamp"] <= request.end_time)
            ].copy()

            if df_temporal.empty:
                continue

            # 2. Spatial Filtering
            df_spatial = filter_by_radius(
                data=df_temporal,
                center_latitude=request.latitude,
                center_longitude=request.longitude,
                radius_km=request.radius_km,
                buffer_km=request.buffer_km,
                use_bounding_box=True,
            )

            if not df_spatial.empty:
                matched_dfs.append(df_spatial)

        # 3. Aggregate results
        if matched_dfs:
            combined = pd.concat(matched_dfs, ignore_index=True)
            combined = combined.drop_duplicates(
                subset=["mmsi", "timestamp"], keep="last"
            )
            combined = combined.sort_values(
                by=["mmsi", "timestamp"]
            ).reset_index(drop=True)
            return combined

        # Empty result fallback with canonical schema
        cols = canonical_cols_template or (
            REQUIRED_COLUMNS + ["is_suspicious_zero", "distance_km"]
        )
        return pd.DataFrame(columns=cols)
