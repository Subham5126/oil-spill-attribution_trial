"""AIS Integration Module.

Provides integration boundaries, adapters, and provider-independent request
contracts connecting upstream ocean drift modeling to downstream AIS services.
"""

from ais.integration.adapter import (
    AISIntegrationResult,
    adapt_drift_origin_result,
)
from ais.integration.search_request import (
    AISSearchRequest,
)

__all__ = [
    "AISSearchRequest",
    "AISIntegrationResult",
    "adapt_drift_origin_result",
]
