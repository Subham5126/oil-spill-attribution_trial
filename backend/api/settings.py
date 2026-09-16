"""Settings & Attribution Calibration API Router."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.logging import logger
from backend.models.settings import AttributionCalibrationModel

router = APIRouter(prefix="/settings", tags=["Settings"])


class AttributionCalibrationPayload(BaseModel):
    spatial_proximity: float = Field(..., description="Spatial proximity weight (0-1 or 0-100)")
    temporal_overlap: float = Field(..., description="Temporal coincidence weight (0-1 or 0-100)")
    drift_consistency: float = Field(..., description="Trajectory/drift alignment weight (0-1 or 0-100)")
    track_consistency: float = Field(..., description="Kinematic behaviour weight (0-1 or 0-100)")
    vessel_type_relevance: Optional[float] = Field(None, description="Vessel type correlation weight")
    ais_quality: Optional[float] = Field(None, description="AIS quality & completeness weight")
    notes: Optional[str] = Field(None, description="Operational justification or note")


def _format_calibration(calib: AttributionCalibrationModel) -> Dict[str, Any]:
    w = calib.to_weights_dict()
    total = sum(w.values())
    pcts = {k: round((v / total) * 100.0, 1) for k, v in w.items()}
    return {
        "version": calib.version,
        "is_active": calib.is_active,
        "notes": calib.notes or "Operational scientific default calibration",
        "weights": {k: round(v, 4) for k, v in w.items()},
        "percentages": pcts,
        "spatial_proximity": pcts.get("spatial_proximity", 0.0),
        "temporal_overlap": pcts.get("temporal_overlap", 0.0),
        "drift_consistency": pcts.get("drift_consistency", 0.0),
        "track_consistency": pcts.get("track_consistency", 0.0),
        "vessel_type_relevance": pcts.get("vessel_type_relevance", 0.0),
        "ais_quality": pcts.get("ais_quality", 0.0),
        "total_percentage": round(sum(pcts.values()), 1),
        "updated_at": calib.updated_at.isoformat() if calib.updated_at else datetime.now(timezone.utc).isoformat(),
    }


def get_or_create_default_calibration(db: Session) -> AttributionCalibrationModel:
    active = db.query(AttributionCalibrationModel).filter_by(is_active=True).first()
    if not active:
        active = AttributionCalibrationModel(
            version="CALIB-v1-DEFAULT",
            spatial_proximity_weight=0.35,
            temporal_overlap_weight=0.25,
            drift_consistency_weight=0.15,
            track_consistency_weight=0.10,
            vessel_type_relevance_weight=0.08,
            ais_quality_weight=0.07,
            is_active=True,
            notes="Baseline multi-criteria forensic calibration (35% Spatial, 25% Temporal, 15% Drift, 10% Kinematics, 8% Type, 7% Quality)",
        )
        db.add(active)
        db.commit()
        db.refresh(active)
    return active


@router.get("/attribution")
def get_attribution_calibration(db: Session = Depends(get_db)):
    """Retrieve active vessel attribution scoring calibration weights and version."""
    if not db:
        return {
            "version": "CALIB-v1-DEFAULT",
            "is_active": True,
            "notes": "Baseline multi-criteria forensic calibration",
            "weights": {
                "spatial_proximity": 0.35,
                "temporal_overlap": 0.25,
                "drift_consistency": 0.15,
                "track_consistency": 0.10,
                "vessel_type_relevance": 0.08,
                "ais_quality": 0.07,
            },
            "percentages": {
                "spatial_proximity": 35.0,
                "temporal_overlap": 25.0,
                "drift_consistency": 15.0,
                "track_consistency": 10.0,
                "vessel_type_relevance": 8.0,
                "ais_quality": 7.0,
            },
            "total_percentage": 100.0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    calib = get_or_create_default_calibration(db)
    return _format_calibration(calib)


@router.put("/attribution")
def update_attribution_calibration(
    payload: AttributionCalibrationPayload,
    db: Session = Depends(get_db),
):
    """Persist new attribution scoring weights with strict 100% sum validation."""
    if not db:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database persistence unavailable",
        )

    # Normalize incoming values (handle either fractions 0-1 or percentages 0-100)
    vals = {
        "spatial_proximity": payload.spatial_proximity,
        "temporal_overlap": payload.temporal_overlap,
        "drift_consistency": payload.drift_consistency,
        "track_consistency": payload.track_consistency,
    }

    # If user provided 4 sliders (or auxiliary weights)
    aux_type = payload.vessel_type_relevance if payload.vessel_type_relevance is not None else 0.0
    aux_ais = payload.ais_quality if payload.ais_quality is not None else 0.0
    vals["vessel_type_relevance"] = aux_type
    vals["ais_quality"] = aux_ais

    # Detect if inputs are on 0-100 scale
    is_percentage = any(v > 1.0 for v in vals.values())
    if is_percentage:
        total_sum = sum(vals.values())
        if abs(total_sum - 100.0) > 1.0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Attribution weights must sum to 100% (currently {total_sum:.1f}%)",
            )
        # Convert to unit ratios
        norm_weights = {k: v / total_sum for k, v in vals.items()}
    else:
        total_sum = sum(vals.values())
        if abs(total_sum - 1.0) > 0.01:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Attribution fractional weights must sum to 1.0 (currently {total_sum:.2f})",
            )
        norm_weights = {k: v / total_sum for k, v in vals.items()}

    # Deactivate previous active calibrations
    db.query(AttributionCalibrationModel).filter_by(is_active=True).update({"is_active": False})

    # Count existing versions to create monotonic version tag
    count = db.query(AttributionCalibrationModel).count()
    new_version = f"CALIB-v{count + 1}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"

    new_calib = AttributionCalibrationModel(
        version=new_version,
        spatial_proximity_weight=norm_weights["spatial_proximity"],
        temporal_overlap_weight=norm_weights["temporal_overlap"],
        drift_consistency_weight=norm_weights["drift_consistency"],
        track_consistency_weight=norm_weights["track_consistency"],
        vessel_type_relevance_weight=norm_weights["vessel_type_relevance"],
        ais_quality_weight=norm_weights["ais_quality"],
        is_active=True,
        notes=payload.notes or f"Updated calibration {new_version}",
    )
    db.add(new_calib)
    db.commit()
    db.refresh(new_calib)

    logger.info(f"[SETTINGS] Persisted new active attribution calibration: {new_version}")
    return _format_calibration(new_calib)
