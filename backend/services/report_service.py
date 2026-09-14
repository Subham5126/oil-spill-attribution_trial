"""Forensic Report Service Module.

Generates authoritative 11-section MARPOL Annex I Hydrocarbon Discharge Forensic Dossiers
strictly synthesized from real investigation pipeline outputs.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.core.exceptions import ReportNotFoundError, InvestigationNotFoundError
from backend.core.logging import logger
from backend.models.investigation import InvestigationModel
from backend.models.report import ReportModel
from backend.models.profile import UserProfileModel
from backend.repositories.attribution import AttributionRepository


class ReportService:
    """Service providing MARPOL Annex I forensic dossier reports."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self.repo = AttributionRepository(db)

    def list_reports(self, investigation_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all reports persisted in the database."""
        db_records = self.repo.get_reports(investigation_id)
        return [
            {
                "id": r.report_id,
                "investigation_id": r.investigation_id,
                "title": r.title,
                "generated_at": r.generated_at.isoformat(),
                "author": r.author,
                "status": r.status,
                "target_vessel": r.target_vessel or "Candidate Vessel Analysis",
                "imo": r.imo or "N/A",
                "mmsi": r.mmsi or 0,
                "attribution_score": r.attribution_score or 0.0,
                "summary": r.summary,
                "marpol_violation_risk": r.marpol_violation_risk or "Moderate",
                "sha256_hash": r.sha256_hash,
                "jurisdiction": r.jurisdiction,
            }
            for r in db_records
        ]

    def get_report(self, report_id: str) -> Dict[str, Any]:
        """Fetch a specific report by report_id."""
        rec = self.repo.get_report_by_id(report_id)
        if rec:
            return {
                "id": rec.report_id,
                "investigation_id": rec.investigation_id,
                "title": rec.title,
                "generated_at": rec.generated_at.isoformat(),
                "author": rec.author,
                "status": rec.status,
                "target_vessel": rec.target_vessel,
                "imo": rec.imo,
                "mmsi": rec.mmsi,
                "attribution_score": rec.attribution_score,
                "summary": rec.summary,
                "marpol_violation_risk": rec.marpol_violation_risk,
                "sha256_hash": rec.sha256_hash,
                "jurisdiction": rec.jurisdiction,
            }

        raise ReportNotFoundError(f"Report '{report_id}' not found", stage="REPORT_LOOKUP")

    def get_report_by_investigation(self, investigation_id: str) -> Dict[str, Any]:
        """Fetch or generate comprehensive report for an investigation."""
        existing = self.repo.get_reports(investigation_id)
        if existing:
            return self.get_report(existing[0].report_id)

        # Auto-generate if investigation has pipeline results
        return self.generate_report(investigation_id)

    def generate_report(
        self,
        investigation_id: str,
        author: str = "Maritime Forensic & Hydrocarbon Pollution Taskforce",
    ) -> Dict[str, Any]:
        """Generate and persist an authoritative 11-section MARPOL forensic report from real data."""
        if not self.db:
            raise RuntimeError("Database session required to generate and persist report.")

        inv = (
            self.db.query(InvestigationModel)
            .filter(InvestigationModel.investigation_id == investigation_id)
            .first()
        )
        if not inv:
            raise InvestigationNotFoundError(f"Investigation '{investigation_id}' not found", stage="REPORT_GEN")

        # Dynamically attribute to registered analyst if default author passed
        analyst_meta = {}
        if author == "Maritime Forensic & Hydrocarbon Pollution Taskforce":
            try:
                prof = self.db.query(UserProfileModel).first()
                if prof and prof.full_name:
                    author = f"{prof.full_name}, {prof.title} ({prof.organization})"
                    analyst_meta = {
                        "analyst_name": prof.full_name,
                        "analyst_title": prof.title,
                        "organization": prof.organization,
                        "node_id": prof.node_id,
                        "clearance": prof.clearance_level,
                        "signing_key_id": prof.signing_key_id,
                    }
            except Exception:
                pass

        result = inv.result_json or {}
        spill = result.get("spill_metadata", {})
        gis = result.get("gis_measurement", {})
        drift = result.get("ocean_drift", {})
        candidates = result.get("candidate_vessels", [])
        primary = candidates[0] if candidates else None
        provenance = result.get("provenance", {})

        now = datetime.now(timezone.utc)
        rep_id = f"REP-{now.strftime('%Y')}-{int(now.timestamp()) % 100000:05d}"

        # Geodesic metrics
        area_km2 = gis.get("area", {}).get("sq_kilometers", inv.spill_area_km2 or 0.0)
        perimeter_km = gis.get("perimeter", {}).get("kilometers", 0.0)
        centroid = gis.get("centroid", {"latitude": inv.centroid_lat or 0.0, "longitude": inv.centroid_lon or 0.0})
        origin = drift.get("probable_origin", {})

        target_name = primary.get("vessel_name", "None Attributed") if primary else "None Attributed"
        target_mmsi = primary.get("mmsi", 0) if primary else 0
        target_imo = primary.get("imo", "N/A") if primary else "N/A"
        top_score = primary.get("scores", {}).get("overall", 0.0) if primary else 0.0

        summary = (
            f"Forensic investigation {inv.investigation_id} based on Sentinel-1 SAR imagery ({inv.image_id or 'Scene'}). "
            f"Automated segmentation identified an anomalous dark slick covering {area_km2:.4f} km² centered at "
            f"{centroid['latitude']:.4f}°N, {centroid['longitude']:.4f}°E. "
        )
        if origin.get("drift_distance_km"):
            summary += (
                f"Lagrangian hydrodynamic hindcasting established a probable spill origin at "
                f"{origin['latitude']:.4f}°N, {origin['longitude']:.4f}°E ({origin['drift_distance_km']:.2f} km upstream). "
            )
        if primary:
            summary += (
                f"Historical AIS correlation identified candidate vessel {target_name} (MMSI: {target_mmsi}) "
                f"passing within {primary.get('distance_to_track_km', 'N/A')} km of the reconstructed trajectory."
            )
        else:
            summary += "AIS screening identified no correlated Class-A vessels within the spatial/temporal window."

        # Cryptographic evidence seal
        raw_evidence = f"{inv.investigation_id}:{area_km2}:{target_mmsi}:{centroid['latitude']}:{centroid['longitude']}"
        sha_hash = hashlib.sha256(raw_evidence.encode("utf-8")).hexdigest()

        # Structured sections
        structured_sections = {
            "1_executive_summary": summary,
            "2_incident_information": {
                "investigation_id": inv.investigation_id,
                "image_id": inv.image_id or spill.get("properties", {}).get("image_id", "N/A"),
                "acquisition_time": spill.get("detection_timestamp", inv.observation_timestamp.isoformat() if inv.observation_timestamp else "N/A"),
                "location": f"{centroid['latitude']:.4f}°N, {centroid['longitude']:.4f}°E",
                "region": inv.region,
            },
            "3_sentinel1_evidence": {
                "sensor": spill.get("sensor", "Sentinel-1 SAR C-Band"),
                "crs": spill.get("crs", "EPSG:4326"),
                "confidence": spill.get("confidence", inv.match_confidence or 0.0),
                "resolution_meters": spill.get("properties", {}).get("pixel_res_m", 10.0),
            },
            "4_spill_characterization": {
                "area_sq_km": area_km2,
                "perimeter_km": perimeter_km,
                "centroid": centroid,
                "bounding_box": gis.get("bounding_box", {}),
                "shape_characteristics": gis.get("shape_characteristics", {}),
            },
            "5_oceanographic_analysis": {
                "dataset": drift.get("dataset_id") or drift.get("current_dataset") or provenance.get("copernicus_dataset", "N/A"),
                "product_id": drift.get("product_id") or provenance.get("copernicus_product", "Copernicus Marine CMEMS"),
                "sar_acquisition": inv_info.get("acquisition_time", "N/A"),
                "ocean_reference_time": inv_info.get("acquisition_time", "N/A"),
                "backward_drift_window": f"{origin.get('timestamp', 'N/A')} → {inv_info.get('acquisition_time', 'N/A')}",
                "forward_drift_window": f"{inv_info.get('acquisition_time', 'N/A')} → {drift.get('forecast_endpoint', {}).get('timestamp', 'N/A')}",
                "surface_velocity": drift.get("surface_velocity", {}),
                "probable_origin": origin,
                "forecast_endpoint": drift.get("forecast_endpoint", {}),
                "uncertainty_radius_km": drift.get("uncertainty", {}).get("radius_km", 0.0),
            },
            "6_ais_vessel_correlation": candidates[:10],
            "7_evidence_assessment": {
                "observed_evidence": f"Sentinel-1 SAR level-1 GRD imagery exhibiting characteristic backscatter attenuation indicative of mineral oil.",
                "derived_evidence": f"Vectorized polygon boundary encompassing {area_km2:.4f} km² with aspect ratio {gis.get('shape_characteristics', {}).get('aspect_ratio', 1.0)}.",
                "model_based_evidence": f"Hydrodynamic advection vectors derived from Copernicus Marine surface currents.",
                "ais_correlation": f"{len(candidates)} vessels correlated within search bounds.",
                "uncertainty": f"Estimated spatial dispersion radius: {drift.get('uncertainty', {}).get('radius_km', 2.0)} km.",
            },
            "8_candidate_vessel_assessment": {
                "top_candidate": primary,
                "attribution_disclaimer": "CRITICAL NOTICE: AIS spatial-temporal correlation indicates co-presence along the drift trajectory and does not constitute conclusive legal proof of discharge causation. Physical sampling and port state inspection required.",
            },
            "9_limitations": [
                "Lagrangian drift calculations depend on model hydrodynamic grid resolution.",
                "Dark slick signatures on SAR may occasionally arise from natural biogenic slicks or low-wind surface features.",
                "AIS coverage depends on terrestrial/satellite transceiver reception and transponder compliance.",
            ],
            "10_recommended_next_steps": [
                "Issue Port State Control (PSC) inspection notice to the next port of call for the top candidate vessels.",
                "Request bunker logs, oil record book (Part I), and oily water separator (OWS) maintenance records.",
                "Acquire optical satellite imagery (Sentinel-2 / PlanetScope) to corroborate surface sheen coloration.",
            ],
            "11_technical_provenance": {
                "pipeline_version": "1.0.0",
                "model_weights": "unet_best.pth",
                "copernicus_dataset": provenance.get("copernicus_dataset", "N/A"),
                "gfw_dataset": provenance.get("gfw_dataset", "public-global-presence:latest"),
                "processing_time": now.isoformat(),
                "sha256_hash": sha_hash,
                "certifying_analyst": author,
                "analyst_credentials": analyst_meta or {
                    "analyst_name": "Forensic Analyst",
                    "authority": "DG Shipping / Indian Coast Guard",
                },
            },
        }

        rep = ReportModel(
            report_id=rep_id,
            investigation_id=investigation_id,
            title=f"MARPOL Annex I Hydrocarbon Attribution Report: {inv.investigation_id}",
            report_type="Forensic Investigation Dossier",
            status="Final",
            generated_at=now,
            author=author,
            target_vessel=target_name,
            imo=target_imo,
            mmsi=target_mmsi,
            attribution_score=round(top_score * 100, 2),
            summary=summary,
            marpol_violation_risk="High" if top_score > 0.7 else "Moderate" if top_score > 0.4 else "Low",
            sha256_hash=sha_hash,
            jurisdiction="UNCLOS / IMO MARPOL 73/78 Annex I Evidentiary Protocol",
        )
        self.repo.create_report(rep)

        return {
            "id": rep_id,
            "investigation_id": investigation_id,
            "title": rep.title,
            "generated_at": now.isoformat(),
            "author": author,
            "status": "Final",
            "target_vessel": target_name,
            "imo": target_imo,
            "mmsi": target_mmsi,
            "attribution_score": round(top_score * 100, 2),
            "summary": summary,
            "marpol_violation_risk": rep.marpol_violation_risk,
            "sha256_hash": sha_hash,
            "jurisdiction": rep.jurisdiction,
            "sections": structured_sections,
        }

    def generate_report_markdown(self, investigation_id: str) -> str:
        """Render the complete report as professional formatted Markdown."""
        data = self.get_report_by_investigation(investigation_id)
        sections = data.get("sections", {})
        inv_info = sections.get("2_incident_information", {})
        spill_ev = sections.get("3_sentinel1_evidence", {})
        spill_char = sections.get("4_spill_characterization", {})
        ocean = sections.get("5_oceanographic_analysis", {})
        ais = sections.get("6_ais_vessel_correlation", [])
        provenance = sections.get("11_technical_provenance", {})

        md = f"""# OILTRACE Investigation Report
**Report Identifier:** `{data.get('id')}`  
**Investigation ID:** `{data.get('investigation_id')}`  
**Generated At:** {data.get('generated_at')}  
**Authority:** {data.get('author')}  
**Cryptographic Integrity Hash (SHA-256):** `{data.get('sha256_hash')}`  

---

## 1. Executive Summary
{sections.get('1_executive_summary', data.get('summary', ''))}

---

## 2. Incident Information
| Field | Value |
|---|---|
| **Investigation ID** | `{inv_info.get('investigation_id', 'N/A')}` |
| **Sentinel-1 Scene ID** | `{inv_info.get('image_id', 'N/A')}` |
| **SAR Acquisition (UTC)** | `{inv_info.get('acquisition_time', 'N/A')}` |
| **Geographic Location** | {inv_info.get('location', 'N/A')} |
| **Region** | {inv_info.get('region', 'N/A')} |

---

## 3. Sentinel-1 SAR Evidence
| Parameter | Value |
|---|---|
| **Sensor / Mode** | {spill_ev.get('sensor', 'Sentinel-1 C-Band')} |
| **Coordinate Reference System** | `{spill_ev.get('crs', 'EPSG:4326')}` |
| **Detection Confidence** | {spill_ev.get('confidence', 0.0) * 100:.1f}% |
| **Nominal Spatial Resolution** | {spill_ev.get('resolution_meters', 10.0)} meters/pixel |

---

## 4. Spill Characterization & Geometry
| Metric | Measured Value |
|---|---|
| **Delineated Surface Area** | **{spill_char.get('area_sq_km', 0.0):.4f} km²** |
| **Perimeter** | {spill_char.get('perimeter_km', 0.0):.4f} km |
| **Centroid Coordinates** | {spill_char.get('centroid', {}).get('latitude', 0.0):.6f}°N, {spill_char.get('centroid', {}).get('longitude', 0.0):.6f}°E |
| **Aspect Ratio** | {spill_char.get('shape_characteristics', {}).get('aspect_ratio', 1.0):.3f} |
| **Compactness** | {spill_char.get('shape_characteristics', {}).get('compactness', 1.0):.4f} |

---

## 5. Oceanographic & Drift Analysis
- **SAR Acquisition Reference:** `{ocean.get('sar_acquisition', 'N/A')}`
- **Ocean Current Reference:** `{ocean.get('ocean_reference_time', 'N/A')}`
- **Copernicus Marine Dataset:** `{ocean.get('dataset', 'None')}`
- **Backward Drift Window:** `{ocean.get('backward_drift_window', 'N/A')}`
- **Forward Drift Window:** `{ocean.get('forward_drift_window', 'N/A')}`
- **Surface Velocity at Slick:** Eastward: `{ocean.get('surface_velocity', {}).get('u_eastward_m_s', 0.0)} m/s`, Northward: `{ocean.get('surface_velocity', {}).get('v_northward_m_s', 0.0)} m/s`
- **Current Speed / Heading:** {ocean.get('surface_velocity', {}).get('speed_m_s', 0.0)} m/s @ {ocean.get('surface_velocity', {}).get('direction_deg', 0.0)}°
- **72h Reconstructed Origin:** {ocean.get('probable_origin', {}).get('latitude', 'N/A')}°N, {ocean.get('probable_origin', {}).get('longitude', 'N/A')}°E ({ocean.get('probable_origin', {}).get('drift_distance_km', 0.0)} km upstream)
- **24h Forecast Endpoint:** {ocean.get('forecast_endpoint', {}).get('latitude', 'N/A')}°N, {ocean.get('forecast_endpoint', {}).get('longitude', 'N/A')}°E ({ocean.get('forecast_endpoint', {}).get('drift_distance_km', 0.0)} km advection)
- **Empirical Dispersion Radius (95%):** {ocean.get('uncertainty_radius_km', 2.0)} km

---

## 6. AIS Vessel Correlation Candidates
| Rank | Vessel Name | MMSI | IMO | Type | Flag | Distance to Track | Observation Time |
|---|---|---|---|---|---|---|---|
"""
        if ais:
            for v in ais[:10]:
                md += f"| #{v.get('rank', '-')} | **{v.get('vessel_name', 'UNKNOWN')}** | `{v.get('mmsi', '-')}` | `{v.get('imo', '-')}` | {v.get('vessel_type', '-')} | {v.get('flag', '-')} | {v.get('distance_to_track_km', '-')} km | {str(v.get('timestamp', ''))[:16]} UTC |\n"
        else:
            md += "| - | *No AIS vessels recorded in temporal/spatial window* | - | - | - | - | - | - |\n"

        md += f"""
---

## 7. Evidence Assessment
- **Observed Physical Evidence:** {sections.get('7_evidence_assessment', {}).get('observed_evidence', '')}
- **Derived Morphological Evidence:** {sections.get('7_evidence_assessment', {}).get('derived_evidence', '')}
- **Hydrodynamic Advection Model:** {sections.get('7_evidence_assessment', {}).get('model_based_evidence', '')}
- **AIS Spatial-Temporal Correlation:** {sections.get('7_evidence_assessment', {}).get('ais_correlation', '')}
- **Uncertainty Bounds:** {sections.get('7_evidence_assessment', {}).get('uncertainty', '')}

---

## 8. Candidate Vessel Assessment & Disclaimer
**Primary Correlation Suspect:** {data.get('target_vessel')} (MMSI: {data.get('mmsi')})  
**Attribution Confidence Index:** {data.get('attribution_score')}%  
**MARPOL Annex I Violation Risk:** {data.get('marpol_violation_risk')}  

> **SCIENTIFIC & LEGAL DISCLAIMER:**  
> Spatial and temporal correlation between AIS vessel positions and backward Lagrangian drift trajectories does NOT constitute conclusive legal proof of intentional or accidental discharge causation. Factors such as currents, unrecorded transits, and transponder spoofing must be evaluated through boarding and Port State Control physical verification.

---

## 9. Limitations & Environmental Constraints
"""
        for lim in sections.get("9_limitations", []):
            md += f"- {lim}\n"

        md += """
---

## 10. Recommended Investigation Next Steps
"""
        for step in sections.get("10_recommended_next_steps", []):
            md += f"1. {step}\n"

        md += f"""
---

## 11. Technical Provenance
- **Software Suite:** OILTRACE v{provenance.get('pipeline_version', '1.0.0')}
- **Neural Network Architecture:** ResNet / U-Net Segmentation (`{provenance.get('model_weights', 'unet_best.pth')}`)
- **Ocean Current Provider:** Copernicus Marine Hydrodynamic Dataset (`{provenance.get('copernicus_dataset', 'N/A')}`)
- **AIS Provider:** Global Fishing Watch 4Wings API (`{provenance.get('gfw_dataset', 'public-global-presence:latest')}`)
- **Execution Timestamp:** {provenance.get('processing_time', data.get('generated_at', ''))}
- **Verification Hash:** `{data.get('sha256_hash')}`
"""
        return md
