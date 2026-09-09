"""Drift Modelling Adapter (Member 4 Integration).

Bridges the backend to Member 4 Lagrangian advection, backward hindcasting,
probable origin determination, and spatial uncertainty calculation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import pandas as pd
import xarray as xr

from ocean.drift import Particle, hindcast_particles, simulate_particles
from ocean.drift.origin import analyze_origin
from ocean.drift.uncertainty import calculate_uncertainty
from integration.contracts.spill_contract import OceanDriftResult, SpillObservation


class DriftAdapter:
    """Service adapter interfacing with Member 4 Drift simulation modules."""

    @staticmethod
    def run_simulation(
        particles: List[Particle],
        current_ds: xr.Dataset,
        wind_ds: xr.Dataset,
        start_time: datetime,
        num_steps: int = 2,
        timestep_seconds: int = 3600,
    ) -> pd.DataFrame:
        """Run forward particle drift simulation."""
        return simulate_particles(
            particles=particles,
            current_dataset=current_ds,
            wind_dataset=wind_ds,
            start_time=start_time,
            num_steps=num_steps,
            timestep_seconds=timestep_seconds,
        )

    @staticmethod
    def run_hindcast(
        particles: List[Particle],
        current_ds: xr.Dataset,
        wind_ds: xr.Dataset,
        observation_time: datetime,
        duration_seconds: int = 14400,
        timestep_seconds: int = 3600,
    ) -> pd.DataFrame:
        """Run backward particle drift hindcast."""
        return hindcast_particles(
            particles=particles,
            current_dataset=current_ds,
            wind_dataset=wind_ds,
            observation_time=observation_time,
            duration_seconds=duration_seconds,
            timestep_seconds=timestep_seconds,
        )

    @staticmethod
    def analyze_release_origin(
        hindcast_df: pd.DataFrame,
        coverage_level: float = 0.5,
    ) -> Dict[str, Any]:
        """Infer probable release origin candidate clusters and score ranking."""
        return analyze_origin(hindcast_df, coverage_level=coverage_level)

    @staticmethod
    def calculate_spatial_uncertainty(
        trajectories: pd.DataFrame,
        timestamp: Any,
        confidence_level: float = 0.95,
    ) -> Any:
        """Calculate empirical dispersion radius and bounding envelope."""
        return calculate_uncertainty(
            trajectories=trajectories,
            timestamp=timestamp,
            confidence_level=confidence_level,
        )
