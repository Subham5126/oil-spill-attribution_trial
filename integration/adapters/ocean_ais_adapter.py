"""Member 4 (Ocean/Drift) to Member 5 (AIS/Attribution) Adapter.

Maps OceanDriftResult / analyze_origin() / calculate_uncertainty() into:
1. AISSearchRequest (for querying AIS providers)
2. AISIntegrationResult (for spatial/temporal AIS filters)
3. OriginMetadata (for attribution scoring engine)
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from ais.integration.adapter import (
    AISIntegrationResult,
    adapt_drift_origin_result,
)
from ais.integration.search_request import AISSearchRequest
from attribution.models import OriginMetadata, validate_origin_metadata
from integration.contracts.spill_contract import OceanDriftResult, SpillObservation


def compute_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate geographic initial bearing (0..360° from North) from point 1 to point 2."""
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dlon = np.radians(lon2 - lon1)
    y = np.sin(dlon) * np.cos(phi2)
    x = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(dlon)
    bearing = np.degrees(np.arctan2(y, x))
    return float((bearing + 360.0) % 360.0)


def adapt_ocean_drift_to_ais(
    ocean_result: Union[OceanDriftResult, Dict[str, Any]],
    spill_observation: Optional[Union[SpillObservation, Dict[str, Any]]] = None,
    buffer_km: float = 1.0,
    before_minutes: float = 30.0,
    after_minutes: float = 30.0,
    default_radius_km: float = 5.0,
) -> Tuple[AISIntegrationResult, OriginMetadata]:
    """Bridge Member 4 OceanDriftResult to Member 5 AIS & Attribution contracts.

    Respects the uncertainty radius from calculate_uncertainty() (DRIFT-06) as the
    authoritative base radius, deriving effective search bounding box and AISSearchRequest.
    Computes and injects the explicit drift direction vector into source_info for ATTR-02.

    Args:
        ocean_result: OceanDriftResult instance or dictionary from analyze_origin().
        spill_observation: Optional SpillObservation instance or dict with observation metadata.
        buffer_km: Empirical buffer in km added to uncertainty radius (default: 1.0 km).
        before_minutes: Time window in minutes before origin timestamp (default: 30.0 min).
        after_minutes: Time window in minutes after origin timestamp (default: 30.0 min).
        default_radius_km: Fallback radius in km if neither uncertainty nor area is available.

    Returns:
        Tuple containing:
        - AISIntegrationResult (for AIS querying and AIS-06 / AIS-07 filtering)
        - OriginMetadata (for ATTR-02 attribution scoring)
    """
    if ocean_result is None:
        raise ValueError("ocean_result must be provided and non-null")

    # 1. Standardize observation dict
    obs_dict: Optional[Dict[str, Any]] = None
    if spill_observation is not None:
        if isinstance(spill_observation, SpillObservation):
            obs_dict = spill_observation.to_dict()
        elif isinstance(spill_observation, dict):
            obs_dict = spill_observation
        else:
            raise TypeError(
                f"spill_observation must be SpillObservation or dict, got {type(spill_observation)}"
            )
    elif isinstance(ocean_result, OceanDriftResult) and ocean_result.spill_observation is not None:
        obs_dict = ocean_result.spill_observation.to_dict()
    elif isinstance(ocean_result, dict) and "spill_observation" in ocean_result:
        obs_dict = ocean_result["spill_observation"]

    # 2. Determine uncertainty radius and candidate object
    explicit_radius_km: Optional[float] = None
    explicit_drift_deg: Optional[float] = None
    uncertainty_dict: Optional[Dict[str, Any]] = None

    if isinstance(ocean_result, OceanDriftResult):
        explicit_radius_km = ocean_result.uncertainty_radius_km
        explicit_drift_deg = ocean_result.drift_direction_deg
        if ocean_result.uncertainty is not None:
            uncertainty_dict = {
                "timestamp": ocean_result.uncertainty.timestamp.isoformat(),
                "particle_count": ocean_result.uncertainty.particle_count,
                "centroid_latitude": float(ocean_result.uncertainty.centroid_latitude),
                "centroid_longitude": float(ocean_result.uncertainty.centroid_longitude),
                "spread_km": float(ocean_result.uncertainty.spread_km),
                "radius_km": float(ocean_result.uncertainty.uncertainty_radius_km),
                "confidence_level": float(ocean_result.uncertainty.confidence_level),
                "min_latitude": float(ocean_result.uncertainty.min_latitude),
                "max_latitude": float(ocean_result.uncertainty.max_latitude),
                "min_longitude": float(ocean_result.uncertainty.min_longitude),
                "max_longitude": float(ocean_result.uncertainty.max_longitude),
            }

        # Build payload compatible with Member 5 adapter
        member4_payload = ocean_result.to_dict()
        # Ensure best candidate region has radius_km explicitly set
        if explicit_radius_km is not None and explicit_radius_km > 0:
            setattr(ocean_result.best_candidate.region, "radius_km", explicit_radius_km)
    else:
        member4_payload = ocean_result
        if "uncertainty" in ocean_result and isinstance(ocean_result["uncertainty"], dict):
            raw_unc = ocean_result["uncertainty"]
            r = raw_unc.get("radius_km") or raw_unc.get("uncertainty_radius_km")
            if r is not None and np.isfinite(r) and r > 0:
                explicit_radius_km = float(r)
            uncertainty_dict = raw_unc
        if "drift_direction_deg" in ocean_result:
            explicit_drift_deg = float(ocean_result["drift_direction_deg"])

    # 3. Calculate drift heading if not explicit, but origin and observation points are known
    best_cand = member4_payload.get("best_candidate")
    if explicit_drift_deg is None and obs_dict is not None and best_cand is not None:
        obs_lat = obs_dict.get("latitude")
        obs_lon = obs_dict.get("longitude")
        reg = getattr(best_cand, "region", None)
        orig_lat = getattr(reg, "centroid_lat", None) if reg else None
        orig_lon = getattr(reg, "centroid_lon", None) if reg else None
        if (
            obs_lat is not None
            and obs_lon is not None
            and orig_lat is not None
            and orig_lon is not None
        ):
            explicit_drift_deg = compute_bearing_deg(
                orig_lat, orig_lon, obs_lat, obs_lon
            )

    # 4. Invoke Member 5 adapter
    effective_default_radius = (
        float(explicit_radius_km)
        if (explicit_radius_km is not None and explicit_radius_km > 0.0)
        else float(default_radius_km)
    )
    integration_result = adapt_drift_origin_result(
        member4_output=member4_payload,
        spill_observation=obs_dict,
        default_radius_km=effective_default_radius,
        buffer_km=buffer_km,
        before_minutes=before_minutes,
        after_minutes=after_minutes,
    )

    # 5. Enrich origin_data uncertainty dict if detailed UncertaintyResult was provided
    if uncertainty_dict is not None:
        merged_uncertainty = dict(integration_result.origin_data.get("uncertainty", {}))
        merged_uncertainty.update(uncertainty_dict)
        integration_result.origin_data["uncertainty"] = merged_uncertainty

    # 6. Build strongly typed OriginMetadata with source_info for ATTR-02
    origin_meta = validate_origin_metadata(integration_result)
    if explicit_drift_deg is not None:
        origin_meta.source_info["drift_direction_deg"] = explicit_drift_deg
        origin_meta.source_info["explicit_drift_direction_deg"] = explicit_drift_deg

    return integration_result, origin_meta
