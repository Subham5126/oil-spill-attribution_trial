"""AIS Data Loader Module.

Exposes the canonical AIS data loading, decompression, validation, and schema definitions.
"""

from ais.data_loader.loader import (
    clean_ais_dataframe,
    detect_compression,
    load_ais_csv,
    resolve_column_mapping,
)
from ais.data_loader.schema import (
    AISDataLoaderError,
    AISInvalidFileError,
    AISMissingRequiredColumnError,
    CANONICAL_COLUMNS,
    COLUMN_ALIASES,
    OPTIONAL_COLUMNS,
    QUALITY_FLAG_COLUMNS,
    REQUIRED_COLUMNS,
)

__all__ = [
    "load_ais_csv",
    "detect_compression",
    "resolve_column_mapping",
    "clean_ais_dataframe",
    "AISDataLoaderError",
    "AISMissingRequiredColumnError",
    "AISInvalidFileError",
    "REQUIRED_COLUMNS",
    "OPTIONAL_COLUMNS",
    "QUALITY_FLAG_COLUMNS",
    "CANONICAL_COLUMNS",
    "COLUMN_ALIASES",
]
