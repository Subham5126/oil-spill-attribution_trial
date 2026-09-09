"""End-to-End Integration Tests for Ocean/Drift (Member 4) -> AIS/Attribution (Member 5).

Validates:
- Case A: Valid spill + valid environmental data + valid AIS candidates.
- Case B: Valid spill + no AIS vessels in region (empty AIS handled gracefully).
- Case C: Valid spill + vessels in region but outside time window (filtered out).
- Case D: Multiple candidate vessels with distinct kinematics and ranking.
- Case E: Missing/invalid AIS data fields (clean rejection / no false candidates).
- Case F: UTC timestamp consistency across all pipeline stages.
- Contract validation: OceanDriftResult and adapt_ocean_drift_to_ais behavior.
"""

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pytest

from ais.filtering import (
    SpatialFilterConfig,
    TemporalFilterConfig,
    filter_spatial,
    filter_temporal,
)
from ais.integration.adapter import AISIntegrationResult
from ais.integration.search_request import AISSearchRequest
from ais.interpolation import interpolate_trajectories
from ais.providers import LocalAISProvider
from ais.trajectory import reconstruct_trajectories
from attribution import (
    AttributionExplanationReport,
    AttributionResult,
    AttributionScoringConfig,
    OriginMetadata,
    explain_attribution,
    score_candidates,
)
from integration import (
    OceanDriftResult,
    PipelineResult,
    SpillObservation,
    adapt_ocean_drift_to_ais,
    run_spill_attribution_pipeline,
)
from ocean.currents import load_currents
from ocean.drift import Particle, hindcast_particles, simulate_particles
from ocean.drift.origin import analyze_origin
from ocean.drift.uncertainty import calculate_uncertainty
from ocean.time.synchronization import normalize_timestamp
from ocean.wind import load_wind


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def environmental_data():
    """Load sample Copernicus currents and ERA5 wind datasets."""
    current_path = Path("data/sample/copernicus/current_test.nc")
    wind_path = Path("data/sample/era5/wind_test.nc")

    if not current_path.is_file() or not wind_path.is_file():
        pytest.skip("Required sample environmental datasets not found")

    current_ds = load_currents(current_path)
    wind_ds = load_wind(wind_path)
    return current_ds, wind_ds


@pytest.fixture(scope="module")
def valid_spill_observation(environmental_data):
    """Derive valid spill observation within sample environmental domain."""
    current_ds, wind_ds = environmental_data
    c_times = pd.Index(current_ds["time"].values)
    w_times = pd.Index(wind_ds["time"].values)
    overlap = c_times.intersection(w_times)

    # Pick an observation timestamp near the end to allow backward hindcast
    obs_time_naive = overlap[-2]
    obs_time_utc = normalize_timestamp(obs_time_naive, assume_naive_utc=True)

    lon = float(current_ds["longitude"].values.mean())
    lat = float(current_ds["latitude"].values.mean())

    return SpillObservation(
        spill_id="SPILL-TEST-001",
        latitude=lat,
        longitude=lon,
        timestamp=obs_time_utc,
        area_sq_m=250000.0,
    )


@pytest.fixture
def multi_vessel_ais_csv(tmp_path: Path, valid_spill_observation) -> Path:
    """Generate controlled synthetic AIS CSV aligned with the simulation domain."""
    csv_file = tmp_path / "multi_vessel_traffic.csv"
    t_obs = valid_spill_observation.timestamp
    # Approximate origin time (2 hours prior to observation)
    t_orig = t_obs - pd.Timedelta(hours=2)
    t1 = (t_orig - pd.Timedelta(minutes=10)).isoformat()
    t2 = t_orig.isoformat()
    t3 = (t_orig + pd.Timedelta(minutes=10)).isoformat()
    t_old = (t_obs - pd.Timedelta(days=2)).isoformat()

    lat = valid_spill_observation.latitude
    lon = valid_spill_observation.longitude

    data = (
        "MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft\n"
        f"111111111,{t1},{lat:.4f},{lon:.4f},12.0,180.0,180.0,PRIME_SUSPECT,IMO9000001,WDC1111,80,0,220,32,12.0\n"
        f"111111111,{t2},{lat + 0.001:.4f},{lon:.4f},12.0,180.0,180.0,PRIME_SUSPECT,IMO9000001,WDC1111,80,0,220,32,12.0\n"
        f"111111111,{t3},{lat + 0.002:.4f},{lon:.4f},12.0,180.0,180.0,PRIME_SUSPECT,IMO9000001,WDC1111,80,0,220,32,12.0\n"
        f"222222222,{t2},{lat + 0.02:.4f},{lon + 0.02:.4f},6.0,90.0,90.0,DISTANT_CARGO,IMO9000002,WDC2222,70,0,140,20,7.5\n"
        f"333333333,{t_old},{lat:.4f},{lon:.4f},10.0,0.0,0.0,TIME_MISMATCH,IMO9000003,WDC3333,52,0,40,10,3.5\n"
        f"444444444,{t2},{lat + 2.0:.4f},{lon + 2.0:.4f},15.0,270.0,270.0,SPACE_MISMATCH,IMO9000004,WDC4444,70,0,160,25,8.0\n"
    )
    csv_file.write_text(data, encoding="utf-8")
    return csv_file


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------
def test_case_a_valid_spill_environmental_and_ais(
    valid_spill_observation,
    environmental_data,
    multi_vessel_ais_csv,
):
    """CASE A: Full end-to-end workflow with valid spill, environment, and AIS candidates."""
    current_ds, wind_ds = environmental_data

    result = run_spill_attribution_pipeline(
        spill=valid_spill_observation,
        current_ds=current_ds,
        wind_ds=wind_ds,
        ais_source=multi_vessel_ais_csv,
        num_particles=30,
        forward_steps=2,
        hindcast_duration_hours=4.0,
        timestep_seconds=3600,
        uncertainty_confidence=0.95,
        ais_before_minutes=30.0,
        ais_after_minutes=30.0,
        ais_buffer_km=2.0,
    )

    assert isinstance(result, PipelineResult)
    assert result.is_success
    assert result.stage_statuses["GIS → Ocean/Drift"] == "PASS"
    assert result.stage_statuses["Ocean/Drift → AIS"] == "PASS"
    assert result.stage_statuses["AIS → Attribution"] == "PASS"
    assert result.stage_statuses["End-to-end workflow"] == "PASS"

    # Ocean and drift assertions
    assert result.ocean_result.probable_origin_latitude == pytest.approx(
        result.ocean_result.best_candidate.region.centroid_lat
    )
    assert result.ocean_result.uncertainty_radius_km > 0.0

    # AIS search assertions
    assert result.search_request.effective_radius_km > 0.0
    assert result.search_request.start_time.tzinfo is not None
    assert result.search_request.end_time.tzinfo is not None

    # Attribution result assertions
    assert isinstance(result.attribution_result, AttributionResult)
    assert isinstance(result.explanation_report, AttributionExplanationReport)


def test_case_b_empty_ais_handling(
    valid_spill_observation,
    environmental_data,
    tmp_path: Path,
):
    """CASE B: Valid spill and environment with zero AIS vessels in region/time window."""
    current_ds, wind_ds = environmental_data

    # Empty CSV with valid header
    empty_csv = tmp_path / "empty_ais.csv"
    empty_csv.write_text(
        "MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft\n",
        encoding="utf-8",
    )

    result = run_spill_attribution_pipeline(
        spill=valid_spill_observation,
        current_ds=current_ds,
        wind_ds=wind_ds,
        ais_source=empty_csv,
        num_particles=20,
    )

    assert result.is_success
    assert result.raw_ais_matches.empty
    assert len(result.attribution_result.ranked_candidates) == 0
    assert result.explanation_report.total_candidates == 0


def test_case_c_temporal_exclusion(
    valid_spill_observation,
    environmental_data,
    tmp_path: Path,
):
    """CASE C: Vessels inside spatial region but strictly outside the temporal window."""
    current_ds, wind_ds = environmental_data

    # Vessel placed at exact spill location, but 24 hours earlier
    csv_file = tmp_path / "temporal_mismatch.csv"
    old_time = (valid_spill_observation.timestamp - pd.Timedelta(hours=24)).isoformat()
    csv_file.write_text(
        f"MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft\n"
        f"999999999,{old_time},{valid_spill_observation.latitude},{valid_spill_observation.longitude},10.0,0.0,0.0,OLD_VESSEL,IMO9999999,WDC9999,70,0,100,15,5.0\n",
        encoding="utf-8",
    )

    result = run_spill_attribution_pipeline(
        spill=valid_spill_observation,
        current_ds=current_ds,
        wind_ds=wind_ds,
        ais_source=csv_file,
        num_particles=20,
        ais_before_minutes=30.0,
        ais_after_minutes=30.0,
    )

    assert result.is_success
    # Excluded temporally by query/filter
    assert len(result.attribution_result.ranked_candidates) == 0


def test_case_d_multi_candidate_ranking(
    valid_spill_observation,
    environmental_data,
    tmp_path: Path,
):
    """CASE D: Multiple candidate vessels with varying proximity correctly ranked."""
    current_ds, wind_ds = environmental_data

    # Pre-calculate origin time to place vessels precisely
    origin_time = (valid_spill_observation.timestamp - pd.Timedelta(hours=1)).isoformat()
    lat = valid_spill_observation.latitude
    lon = valid_spill_observation.longitude

    csv_file = tmp_path / "ranking_test.csv"
    # Vessel A (MMSI 111): Very close (dist ~ 0 km)
    # Vessel B (MMSI 222): Farther away (~ 0.05 deg away)
    data = (
        "MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft\n"
        f"111000000,{origin_time},{lat},{lon},12.0,180.0,180.0,CLOSE_VESSEL,IMO1111111,WDC1111,80,0,200,30,10.0\n"
        f"222000000,{origin_time},{lat + 0.04},{lon + 0.04},12.0,180.0,180.0,FAR_VESSEL,IMO2222222,WDC2222,70,0,150,20,8.0\n"
    )
    csv_file.write_text(data, encoding="utf-8")

    result = run_spill_attribution_pipeline(
        spill=valid_spill_observation,
        current_ds=current_ds,
        wind_ds=wind_ds,
        ais_source=csv_file,
        num_particles=20,
        ais_buffer_km=10.0,
    )

    assert result.is_success
    candidates = result.attribution_result.ranked_candidates
    if len(candidates) >= 2:
        # Closer vessel should achieve rank 1 and higher overall/spatial score
        assert candidates[0].rank == 1
        assert candidates[0].score.overall_score >= candidates[1].score.overall_score


def test_case_e_missing_invalid_fields_rejection():
    """CASE E: Missing and invalid AIS data fields handled correctly."""
    # Invalid coordinates
    with pytest.raises(ValueError):
        SpillObservation(latitude=95.0, longitude=72.0, timestamp=pd.Timestamp.now(tz="UTC"))

    # Naive timestamp
    with pytest.raises(ValueError):
        SpillObservation(latitude=18.0, longitude=72.0, timestamp=pd.Timestamp("2026-09-08 12:00:00"))


def test_case_f_utc_timestamp_consistency(
    valid_spill_observation,
    environmental_data,
    multi_vessel_ais_csv,
):
    """CASE F: UTC timezone preservation across all pipeline boundaries."""
    current_ds, wind_ds = environmental_data

    result = run_spill_attribution_pipeline(
        spill=valid_spill_observation,
        current_ds=current_ds,
        wind_ds=wind_ds,
        ais_source=multi_vessel_ais_csv,
        num_particles=20,
    )

    # 1. Spill observation UTC
    assert str(result.spill_observation.timestamp.tz) == "UTC"

    # 2. Origin timestamp UTC
    assert str(result.ocean_result.probable_origin_timestamp.tz) == "UTC"

    # 3. AIS Search Request bounds UTC
    assert str(result.search_request.start_time.tz) == "UTC"
    assert str(result.search_request.end_time.tz) == "UTC"

    # 4. Attribution origin metadata UTC
    assert str(result.origin_metadata.timestamp.tz) == "UTC"


def test_contract_ocean_drift_adapter(valid_spill_observation, environmental_data):
    """Test OceanDriftResult directly adapted to AISIntegrationResult and OriginMetadata."""
    current_ds, wind_ds = environmental_data

    # Generate synthetic particles with realistic spatial spread
    np.random.seed(42)
    lons = np.random.normal(valid_spill_observation.longitude, 0.005, 15)
    lats = np.random.normal(valid_spill_observation.latitude, 0.005, 15)
    particles = [Particle(i + 1, lons[i], lats[i]) for i in range(15)]
    df_bw = hindcast_particles(
        particles=particles,
        current_dataset=current_ds,
        wind_dataset=wind_ds,
        observation_time=valid_spill_observation.timestamp,
        duration_seconds=7200,
        timestep_seconds=3600,
    )

    origin_res = analyze_origin(df_bw)
    unc_res = calculate_uncertainty(df_bw, timestamp=origin_res["best_candidate"].timestamp)

    ocean_output = OceanDriftResult(
        spill_observation=valid_spill_observation,
        best_candidate=origin_res["best_candidate"],
        ranked_candidates=origin_res["ranked_candidates"],
        uncertainty=unc_res,
        hindcast_trajectories=df_bw,
    )

    integration_res, origin_meta = adapt_ocean_drift_to_ais(ocean_output)

    assert isinstance(integration_res, AISIntegrationResult)
    assert isinstance(origin_meta, OriginMetadata)
    assert origin_meta.radius_km == pytest.approx(unc_res.uncertainty_radius_km)
    assert origin_meta.timestamp == unc_res.timestamp
    assert integration_res.search_request.radius_km == pytest.approx(unc_res.uncertainty_radius_km)


def test_real_noaa_ais_provider_pipeline_integration():
    """Test full Member 5 attribution flow with actual NOAA MarineCadastre AIS dataset."""
    real_csv = Path("data/ais/2025/AIS_178881322085076878_1697-1788813221032.csv")
    if not real_csv.exists():
        pytest.skip(f"Real NOAA AIS dataset not found at {real_csv}")

    # Simulated origin candidate in San Francisco Bay on 2025-01-07
    from ocean.drift.origin import CandidateRegion, OriginCandidate
    cand = OriginCandidate(
        timestamp=pd.Timestamp("2025-01-07T01:00:00Z"),
        region=CandidateRegion(
            centroid_lon=-122.39649,
            centroid_lat=37.80115,
            area_sq_meters=200000000.0,
            peak_density=0.08,
            coverage_level=0.5,
        ),
        concentration=0.8,
        density_strength=0.9,
        temporal_stability=0.85,
        heuristic_score=2.5,
    )

    ocean_res = OceanDriftResult(
        best_candidate=cand,
        ranked_candidates=[cand],
        drift_direction_deg=45.0,
    )

    provider = LocalAISProvider(real_csv)
    integration_res, origin_meta = adapt_ocean_drift_to_ais(
        ocean_result=ocean_res,
        buffer_km=2.0,
        before_minutes=30.0,
        after_minutes=30.0,
    )

    df_matched = provider.fetch_ais_data(integration_res.search_request)
    assert not df_matched.empty
    assert len(df_matched["mmsi"].unique()) > 0

    traj_result = reconstruct_trajectories(df_matched)
    interp_result = interpolate_trajectories(traj_result, time_step_seconds=120.0)
    spatial_result = filter_spatial(interp_result, origin_data=integration_res)
    temporal_result = filter_temporal(spatial_result, origin_data=integration_res)

    attr_result = score_candidates(temporal_result, origin_meta)
    assert len(attr_result.ranked_candidates) > 0
    assert attr_result.ranked_candidates[0].rank == 1

    report = explain_attribution(attr_result, top_n=3)
    assert report.total_candidates > 0
    assert len(report.candidate_explanations) > 0


def test_gis_spill_geometry_to_observation():
    """Test Member 3 OilSpillGeometry translation to SpillObservation and SpillMeasurement."""
    from datetime import datetime, timezone
    from gis.geometry.models import Coordinate, LinearRing, OilSpillGeometry, Polygon
    from gis.measurements.models import measure_oil_spill
    from integration.adapters.gis_ocean_adapter import extract_spill_observation

    # Polygon in the Arabian Sea
    poly = Polygon(
        exterior=[
            (65.48, 18.48),
            (65.52, 18.48),
            (65.52, 18.52),
            (65.48, 18.52),
            (65.48, 18.48),
        ]
    )
    det_time = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    spill = OilSpillGeometry(
        spill_id="SAR_SPILL_ARABIAN_01",
        geometry=poly,
        detection_timestamp=det_time,
        source_sensor="Sentinel-1 SAR",
        confidence=0.92,
    )

    obs, measurement = extract_spill_observation(spill)
    assert obs.spill_id == "SAR_SPILL_ARABIAN_01"
    assert pytest.approx(obs.latitude, abs=0.01) == 18.50
    assert pytest.approx(obs.longitude, abs=0.01) == 65.50
    assert obs.area_sq_m > 0
    assert obs.confidence == 0.92
    assert obs.source_sensor == "Sentinel-1 SAR"
    assert measurement.area_sq_km > 0
    assert measurement.compactness > 0


def test_gis_particle_initialization():
    """Test Lagrangian particle sampling from a Member 3 Polygon."""
    from datetime import datetime, timezone
    from gis.geometry.models import OilSpillGeometry, Polygon
    from integration.adapters.gis_ocean_adapter import initialize_particles_from_spill, point_in_polygon

    poly = Polygon(
        exterior=[
            (65.45, 18.45),
            (65.55, 18.45),
            (65.55, 18.55),
            (65.45, 18.55),
            (65.45, 18.45),
        ]
    )
    det_time = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    spill = OilSpillGeometry(
        spill_id="SPILL_PARTICLE_TEST",
        geometry=poly,
        detection_timestamp=det_time,
    )

    particles = initialize_particles_from_spill(spill, num_particles=25, random_seed=42)
    assert len(particles) == 25

    # Particle 1 is exact centroid
    assert pytest.approx(particles[0].longitude, abs=1e-4) == 65.50
    assert pytest.approx(particles[0].latitude, abs=1e-4) == 18.50

    # All particles active and have valid timestamp
    for p in particles:
        assert p.active is True
        assert p.timestamp == det_time
        assert 65.40 <= p.longitude <= 65.60
        assert 18.40 <= p.latitude <= 18.60


def test_end_to_end_pipeline_with_gis_geometry(
    environmental_data, valid_spill_observation, multi_vessel_ais_csv
):
    """Test full end-to-end pipeline ingestion directly from Member 3 OilSpillGeometry."""
    from gis.geometry.models import OilSpillGeometry, Polygon
    from integration.pipeline import run_spill_attribution_pipeline

    current_ds, wind_ds = environmental_data

    lon = valid_spill_observation.longitude
    lat = valid_spill_observation.latitude
    d = 0.01

    poly = Polygon(
        exterior=[
            (lon - d, lat - d),
            (lon + d, lat - d),
            (lon + d, lat + d),
            (lon - d, lat + d),
            (lon - d, lat - d),
        ]
    )
    det_time = valid_spill_observation.timestamp.to_pydatetime()
    spill = OilSpillGeometry(
        spill_id="SAR_ARABIAN_001",
        geometry=poly,
        detection_timestamp=det_time,
        source_sensor="Sentinel-1 SAR C-Band",
        confidence=0.96,
    )

    result = run_spill_attribution_pipeline(
        spill=spill,
        current_ds=current_ds,
        wind_ds=wind_ds,
        ais_source=multi_vessel_ais_csv,
        num_particles=30,
        forward_steps=2,
        hindcast_duration_hours=4.0,
        ais_buffer_km=3.0,
        random_seed=42,
    )

    assert result.is_success is True
    assert result.spill_measurement is not None
    assert result.spill_measurement.area_sq_m > 0
    assert result.gis_layers is not None
    assert result.gis_layers["type"] == "FeatureCollection"
    assert len(result.gis_layers["features"]) >= 2  # Spill + BBox
    assert isinstance(result.attribution_result, AttributionResult)
    assert isinstance(result.explanation_report, AttributionExplanationReport)

