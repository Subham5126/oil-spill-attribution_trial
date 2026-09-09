"""GIS to Ocean/Drift Adapter (Member 3 -> Member 4).

Provides translation and particle initialization functions that convert
Member 3 GIS geometric models (OilSpillGeometry, Polygon, MultiPolygon)
and SpillMeasurements into initial Lagrangian Particle collections
conforming to Member 4's simulation and hindcast interfaces.
"""

from __future__ import annotations

import math
from typing import Any, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from gis.geometry.models import (
    BoundingBox,
    MultiPolygon,
    OilSpillGeometry,
    Point as GisPoint,
    Polygon as GisPolygon,
)
from gis.measurements.models import SpillMeasurement, measure_oil_spill
from integration.contracts.spill_contract import SpillObservation
from ocean.drift.particle import Particle


def extract_spill_observation(
    spill: Union[OilSpillGeometry, SpillObservation, GisPolygon, MultiPolygon],
    timestamp: Optional[Any] = None,
) -> Tuple[SpillObservation, SpillMeasurement]:
    """Extract or construct SpillObservation and SpillMeasurement from any supported spill input.

    Args:
        spill: OilSpillGeometry, SpillObservation, Polygon, or MultiPolygon.
        timestamp: Optional fallback timestamp if input does not contain one.

    Returns:
        Tuple of (SpillObservation, SpillMeasurement).
    """
    if isinstance(spill, SpillObservation):
        if isinstance(spill.polygon, (GisPolygon, MultiPolygon, OilSpillGeometry)):
            measurement = measure_oil_spill(spill.polygon)
        else:
            # Synthetic or point-based observation
            centroid_pt = GisPoint(spill.longitude, spill.latitude)
            area = spill.area_sq_m or 10000.0
            radius_deg = math.sqrt(area / math.pi) / 111320.0
            bbox = BoundingBox(
                min_x=spill.longitude - radius_deg,
                min_y=spill.latitude - radius_deg,
                max_x=spill.longitude + radius_deg,
                max_y=spill.latitude + radius_deg,
            )
            perim = spill.perimeter_m or (2 * math.pi * math.sqrt(area / math.pi))
            measurement = SpillMeasurement(
                area_sq_m=area,
                area_sq_km=area / 1e6,
                perimeter_m=perim,
                perimeter_km=perim / 1000.0,
                centroid=centroid_pt,
                bounding_box=bbox,
                bbox_width_m=radius_deg * 2 * 111320.0,
                bbox_height_m=radius_deg * 2 * 111320.0,
                aspect_ratio=spill.aspect_ratio or 1.0,
                compactness=spill.compactness or 1.0,
                spill_id=spill.spill_id,
            )
        return spill, measurement

    if isinstance(spill, OilSpillGeometry):
        measurement = measure_oil_spill(spill)
        obs = SpillObservation.from_oil_spill_geometry(spill, measurement=measurement)
        return obs, measurement

    if isinstance(spill, (GisPolygon, MultiPolygon)):
        measurement = measure_oil_spill(spill)
        ts = timestamp or pd.Timestamp.now(tz="UTC")
        obs = SpillObservation(
            latitude=measurement.centroid.lat,
            longitude=measurement.centroid.lon,
            timestamp=ts,
            spill_id=getattr(measurement, "spill_id", "detected_spill"),
            area_sq_m=measurement.area_sq_m,
            polygon=spill,
            perimeter_m=measurement.perimeter_m,
            bounding_box=measurement.bounding_box.to_tuple() if measurement.bounding_box else None,
            compactness=measurement.compactness,
            aspect_ratio=measurement.aspect_ratio,
        )
        return obs, measurement

    raise TypeError(
        f"Unsupported spill type: {type(spill)}. Expected OilSpillGeometry, SpillObservation, Polygon, or MultiPolygon."
    )


def point_in_polygon(lon: float, lat: float, polygon: Union[GisPolygon, MultiPolygon]) -> bool:
    """Check if a coordinate (lon, lat) lies inside a Member 3 Polygon or MultiPolygon.

    Uses ray casting algorithm for point-in-polygon testing without hard external dependencies.
    """
    if isinstance(polygon, MultiPolygon):
        return any(point_in_polygon(lon, lat, p) for p in polygon.polygons)

    # Check exterior ring
    ext_coords = polygon.exterior.coordinates
    inside = False
    n = len(ext_coords)
    p1x, p1y = ext_coords[0].lon, ext_coords[0].lat
    for i in range(1, n + 1):
        p2x, p2y = ext_coords[i % n].lon, ext_coords[i % n].lat
        if lat > min(p1y, p2y):
            if lat <= max(p1y, p2y):
                if lon <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (lat - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or lon <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y

    if not inside:
        return False

    # Check if point is inside any interior hole ring (if inside hole, then not inside polygon)
    for hole in polygon.interiors:
        hole_coords = hole.coordinates
        hole_inside = False
        nh = len(hole_coords)
        h1x, h1y = hole_coords[0].lon, hole_coords[0].lat
        for i in range(1, nh + 1):
            h2x, h2y = hole_coords[i % nh].lon, hole_coords[i % nh].lat
            if lat > min(h1y, h2y):
                if lat <= max(h1y, h2y):
                    if lon <= max(h1x, h2x):
                        if h1y != h2y:
                            hxinters = (lat - h1y) * (h2x - h1x) / (h2y - h1y) + h1x
                        if h1x == h2x or lon <= hxinters:
                            hole_inside = not hole_inside
            h1x, h1y = h2x, h2y
        if hole_inside:
            return False

    return True


def initialize_particles_from_spill(
    spill: Union[OilSpillGeometry, SpillObservation, GisPolygon, MultiPolygon],
    num_particles: int = 50,
    random_seed: Optional[int] = 42,
) -> List[Particle]:
    """Initialize a collection of Lagrangian Particles distributed across the observed oil spill.

    Particle 0 is positioned at the exact geodesic centroid of the spill.
    The remaining particles are sampled deterministically inside the spill polygon boundary.
    If the polygon is narrow or discrete, falls back gracefully to a bounded dispersion
    scaled by the spill's physical dimensions.

    Args:
        spill: OilSpillGeometry, SpillObservation, Polygon, or MultiPolygon.
        num_particles: Total number of particles to initialize (must be >= 1).
        random_seed: Random seed for deterministic reproducibility.

    Returns:
        List of Member 4 Particle instances ready for simulation or hindcasting.
    """
    if num_particles < 1:
        raise ValueError(f"num_particles must be at least 1, got {num_particles}")

    obs, measurement = extract_spill_observation(spill)
    centroid_lon = measurement.centroid.lon
    centroid_lat = measurement.centroid.lat
    obs_time = obs.timestamp

    # Seed RNG if provided
    rng = np.random.default_rng(random_seed)

    particles: List[Particle] = []

    # Particle 0: Exact geodesic centroid
    particles.append(
        Particle(
            particle_id=1,
            longitude=float(centroid_lon),
            latitude=float(centroid_lat),
            timestamp=obs_time,
            active=True,
        )
    )

    if num_particles == 1:
        return particles

    # Determine spatial bounding box for sampling
    bbox = measurement.bounding_box
    min_lon, min_lat = bbox.min_x, bbox.min_y
    max_lon, max_lat = bbox.max_x, bbox.max_y

    polygon_geom = obs.polygon
    is_geom_valid = isinstance(polygon_geom, (GisPolygon, MultiPolygon))

    # Deterministic rejection sampling inside polygon
    remaining = num_particles - 1
    collected: List[Tuple[float, float]] = []
    max_attempts = max(500, remaining * 50)
    attempts = 0

    if is_geom_valid:
        while len(collected) < remaining and attempts < max_attempts:
            cand_lon = float(rng.uniform(min_lon, max_lon))
            cand_lat = float(rng.uniform(min_lat, max_lat))
            if point_in_polygon(cand_lon, cand_lat, polygon_geom):
                collected.append((cand_lon, cand_lat))
            attempts += 1

    # If sampling within polygon produced fewer than required (e.g. very thin polygon or non-polygon input),
    # sample from a Gaussian centered at centroid scaled by equivalent circular radius
    if len(collected) < remaining:
        radius_m = math.sqrt(max(measurement.area_sq_m, 100.0) / math.pi)
        sigma_deg = (radius_m / 111320.0) * 0.5  # ~2-sigma covers the spill radius
        deficit = remaining - len(collected)
        lons_fallback = rng.normal(centroid_lon, sigma_deg, deficit)
        lats_fallback = rng.normal(centroid_lat, sigma_deg, deficit)
        for flon, flat in zip(lons_fallback, lats_fallback):
            collected.append((float(flon), float(flat)))

    # Construct remaining Particle instances
    for idx, (lon, lat) in enumerate(collected[:remaining]):
        particles.append(
            Particle(
                particle_id=idx + 2,
                longitude=lon,
                latitude=lat,
                timestamp=obs_time,
                active=True,
            )
        )

    return particles
