"""Test Suite for Forensic PDF Report Generation, Data Consistency, and Snapshot Isolation."""

import re
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.database import get_session
from backend.services.pdf_report_service import PDFReportService
from backend.services.pipeline_service import PipelineService
from backend.models.investigation import InvestigationModel


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def seed_inv_48d499():
    """Ensure INV-2026-48D499 is populated with exact canonical benchmark data."""
    db = get_session()
    existing = db.query(InvestigationModel).filter(InvestigationModel.investigation_id == "INV-2026-48D499").first()
    canonical_result = {
        "incident_id": "INV-2026-48D499",
        "primary_suspect": {
            "mmsi": 371123000,
            "vessel_name": "STANFORD ENERGY",
            "imo": "9384801",
            "callsign": "HP8921",
            "flag": "Panama",
            "vessel_type": "Tanker",
            "confidence_score": 88.9,
            "confidence_level": "HIGH",
            "distance_to_spill_km": 10.21,
            "distance_to_track_km": 3.74,
            "scores": {
                "spatial": 0.898,
                "temporal": 0.900,
                "trajectory": 0.963,
                "behaviour": 0.850,
            },
            "confidence_factors": {
                "spatial_proximity": 89.8,
                "temporal_coincidence": 90.0,
                "trajectory_alignment": 96.3,
                "kinematic_behaviour": 85.0,
            },
            "closest_point": {
                "latitude": 25.88,
                "longitude": 54.52,
                "timestamp": "2026-04-18T02:45:00Z",
            },
        },
        "candidate_vessels": [
            {
                "mmsi": 371123000,
                "vessel_name": "STANFORD ENERGY",
                "confidence_score": 88.9,
                "distance_to_spill_km": 10.21,
                "distance_to_track_km": 3.74,
                "scores": {
                    "spatial": 0.898,
                    "temporal": 0.900,
                    "trajectory": 0.963,
                    "behaviour": 0.850,
                },
            },
            {
                "mmsi": 403512000,
                "vessel_name": "AL DURRAH",
                "confidence_score": 64.2,
                "distance_to_spill_km": 14.80,
                "distance_to_track_km": 6.10,
                "scores": {
                    "spatial": 0.650,
                    "temporal": 0.700,
                    "trajectory": 0.600,
                    "behaviour": 0.620,
                },
            },
        ],
        "pipeline_execution": {
            "status": "PASS",
            "pipeline_run_id": "RUN-2026-48D499-001",
            "snapshot_id": "INV-2026-48D499 / RUN-2026-48D499-001 / V2",
        },
    }
    if not existing:
        inv = InvestigationModel(
            investigation_id="INV-2026-48D499",
            title="Sentinel-1 SAR Oil Slick Detection (Sirri Island Corridor)",
            region="Persian Gulf (Sirri / UAE Corridor)",
            priority="High",
            status="Active",
            pipeline_status="COMPLETED",
            observation_timestamp=datetime(2026, 4, 18, 2, 45, tzinfo=timezone.utc),
            sar_acquisition_time=datetime(2026, 4, 18, 2, 45, tzinfo=timezone.utc),
            sar_acquisition_time_source="Sentinel-1 SAR Manifest SAFE",
            sar_acquisition_time_verified=True,
            centroid_lat=25.88,
            centroid_lon=54.52,
            spill_area_km2=4.85,
            suspect_vessel="STANFORD ENERGY",
            match_confidence=88.9,
            image_id="00064",
            source_image_path="data/sentinel_images/00064.tif",
            result_json=canonical_result,
        )
        db.add(inv)
        db.commit()
    else:
        existing.result_json = canonical_result
        db.commit()
    db.close()


def test_pdf_service_direct_generation():
    """Verify that PDFReportService produces valid, high-fidelity PDF bytes for the active investigation."""
    db = get_session()
    service = PDFReportService(db)
    
    pdf_bytes = service.generate_pdf_bytes("INV-2026-48D499")
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 50000, f"Expected substantial PDF (>50KB), got {len(pdf_bytes)} bytes"
    assert pdf_bytes.startswith(b"%PDF"), "Must start with %PDF header"
    assert b"%%EOF" in pdf_bytes[-2048:], "Must contain %%EOF marker near end"
    db.close()


def test_canonical_result_consistency_inv_2026_48d499(client):
    """TEST 1 & Acceptance Test: Verify zero analytical mismatch between website/API and PDF for INV-2026-48D499."""
    # 1. Fetch canonical M5 result via API endpoints (/result and /attribution)
    res_resp = client.get("/api/investigations/INV-2026-48D499/result")
    assert res_resp.status_code == 200
    api_res = res_resp.json()

    attr_resp = client.get("/api/investigations/INV-2026-48D499/attribution")
    assert attr_resp.status_code == 200
    assert attr_resp.json() == api_res

    ps = api_res["primary_suspect"]
    assert ps["vessel_name"] == "STANFORD ENERGY"
    assert ps["confidence_score"] == 88.9
    assert ps["confidence_level"] == "HIGH"
    assert ps["distance_to_track_km"] == 3.74
    assert ps["distance_to_spill_km"] == 10.21
    assert ps["scores"]["spatial"] == 0.898
    assert ps["scores"]["temporal"] == 0.9
    assert ps["scores"]["trajectory"] == 0.963
    assert ps["scores"]["behaviour"] == 0.85

    # 2. Generate PDF and verify exact analytical text alignment
    db = get_session()
    service = PDFReportService(db)
    pdf_bytes = service.generate_pdf_bytes("INV-2026-48D499")
    assert pdf_bytes.startswith(b"%PDF")
    text = pdf_bytes.decode("latin1", errors="ignore")

    # Primary vessel identity
    assert "STANFORD ENERGY" in text

    # Canonical overall confidence score (88.9 / 100)
    assert "88.9 / 100" in text
    assert "88.9%" in text

    # Dual distances exposed without ambiguity
    assert "3.74 km" in text
    assert "10.21 km" in text
    assert "drift corridor" in text
    assert "slick centroid" in text

    # Factor-level breakdown
    assert "89.8%" in text  # Spatial Proximity
    assert "90.0%" in text  # Temporal Coincidence
    assert "96.3%" in text  # Trajectory Alignment
    assert "85.0%" in text  # Kinematic Behaviour

    # Candidate ranking order
    assert "#1" in text
    assert "AL DURRAH" in text  # Candidate #2

    # Source of truth assurance footnote
    assert "CANONICAL EVIDENCE ASSURANCE" in text
    db.close()


def test_investigation_isolation_and_evidence_integrity():
    """TEST 3: Verify strict evidentiary isolation: Case A data cannot leak into Case B report."""
    db = get_session()
    service = PDFReportService(db)

    # Ensure a second distinct investigation exists for isolation verification
    inv2_id = "INV-TEST-ISOLATION-99"
    existing_inv2 = db.query(InvestigationModel).filter(InvestigationModel.investigation_id == inv2_id).first()
    if not existing_inv2:
        inv2 = InvestigationModel(
            investigation_id=inv2_id,
            title="Red Sea Offshore Incident Case B",
            status="Completed",
            priority="Medium",
            region="Red Sea / Yanbu Corridor",
            image_id="00643",
            pipeline_status="COMPLETED",
            sar_acquisition_time=datetime(2018, 9, 22, 5, 30, tzinfo=timezone.utc),
            sar_acquisition_time_source="project_scene_catalog",
            sar_acquisition_time_verified=True,
            centroid_lat=24.1234,
            centroid_lon=37.5678,
            spill_area_km2=2.15,
            match_confidence=78.5,
            result_json={
                "spill_metadata": {"spill_id": inv2_id},
                "gis_measurement": {"area": {"sq_kilometers": 2.15}, "centroid": {"latitude": 24.1234, "longitude": 37.5678}},
                "ocean_drift": {"probable_origin": {"latitude": 24.2, "longitude": 37.5, "drift_distance_km": 12.4}},
                "primary_suspect": {
                    "vessel_name": "ISOLATION TANKER BETA",
                    "mmsi": 987654321,
                    "imo": "9876543",
                    "vessel_type": "TANKER",
                    "confidence_score": 78.5,
                    "confidence_level": "HIGH",
                    "distance_to_track_km": 2.10,
                    "distance_to_spill_km": 8.45,
                    "scores": {"overall": 0.85, "spatial": 0.82, "temporal": 0.85, "trajectory": 0.88, "behaviour": 0.80},
                },
                "candidate_vessels": [
                    {
                        "rank": 1,
                        "vessel_name": "ISOLATION TANKER BETA",
                        "mmsi": 987654321,
                        "imo": "9876543",
                        "vessel_type": "TANKER",
                        "confidence_score": 78.5,
                        "distance_to_track_km": 2.10,
                        "distance_to_spill_km": 8.45,
                        "scores": {"overall": 0.85},
                    }
                ],
                "pipeline_execution": {
                    "status": "PASS",
                    "pipeline_run_id": f"RUN-{inv2_id}-001",
                    "snapshot_id": f"{inv2_id} / RUN-{inv2_id}-001 / V2",
                },
            },
        )
        db.add(inv2)
        db.commit()

    pdf_main = service.generate_pdf_bytes("INV-2026-48D499")
    pdf_inv2 = service.generate_pdf_bytes(inv2_id)

    # Verify ID isolation
    assert b"INV-2026-48D499" in pdf_main
    assert b"INV-TEST-ISOLATION-99" not in pdf_main

    assert b"INV-TEST-ISOLATION-99" in pdf_inv2
    assert b"INV-2026-48D499" not in pdf_inv2

    # Verify vessel isolation
    assert b"STANFORD ENERGY" in pdf_main
    assert b"ISOLATION TANKER BETA" not in pdf_main

    assert b"ISOLATION TANKER BETA" in pdf_inv2
    assert b"STANFORD ENERGY" not in pdf_inv2

    db.close()


def test_multi_pipeline_run_isolation():
    """TEST 2: Verify that report generation binds strictly to the requested completed run."""
    db = get_session()
    service = PDFReportService(db)

    inv = db.query(InvestigationModel).filter(InvestigationModel.investigation_id == "INV-2026-48D499").first()
    assert inv is not None

    current_run_id = inv.result_json.get("pipeline_execution", {}).get("pipeline_run_id")

    # Generate with correct run_id
    pdf_bytes = service.generate_pdf_bytes("INV-2026-48D499", pipeline_run_id=current_run_id)
    assert pdf_bytes.startswith(b"%PDF")

    # Attempt to request with mismatched/foreign run_id -> must be rejected
    with pytest.raises(ValueError, match="does not match persisted snapshot run"):
        service.generate_pdf_bytes("INV-2026-48D499", pipeline_run_id="RUN-ANOTHER-EXECUTION-999")

    db.close()


def test_inconsistent_snapshot_validation_blocking():
    """TEST 4 & 5: Verify pre-generation validator blocks PDF generation if snapshot data is inconsistent."""
    db = get_session()
    service = PDFReportService(db)

    inv = db.query(InvestigationModel).filter(InvestigationModel.investigation_id == "INV-2026-48D499").first()
    assert inv is not None

    # Corrupt primary suspect to simulate analytical mismatch
    corrupted_result = dict(inv.result_json)
    corrupted_result["primary_suspect"] = {"mmsi": 999999999, "vessel_name": "CORRUPTED VESSEL"}

    with pytest.raises(ValueError, match="Report generation blocked"):
        service.validate_investigation_snapshot(inv, corrupted_result)

    # Test invalid confidence score bound
    corrupted_score_result = dict(inv.result_json)
    corrupted_score_result["primary_suspect"]["confidence_score"] = 999.0
    with pytest.raises(ValueError, match="Report generation blocked"):
        service.validate_investigation_snapshot(inv, corrupted_score_result)

    db.close()


def test_pdf_download_endpoint(client):
    """Verify GET /api/investigations/{id}/report/pdf endpoint contract."""
    response = client.get("/api/investigations/INV-2026-48D499/report/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert 'attachment; filename="OILTRACE_INV-2026-48D499_Forensic_Report.pdf"' in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 50000


def test_pdf_view_inline_endpoint(client):
    """Verify GET /api/investigations/{id}/report/pdf/view endpoint contract."""
    response = client.get("/api/investigations/INV-2026-48D499/report/pdf/view")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert 'inline; filename="OILTRACE_INV-2026-48D499_Forensic_Report.pdf"' in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_legacy_download_endpoint_now_returns_pdf(client):
    """Verify legacy /report/download now serves the authoritative PDF instead of Markdown."""
    response = client.get("/api/investigations/INV-2026-48D499/report/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert not response.content.startswith(b"# OILTRACE Investigation Report")


def test_invalid_investigation_safe_error(client):
    """Verify that non-existent investigation returns safe error without leaking traceback."""
    response = client.get("/api/investigations/NON_EXISTENT_ID/report/pdf")
    assert response.status_code == 500
    data = response.json()
    assert "Unable to generate forensic PDF." in data["detail"]


def test_investigation_report_endpoint_inv_2026_7fdb03(client):
    """Regression test: GET /api/investigations/INV-2026-7FDB03/report returns 200 with authoritative SAR timestamp."""
    db = get_session()
    existing = db.query(InvestigationModel).filter(InvestigationModel.investigation_id == "INV-2026-7FDB03").first()
    if not existing:
        inv = InvestigationModel(
            investigation_id="INV-2026-7FDB03",
            title="Sentinel-1 SAR Oil Slick Detection (Persian Gulf)",
            region="Persian Gulf (Sirri / UAE Corridor)",
            priority="High",
            status="Active",
            pipeline_status="COMPLETED",
            observation_timestamp=datetime(2018, 1, 30, 0, 0, tzinfo=timezone.utc),
            sar_acquisition_time=datetime(2018, 1, 30, 0, 0, tzinfo=timezone.utc),
            sar_acquisition_time_source="Sentinel-1 SAR Manifest SAFE",
            sar_acquisition_time_verified=True,
            centroid_lat=27.7668,
            centroid_lon=49.2042,
            spill_area_km2=5.2,
            suspect_vessel="STANFORD ENERGY",
            match_confidence=88.9,
            image_id="00031",
            source_image_path="data/sentinel_images/00031.tif",
            result_json={
                "incident_id": "INV-2026-7FDB03",
                "spill_metadata": {
                    "spill_id": "INV-2026-7FDB03",
                    "centroid": {"latitude": 27.7668, "longitude": 49.2042},
                    "area_km2": 5.2,
                    "perimeter_km": 14.5,
                    "sar_acquisition_time": "2018-01-30T00:00:00Z",
                    "confidence": 0.889,
                },
                "primary_suspect": {
                    "mmsi": 371123000,
                    "vessel_name": "STANFORD ENERGY",
                    "confidence_score": 88.9,
                    "distance_to_spill_km": 10.21,
                    "distance_to_track_km": 3.74,
                },
                "ocean_drift": {
                    "backward_drift_window": "2018-01-29T00:00:00Z to 2018-01-30T00:00:00Z",
                    "forward_drift_window": "2018-01-30T00:00:00Z to 2018-01-31T00:00:00Z",
                    "probable_origin": {"latitude": 27.7668, "longitude": 49.2042},
                    "uncertainty_radius_km": 2.5,
                },
            },
        )
        db.add(inv)
        db.commit()

    # 1. Result endpoint must return 200
    res_resp = client.get("/api/investigations/INV-2026-7FDB03/result")
    assert res_resp.status_code == 200
    result_data = res_resp.json()
    assert result_data["spill_metadata"]["spill_id"] == "INV-2026-7FDB03"

    # 2. Report endpoint must return 200
    rep_resp = client.get("/api/investigations/INV-2026-7FDB03/report")
    assert rep_resp.status_code == 200
    report_data = rep_resp.json()
    assert report_data["investigation_id"] == "INV-2026-7FDB03"

    sections = report_data.get("sections", {})
    inv_info = sections.get("2_incident_information", {})
    ocean_info = sections.get("5_oceanographic_analysis", {})

    expected_ts = "2018-01-30T00:00:00Z"
    assert inv_info.get("acquisition_time") == expected_ts
    assert ocean_info.get("sar_acquisition") == expected_ts
    assert ocean_info.get("ocean_reference_time") == expected_ts
    assert expected_ts in ocean_info.get("backward_drift_window", "")
    assert expected_ts in ocean_info.get("forward_drift_window", "")

    # 3. PDF endpoint must also succeed
    pdf_resp = client.get("/api/investigations/INV-2026-7FDB03/report/pdf/view")
    assert pdf_resp.status_code == 200
    assert pdf_resp.content.startswith(b"%PDF")

