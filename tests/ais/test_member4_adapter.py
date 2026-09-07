"""Comprehensive unit tests for Member 4 Drift Origin Adapter and AISSearchRequest.

Tests cover:
A. Current Member 4 format
B. Radius compatibility and precedence
C. Time window handling and UTC normalization
D. Spatial calculations and bounding box generation
E. Standardized origin data format and JSON serializability
F. Strict input validation and error cases
G. Caller input immutability
H. AISSearchRequest standalone behavior
I. End-to-end compatibility with AIS-06 and AIS-07 filtering
"""

import copy
import dataclasses
import json
import math
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import pytest

from ais.filtering import filter_spatial, filter_temporal
from ais.filtering.spatial import derive_bounding_box
from ais.integration import (
    AISIntegrationResult,
    AISSearchRequest,
    adapt_drift_origin_result,
)


# ---------------------------------------------------------------------------
# Test Helpers & Synthetic Member 4 Dataclasses
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class SyntheticCandidateRegion:
    """Matches Member 4 CandidateRegion dataclass schema."""

    centroid_lon: float
    centroid_lat: float
    area_sq_meters: float
    peak_density: float = 0.05
    coverage_level: float = 0.5
    radius_km: Optional[float] = None


@dataclasses.dataclass
class SyntheticOriginCandidate:
    """Matches Member 4 OriginCandidate dataclass schema."""

    timestamp: pd.Timestamp
    region: SyntheticCandidateRegion
    concentration: float = 0.8
    density_strength: float = 0.9
    temporal_stability: float = 0.7
    heuristic_score: float = 2.4


@pytest.fixture
def current_member4_sample() -> Dict[str, Any]:
    """Sample output conforming to current Member 4 ocean.drift.origin.analyze_origin()."""
    t_best = pd.Timestamp("2026-09-07T01:00:00Z")
    t_alt = pd.Timestamp("2026-09-07T00:00:00Z")

    best_region = SyntheticCandidateRegion(
        centroid_lon=72.5156,
        centroid_lat=18.5006,
        area_sq_meters=3828700.0,  # ~1.1039 km equivalent radius
        peak_density=0.082,
        coverage_level=0.50,
    )
    best_cand = SyntheticOriginCandidate(
        timestamp=t_best,
        region=best_region,
        concentration=0.85,
        density_strength=0.92,
        temporal_stability=0.78,
        heuristic_score=2.9964,
    )

    alt_region = SyntheticCandidateRegion(
        centroid_lon=72.5100,
        centroid_lat=18.4950,
        area_sq_meters=5000000.0,
        peak_density=0.060,
        coverage_level=0.50,
    )
    alt_cand = SyntheticOriginCandidate(
        timestamp=t_alt,
        region=alt_region,
        concentration=0.60,
        density_strength=0.70,
        temporal_stability=0.80,
        heuristic_score=2.1000,
    )

    return {
        "ranked_candidates": [best_cand, alt_cand],
        "best_time": t_best,
        "best_candidate": best_cand,
    }


# ---------------------------------------------------------------------------
# Group A: Current Member 4 Format
# ---------------------------------------------------------------------------
def test_current_member4_format_extraction(current_member4_sample):
    """Adapter extracts best candidate, coordinates, and timestamp correctly."""
    result = adapt_drift_origin_result(current_member4_sample)
    assert isinstance(result, AISIntegrationResult)
    assert isinstance(result.search_request, AISSearchRequest)

    req = result.search_request
    assert req.latitude == pytest.approx(18.5006)
    assert req.longitude == pytest.approx(72.5156)
    assert req.source_timestamp == pd.Timestamp("2026-09-07T01:00:00Z")

    orig = result.origin
    assert orig["latitude"] == pytest.approx(18.5006)
    assert orig["longitude"] == pytest.approx(72.5156)
    assert orig["timestamp"] == "2026-09-07T01:00:00+00:00"
    assert orig["relative_score"] == pytest.approx(2.9964)


def test_current_member4_single_candidate_object_passed_directly():
    """Adapter can accept an OriginCandidate object directly."""
    t_best = pd.Timestamp("2026-09-07T02:00:00Z")
    region = SyntheticCandidateRegion(
        centroid_lon=72.50,
        centroid_lat=18.50,
        area_sq_meters=1000000.0,
    )
    cand = SyntheticOriginCandidate(
        timestamp=t_best,
        region=region,
        heuristic_score=1.5,
    )
    result = adapt_drift_origin_result(cand)
    assert result.search_request.latitude == 18.50
    assert result.search_request.longitude == 72.50
    assert result.search_request.source_timestamp == t_best


# ---------------------------------------------------------------------------
# Group B: Radius Compatibility & Precedence
# ---------------------------------------------------------------------------
def test_radius_area_only_conversion():
    """area_sq_meters is correctly converted using sqrt(area/pi)/1000."""
    area_m2 = 12566370.614359173  # pi * (2000 m)^2 => radius = 2.0 km
    expected_radius_km = math.sqrt(area_m2 / math.pi) / 1000.0
    assert expected_radius_km == pytest.approx(2.0, rel=1e-6)

    payload = {
        "best_candidate": {
            "timestamp": "2026-09-07T01:00:00Z",
            "region": {
                "centroid_lat": 18.5,
                "centroid_lon": 72.5,
                "area_sq_meters": area_m2,
            },
        }
    }
    result = adapt_drift_origin_result(payload)
    assert result.search_request.radius_km == pytest.approx(2.0, rel=1e-6)
    assert result.uncertainty["radius_km"] == pytest.approx(2.0, rel=1e-6)


def test_radius_explicit_radius_only():
    """Explicit radius_km is used directly when present."""
    payload = {
        "best_candidate": {
            "timestamp": "2026-09-07T01:00:00Z",
            "region": {
                "centroid_lat": 18.5,
                "centroid_lon": 72.5,
                "radius_km": 3.75,
            },
        }
    }
    result = adapt_drift_origin_result(payload)
    assert result.search_request.radius_km == pytest.approx(3.75)
    assert result.uncertainty["radius_km"] == pytest.approx(3.75)


def test_radius_both_present_radius_is_authoritative():
    """When both radius_km and area_sq_meters are present, radius_km takes precedence."""
    payload = {
        "best_candidate": {
            "timestamp": "2026-09-07T01:00:00Z",
            "region": {
                "centroid_lat": 18.5,
                "centroid_lon": 72.5,
                "radius_km": 4.5,
                "area_sq_meters": 1000000.0,  # would yield ~0.564 km
            },
        }
    }
    result = adapt_drift_origin_result(payload)
    assert result.search_request.radius_km == pytest.approx(4.5)
    assert result.uncertainty["radius_km"] == pytest.approx(4.5)


def test_radius_neither_present_uses_default():
    """When neither radius_km nor area_sq_meters is present, default_radius_km is used."""
    payload = {
        "best_candidate": {
            "timestamp": "2026-09-07T01:00:00Z",
            "region": {
                "centroid_lat": 18.5,
                "centroid_lon": 72.5,
            },
        }
    }
    result = adapt_drift_origin_result(payload, default_radius_km=7.5)
    assert result.search_request.radius_km == pytest.approx(7.5)


def test_radius_invalid_radius_falls_back_to_valid_area():
    """Invalid radius_km (negative, NaN, zero) falls back to valid area_sq_meters."""
    area_m2 = 3141592.653589793  # pi * (1000m)^2 => 1.0 km
    payload = {
        "best_candidate": {
            "timestamp": "2026-09-07T01:00:00Z",
            "region": {
                "centroid_lat": 18.5,
                "centroid_lon": 72.5,
                "radius_km": -10.0,  # Invalid
                "area_sq_meters": area_m2,  # Valid
            },
        }
    }
    result = adapt_drift_origin_result(payload)
    assert result.search_request.radius_km == pytest.approx(1.0, rel=1e-5)


def test_radius_invalid_area_falls_back_to_default():
    """Invalid area_sq_meters falls back to default_radius_km."""
    payload = {
        "best_candidate": {
            "timestamp": "2026-09-07T01:00:00Z",
            "region": {
                "centroid_lat": 18.5,
                "centroid_lon": 72.5,
                "area_sq_meters": np.nan,  # Invalid
            },
        }
    }
    result = adapt_drift_origin_result(payload, default_radius_km=6.2)
    assert result.search_request.radius_km == pytest.approx(6.2)


def test_buffer_handling():
    """buffer_km is properly added to effective search radius and passed to search request."""
    payload = {
        "best_candidate": {
            "timestamp": "2026-09-07T01:00:00Z",
            "region": {
                "centroid_lat": 18.5,
                "centroid_lon": 72.5,
                "radius_km": 5.0,
            },
        }
    }
    result = adapt_drift_origin_result(payload, buffer_km=2.5)
    assert result.search_request.radius_km == pytest.approx(5.0)
    assert result.search_request.buffer_km == pytest.approx(2.5)
    assert result.search_request.effective_radius_km == pytest.approx(7.5)


# ---------------------------------------------------------------------------
# Group C: Time Window & Normalization
# ---------------------------------------------------------------------------
def test_time_symmetric_window(current_member4_sample):
    """Symmetric before/after window produces [origin - W, origin + W]."""
    result = adapt_drift_origin_result(
        current_member4_sample,
        before_minutes=45.0,
        after_minutes=45.0,
    )
    req = result.search_request
    assert req.start_time == pd.Timestamp("2026-09-07T00:15:00Z")
    assert req.end_time == pd.Timestamp("2026-09-07T01:45:00Z")
    assert req.duration_minutes == pytest.approx(90.0)


def test_time_asymmetric_window(current_member4_sample):
    """Asymmetric before/after window produces independent start and end times."""
    result = adapt_drift_origin_result(
        current_member4_sample,
        before_minutes=60.0,
        after_minutes=15.0,
    )
    req = result.search_request
    assert req.start_time == pd.Timestamp("2026-09-07T00:00:00Z")
    assert req.end_time == pd.Timestamp("2026-09-07T01:15:00Z")
    assert req.duration_minutes == pytest.approx(75.0)


def test_time_zero_minute_window(current_member4_sample):
    """Zero-minute window produces start_time == end_time == origin_time."""
    result = adapt_drift_origin_result(
        current_member4_sample,
        before_minutes=0.0,
        after_minutes=0.0,
    )
    req = result.search_request
    assert req.start_time == pd.Timestamp("2026-09-07T01:00:00Z")
    assert req.end_time == pd.Timestamp("2026-09-07T01:00:00Z")
    assert req.duration_seconds == 0.0


def test_time_utc_normalization():
    """Non-UTC timezone-aware timestamp is normalized to UTC."""
    t_edt = pd.Timestamp("2026-09-06T21:00:00-04:00")  # Equal to 2026-09-07 01:00:00 UTC
    payload = {
        "best_candidate": {
            "timestamp": t_edt,
            "region": {"centroid_lat": 18.5, "centroid_lon": 72.5, "radius_km": 1.0},
        }
    }
    result = adapt_drift_origin_result(payload)
    assert result.search_request.source_timestamp == pd.Timestamp("2026-09-07T01:00:00Z")
    assert result.origin["timestamp"] == "2026-09-07T01:00:00+00:00"


def test_time_naive_timestamp_rejected():
    """Timezone-naive timestamp raises ValueError."""
    t_naive = pd.Timestamp("2026-09-07 01:00:00")  # No tz
    payload = {
        "best_candidate": {
            "timestamp": t_naive,
            "region": {"centroid_lat": 18.5, "centroid_lon": 72.5, "radius_km": 1.0},
        }
    }
    with pytest.raises(ValueError, match="must be timezone-aware"):
        adapt_drift_origin_result(payload)


# ---------------------------------------------------------------------------
# Group D: Spatial Calculations & Bounding Box
# ---------------------------------------------------------------------------
def test_spatial_bounding_box_generation():
    """Bounding box matches derive_bounding_box with effective search radius."""
    lat, lon = 18.5006, 72.5156
    radius_km, buffer_km = 3.0, 1.5
    eff_radius = radius_km + buffer_km

    expected_bbox = derive_bounding_box(lat, lon, eff_radius)

    payload = {
        "best_candidate": {
            "timestamp": "2026-09-07T01:00:00Z",
            "region": {
                "centroid_lat": lat,
                "centroid_lon": lon,
                "radius_km": radius_km,
            },
        }
    }
    result = adapt_drift_origin_result(payload, buffer_km=buffer_km)
    req = result.search_request

    assert req.bounding_box == expected_bbox
    assert req.min_latitude == expected_bbox[0]
    assert req.max_latitude == expected_bbox[1]
    assert req.min_longitude == expected_bbox[2]
    assert req.max_longitude == expected_bbox[3]

    # Check uncertainty dictionary preserves bounding box
    unc = result.uncertainty
    assert unc["min_latitude"] == expected_bbox[0]
    assert unc["max_latitude"] == expected_bbox[1]
    assert unc["min_longitude"] == expected_bbox[2]
    assert unc["max_longitude"] == expected_bbox[3]


def test_spatial_anti_meridian_handling():
    """Bounding box derivation handles coordinates near the anti-meridian (+/-180)."""
    payload = {
        "best_candidate": {
            "timestamp": "2026-09-07T01:00:00Z",
            "region": {
                "centroid_lat": 10.0,
                "centroid_lon": 179.5,
                "radius_km": 100.0,
            },
        }
    }
    result = adapt_drift_origin_result(payload, buffer_km=0.0)
    bbox = result.search_request.bounding_box
    # Across anti-meridian, min_lon > max_lon in the wrapped convention
    assert bbox[2] > bbox[3]


# ---------------------------------------------------------------------------
# Group E: Standardized Output & JSON Serializability
# ---------------------------------------------------------------------------
def test_standardized_output_json_serializable(current_member4_sample):
    """Standardized origin_data and search_request are completely JSON-serializable."""
    result = adapt_drift_origin_result(current_member4_sample)

    # Must serialize without raising TypeError
    json_str_origin = json.dumps(result.origin_data)
    assert len(json_str_origin) > 0

    json_str_req = json.dumps(result.search_request.to_dict())
    assert len(json_str_req) > 0

    json_str_full = json.dumps(result.to_dict())
    assert len(json_str_full) > 0


def test_standardized_output_keys_and_values(current_member4_sample):
    """Origin data preserves relative_score, coverage_level, and candidates."""
    result = adapt_drift_origin_result(current_member4_sample)
    data = result.origin_data

    assert "origin" in data
    assert "uncertainty" in data
    assert "candidate_origins" in data

    assert data["origin"]["relative_score"] == pytest.approx(2.9964)
    assert data["uncertainty"]["confidence_level"] == pytest.approx(0.50)

    # 2 candidates from fixture
    assert len(data["candidate_origins"]) == 2
    c0 = data["candidate_origins"][0]
    assert c0["heuristic_score"] == pytest.approx(2.9964)
    assert c0["timestamp"] == "2026-09-07T01:00:00+00:00"

    c1 = data["candidate_origins"][1]
    assert c1["heuristic_score"] == pytest.approx(2.1000)
    assert c1["timestamp"] == "2026-09-07T00:00:00+00:00"


def test_spill_observation_optional(current_member4_sample):
    """When spill_observation is not supplied, it is omitted and not fabricated."""
    result_no_obs = adapt_drift_origin_result(current_member4_sample, spill_observation=None)
    assert "spill_observation" not in result_no_obs.origin_data
    assert result_no_obs.spill_observation is None

    # When supplied, it is preserved and validated
    obs_input = {
        "timestamp": "2026-09-07T05:00:00Z",
        "latitude": 18.5000,
        "longitude": 72.5000,
    }
    result_with_obs = adapt_drift_origin_result(
        current_member4_sample,
        spill_observation=obs_input,
    )
    assert "spill_observation" in result_with_obs.origin_data
    obs = result_with_obs.spill_observation
    assert obs["timestamp"] == "2026-09-07T05:00:00+00:00"
    assert obs["latitude"] == pytest.approx(18.5000)
    assert obs["longitude"] == pytest.approx(72.5000)


# ---------------------------------------------------------------------------
# Group F: Validation & Error Handling
# ---------------------------------------------------------------------------
def test_validation_missing_member4_output():
    """Passing None as member4_output raises ValueError."""
    with pytest.raises(ValueError, match="member4_output must be provided"):
        adapt_drift_origin_result(None)


def test_validation_empty_dict():
    """Passing empty dictionary raises ValueError."""
    with pytest.raises(ValueError, match="must contain 'best_candidate' or non-empty 'ranked_candidates'"):
        adapt_drift_origin_result({})


def test_validation_missing_timestamp():
    """Missing candidate timestamp raises ValueError."""
    payload = {
        "best_candidate": {
            "region": {"centroid_lat": 18.5, "centroid_lon": 72.5, "radius_km": 1.0},
        }
    }
    with pytest.raises(ValueError, match="timestamp"):
        adapt_drift_origin_result(payload)


def test_validation_missing_coordinates():
    """Missing coordinates raises ValueError."""
    payload = {
        "best_candidate": {
            "timestamp": "2026-09-07T01:00:00Z",
            "region": {"radius_km": 1.0},
        }
    }
    with pytest.raises(ValueError, match="coordinates must be provided"):
        adapt_drift_origin_result(payload)


def test_validation_invalid_coordinates():
    """Out-of-bounds or non-finite coordinates raise ValueError."""
    # Latitude > 90
    payload_lat = {
        "best_candidate": {
            "timestamp": "2026-09-07T01:00:00Z",
            "region": {"centroid_lat": 95.0, "centroid_lon": 72.5},
        }
    }
    with pytest.raises(ValueError, match="Latitude must be a finite number in"):
        adapt_drift_origin_result(payload_lat)

    # Longitude NaN
    payload_lon = {
        "best_candidate": {
            "timestamp": "2026-09-07T01:00:00Z",
            "region": {"centroid_lat": 18.5, "centroid_lon": np.nan},
        }
    }
    with pytest.raises(ValueError, match="Longitude must be a finite number in"):
        adapt_drift_origin_result(payload_lon)


def test_validation_invalid_window():
    """Negative before_minutes or after_minutes raises ValueError."""
    payload = {
        "best_candidate": {
            "timestamp": "2026-09-07T01:00:00Z",
            "region": {"centroid_lat": 18.5, "centroid_lon": 72.5, "radius_km": 1.0},
        }
    }
    with pytest.raises(ValueError, match="before_minutes must be a finite non-negative number"):
        adapt_drift_origin_result(payload, before_minutes=-10.0)

    with pytest.raises(ValueError, match="after_minutes must be a finite non-negative number"):
        adapt_drift_origin_result(payload, after_minutes=-5.0)


def test_validation_invalid_radius():
    """Invalid default_radius_km or buffer_km raises ValueError."""
    payload = {
        "best_candidate": {
            "timestamp": "2026-09-07T01:00:00Z",
            "region": {"centroid_lat": 18.5, "centroid_lon": 72.5, "radius_km": 1.0},
        }
    }
    with pytest.raises(ValueError, match="default_radius_km must be a finite number > 0"):
        adapt_drift_origin_result(payload, default_radius_km=-1.0)

    with pytest.raises(ValueError, match="buffer_km must be a finite non-negative number"):
        adapt_drift_origin_result(payload, buffer_km=-2.0)


# ---------------------------------------------------------------------------
# Group G: Caller Input Immutability
# ---------------------------------------------------------------------------
def test_input_immutability(current_member4_sample):
    """Adapter does not mutate the caller's input objects or dictionaries."""
    sample_copy = copy.deepcopy(current_member4_sample)
    spill_obs = {"timestamp": "2026-09-07T05:00:00Z", "latitude": 18.5, "longitude": 72.5}
    obs_copy = copy.deepcopy(spill_obs)

    _ = adapt_drift_origin_result(current_member4_sample, spill_observation=spill_obs)

    assert current_member4_sample == sample_copy
    assert spill_obs == obs_copy


# ---------------------------------------------------------------------------
# Group H: AISSearchRequest Standalone
# ---------------------------------------------------------------------------
def test_ais_search_request_valid():
    """AISSearchRequest initializes properly with valid arguments and derives bbox."""
    req = AISSearchRequest(
        latitude=20.0,
        longitude=70.0,
        radius_km=10.0,
        start_time=pd.Timestamp("2026-09-07T00:00:00Z"),
        end_time=pd.Timestamp("2026-09-07T02:00:00Z"),
        buffer_km=2.0,
    )
    assert req.latitude == 20.0
    assert req.longitude == 70.0
    assert req.radius_km == 10.0
    assert req.buffer_km == 2.0
    assert req.effective_radius_km == 12.0
    assert req.duration_minutes == 120.0
    assert req.bounding_box is not None


def test_ais_search_request_end_before_start_rejected():
    """end_time < start_time raises ValueError."""
    with pytest.raises(ValueError, match="must be greater than or equal to start_time"):
        AISSearchRequest(
            latitude=20.0,
            longitude=70.0,
            radius_km=10.0,
            start_time=pd.Timestamp("2026-09-07T02:00:00Z"),
            end_time=pd.Timestamp("2026-09-07T01:00:00Z"),
        )


def test_ais_search_request_invalid_radius():
    """Non-positive or non-finite radius_km raises ValueError."""
    with pytest.raises(ValueError, match="radius_km must be a finite number > 0"):
        AISSearchRequest(
            latitude=20.0,
            longitude=70.0,
            radius_km=0.0,
            start_time=pd.Timestamp("2026-09-07T00:00:00Z"),
            end_time=pd.Timestamp("2026-09-07T01:00:00Z"),
        )


# ---------------------------------------------------------------------------
# Group I: End-to-End Compatibility with AIS-06 and AIS-07 Filtering
# ---------------------------------------------------------------------------
def test_end_to_end_filter_compatibility(current_member4_sample):
    """Adapter output can be consumed directly by AIS-06 and AIS-07 filters."""
    # Synthetic AIS DataFrame near Mumbai origin (18.5006, 72.5156) at 2026-09-07T01:00:00Z
    df_ais = pd.DataFrame(
        {
            "mmsi": [111222333, 444555666],
            "timestamp": pd.to_datetime(
                ["2026-09-07T01:05:00Z", "2026-09-07T04:00:00Z"], utc=True
            ),
            "latitude": [18.5006, 18.5006],
            "longitude": [72.5156, 72.5156],
        }
    )

    integration_result = adapt_drift_origin_result(
        current_member4_sample,
        default_radius_km=5.0,
        before_minutes=30.0,
        after_minutes=30.0,
    )

    # 1. Feed into AIS-06 Spatial Filter directly using integration_result
    spatial_res = filter_spatial(df_ais, origin_data=integration_result)
    assert len(spatial_res.data) == 2  # Both vessels are at the origin coordinates

    # 2. Feed into AIS-07 Temporal Filter
    temporal_res = filter_temporal(spatial_res, origin_data=integration_result)
    assert len(temporal_res.data) == 1
    assert temporal_res.data["mmsi"].iloc[0] == 111222333  # Only the 01:05:00 ping is in the window
