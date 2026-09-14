from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.services.layer_service import LayerService

router = APIRouter(prefix="/layers", tags=["GIS Layers"])


@router.get("/geojson")
def get_latest_layers_geojson(
    mode: Optional[str] = Query(default=None, description="Run mode filter"),
    db: Session = Depends(get_db),
):
    """Serve the active multi-layer GeoJSON FeatureCollection for frontend MapLibre rendering."""
    service = LayerService(db)
    return JSONResponse(content=service.get_latest_layers_geojson(mode=mode))


@router.get("/{investigation_id}")
def get_layers_for_investigation(investigation_id: str, db: Session = Depends(get_db)):
    """Serve GeoJSON FeatureCollection corresponding to a specific incident."""
    service = LayerService(db)
    return JSONResponse(content=service.get_layers_for_investigation(investigation_id))
