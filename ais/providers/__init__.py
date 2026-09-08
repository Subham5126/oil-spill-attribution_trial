"""AIS Provider Layer.

Provides provider-independent interfaces and concrete implementations for querying
and retrieving AIS vessel observations across local datasets and remote data services.
"""

from ais.providers.base import (
    AISProvider,
    AISProviderConfigError,
    AISProviderConnectionError,
    AISProviderError,
    AISProviderNotFoundError,
)
from ais.providers.local import LocalAISProvider

__all__ = [
    "AISProvider",
    "LocalAISProvider",
    "AISProviderError",
    "AISProviderNotFoundError",
    "AISProviderConfigError",
    "AISProviderConnectionError",
]
