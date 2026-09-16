"""Sentinel-1 Imagery Discovery API Router."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.services.image_service import ImageService

router = APIRouter(prefix="/images", tags=["Imagery"])


@router.get("", response_model=List[Dict[str, Any]])
def list_available_images(
    region: Optional[str] = Query(None, description="Filter by marine region"),
    limit: int = Query(50, ge=1, le=500, description="Max images to return"),
):
    """List available real Sentinel-1 SAR GeoTIFF scenes from repository inventory."""
    return ImageService.list_images(region=region, limit=limit)


@router.get("/{image_id}", response_model=Dict[str, Any])
def get_image_details(image_id: str):
    """Retrieve metadata, spatial bounds, and CRS for a specific Sentinel-1 image."""
    meta = ImageService.get_image_metadata(image_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sentinel-1 image '{image_id}' not found in inventory or local storage.",
        )
    return meta
