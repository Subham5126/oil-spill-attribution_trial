"""Unit tests for Forensic Reconstruction Service (Incident Replay)."""

import pytest
from unittest.mock import MagicMock
from backend.services.reconstruction_service import ReconstructionService, calculate_heading, haversine_distance_km
from backend.models.investigation import InvestigationModel


def test_calculate_heading_cardinal_directions():
    # Due North: lat increases, lon constant -> heading 0
    h_north = calculate_heading(0.0, 0.0, 1.0, 0.0)
    assert abs(h_north - 0.0) < 0.1

    # Due East: lat constant, lon increases -> heading 90
    h_east = calculate_heading(0.0, 0.0, 0.0, 1.0)
    assert abs(h_east - 90.0) < 0.1

    # Due South: lat decreases, lon constant -> heading 180
    h_south = calculate_heading(1.0, 0.0, 0.0, 0.0)
    assert abs(h_south - 180.0) < 0.1

    # Due West: lat constant, lon decreases -> heading 270
    h_west = calculate_heading(0.0, 1.0, 0.0, 0.0)
    assert abs(h_west - 270.0) < 0.1


def test_haversine_distance_km():
    # Approx distance between (0, 0) and (1, 0) is ~111 km
    d = haversine_distance_km(0.0, 0.0, 1.0, 0.0)
    assert 110.0 < d < 112.0


def test_reconstruction_service_compilation():
    mock_db = MagicMock()
    mock_inv = MagicMock(spec=InvestigationModel)
    mock_inv.investigation_id = "INV-TEST-001"
    mock_inv.title = "Test Incident"
    mock_inv.region = "North Sea"
    mock_inv.centroid_lat = 55.2
    mock_inv.centroid_lon = 5.8
    mock_inv.spill_area_km2 = 3.5
    mock_inv.match_confidence = 0.92
    mock_inv.image_id = "test_scene.tif"
    mock_inv.observation_timestamp = None

    # Real polygon in geojson_layers
    mock_inv.geojson_layers = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "layer_type": "oil_spill",
                    "area_sq_km": 3.5,
                    "perimeter_km": 12.4,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[5.8, 55.2], [5.82, 55.21], [5.81, 55.22], [5.8, 55.2]]],
                },
            },
            {
                "type": "Feature",
                "properties": {"layer_type": "drift_hindcast"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[5.7, 55.1], [5.75, 55.15], [5.8, 55.2]],
                },
            },
        ],
    }

    mock_inv.result_json = {
        "gis_measurement": {
            "centroid": {"latitude": 55.2, "longitude": 5.8},
        },
        "ocean_drift": {
            "surface_velocity": {
                "u_eastward_m_s": 0.12,
                "v_northward_m_s": 0.08,
                "speed_m_s": 0.144,
                "direction_deg": 56.3,
            },
            "probable_origin": {
                "latitude": 55.1,
                "longitude": 5.7,
                "drift_distance_km": 15.2,
                "timestamp": "2026-09-12T00:00:00Z",
            },
        },
        "primary_suspect": {
            "vessel_name": "NORDIC GLORY",
            "mmsi": 219000111,
            "vessel_type": "Oil Tanker",
            "latitude": 55.12,
            "longitude": 5.71,
            "trajectory": [
                {"latitude": 55.08, "longitude": 5.68, "timestamp": "2026-09-11T22:00:00Z"},
                {"latitude": 55.12, "longitude": 5.71, "timestamp": "2026-09-12T00:00:00Z"},
                {"latitude": 55.16, "longitude": 5.74, "timestamp": "2026-09-12T02:00:00Z"},
            ],
            "scores": {"overall": 0.94},
        },
    }

    mock_db.query.return_value.filter.return_value.first.return_value = mock_inv

    svc = ReconstructionService(mock_db)
    rec = svc.get_reconstruction("INV-TEST-001")

    assert rec["investigation_id"] == "INV-TEST-001"
    assert rec["reconstruction_status"] == "FULL_RECONSTRUCTION"
    assert rec["vessel"]["vessel_name"] == "NORDIC GLORY"
    assert rec["vessel"]["has_track"] is True
    assert rec["spill_geometry"]["type"] == "Polygon"
    assert rec["spill_geometry"]["area_sq_km"] == 3.5
    assert len(rec["drift_trajectory"]["coordinates"]) >= 2
    assert len(rec["timeline"]) == 5
    assert "release_window" in rec
    assert "FORENSIC RECONSTRUCTION" in rec["disclaimer"]


def test_reconstruction_missing_vessel_honest_status():
    mock_db = MagicMock()
    mock_inv = MagicMock(spec=InvestigationModel)
    mock_inv.investigation_id = "INV-NO-VESSEL"
    mock_inv.title = "Unattributed Incident"
    mock_inv.region = "North Sea"
    mock_inv.centroid_lat = 55.2
    mock_inv.centroid_lon = 5.8
    mock_inv.spill_area_km2 = 1.2
    mock_inv.match_confidence = 0.99
    mock_inv.image_id = "00003.tif"
    mock_inv.observation_timestamp = None
    mock_inv.geojson_layers = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"layer_type": "oil_spill", "area_sq_km": 1.2, "perimeter_km": 8.0},
                "geometry": {"type": "Polygon", "coordinates": [[[5.8, 55.2], [5.82, 55.21], [5.8, 55.2]]]},
            }
        ]
    }
    mock_inv.result_json = {
        "candidate_vessels": [],
        "primary_suspect": None,
        "ocean_drift": {
            "surface_velocity": {"u_eastward_m_s": 0.1, "v_northward_m_s": 0.05, "speed_m_s": 0.11},
            "probable_origin": {"latitude": 55.1, "longitude": 5.7, "timestamp": "2026-09-12T00:00:00Z"},
        }
    }
    mock_db.query.return_value.filter.return_value.first.return_value = mock_inv

    svc = ReconstructionService(mock_db)
    rec = svc.get_reconstruction("INV-NO-VESSEL")

    assert rec["reconstruction_status"] == "VESSEL_UNAVAILABLE"
    assert rec["vessel"] is None
    assert rec["ais_track"] is None
    assert rec["timeline"][0]["name"] == "Spill Origin Area"
    assert rec["timeline"][0]["active_vessel"] is False
