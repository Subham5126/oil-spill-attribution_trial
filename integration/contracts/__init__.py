"""Integration Contracts Package.

Exposes data contracts connecting Member 4 (Ocean/Drift) and Member 5 (AIS/Attribution).
"""

from integration.contracts.spill_contract import (
    OceanDriftResult,
    SpillObservation,
)

__all__ = [
    "SpillObservation",
    "OceanDriftResult",
]
