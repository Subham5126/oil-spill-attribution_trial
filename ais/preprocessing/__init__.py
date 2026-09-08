"""AIS Preprocessing and Cleaning Module.

Provides kinematic derivation, sequence-aware anomaly detection, and data-quality
cleaning for canonical AIS datasets.
"""

from ais.preprocessing.cleaner import CleaningReport, clean_ais_data
from ais.preprocessing.config import CleaningConfig
from ais.preprocessing.kinematics import (
    compute_inter_ping_kinematics,
    haversine_distance_nm,
)

__all__ = [
    "CleaningConfig",
    "CleaningReport",
    "compute_inter_ping_kinematics",
    "haversine_distance_nm",
    "clean_ais_data",
]
