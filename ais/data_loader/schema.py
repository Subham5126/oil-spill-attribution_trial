"""AIS Data Loader Schema and Constants.

This module defines canonical column names, provider alias mappings,
validation constraints, sentinel values, and custom exceptions for the
AIS data ingestion pipeline according to ITU-R M.1371 and project specifications.
"""

from typing import Dict, List, Set

# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class AISDataLoaderError(Exception):
    """Base exception for all AIS data loader errors."""
    pass


class AISMissingRequiredColumnError(AISDataLoaderError):
    """Raised when one or more required canonical columns cannot be resolved."""
    def __init__(self, missing_columns: List[str], available_columns: List[str]):
        self.missing_columns = missing_columns
        self.available_columns = available_columns
        super().__init__(
            f"Missing required AIS column(s): {missing_columns}. "
            f"Available resolved columns: {available_columns}"
        )


class AISInvalidFileError(AISDataLoaderError):
    """Raised when an input file is invalid, missing, empty, or corrupted."""
    pass


# ---------------------------------------------------------------------------
# Canonical Column Definitions
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS: List[str] = [
    "mmsi",
    "timestamp",
    "latitude",
    "longitude",
]

OPTIONAL_COLUMNS: List[str] = [
    "sog",
    "cog",
    "heading",
    "vessel_name",
    "imo",
    "callsign",
    "vessel_type",
    "nav_status",
    "length",
    "width",
    "draught",
]

QUALITY_FLAG_COLUMNS: List[str] = [
    "is_suspicious_zero",
]

CANONICAL_COLUMNS: List[str] = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# ---------------------------------------------------------------------------
# Column Alias Mappings
#
# Note: In accordance with ARCHITECTURE.md Section 30 and AIS-01 research,
# generic single-letter coordinate symbols ('x', 'y') are intentionally
# EXCLUDED to prevent accidental coordinate-axis transposition.
# ---------------------------------------------------------------------------

COLUMN_ALIASES: Dict[str, List[str]] = {
    "mmsi": ["mmsi", "user_id", "userid"],
    "timestamp": [
        "basedatetime",
        "base_date_time",
        "timestamp",
        "time",
        "date_time_utc",
        "datetime",
        "date_time",
    ],
    "latitude": ["lat", "latitude"],
    "longitude": ["lon", "long", "longitude"],
    "sog": ["sog", "speed", "speed_over_ground", "speedoverground"],
    "cog": ["cog", "course", "course_over_ground", "courseoverground"],
    "heading": ["heading", "true_heading", "trueheading", "th"],
    "vessel_name": ["vesselname", "vessel_name", "name", "ship_name", "shipname"],
    "imo": ["imo", "imo_number", "imonumber"],
    "callsign": ["callsign", "call_sign"],
    "vessel_type": ["vesseltype", "vessel_type", "ship_type", "shiptype"],
    "nav_status": [
        "status",
        "nav_status",
        "navstatus",
        "navigational_status",
        "navigationalstatus",
    ],
    "length": ["length", "loa"],
    "width": ["width", "beam"],
    "draught": ["draft", "draught"],
}

# ---------------------------------------------------------------------------
# Physical Validation Constraints & Sentinels (ITU-R M.1371)
# ---------------------------------------------------------------------------

LAT_MIN: float = -90.0
LAT_MAX: float = 90.0

LON_MIN: float = -180.0
LON_MAX: float = 180.0

SOG_MIN: float = 0.0
SOG_MAX: float = 102.2
SOG_SENTINEL: float = 102.3  # ITU-R default for "not available"

COG_MIN: float = 0.0
COG_MAX: float = 360.0
COG_SENTINEL: float = 360.0  # ITU-R default for "not available"

HEADING_MIN: float = 0.0
HEADING_MAX: float = 359.0
HEADING_SENTINEL: float = 511.0  # ITU-R default for "not available"

LATITUDE_SENTINEL: float = 91.0  # ITU-R default for "not available"
LONGITUDE_SENTINEL: float = 181.0  # ITU-R default for "not available"

# MMSI bounds: standard ship stations are 9-digit integers (200000000 - 775999999)
# Coastal / SAR stations may start with 00 or 111, but MMSI must be a valid positive integer.
MMSI_MIN: int = 100000000
MMSI_MAX: int = 999999999
