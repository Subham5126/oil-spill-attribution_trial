"""Probable Oil-Spill Origin / Spatial Likelihood Analysis."""

import numpy as np
import pandas as pd
from typing import List, Dict, Any
from scipy.stats import gaussian_kde
import dataclasses


class OriginAnalysisError(ValueError):
    """Raised when origin analysis fails due to invalid inputs or constraints."""
    pass


@dataclasses.dataclass
class CandidateRegion:
    """Represents a high-density candidate origin region."""
    centroid_lon: float
    centroid_lat: float
    area_sq_meters: float
    peak_density: float
    coverage_level: float


@dataclasses.dataclass
class OriginCandidate:
    """Represents a candidate origin at a specific historical timestamp."""
    timestamp: pd.Timestamp
    region: CandidateRegion
    concentration: float
    density_strength: float
    temporal_stability: float
    heuristic_score: float


def _local_metric_projection(lons: np.ndarray, lats: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float, float, float]:
    """
    Project longitude/latitude into a local metric coordinate system (Equirectangular approximation).
    This avoids complex external dependencies while satisfying the MVP requirement for regional spills.
    The approximation is highly accurate for distances under 500km away from the centroid.
    """
    R = 6371000.0
    center_lon = float(np.mean(lons))
    center_lat = float(np.mean(lats))
    
    m_per_deg_lat = np.pi * R / 180.0
    safe_lat = np.clip(center_lat, -89.99, 89.99)
    m_per_deg_lon = m_per_deg_lat * np.cos(np.radians(safe_lat))
    
    x = (lons - center_lon) * m_per_deg_lon
    y = (lats - center_lat) * m_per_deg_lat
    
    return x, y, center_lon, center_lat, m_per_deg_lon, m_per_deg_lat


def _haversine_distance(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculate the great circle distance in meters between two points on the earth."""
    R = 6371000.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi/2.0)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda/2.0)**2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return R * c


def _calculate_hdr(x: np.ndarray, y: np.ndarray, coverage_level: float = 0.5) -> tuple[np.ndarray, np.ndarray, float, float]:
    """
    Perform KDE and identify the Highest Density Region (HDR) covering the requested density mass.
    Returns: (hdr_x, hdr_y, area_sq_meters, peak_density)
    """
    # Handle singularity when particles are perfectly clustered
    if len(x) <= 2 or (np.std(x) < 1.0 and np.std(y) < 1.0):
        return np.array([np.mean(x)]), np.array([np.mean(y)]), np.nan, np.nan

    jitter_x = np.random.normal(0, 1e-3, size=x.shape)
    jitter_y = np.random.normal(0, 1e-3, size=y.shape)
    
    try:
        kde = gaussian_kde(np.vstack([x + jitter_x, y + jitter_y]))
    except np.linalg.LinAlgError:
        return np.array([np.mean(x)]), np.array([np.mean(y)]), np.nan, np.nan
    
    # Evaluate on a grid covering the bounds
    grid_size = 50
    margin = 0.5 * (np.max(x) - np.min(x) + 1.0)
    xi, yi = np.mgrid[
        np.min(x)-margin : np.max(x)+margin : complex(0, grid_size),
        np.min(y)-margin : np.max(y)+margin : complex(0, grid_size)
    ]
    
    positions = np.vstack([xi.ravel(), yi.ravel()])
    densities = kde(positions)
    
    peak_density = float(np.max(densities))
    if peak_density <= 0:
        return np.array([np.mean(x)]), np.array([np.mean(y)]), np.nan, np.nan
        
    # Calculate cell area
    dx_cell = (xi[1,0] - xi[0,0])
    dy_cell = (yi[0,1] - yi[0,0])
    cell_area = abs(dx_cell * dy_cell)
    
    # Sort densities to compute HDR based on probability mass
    sorted_densities = np.sort(densities)[::-1]
    cumulative_mass = np.cumsum(sorted_densities * cell_area)
    
    # Find threshold density that encompasses the requested mass coverage
    threshold_idx = np.searchsorted(cumulative_mass, coverage_level)
    if threshold_idx >= len(sorted_densities):
        threshold_idx = len(sorted_densities) - 1
        
    density_threshold = sorted_densities[threshold_idx]
    
    hdr_mask = densities >= density_threshold
    hdr_x = positions[0][hdr_mask]
    hdr_y = positions[1][hdr_mask]
    
    area_sq_meters = np.sum(hdr_mask) * cell_area
    
    # If grid resolution is too coarse, fallback to 1 cell area minimum
    if area_sq_meters <= 0:
        area_sq_meters = cell_area
        
    return hdr_x, hdr_y, float(area_sq_meters), peak_density


def analyze_origin(
    trajectories: pd.DataFrame,
    coverage_level: float = 0.5,
    w_concentration: float = 1.0,
    w_density: float = 1.0,
    w_stability: float = 1.0
) -> Dict[str, Any]:
    """
    Analyze backward trajectories to identify candidate origin regions and times.
    
    Args:
        trajectories: DataFrame output from OCEAN-07 hindcast.
        coverage_level: Probability mass threshold for High Density Region (0.0 to 1.0).
        w_concentration: Weight for spatial concentration score.
        w_density: Weight for density strength score.
        w_stability: Weight for temporal stability score.
        
    Returns:
        A dictionary containing:
        - "ranked_candidates": List of OriginCandidate objects ranked by score.
        - "best_time": The pd.Timestamp of the highest-scoring candidate.
        - "best_candidate": The highest-scoring OriginCandidate.
        
    Raises:
        OriginAnalysisError: If inputs are invalid or empty.
    """
    if trajectories is None or trajectories.empty:
        raise OriginAnalysisError("Trajectories DataFrame cannot be empty.")
        
    if not (0.0 < coverage_level <= 1.0):
        raise OriginAnalysisError("coverage_level must be between 0.0 (exclusive) and 1.0.")
        
    if not (w_concentration >= 0 and w_density >= 0 and w_stability >= 0):
        raise OriginAnalysisError("Score weights must be non-negative.")
        
    required_cols = {"particle_id", "timestamp", "longitude", "latitude", "active"}
    if not required_cols.issubset(trajectories.columns):
        raise OriginAnalysisError(f"Trajectories DataFrame is missing required columns: {required_cols}")
        
    active_traj = trajectories[trajectories["active"]].copy()
    if active_traj.empty:
        raise OriginAnalysisError("No active particles found in trajectories.")
        
    if not np.isfinite(active_traj["longitude"]).all() or not np.isfinite(active_traj["latitude"]).all():
        raise OriginAnalysisError("Trajectories contain invalid (NaN/Inf) coordinates.")

    timestamps = sorted(active_traj["timestamp"].unique(), reverse=True) # newest to oldest
    
    raw_candidates = []
    
    for t in timestamps:
        t_data = active_traj[active_traj["timestamp"] == t]
        
        lons = t_data["longitude"].values
        lats = t_data["latitude"].values
        
        if len(t_data) <= 2:
            region = CandidateRegion(float(np.mean(lons)), float(np.mean(lats)), np.nan, np.nan, coverage_level)
            raw_candidates.append({
                "timestamp": t,
                "region": region,
                "area": np.nan,
                "peak_density": np.nan,
                "centroid_lon": float(np.mean(lons)),
                "centroid_lat": float(np.mean(lats))
            })
            continue
            
        # Project to local metric CRS
        x, y, center_lon, center_lat, mx, my = _local_metric_projection(lons, lats)
        
        # KDE and HDR
        hdr_x, hdr_y, area, peak_dens = _calculate_hdr(x, y, coverage_level)
        
        # HDR Centroid
        if len(hdr_x) == 0 or len(hdr_y) == 0:
            hdr_center_x = np.mean(x)
            hdr_center_y = np.mean(y)
        else:
            hdr_center_x = np.mean(hdr_x)
            hdr_center_y = np.mean(hdr_y)
        
        # Project back to geographic
        hdr_lon = center_lon + (hdr_center_x / mx)
        hdr_lat = center_lat + (hdr_center_y / my)
        
        region = CandidateRegion(hdr_lon, hdr_lat, area, peak_dens, coverage_level)
        raw_candidates.append({
            "timestamp": t,
            "region": region,
            "area": area,
            "peak_density": peak_dens,
            "centroid_lon": hdr_lon,
            "centroid_lat": hdr_lat
        })

    # Normalize metrics
    valid_areas = [c["area"] for c in raw_candidates if not np.isnan(c["area"]) and c["area"] > 0]
    max_area = max(valid_areas) if valid_areas else 1.0
    
    valid_peaks = [c["peak_density"] for c in raw_candidates if not np.isnan(c["peak_density"])]
    max_peak = max(valid_peaks) if valid_peaks else 1.0
    
    candidates = []
    for i, rc in enumerate(raw_candidates):
        # Concentration ~ 1 / area (normalized). Exclude degenerate regions.
        if np.isnan(rc["area"]) or rc["area"] <= 0:
            c_score = 0.0
            d_score = 0.0
        else:
            c_score = max_area / rc["area"]
            d_score = rc["peak_density"] / max_peak
            
        # Temporal stability: distance to PREVIOUS historical timestep (i+1 in our newest-to-oldest list)
        stability_score = 1.0
        if i < len(raw_candidates) - 1:
            prev_rc = raw_candidates[i+1] # Historical previous step (older)
            dist = _haversine_distance(rc["centroid_lon"], rc["centroid_lat"], prev_rc["centroid_lon"], prev_rc["centroid_lat"])
            stability_score = 1.0 / (1.0 + dist / 1000.0) # decay with km distance
            
        candidates.append(OriginCandidate(
            timestamp=rc["timestamp"],
            region=rc["region"],
            concentration=c_score,
            density_strength=d_score,
            temporal_stability=stability_score,
            heuristic_score=0.0 # calculated below
        ))

    # Normalize concentration to [0, 1] across candidates to keep weights balanced
    max_c = max([c.concentration for c in candidates] + [0.0])
    for c in candidates:
        if max_c > 0:
            c.concentration /= max_c
        
        # Score = heuristic weighted sum
        c.heuristic_score = (w_concentration * c.concentration + 
                             w_density * c.density_strength + 
                             w_stability * c.temporal_stability)

    # Rank
    ranked = sorted(candidates, key=lambda c: c.heuristic_score, reverse=True)
    
    return {
        "ranked_candidates": ranked,
        "best_time": ranked[0].timestamp,
        "best_candidate": ranked[0]
    }
