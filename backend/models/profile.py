"""User Profile Database Model.

Persists logged-in analyst credentials, authority details, and node configurations.
"""

from __future__ import annotations

from sqlalchemy import Column, String, Text
from backend.models.base import Base, TimestampMixin


class UserProfileModel(Base, TimestampMixin):
    """Analyst User Profile model."""

    __tablename__ = "user_profiles"

    id = Column(String(64), primary_key=True, default="default-analyst")
    full_name = Column(String(128), nullable=False, default="Cmdr. Rajesh K. Varma")
    call_sign = Column(String(64), nullable=False, default="CG-FOR-904")
    title = Column(String(128), nullable=False, default="Senior Marine Forensic Analyst")
    organization = Column(String(128), nullable=False, default="DG Shipping / Indian Coast Guard")
    station = Column(String(128), nullable=False, default="Western Seaboard Command, Mumbai")
    clearance_level = Column(String(64), nullable=False, default="Class-I Maritime Forensic Authority")
    email = Column(String(128), nullable=False, default="rajesh.varma@dgshipping.gov.in")
    phone = Column(String(64), nullable=False, default="+91 (22) 2269-8000 (Ext 402)")
    radio_frequency = Column(String(64), nullable=False, default="VHF Ch 16 / DSC 2187.5 kHz")
    node_id = Column(String(64), nullable=False, default="Node #IND-WEST-01")
    surveillance_sector = Column(String(128), nullable=False, default="Exclusive Economic Zone (EEZ) — West Sector")
    authorization_scope = Column(String(128), nullable=False, default="MARPOL Annex I Enforcement & Legal Prosecution")
    signing_key_id = Column(String(128), nullable=False, default="ECDSA-P384-DG-SHIP-2026-KEY-7F9A")
    department = Column(String(128), nullable=True, default="Maritime Environmental Enforcement Division")
    specialization = Column(String(128), nullable=True, default="SAR Detection & Hydrodynamic Drift Reconstruction")
    avatar_url = Column(Text, nullable=True)
    bio = Column(Text, nullable=True, default="Principal investigator specializing in synthetic aperture radar (SAR) hydrocarbon detection, hydrodynamic drift hindcast analysis, and AIS maritime correlation for environmental enforcement.")
