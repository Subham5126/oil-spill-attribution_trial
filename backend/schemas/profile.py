"""User Profile Pydantic Schemas."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class UserProfileBase(BaseModel):
    """Base fields for an analyst profile."""

    full_name: str = Field(..., description="Analyst full name with honorific/rank")
    call_sign: str = Field(..., description="Operational call sign or identification number")
    title: str = Field(..., description="Official job title or designation")
    organization: str = Field(..., description="Maritime authority or agency")
    station: str = Field(..., description="Assigned duty station or base")
    clearance_level: str = Field(..., description="Security clearance and operational rank")
    email: str = Field(..., description="Official government / organizational email")
    phone: str = Field(..., description="Official desk or mobile hotline number")
    radio_frequency: str = Field(..., description="Operational VHF / HF radio monitoring channel")
    node_id: str = Field(..., description="OILTRACE hardware node identifier")
    surveillance_sector: str = Field(..., description="Assigned geographic surveillance sector or EEZ")
    authorization_scope: str = Field(..., description="Legal and regulatory enforcement mandate")
    signing_key_id: Optional[str] = Field("ECDSA-P384-DG-SHIP-2026-KEY-7F9A", description="ECDSA cryptographic evidence key fingerprint")
    department: Optional[str] = Field("Maritime Environmental Enforcement Division", description="Department or division")
    specialization: Optional[str] = Field("SAR Detection & Hydrodynamic Drift Reconstruction", description="Operational specialization")
    avatar_url: Optional[str] = Field(None, description="Base64 encoded avatar image or URL")
    bio: Optional[str] = Field(None, description="Short professional bio and specialization notes")


class UserProfileUpdate(BaseModel):
    """Payload for updating an analyst profile (all fields optional)."""

    full_name: Optional[str] = None
    call_sign: Optional[str] = None
    title: Optional[str] = None
    organization: Optional[str] = None
    station: Optional[str] = None
    clearance_level: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    radio_frequency: Optional[str] = None
    node_id: Optional[str] = None
    surveillance_sector: Optional[str] = None
    authorization_scope: Optional[str] = None
    signing_key_id: Optional[str] = None
    department: Optional[str] = None
    specialization: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None


class UserProfileResponse(UserProfileBase):
    """Response payload for analyst profile."""

    id: str = "default-analyst"

    model_config = ConfigDict(from_attributes=True)
