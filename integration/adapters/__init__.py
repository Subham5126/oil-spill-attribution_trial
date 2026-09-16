"""Integration Adapters Package.

Bridges Member 4 Ocean and Drift models into Member 5 AIS and Attribution engines.
"""

from integration.adapters.gis_ocean_adapter import (
    extract_spill_observation,
    initialize_particles_from_spill,
    point_in_polygon,
)
from integration.adapters.ocean_ais_adapter import (
    adapt_ocean_drift_to_ais,
    compute_bearing_deg,
)

__all__ = [
    "adapt_ocean_drift_to_ais",
    "compute_bearing_deg",
    "extract_spill_observation",
    "initialize_particles_from_spill",
    "point_in_polygon",
]
