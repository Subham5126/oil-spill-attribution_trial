"""Drift Analysis & Simulation API Router."""

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.schemas.drift import DriftSimulateRequest, OceanDriftResponse
from backend.services.drift_service import DriftService

router = APIRouter(prefix="/drift", tags=["Drift"])


@router.get("/{investigation_id}", response_model=OceanDriftResponse)
def get_drift_results(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve ocean current, windage, and Lagrangian drift results for an incident."""
    service = DriftService(db)
    return service.get_drift_result(investigation_id)


@router.post("/simulate")
def simulate_custom_drift(payload: DriftSimulateRequest, db: Session = Depends(get_db)):
    """Run on-demand Lagrangian simulation from custom coordinates, duration, and timestep.

    Matches frontend runCustomDriftSimulation contract.
    """
    service = DriftService(db)
    return service.simulate_custom_drift(payload)


@router.get("/{investigation_id}/current-field")
def get_current_field(investigation_id: str, db: Session = Depends(get_db)):
    """Retrieve real Copernicus Marine surface current vectors for the incident domain."""
    from backend.services.reconstruction_service import ReconstructionService
    service = ReconstructionService(db)
    recon = service.get_reconstruction(investigation_id)
    return recon.get("ocean_current_field", {"type": "FeatureCollection", "features": []})

