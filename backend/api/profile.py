"""Analyst User Profile API Router."""

from __future__ import annotations

import base64
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.logging import logger
from backend.models.profile import UserProfileModel
from backend.schemas.profile import UserProfileResponse, UserProfileUpdate

router = APIRouter(prefix="/profile", tags=["User Profile"])

DEFAULT_PROFILE = {
    "id": "default-analyst",
    "full_name": "Cmdr. Rajesh K. Varma",
    "call_sign": "CG-FOR-904",
    "title": "Senior Marine Forensic Analyst",
    "organization": "DG Shipping / Indian Coast Guard",
    "station": "Western Seaboard Command, Mumbai",
    "clearance_level": "Class-I Maritime Forensic Authority",
    "email": "rajesh.varma@dgshipping.gov.in",
    "phone": "+91 (22) 2269-8000 (Ext 402)",
    "radio_frequency": "VHF Ch 16 / DSC 2187.5 kHz",
    "node_id": "Node #IND-WEST-01",
    "surveillance_sector": "Exclusive Economic Zone (EEZ) — West Sector",
    "authorization_scope": "MARPOL Annex I Enforcement & Legal Prosecution",
    "signing_key_id": "ECDSA-P384-DG-SHIP-2026-KEY-7F9A",
    "department": "Maritime Environmental Enforcement Division",
    "specialization": "SAR Detection & Hydrodynamic Drift Reconstruction",
    "avatar_url": None,
    "bio": "Principal investigator specializing in synthetic aperture radar (SAR) hydrocarbon detection, hydrodynamic drift hindcast analysis, and AIS maritime correlation for environmental enforcement.",
}

ALLOWED_MIME_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
MAX_PHOTO_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def _get_or_create_profile(db: Session) -> UserProfileModel:
    """Retrieve existing analyst profile or seed default if table empty."""
    profile = db.query(UserProfileModel).filter(UserProfileModel.id == "default-analyst").first()
    if not profile:
        profile = UserProfileModel(**DEFAULT_PROFILE)
        db.add(profile)
        db.commit()
        db.refresh(profile)
        logger.info("Default analyst profile initialized in database.")
    return profile


@router.get("", response_model=UserProfileResponse)
def get_user_profile(db: Session = Depends(get_db)):
    """Retrieve the logged-in analyst's profile."""
    try:
        profile = _get_or_create_profile(db)
        return profile
    except Exception as e:
        logger.error(f"Error fetching analyst profile: {e}")
        return UserProfileResponse(**DEFAULT_PROFILE)


@router.put("", response_model=UserProfileResponse)
def update_user_profile(payload: UserProfileUpdate, db: Session = Depends(get_db)):
    """Update analyst profile fields and persist."""
    try:
        profile = _get_or_create_profile(db)
        update_data = payload.model_dump(exclude_unset=True)

        for key, value in update_data.items():
            if hasattr(profile, key):
                setattr(profile, key, value)

        db.commit()
        db.refresh(profile)
        logger.info(f"Analyst profile updated for '{profile.full_name}'.")
        return profile
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update analyst profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update analyst profile: {str(e)}",
        )


@router.post("/photo", response_model=UserProfileResponse)
async def upload_profile_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload and persist a new profile avatar image (JPG, PNG, WEBP, max 5MB)."""
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type '{content_type}'. Allowed formats are JPG, PNG, and WEBP.",
        )

    content = await file.read()
    if len(content) > MAX_PHOTO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed size of 5 MB ({len(content)} bytes).",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    try:
        b64_str = base64.b64encode(content).decode("utf-8")
        data_uri = f"data:{content_type};base64,{b64_str}"

        profile = _get_or_create_profile(db)
        profile.avatar_url = data_uri
        db.commit()
        db.refresh(profile)
        logger.info(f"Updated profile photo for {profile.full_name} ({len(content)} bytes).")
        return profile
    except Exception as e:
        db.rollback()
        logger.error(f"Photo upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Photo upload failed: {str(e)}",
        )


@router.delete("/photo", response_model=UserProfileResponse)
def delete_profile_photo(db: Session = Depends(get_db)):
    """Remove user's custom profile avatar and revert to default initials."""
    try:
        profile = _get_or_create_profile(db)
        profile.avatar_url = None
        db.commit()
        db.refresh(profile)
        logger.info(f"Removed custom profile photo for {profile.full_name}.")
        return profile
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to remove profile photo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove profile photo: {str(e)}",
        )
