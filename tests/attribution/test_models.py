"""Unit tests for Attribution models, contracts, and validation layer (ATTR-01).

Validates:
- Valid creation of all attribution models.
- Coordinate boundaries and validation.
- UTC timezone awareness for timestamps.
- Score interval validation [0.0, 1.0] and interpretability rules.
- Required and optional AIS columns validation.
- Integration with AIS-07 TemporalFilterResult.
- Origin metadata validation from Member 4 / AIS-08.
- Serialization and deterministic representation.
- Empty candidate handling.
"""

from datetime import datetime
import json
from typing import Any, Dict

import numpy as np
import pandas as pd
import pytest

from ais.filtering.temporal import TemporalFilterReport, TemporalFilterResult
from attribution.models import (
    OPTIONAL_AIS_COLUMNS,
    REQUIRED_AIS_COLUMNS,
    AttributedCandidate,
    AttributionEvidence,
    AttributionReport,
    AttributionResult,
    CandidateVessel,
    OriginMetadata,
    VesselScore,
    validate_ais_observations,
    validate_origin_metadata,
)


# ===========================================================================
# 1. CandidateVessel Tests
# ===========================================================================
class TestCandidateVessel:
    def test_valid_creation(self):
        """Test creating a valid CandidateVessel with all fields."""
        vessel = CandidateVessel(
            mmsi=211987654,
            vessel_name="PACIFIC TRADER",
            vessel_type="Tanker",
            imo="IMO9123456",
            callsign="WDC1234",
            length=180.0,
            width=32.0,
            draft=10.5,
            total_observations=50,
            actual_observations=40,
            interpolated_observations=10,
            min_distance_km=1.25,
            closest_approach_time=pd.Timestamp("2025-01-08T00:15:00Z"),
            first_observed_time=pd.Timestamp("2025-01-07T23:50:00Z"),
            last_observed_time=pd.Timestamp("2025-01-08T00:40:00Z"),
            mean_sog_knots=12.4,
            segment_ids=["seg_001", "seg_002"],
        )
        assert vessel.mmsi == 211987654
        assert vessel.vessel_name == "PACIFIC TRADER"
        assert vessel.length == 180.0
        assert vessel.min_distance_km == 1.25
        assert vessel.closest_approach_time.tzinfo is not None

    def test_invalid_mmsi_rejected(self):
        """Test that negative, zero, or non-integer MMSI values are rejected."""
        with pytest.raises(ValueError, match="mmsi"):
            CandidateVessel(mmsi=0)

        with pytest.raises(ValueError, match="mmsi"):
            CandidateVessel(mmsi=-123456789)

        with pytest.raises(ValueError, match="mmsi"):
            CandidateVessel(mmsi="not_an_mmsi")  # type: ignore

    def test_negative_distance_rejected(self):
        """Test that negative min_distance_km is rejected."""
        with pytest.raises(ValueError, match="min_distance_km"):
            CandidateVessel(mmsi=211987654, min_distance_km=-0.5)

    def test_negative_dimensions_rejected(self):
        """Test that negative dimensions are rejected."""
        with pytest.raises(ValueError, match="length"):
            CandidateVessel(mmsi=211987654, length=-10.0)
        with pytest.raises(ValueError, match="width"):
            CandidateVessel(mmsi=211987654, width=-5.0)
        with pytest.raises(ValueError, match="draft"):
            CandidateVessel(mmsi=211987654, draft=-2.0)

    def test_naive_timestamp_rejected(self):
        """Test that timezone-naive timestamps raise ValueError."""
        with pytest.raises(ValueError, match="timezone-aware"):
            CandidateVessel(
                mmsi=211987654,
                closest_approach_time=pd.Timestamp("2025-01-08 00:15:00"),  # naive
            )

    def test_serialization(self):
        """Test CandidateVessel to_dict serialization and JSON compatibility."""
        vessel = CandidateVessel(
            mmsi=211987654,
            vessel_name="PACIFIC TRADER",
            closest_approach_time=pd.Timestamp("2025-01-08T00:15:00Z"),
            min_distance_km=2.5,
        )
        d = vessel.to_dict()
        assert d["mmsi"] == 211987654
        assert d["vessel_name"] == "PACIFIC TRADER"
        assert d["closest_approach_time"] == "2025-01-08T00:15:00+00:00"
        # Verify JSON serializability
        dumped = json.dumps(d)
        assert "PACIFIC TRADER" in dumped


# ===========================================================================
# 2. AttributionEvidence Tests
# ===========================================================================
class TestAttributionEvidence:
    def test_valid_evidence_creation(self):
        """Test AttributionEvidence with multi-criteria fields."""
        evidence = AttributionEvidence(
            min_distance_km=0.85,
            time_of_closest_approach=pd.Timestamp("2025-01-08T00:15:00Z"),
            time_difference_seconds=120.0,
            spatial_proximity_notes="Within 1 km of origin centroid",
            temporal_alignment_notes="2 minutes from estimated release time",
            trajectory_consistency_score=0.92,
            movement_direction_deg=185.0,
            heading_drift_alignment_deg=12.0,
            mean_speed_knots=11.5,
            speed_consistency_notes="Steady cruising speed",
            telemetry_continuity=0.98,
            ais_gap_count=0,
            interpolated_ratio=0.15,
            vessel_type_relevance="Crude oil tanker",
            supporting_factors=["Closest vessel to origin", "Course aligned with slick axis"],
            contradicting_factors=[],
        )
        assert evidence.min_distance_km == 0.85
        assert evidence.trajectory_consistency_score == 0.92
        assert len(evidence.supporting_factors) == 2

    def test_invalid_score_ratios_rejected(self):
        """Test that scores or ratios outside [0.0, 1.0] are rejected."""
        with pytest.raises(ValueError, match="trajectory_consistency_score"):
            AttributionEvidence(trajectory_consistency_score=1.5)
        with pytest.raises(ValueError, match="telemetry_continuity"):
            AttributionEvidence(telemetry_continuity=-0.1)
        with pytest.raises(ValueError, match="interpolated_ratio"):
            AttributionEvidence(interpolated_ratio=2.0)

    def test_negative_distance_rejected(self):
        """Test that negative min_distance_km is rejected."""
        with pytest.raises(ValueError, match="min_distance_km"):
            AttributionEvidence(min_distance_km=-1.0)

    def test_evidence_serialization(self):
        """Test AttributionEvidence to_dict serialization."""
        evidence = AttributionEvidence(
            min_distance_km=1.2,
            time_of_closest_approach=pd.Timestamp("2025-01-08T00:15:00Z"),
            supporting_factors=["Close proximity"],
        )
        d = evidence.to_dict()
        assert d["min_distance_km"] == 1.2
        assert d["supporting_factors"] == ["Close proximity"]
        json_str = json.dumps(d)
        assert "Close proximity" in json_str


# ===========================================================================
# 3. VesselScore Tests
# ===========================================================================
class TestVesselScore:
    def test_valid_scores(self):
        """Test creating VesselScore with valid values in [0.0, 1.0]."""
        score = VesselScore(
            spatial_score=0.85,
            temporal_score=0.90,
            trajectory_score=0.75,
            behaviour_score=0.80,
            overall_score=0.825,
        )
        assert score.spatial_score == 0.85
        assert score.overall_score == 0.825

    def test_boundary_scores(self):
        """Test boundary values 0.0 and 1.0."""
        score_zero = VesselScore(overall_score=0.0)
        assert score_zero.overall_score == 0.0

        score_one = VesselScore(overall_score=1.0)
        assert score_one.overall_score == 1.0

    def test_score_out_of_bounds_rejected(self):
        """Test that scores < 0.0 or > 1.0 raise ValueError."""
        with pytest.raises(ValueError, match="overall_score"):
            VesselScore(overall_score=1.01)

        with pytest.raises(ValueError, match="overall_score"):
            VesselScore(overall_score=-0.01)

        with pytest.raises(ValueError, match="spatial_score"):
            VesselScore(spatial_score=2.0)

        with pytest.raises(ValueError, match="temporal_score"):
            VesselScore(temporal_score=-0.5)

    def test_nan_or_inf_score_rejected(self):
        """Test that NaN or Infinite score values raise ValueError."""
        with pytest.raises(ValueError, match="overall_score"):
            VesselScore(overall_score=float("nan"))

        with pytest.raises(ValueError, match="spatial_score"):
            VesselScore(spatial_score=float("inf"))

    def test_score_serialization(self):
        """Test VesselScore serialization."""
        score = VesselScore(spatial_score=0.9, overall_score=0.85)
        d = score.to_dict()
        assert d["spatial_score"] == 0.9
        assert d["temporal_score"] is None
        assert d["overall_score"] == 0.85
        assert json.dumps(d)


# ===========================================================================
# 4. AttributedCandidate Tests
# ===========================================================================
class TestAttributedCandidate:
    def test_valid_candidate(self):
        """Test creating an AttributedCandidate."""
        vessel = CandidateVessel(mmsi=205123456, vessel_name="VESSEL_A")
        score = VesselScore(overall_score=0.88)
        evidence = AttributionEvidence(min_distance_km=1.1)

        candidate = AttributedCandidate(
            rank=1,
            vessel=vessel,
            score=score,
            evidence=evidence,
        )
        assert candidate.rank == 1
        assert candidate.mmsi == 205123456
        assert candidate.overall_score == 0.88

    def test_invalid_rank_rejected(self):
        """Test rank < 1 raises ValueError."""
        vessel = CandidateVessel(mmsi=205123456)
        score = VesselScore(overall_score=0.5)

        with pytest.raises(ValueError, match="rank"):
            AttributedCandidate(rank=0, vessel=vessel, score=score)

        with pytest.raises(ValueError, match="rank"):
            AttributedCandidate(rank=-1, vessel=vessel, score=score)

    def test_type_validation(self):
        """Test that invalid types for vessel, score, or evidence raise TypeError."""
        vessel = CandidateVessel(mmsi=205123456)
        score = VesselScore(overall_score=0.5)

        with pytest.raises(TypeError, match="CandidateVessel"):
            AttributedCandidate(rank=1, vessel="not_a_vessel", score=score)  # type: ignore

        with pytest.raises(TypeError, match="VesselScore"):
            AttributedCandidate(rank=1, vessel=vessel, score="not_a_score")  # type: ignore


# ===========================================================================
# 5. OriginMetadata Tests
# ===========================================================================
class TestOriginMetadata:
    def test_valid_creation(self):
        """Test creating OriginMetadata directly."""
        meta = OriginMetadata(
            timestamp=pd.Timestamp("2025-01-08T00:15:00Z"),
            latitude=28.0,
            longitude=-90.0,
            radius_km=5.0,
            confidence_level=0.5,
        )
        assert meta.latitude == 28.0
        assert meta.longitude == -90.0
        assert meta.radius_km == 5.0
        assert meta.confidence_level == 0.5

    def test_invalid_coordinates_rejected(self):
        """Test latitude/longitude bounds enforcement."""
        with pytest.raises(ValueError, match="latitude"):
            OriginMetadata(
                timestamp=pd.Timestamp("2025-01-08T00:15:00Z"),
                latitude=91.0,
                longitude=-90.0,
            )
        with pytest.raises(ValueError, match="longitude"):
            OriginMetadata(
                timestamp=pd.Timestamp("2025-01-08T00:15:00Z"),
                latitude=28.0,
                longitude=-181.0,
            )

    def test_invalid_radius_rejected(self):
        """Test negative radius rejection."""
        with pytest.raises(ValueError, match="radius_km"):
            OriginMetadata(
                timestamp=pd.Timestamp("2025-01-08T00:15:00Z"),
                latitude=28.0,
                longitude=-90.0,
                radius_km=-2.0,
            )

    def test_from_origin_data_dict(self):
        """Test parsing standardized Member 4 / AIS-08 origin_data dictionary."""
        origin_dict = {
            "origin": {
                "timestamp": "2025-01-08T00:15:00Z",
                "latitude": 28.123,
                "longitude": -90.456,
            },
            "uncertainty": {
                "radius_km": 4.5,
                "confidence_level": 0.68,
            },
        }
        meta = OriginMetadata.from_origin_data(origin_dict)
        assert meta.latitude == 28.123
        assert meta.longitude == -90.456
        assert meta.radius_km == 4.5
        assert meta.confidence_level == 0.68

    def test_from_origin_data_missing_fields_rejected(self):
        """Test rejection when required origin fields are absent."""
        with pytest.raises(ValueError, match="timestamp"):
            OriginMetadata.from_origin_data({"origin": {"latitude": 28.0, "longitude": -90.0}})

        with pytest.raises(ValueError, match="latitude"):
            OriginMetadata.from_origin_data({"origin": {"timestamp": "2025-01-08T00:15:00Z"}})


# ===========================================================================
# 6. AttributionResult & Report Tests
# ===========================================================================
class TestAttributionResult:
    @pytest.fixture
    def sample_result(self) -> AttributionResult:
        """Create a multi-candidate AttributionResult fixture."""
        v1 = CandidateVessel(mmsi=205123456, vessel_name="VESSEL_A", min_distance_km=0.5, total_observations=10)
        v2 = CandidateVessel(mmsi=211987654, vessel_name="VESSEL_B", min_distance_km=2.1, total_observations=5)
        c1 = AttributedCandidate(rank=1, vessel=v1, score=VesselScore(overall_score=0.92))
        c2 = AttributedCandidate(rank=2, vessel=v2, score=VesselScore(overall_score=0.64))

        origin = OriginMetadata(
            timestamp=pd.Timestamp("2025-01-08T00:15:00Z"),
            latitude=28.0,
            longitude=-90.0,
            radius_km=5.0,
        )
        report = AttributionReport(
            total_input_observations=15,
            total_candidate_vessels=2,
            evaluation_timestamp="2026-09-08T15:00:00Z",
            origin_timestamp="2025-01-08T00:15:00Z",
        )
        return AttributionResult(
            ranked_candidates=[c1, c2],
            origin_metadata=origin,
            report=report,
        )

    def test_properties_and_lookups(self, sample_result: AttributionResult):
        """Test candidate lookups and top candidate access."""
        assert sample_result.candidate_mmsis == [205123456, 211987654]
        assert sample_result.top_candidate is not None
        assert sample_result.top_candidate.mmsi == 205123456
        assert sample_result.top_candidate.overall_score == 0.92

        cand = sample_result.get_candidate(211987654)
        assert cand is not None
        assert cand.rank == 2

        assert sample_result.get_candidate(999999999) is None

    def test_to_dataframe(self, sample_result: AttributionResult):
        """Test tabular dataframe summary conversion."""
        df = sample_result.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df["mmsi"]) == [205123456, 211987654]
        assert list(df["rank"]) == [1, 2]
        assert list(df["overall_score"]) == [0.92, 0.64]

    def test_deterministic_serialization(self, sample_result: AttributionResult):
        """Test deterministic JSON serialization."""
        d = sample_result.to_dict()
        assert "ranked_candidates" in d
        assert len(d["ranked_candidates"]) == 2
        assert d["ranked_candidates"][0]["rank"] == 1
        assert d["ranked_candidates"][1]["rank"] == 2

        # Verify JSON serializability
        json_str = json.dumps(d)
        assert "VESSEL_A" in json_str

    def test_empty_candidates_handling(self):
        """Test AttributionResult with zero candidate vessels."""
        origin = OriginMetadata(
            timestamp=pd.Timestamp("2025-01-08T00:15:00Z"),
            latitude=28.0,
            longitude=-90.0,
        )
        report = AttributionReport(
            total_input_observations=0,
            total_candidate_vessels=0,
            evaluation_timestamp="2026-09-08T15:00:00Z",
        )
        empty_res = AttributionResult(
            ranked_candidates=[],
            origin_metadata=origin,
            report=report,
        )
        assert empty_res.candidate_mmsis == []
        assert empty_res.top_candidate is None
        assert empty_res.get_candidate(123456789) is None

        df = empty_res.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert "mmsi" in df.columns

        d = empty_res.to_dict()
        assert d["ranked_candidates"] == []


# ===========================================================================
# 7. AIS Ingestion & Observation Validation Tests
# ===========================================================================
class TestValidateAISObservations:
    @pytest.fixture
    def valid_ais_df(self) -> pd.DataFrame:
        """Create a valid observation-level AIS DataFrame conforming to AIS-07 output."""
        return pd.DataFrame({
            "mmsi": [205123456, 205123456, 211987654],
            "timestamp": pd.to_datetime([
                "2025-01-08T00:00:00Z",
                "2025-01-08T00:10:00Z",
                "2025-01-08T00:15:00Z",
            ]),
            "latitude": [28.00, 28.01, 28.05],
            "longitude": [-90.00, -90.01, -90.02],
            "distance_km": [0.5, 1.2, 3.4],
            "sog": [10.0, 10.2, 5.0],
            "vessel_name": ["VESSEL_A", "VESSEL_A", "VESSEL_B"],
            "trajectory_segment_id": ["seg_1", "seg_1", "seg_2"],
            "is_interpolated": [False, True, False],
        })

    def test_valid_dataframe_accepted(self, valid_ais_df: pd.DataFrame):
        """Test that a compliant DataFrame passes validation and preserves columns."""
        res = validate_ais_observations(valid_ais_df)
        assert len(res) == 3
        assert set(REQUIRED_AIS_COLUMNS).issubset(set(res.columns))
        assert "sog" in res.columns
        assert "is_interpolated" in res.columns
        assert res["timestamp"].dt.tz is not None

    def test_missing_required_column_rejected(self, valid_ais_df: pd.DataFrame):
        """Test that missing required columns raise ValueError."""
        for req_col in REQUIRED_AIS_COLUMNS:
            invalid_df = valid_ais_df.drop(columns=[req_col])
            with pytest.raises(ValueError, match="missing required columns"):
                validate_ais_observations(invalid_df)

    def test_invalid_coordinates_rejected(self, valid_ais_df: pd.DataFrame):
        """Test out-of-bounds coordinates raise ValueError."""
        bad_lat = valid_ais_df.copy()
        bad_lat.loc[0, "latitude"] = 95.0
        with pytest.raises(ValueError, match="latitudes outside"):
            validate_ais_observations(bad_lat)

        bad_lon = valid_ais_df.copy()
        bad_lon.loc[0, "longitude"] = -190.0
        with pytest.raises(ValueError, match="longitudes outside"):
            validate_ais_observations(bad_lon)

    def test_negative_distance_rejected(self, valid_ais_df: pd.DataFrame):
        """Test negative distance_km values raise ValueError."""
        bad_dist = valid_ais_df.copy()
        bad_dist.loc[0, "distance_km"] = -0.1
        with pytest.raises(ValueError, match="negative distance_km"):
            validate_ais_observations(bad_dist)

    def test_naive_timestamps_rejected(self, valid_ais_df: pd.DataFrame):
        """Test timezone-naive timestamps raise ValueError."""
        bad_ts = valid_ais_df.copy()
        bad_ts["timestamp"] = pd.to_datetime(["2025-01-08 00:00:00", "2025-01-08 00:10:00", "2025-01-08 00:15:00"])
        with pytest.raises(ValueError, match="timezone-aware"):
            validate_ais_observations(bad_ts)

    def test_invalid_mmsi_rejected(self, valid_ais_df: pd.DataFrame):
        """Test non-positive MMSI in observations raises ValueError."""
        bad_mmsi = valid_ais_df.copy()
        bad_mmsi.loc[0, "mmsi"] = 0
        with pytest.raises(ValueError, match="non-positive MMSI"):
            validate_ais_observations(bad_mmsi)

    def test_temporal_filter_result_accepted(self, valid_ais_df: pd.DataFrame):
        """Test that an AIS-07 TemporalFilterResult object is accepted directly."""
        report = TemporalFilterReport(
            total_input_records=3,
            matched_records=3,
            unique_vessels_in=2,
            unique_vessels_matched=2,
            origin_timestamp="2025-01-08T00:15:00Z",
            window_minutes=30.0,
            before_minutes=30.0,
            after_minutes=30.0,
            start_timestamp="2025-01-07T23:45:00Z",
            end_timestamp="2025-01-08T00:45:00Z",
            earliest_retained_timestamp="2025-01-08T00:00:00Z",
            latest_retained_timestamp="2025-01-08T00:15:00Z",
            segments_matched=2,
        )
        t_result = TemporalFilterResult(data=valid_ais_df, report=report)

        validated_df = validate_ais_observations(t_result)
        assert isinstance(validated_df, pd.DataFrame)
        assert len(validated_df) == 3
        assert set(validated_df["mmsi"]) == {205123456, 211987654}

    def test_empty_dataframe_accepted(self):
        """Test validating an empty DataFrame with required schema."""
        empty_df = pd.DataFrame(columns=list(REQUIRED_AIS_COLUMNS))
        res = validate_ais_observations(empty_df)
        assert isinstance(res, pd.DataFrame)
        assert len(res) == 0

    def test_unsupported_type_rejected(self):
        """Test non-DataFrame unsupported object raises TypeError."""
        with pytest.raises(TypeError, match="Unsupported data type"):
            validate_ais_observations("invalid_input")


# ===========================================================================
# 8. Origin Metadata Validation Tests
# ===========================================================================
class TestValidateOriginMetadata:
    def test_with_integration_result_mock(self):
        """Test with object mimicking AISIntegrationResult from AIS-08."""
        class MockAISIntegrationResult:
            @property
            def origin(self) -> Dict[str, Any]:
                return {
                    "timestamp": "2025-01-08T00:15:00Z",
                    "latitude": 28.0,
                    "longitude": -90.0,
                }

            @property
            def uncertainty(self) -> Dict[str, Any]:
                return {
                    "radius_km": 5.0,
                    "confidence_level": 0.5,
                }

        mock_obj = MockAISIntegrationResult()
        meta = validate_origin_metadata(mock_obj)
        assert isinstance(meta, OriginMetadata)
        assert meta.latitude == 28.0
        assert meta.longitude == -90.0
        assert meta.radius_km == 5.0
        assert meta.confidence_level == 0.5


# ===========================================================================
# 9. Hardened Validation Regression Tests (ATTR-01 Review Fixes)
# ===========================================================================
class TestHardenedValidation:
    def test_fractional_mmsi_rejected_in_dataframe(self):
        """Reject non-integer numeric MMSIs instead of silently truncating."""
        df_float_mmsi = pd.DataFrame({
            "mmsi": [205123456.5, 211987654.0],
            "timestamp": pd.to_datetime(["2025-01-08T00:00:00Z", "2025-01-08T00:10:00Z"]),
            "latitude": [28.0, 28.01],
            "longitude": [-90.0, -90.01],
            "distance_km": [1.0, 2.0],
        })
        with pytest.raises(ValueError, match="non-integer floating-point"):
            validate_ais_observations(df_float_mmsi)

    def test_integer_like_string_mmsi_accepted_in_dataframe(self):
        """Accept valid integer-like string MMSIs and convert cleanly."""
        df_str_mmsi = pd.DataFrame({
            "mmsi": ["205123456", "211987654"],
            "timestamp": pd.to_datetime(["2025-01-08T00:00:00Z", "2025-01-08T00:10:00Z"]),
            "latitude": [28.0, 28.01],
            "longitude": [-90.0, -90.01],
            "distance_km": [1.0, 2.0],
        })
        validated = validate_ais_observations(df_str_mmsi)
        assert list(validated["mmsi"]) == [205123456, 211987654]
        assert pd.api.types.is_integer_dtype(validated["mmsi"])

    def test_boolean_mmsi_rejected_in_dataframe(self):
        """Reject boolean MMSI values with controlled ValueError."""
        df_bool_mmsi = pd.DataFrame({
            "mmsi": [True, False],
            "timestamp": pd.to_datetime(["2025-01-08T00:00:00Z", "2025-01-08T00:10:00Z"]),
            "latitude": [28.0, 28.01],
            "longitude": [-90.0, -90.01],
            "distance_km": [1.0, 2.0],
        })
        with pytest.raises(ValueError, match="boolean"):
            validate_ais_observations(df_bool_mmsi)

    def test_non_numeric_coordinates_rejected_with_value_error(self):
        """Ensure non-numeric coordinates produce controlled ValueError, not TypeError."""
        df_bad_lat = pd.DataFrame({
            "mmsi": [205123456],
            "timestamp": [pd.Timestamp("2025-01-08T00:00:00Z")],
            "latitude": ["invalid_latitude"],
            "longitude": [-90.0],
            "distance_km": [1.0],
        })
        with pytest.raises(ValueError, match="latitude"):
            validate_ais_observations(df_bad_lat)

        df_bad_lon = pd.DataFrame({
            "mmsi": [205123456],
            "timestamp": [pd.Timestamp("2025-01-08T00:00:00Z")],
            "latitude": [28.0],
            "longitude": [{"bad": "object"}],
            "distance_km": [1.0],
        })
        with pytest.raises(ValueError, match="longitude"):
            validate_ais_observations(df_bad_lon)

    def test_boolean_coordinates_rejected(self):
        """Ensure boolean coordinate values produce controlled ValueError."""
        df_bool_lat = pd.DataFrame({
            "mmsi": [205123456],
            "timestamp": [pd.Timestamp("2025-01-08T00:00:00Z")],
            "latitude": [True],
            "longitude": [-90.0],
            "distance_km": [1.0],
        })
        with pytest.raises(ValueError, match="boolean"):
            validate_ais_observations(df_bool_lat)

    def test_non_numeric_distance_rejected_with_value_error(self):
        """Ensure non-numeric distance produces controlled ValueError, not TypeError."""
        df_bad_dist = pd.DataFrame({
            "mmsi": [205123456],
            "timestamp": [pd.Timestamp("2025-01-08T00:00:00Z")],
            "latitude": [28.0],
            "longitude": [-90.0],
            "distance_km": ["non_numeric_km"],
        })
        with pytest.raises(ValueError, match="distance_km"):
            validate_ais_observations(df_bad_dist)

    def test_boolean_distance_rejected(self):
        """Ensure boolean distance values produce controlled ValueError."""
        df_bool_dist = pd.DataFrame({
            "mmsi": [205123456],
            "timestamp": [pd.Timestamp("2025-01-08T00:00:00Z")],
            "latitude": [28.0],
            "longitude": [-90.0],
            "distance_km": [False],
        })
        with pytest.raises(ValueError, match="boolean"):
            validate_ais_observations(df_bool_dist)

    def test_candidate_vessel_fractional_mmsi_rejected(self):
        """Reject fractional MMSI in CandidateVessel."""
        with pytest.raises(ValueError, match="integer"):
            CandidateVessel(mmsi=123456789.5)

        with pytest.raises(ValueError, match="integer"):
            CandidateVessel(mmsi="123456789.5")

        with pytest.raises(ValueError, match="boolean"):
            CandidateVessel(mmsi=True)  # type: ignore

    def test_candidate_vessel_counts_must_be_non_negative_integers(self):
        """Validate counts must be non-negative integers."""
        with pytest.raises(ValueError, match="total_observations"):
            CandidateVessel(mmsi=205123456, total_observations=-1)

        with pytest.raises(ValueError, match="total_observations"):
            CandidateVessel(mmsi=205123456, total_observations=1.5)  # type: ignore

        with pytest.raises(ValueError, match="actual_observations"):
            CandidateVessel(mmsi=205123456, actual_observations=True)  # type: ignore

        with pytest.raises(ValueError, match="interpolated_observations"):
            CandidateVessel(mmsi=205123456, interpolated_observations="five")  # type: ignore

    def test_candidate_vessel_mean_sog_knots_validation(self):
        """Validate mean_sog_knots must be finite and non-negative."""
        # Negative rejected
        with pytest.raises(ValueError, match="mean_sog_knots"):
            CandidateVessel(mmsi=205123456, mean_sog_knots=-0.1)

        # NaN rejected
        with pytest.raises(ValueError, match="mean_sog_knots"):
            CandidateVessel(mmsi=205123456, mean_sog_knots=float("nan"))

        # Inf rejected
        with pytest.raises(ValueError, match="mean_sog_knots"):
            CandidateVessel(mmsi=205123456, mean_sog_knots=float("inf"))

        # Non-numeric rejected
        with pytest.raises(ValueError, match="mean_sog_knots"):
            CandidateVessel(mmsi=205123456, mean_sog_knots="ten")  # type: ignore

        # Valid finite positive accepted
        v = CandidateVessel(mmsi=205123456, mean_sog_knots=12.4)
        assert v.mean_sog_knots == 12.4

    def test_dataframe_mixed_timezones_normalized_to_utc(self):
        """Ensure mixed timezone offsets normalize cleanly to UTC."""
        df_mixed_tz = pd.DataFrame({
            "mmsi": [205123456, 211987654],
            "timestamp": ["2025-01-08T00:00:00Z", "2025-01-08T05:30:00+05:30"],
            "latitude": [28.0, 28.1],
            "longitude": [-90.0, -90.1],
            "distance_km": [1.0, 2.0],
        })
        validated = validate_ais_observations(df_mixed_tz)
        expected_utc = pd.Timestamp("2025-01-08T00:00:00Z")
        assert (validated["timestamp"] == expected_utc).all()
        assert str(validated["timestamp"].dt.tz) == "UTC"

    def test_dataframe_mixed_aware_and_naive_timestamps_rejected(self):
        """Ensure mixing timezone-aware and naive timestamps fails with clear ValueError."""
        df_mixed_naive = pd.DataFrame({
            "mmsi": [205123456, 211987654],
            "timestamp": ["2025-01-08T00:00:00Z", "2025-01-08 00:00:00"],  # one naive
            "latitude": [28.0, 28.1],
            "longitude": [-90.0, -90.1],
            "distance_km": [1.0, 2.0],
        })
        with pytest.raises(ValueError, match="timezone-aware"):
            validate_ais_observations(df_mixed_naive)
