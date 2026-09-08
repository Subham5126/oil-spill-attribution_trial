"""Provider-independent abstract base class and exceptions for AIS data providers.

Defines the contract for fetching AIS observations across different backends
(local file archives, geospatial databases, and remote public/commercial APIs).
"""

from __future__ import annotations

import abc
from typing import Optional

import pandas as pd

from ais.integration.search_request import AISSearchRequest


class AISProviderError(Exception):
    """Base exception for all AIS provider errors."""

    pass


class AISProviderNotFoundError(AISProviderError):
    """Raised when configured dataset, file, or endpoint is not found."""

    pass


class AISProviderConfigError(AISProviderError):
    """Raised when provider configuration or parameters are invalid."""

    pass


class AISProviderConnectionError(AISProviderError):
    """Raised when connection to an external or remote AIS provider fails."""

    pass


class AISProvider(abc.ABC):
    """Abstract base class for all AIS data providers.

    All providers accept an AISSearchRequest and return a canonical pandas DataFrame
    containing AIS observations within the requested spatial and temporal bounds.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique human-readable identifier for the provider."""
        raise NotImplementedError

    @abc.abstractmethod
    def health_check(self) -> bool:
        """Verify that the provider backend or data source is accessible and available.

        Returns:
            True if the provider is ready to serve queries, False otherwise.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_ais_data(self, request: AISSearchRequest) -> pd.DataFrame:
        """Query and retrieve canonical AIS observations matching search criteria.

        Args:
            request: An AISSearchRequest defining spatio-temporal query parameters.

        Returns:
            A pandas DataFrame adhering to the project's canonical AIS schema.
            Returns an empty DataFrame with canonical columns if no observations match.

        Raises:
            AISProviderError: If the query fails or data cannot be retrieved.
            TypeError: If request is not an AISSearchRequest instance.
        """
        raise NotImplementedError
