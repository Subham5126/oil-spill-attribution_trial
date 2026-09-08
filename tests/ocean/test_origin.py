import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from ocean.drift.origin import analyze_origin, OriginAnalysisError, CandidateRegion, OriginCandidate

def create_synthetic_trajectories(configs):
    """
    Create a DataFrame of trajectories.
    configs is a list of tuples: (timestamp, [(lon, lat, active), ...])
    """
    records = []
    pid = 1
    for t_str, particles in configs:
        t = pd.Timestamp(t_str)
        for lon, lat, active in particles:
            records.append({
                "particle_id": pid,
                "timestamp": t,
                "longitude": lon,
                "latitude": lat,
                "active": active
            })
            pid += 1
    return pd.DataFrame(records)

def test_empty_input_raises_error():
    with pytest.raises(OriginAnalysisError, match="cannot be empty"):
        analyze_origin(pd.DataFrame())
        
def test_missing_columns_raises_error():
    df = pd.DataFrame({"longitude": [10.0], "latitude": [10.0]})
    with pytest.raises(OriginAnalysisError, match="missing required columns"):
        analyze_origin(df)

def test_invalid_coordinates_raises_error():
    df = create_synthetic_trajectories([("2025-01-01T00:00:00Z", [(np.nan, 10.0, True)])])
    with pytest.raises(OriginAnalysisError, match="invalid \\(NaN/Inf\\) coordinates"):
        analyze_origin(df)

def test_inactive_particles_excluded():
    # Only inactive particles
    df = create_synthetic_trajectories([("2025-01-01T00:00:00Z", [(10.0, 10.0, False), (10.1, 10.1, False)])])
    with pytest.raises(OriginAnalysisError, match="No active particles"):
        analyze_origin(df)

def test_single_timestep_clustered_particles():
    df = create_synthetic_trajectories([
        ("2025-01-01T00:00:00Z", [
            (10.0001, 10.0001, True),
            (10.0002, 10.0002, True),
            (10.0001, 10.0002, True),
            (10.0002, 10.0001, True),
        ])
    ])
    result = analyze_origin(df)
    assert len(result["ranked_candidates"]) == 1
    cand = result["best_candidate"]
    assert np.isclose(cand.region.centroid_lon, 10.00015, atol=1e-3)
    assert np.isclose(cand.region.centroid_lat, 10.00015, atol=1e-3)

def test_concentration_score():
    # T1: Very concentrated
    # T2: Widely dispersed
    df = create_synthetic_trajectories([
        ("2025-01-01T01:00:00Z", [
            (10.0001, 10.0001, True), (10.0002, 10.0002, True),
            (10.0001, 10.0002, True), (10.0002, 10.0001, True)
        ]),
        ("2025-01-01T00:00:00Z", [
            (9.0, 9.0, True), (11.0, 11.0, True),
            (9.0, 11.0, True), (11.0, 9.0, True)
        ])
    ])
    result = analyze_origin(df)
    cands = {c.timestamp: c for c in result["ranked_candidates"]}
    
    t1 = pd.Timestamp("2025-01-01T01:00:00Z")
    t2 = pd.Timestamp("2025-01-01T00:00:00Z")
    
    assert cands[t1].concentration > cands[t2].concentration

def test_origin_scoring_and_ranking():
    df = create_synthetic_trajectories([
        ("2025-01-01T01:00:00Z", [
            (10.0001, 10.0001, True), (10.0002, 10.0002, True),
            (10.0001, 10.0002, True), (10.0002, 10.0001, True)
        ]),
        ("2025-01-01T00:00:00Z", [
            (9.0, 9.0, True), (11.0, 11.0, True),
            (9.0, 11.0, True), (11.0, 9.0, True)
        ])
    ])
    result = analyze_origin(df, w_concentration=1.0, w_density=0.0, w_stability=0.0)
    best = result["best_candidate"]
    
    # Highly concentrated should be the best candidate when weight is on concentration
    assert best.timestamp == pd.Timestamp("2025-01-01T01:00:00Z")
    
    ranked = result["ranked_candidates"]
    assert ranked[0].heuristic_score >= ranked[1].heuristic_score

def test_temporal_stability():
    # T3, T2, T1 (T3 is newest).
    # T3 -> T2: centroid moves little
    # T2 -> T1: centroid moves heavily
    df = create_synthetic_trajectories([
        ("2025-01-01T02:00:00Z", [
            (10.0, 10.0, True), (10.0, 10.01, True), (10.01, 10.0, True)
        ]),
        ("2025-01-01T01:00:00Z", [
            (10.001, 10.001, True), (10.001, 10.011, True), (10.011, 10.001, True)
        ]),
        ("2025-01-01T00:00:00Z", [
            (12.0, 12.0, True), (12.0, 12.01, True), (12.01, 12.0, True)
        ])
    ])
    result = analyze_origin(df)
    cands = {c.timestamp: c for c in result["ranked_candidates"]}
    
    t3 = pd.Timestamp("2025-01-01T02:00:00Z")
    t2 = pd.Timestamp("2025-01-01T01:00:00Z")
    t1 = pd.Timestamp("2025-01-01T00:00:00Z")
    
    # Stability: comparing distance to previous historical step (older).
    # t1 (oldest) has no older step -> stability 1.0
    # t2 compares to t1 -> large distance -> low stability
    # t3 compares to t2 -> small distance -> high stability
    assert cands[t3].temporal_stability > cands[t2].temporal_stability

def test_no_mutation():
    df = create_synthetic_trajectories([("2025-01-01T00:00:00Z", [(10.0, 10.0, True), (10.1, 10.1, True)])])
    df_copy = df.copy()
    analyze_origin(df)
    pd.testing.assert_frame_equal(df, df_copy)

def test_determinism():
    df = create_synthetic_trajectories([("2025-01-01T00:00:00Z", [(10.0, 10.0, True), (10.1, 10.1, True), (10.0, 10.1, True)])])
    res1 = analyze_origin(df)
    res2 = analyze_origin(df)
    assert res1["best_candidate"].heuristic_score == res2["best_candidate"].heuristic_score
    assert res1["best_candidate"].region.centroid_lon == res2["best_candidate"].region.centroid_lon

def test_realistic_integration():
    from ocean.currents import load_currents
    from ocean.wind import load_wind
    from ocean.drift import Particle, hindcast_particles
    
    current_path = Path("data/sample/copernicus/current_test.nc")
    wind_path = Path("data/sample/era5/wind_test.nc")
    
    if not current_path.is_file() or not wind_path.is_file():
        pytest.skip("Sample NetCDF files not available")
        
    current_ds = load_currents(current_path)
    wind_ds = load_wind(wind_path)
    
    lon = float(current_ds["longitude"].values.mean())
    lat = float(current_ds["latitude"].values.mean())
    obs_time = pd.Timestamp(current_ds["time"].values[-2]).tz_localize("UTC")
    
    # Slight scatter
    particles = [
        Particle(1, lon, lat),
        Particle(2, lon + 0.01, lat + 0.01),
        Particle(3, lon - 0.01, lat - 0.01),
        Particle(4, lon + 0.01, lat - 0.01)
    ]
    
    traj_df = hindcast_particles(particles, current_ds, wind_ds, obs_time, duration_seconds=7200, timestep_seconds=3600)
    
    # Now analyze the origin
    res = analyze_origin(traj_df)
    
    assert "best_time" in res
    assert "best_candidate" in res
    assert len(res["ranked_candidates"]) == 3 # 7200 duration / 3600 step -> 3 records per particle
    
    best = res["best_candidate"]
    assert np.isfinite(best.region.centroid_lon)
    assert np.isfinite(best.region.centroid_lat)
    assert best.heuristic_score > 0

def test_projection_accuracy():
    from ocean.drift.origin import _local_metric_projection, _haversine_distance
    # Equator, 1 degree lon diff
    lons = np.array([0.0, 1.0])
    lats = np.array([0.0, 0.0])
    x, y, clon, clat, mx, my = _local_metric_projection(lons, lats)
    
    dist_approx = abs(x[1] - x[0])
    dist_exact = _haversine_distance(0.0, 0.0, 1.0, 0.0)
    
    # Error should be < 0.1% for regional scales
    assert abs(dist_approx - dist_exact) / dist_exact < 0.001

def test_hdr_mass_coverage():
    # 50% HDR should be smaller area than 80% HDR
    df = create_synthetic_trajectories([
        ("2025-01-01T01:00:00Z", [
            (10.0 + i*0.001, 10.0 + j*0.001, True)
            for i in range(10) for j in range(10)
        ])
    ])
    res_50 = analyze_origin(df, coverage_level=0.5)["best_candidate"]
    res_80 = analyze_origin(df, coverage_level=0.8)["best_candidate"]
    
    assert res_50.region.area_sq_meters < res_80.region.area_sq_meters

def test_degenerate_fallback_concentration():
    # Only 2 particles = degenerate
    df = create_synthetic_trajectories([
        ("2025-01-01T01:00:00Z", [
            (10.0, 10.0, True), (10.0, 10.1, True)
        ])
    ])
    res = analyze_origin(df)["best_candidate"]
    # Should get 0.0 concentration instead of infinity
    assert res.concentration == 0.0
    assert np.isnan(res.region.area_sq_meters)

def test_invalid_weights_rejected():
    df = create_synthetic_trajectories([
        ("2025-01-01T01:00:00Z", [(10.0, 10.0, True), (10.0, 10.1, True), (10.1, 10.0, True)])
    ])
    with pytest.raises(OriginAnalysisError, match="non-negative"):
        analyze_origin(df, w_concentration=-1.0)
