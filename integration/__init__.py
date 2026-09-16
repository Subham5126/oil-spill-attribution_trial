"""Integrated Oil Spill Attribution Pipeline Package.

Bridges Member 4 Ocean and Drift models with Member 5 AIS and Attribution engines.
"""

from integration.adapters.ocean_ais_adapter import (
    adapt_ocean_drift_to_ais,
    compute_bearing_deg,
)
from integration.contracts.spill_contract import (
    OceanDriftResult,
    SpillObservation,
)
from integration.pipeline import (
    PipelineResult,
    run_spill_attribution_pipeline,
)

__all__ = [
    "SpillObservation",
    "OceanDriftResult",
    "adapt_ocean_drift_to_ais",
    "compute_bearing_deg",
    "PipelineResult",
    "run_spill_attribution_pipeline",
]
