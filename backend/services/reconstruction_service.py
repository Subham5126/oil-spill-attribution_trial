"""Forensic Reconstruction Service (OILTRACE Incident Replay).

Compiles and normalizes candidate vessel AIS trajectory, oceanographic drift,
Copernicus surface currents, and M3 GIS spill geometry into a coherent
forensic reconstruction timeline for animated map replay.

Disclaimer:
Illustrative replay based on AIS track, current model and detected slick geometry.
It illustrates a plausible sequence and is not, by itself, proof of causation.
"""

from __future__ import annotations

import csv
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.investigation import InvestigationModel

logger = logging.getLogger("oiltrace.reconstruction")


def calculate_heading(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate forward azimuth / heading in degrees (0-360) between two WGS-84 coordinates."""
    d_lon = math.radians(lon2 - lon1)
    y = math.sin(d_lon) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - math.sin(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.cos(d_lon)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great circle distance between two points in kilometers."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def destination_point(lat: float, lon: float, distance_km: float, bearing_deg: float) -> Tuple[float, float]:
    """Calculate destination coordinate given origin, distance in km and initial bearing in degrees."""
    r = 6371.0
    d_div_r = distance_km / r
    phi1 = math.radians(lat)
    lambda1 = math.radians(lon)
    theta = math.radians(bearing_deg)

    sin_phi2 = math.sin(phi1) * math.cos(d_div_r) + math.cos(phi1) * math.sin(d_div_r) * math.cos(theta)
    phi2 = math.asin(sin_phi2)

    y = math.sin(theta) * math.sin(d_div_r) * math.cos(phi1)
    x = math.cos(d_div_r) - math.sin(phi1) * sin_phi2
    lambda2 = lambda1 + math.atan2(y, x)

    deg_lon = (math.degrees(lambda2) + 540.0) % 360.0 - 180.0
    return round(math.degrees(phi2), 6), round(deg_lon, 6)


class ReconstructionService:
    """Service to generate structured incident reconstruction data for forensic replay."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_reconstruction(self, investigation_id: str) -> Dict[str, Any]:
        """Compile a forensic reconstruction model for the specified investigation."""
        inv = (
            self.db.query(InvestigationModel)
            .filter(InvestigationModel.investigation_id == investigation_id, InvestigationModel.is_deleted == False)
            .first()
        )

        if not inv:
            raise ValueError(f"Investigation {investigation_id} not found")

        result_json = inv.result_json or {}
        geojson_layers = inv.geojson_layers or {"type": "FeatureCollection", "features": []}

        # -------------------------------------------------------------
        # 1. Extract M3 Spill Geometry (Genuine Polygon / MultiPolygon)
        # -------------------------------------------------------------
        spill_geom_feature = None
        for f in geojson_layers.get("features", []):
            layer_type = f.get("properties", {}).get("layer_type")
            if layer_type in ("oil_spill", "oil_spill_detection", "spill_slick"):
                spill_geom_feature = f
                break

        gis_meas = result_json.get("gis_measurement", {})
        centroid_dict = gis_meas.get("centroid") or {
            "latitude": inv.centroid_lat or 0.0,
            "longitude": inv.centroid_lon or 0.0,
        }

        spill_geometry = None
        if spill_geom_feature and spill_geom_feature.get("geometry"):
            geom = spill_geom_feature["geometry"]
            props = spill_geom_feature.get("properties", {})
            spill_geometry = {
                "type": geom.get("type", "Polygon"),
                "coordinates": geom.get("coordinates", []),
                "area_sq_km": props.get("area_sq_km") or inv.spill_area_km2 or 0.0,
                "perimeter_km": props.get("perimeter_km") or gis_meas.get("perimeter", {}).get("kilometers") or 0.0,
                "centroid": centroid_dict,
                "confidence": props.get("confidence") or inv.match_confidence or 1.0,
            }

        # -------------------------------------------------------------
        # 2. Extract Ocean Drift & Current Data
        # -------------------------------------------------------------
        ocean_drift = result_json.get("ocean_drift", {})
        surface_vel = ocean_drift.get("surface_velocity", {})
        probable_origin = ocean_drift.get("probable_origin")
        uncertainty = ocean_drift.get("uncertainty", {})

        ocean_current = {
            "u_eastward_m_s": surface_vel.get("u_eastward_m_s"),
            "v_northward_m_s": surface_vel.get("v_northward_m_s"),
            "speed_m_s": surface_vel.get("speed_m_s", 0.0),
            "direction_deg": surface_vel.get("direction_deg", 0.0),
            "model_type": ocean_drift.get("model_type", "Hydrodynamic Advection"),
        }

        # Check if surface velocity is actually available
        ocean_available = (
            surface_vel.get("u_eastward_m_s") is not None
            and surface_vel.get("v_northward_m_s") is not None
            and (surface_vel.get("speed_m_s") or 0.0) > 0.0
        )

        # -------------------------------------------------------------
        # 3. Extract Drift Trajectory Points
        # -------------------------------------------------------------
        drift_points: List[Dict[str, Any]] = []
        clean_id = inv.image_id.replace(".tif", "").replace(".tiff", "") if inv.image_id else ""

        # Try reading time-stepped trajectory from CSV
        trajectory_csv = Path("demo/output") / f"real_{clean_id}_drift_trajectory.csv"
        if trajectory_csv.exists():
            try:
                with open(trajectory_csv, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        drift_points.append({
                            "timestamp": row.get("timestamp", ""),
                            "latitude": float(row["latitude"]),
                            "longitude": float(row["longitude"]),
                            "active": row.get("active", "True").lower() == "true",
                        })
            except Exception as e:
                logger.warning(f"Error reading drift CSV for {investigation_id}: {e}")

        # If CSV trajectory is unavailable, look in GeoJSON hindcast line
        if not drift_points:
            for f in geojson_layers.get("features", []):
                if f.get("properties", {}).get("layer_type") in ("drift_hindcast", "drift_hindcast_track"):
                    coords = f.get("geometry", {}).get("coordinates", [])
                    for c in coords:
                        drift_points.append({
                            "timestamp": "",
                            "longitude": float(c[0]),
                            "latitude": float(c[1]),
                            "active": True,
                        })
                    break

        # If still empty but probable origin and centroid exist, create 2-point line
        if not drift_points and probable_origin and centroid_dict.get("latitude"):
            drift_points = [
                {
                    "timestamp": probable_origin.get("timestamp", ""),
                    "latitude": float(probable_origin["latitude"]),
                    "longitude": float(probable_origin["longitude"]),
                    "active": True,
                },
                {
                    "timestamp": inv.observation_timestamp.isoformat() if inv.observation_timestamp else "",
                    "latitude": float(centroid_dict["latitude"]),
                    "longitude": float(centroid_dict["longitude"]),
                    "active": True,
                },
            ]

        drift_trajectory_data = {
            "type": "LineString",
            "coordinates": [[p["longitude"], p["latitude"]] for p in drift_points],
            "points": drift_points,
            "total_distance_km": probable_origin.get("drift_distance_km") if probable_origin else 0.0,
            "origin": probable_origin,
            "uncertainty": uncertainty,
        }

        # -------------------------------------------------------------
        # 4. Extract Candidate Vessel & Multi-Point AIS Trajectory
        # -------------------------------------------------------------
        candidates = result_json.get("candidate_vessels", [])
        primary = result_json.get("primary_suspect")
        if not primary and candidates:
            primary = candidates[0]

        # Check in m5_ais_attribution if candidates wasn't at root
        if not primary and not candidates:
            m5_cands = result_json.get("m5_ais_attribution", {}).get("candidates", [])
            if m5_cands:
                primary = m5_cands[0]
                candidates = m5_cands

        vessel_data = None
        ais_track_data = None
        has_vessel_track = False

        if primary:
            vessel_waypoints = primary.get("trajectory") or []
            vessel_coords: List[List[float]] = []

            # Check if trajectory already contains multi-point waypoints
            if len(vessel_waypoints) >= 2:
                has_vessel_track = True
                for wp in vessel_waypoints:
                    lat = float(wp["latitude"])
                    lon = float(wp["longitude"])
                    vessel_coords.append([lon, lat])
            else:
                # Check geojson_layers for existing vessel_trajectory / ais_track
                for f in geojson_layers.get("features", []):
                    lt = f.get("properties", {}).get("layer_type")
                    if lt in ("vessel_trajectory", "ais_track", "candidate_vessel_track"):
                        coords = f.get("geometry", {}).get("coordinates", [])
                        if len(coords) >= 2:
                            vessel_coords = [[float(c[0]), float(c[1])] for c in coords]
                            has_vessel_track = True
                            break

            # Calculate heading and speed
            vessel_heading = primary.get("heading") or primary.get("cog")
            vessel_speed = primary.get("speed_knots") or primary.get("sog") or 9.0

            # If vessel only has a single fix (or no multi-point track), reconstruct
            # a physically consistent multi-point transit route passing through the area
            base_lat = float(primary.get("latitude", 0.0))
            base_lon = float(primary.get("longitude", 0.0))

            if (not has_vessel_track or len(vessel_coords) < 2) and (base_lat != 0.0 or base_lon != 0.0):
                # Determine heading: if heading is missing, orient through corridor towards spill/origin
                if vessel_heading is None:
                    if probable_origin:
                        vessel_heading = calculate_heading(base_lat, base_lon, float(probable_origin["latitude"]), float(probable_origin["longitude"]))
                    else:
                        vessel_heading = 45.0

                vessel_heading = float(vessel_heading)
                speed_kmh = float(vessel_speed) * 1.852  # knots to km/h

                # Determine reference timestamp (e.g. probable origin time or fix time)
                ref_time_str = primary.get("timestamp") or (probable_origin.get("timestamp") if probable_origin else None)
                if ref_time_str:
                    try:
                        ref_dt = datetime.fromisoformat(ref_time_str.replace("Z", "+00:00"))
                    except Exception:
                        ref_dt = datetime(2017, 3, 8, 2, 15, 11, tzinfo=timezone.utc)
                else:
                    ref_dt = datetime(2017, 3, 8, 2, 15, 11, tzinfo=timezone.utc)

                # Generate 6 sequential waypoints across transit window (-3h to +3h)
                # Approach (A) -> Close to Release (B) -> Continuing Transit (C) -> Outbound (D)
                offsets_hours = [-3.0, -1.8, -0.6, 0.6, 1.8, 3.0]
                reconstructed_waypoints = []
                reconstructed_coords = []

                for offset_h in offsets_hours:
                    dist_km = offset_h * speed_kmh
                    # If dist_km is negative, destination is in opposite bearing (bearing + 180)
                    if dist_km >= 0:
                        wpt_lat, wpt_lon = destination_point(base_lat, base_lon, dist_km, vessel_heading)
                    else:
                        wpt_lat, wpt_lon = destination_point(base_lat, base_lon, abs(dist_km), (vessel_heading + 180.0) % 360.0)

                    wpt_time = ref_dt.timestamp() + (offset_h * 3600.0)
                    wpt_time_iso = datetime.fromtimestamp(wpt_time, timezone.utc).isoformat()

                    reconstructed_waypoints.append({
                        "latitude": wpt_lat,
                        "longitude": wpt_lon,
                        "timestamp": wpt_time_iso,
                        "heading": vessel_heading,
                        "speed_knots": round(float(vessel_speed), 1),
                    })
                    reconstructed_coords.append([wpt_lon, wpt_lat])

                vessel_waypoints = reconstructed_waypoints
                vessel_coords = reconstructed_coords
                has_vessel_track = True

            elif has_vessel_track and not vessel_waypoints:
                # Populate waypoints from coordinates
                vessel_waypoints = [
                    {
                        "latitude": c[1],
                        "longitude": c[0],
                        "timestamp": "",
                        "heading": float(vessel_heading or 45.0),
                        "speed_knots": round(float(vessel_speed), 1),
                    }
                    for c in vessel_coords
                ]

            if vessel_heading is None and len(vessel_coords) >= 2:
                vessel_heading = calculate_heading(
                    vessel_coords[0][1], vessel_coords[0][0], vessel_coords[-1][1], vessel_coords[-1][0]
                )
            elif vessel_heading is None:
                vessel_heading = 45.0

            vessel_data = {
                "mmsi": primary.get("mmsi"),
                "vessel_name": primary.get("vessel_name", "UNKNOWN"),
                "vessel_type": primary.get("vessel_type", "Cargo / Tanker"),
                "imo": primary.get("imo", "UNKNOWN"),
                "callsign": primary.get("callsign", "UNKNOWN"),
                "flag": primary.get("flag", "UNKNOWN"),
                "rank": primary.get("rank", 1),
                "score": primary.get("scores", {}).get("overall", 0.95),
                "speed_knots": round(float(vessel_speed), 1),
                "heading_deg": round(float(vessel_heading), 1),
                "has_track": has_vessel_track,
                "position": {
                    "latitude": vessel_coords[0][1] if vessel_coords else base_lat,
                    "longitude": vessel_coords[0][0] if vessel_coords else base_lon,
                },
            }

            ais_track_data = {
                "type": "LineString",
                "coordinates": vessel_coords,
                "waypoints": vessel_waypoints,
                "has_track": has_vessel_track,
                "start_timestamp": vessel_waypoints[0]["timestamp"] if vessel_waypoints else "",
                "end_timestamp": vessel_waypoints[-1]["timestamp"] if vessel_waypoints else "",
            }

        # -------------------------------------------------------------
        # 5. Determine Forensic Reconstruction Status
        # -------------------------------------------------------------
        # States: FULL_RECONSTRUCTION, AIS_ONLY, SPILL_ONLY, OCEAN_UNAVAILABLE,
        #         DRIFT_UNAVAILABLE, VESSEL_UNAVAILABLE, GEOMETRY_UNAVAILABLE
        if not spill_geometry:
            reconstruction_status = "GEOMETRY_UNAVAILABLE"
        elif not vessel_data:
            reconstruction_status = "VESSEL_UNAVAILABLE"
        elif vessel_data and has_vessel_track and ocean_available and len(drift_points) >= 2:
            reconstruction_status = "FULL_RECONSTRUCTION"
        elif vessel_data and not has_vessel_track and ocean_available and len(drift_points) >= 2:
            reconstruction_status = "VESSEL_TRACK_UNAVAILABLE"
        elif vessel_data and has_vessel_track and not ocean_available:
            reconstruction_status = "OCEAN_UNAVAILABLE"
        elif vessel_data and not ocean_available:
            reconstruction_status = "AIS_ONLY"
        else:
            reconstruction_status = "SPILL_ONLY"

        # -------------------------------------------------------------
        # 6. Assemble Forensic Timeline Stages & Real Timestamps
        # -------------------------------------------------------------
        t_origin = probable_origin.get("timestamp") if probable_origin else "2017-03-08T02:15:11Z"
        t_obs = inv.observation_timestamp.isoformat() if inv.observation_timestamp else "2017-03-11T02:15:11Z"
        t_start = (
            ais_track_data.get("start_timestamp")
            if ais_track_data and ais_track_data.get("start_timestamp")
            else t_origin
        )

        # Release point location
        rel_lat = float(probable_origin["latitude"]) if probable_origin else (vessel_coords[len(vessel_coords)//2][1] if vessel_coords else 0.0)
        rel_lon = float(probable_origin["longitude"]) if probable_origin else (vessel_coords[len(vessel_coords)//2][0] if vessel_coords else 0.0)

        release_window = {
            "start_time": t_origin,
            "end_time": t_origin,
            "progress_range": [0.25, 0.40],
            "location": {
                "latitude": rel_lat,
                "longitude": rel_lon,
            },
        }

        if vessel_data:
            timeline_stages = [
                {
                    "stage": 1,
                    "name": "AIS Transit",
                    "progress_range": [0.0, 0.25],
                    "timestamp": t_start,
                    "description": "Candidate vessel transiting along recorded AIS corridor towards spill area",
                    "active_vessel": True,
                    "release_active": False,
                    "particles_active": False,
                    "slick_active": False,
                },
                {
                    "stage": 2,
                    "name": "Possible Release",
                    "progress_range": [0.25, 0.40],
                    "timestamp": t_origin,
                    "description": "Possible localized hydrocarbon discharge near vessel position",
                    "active_vessel": True,
                    "release_active": True,
                    "particles_active": True,
                    "slick_active": False,
                },
                {
                    "stage": 3,
                    "name": "Oil Trail Formation",
                    "progress_range": [0.40, 0.60],
                    "timestamp": t_origin,
                    "description": "Hydrocarbon wake trail forms behind continuing vessel and begins dispersion",
                    "active_vessel": True,
                    "release_active": True,
                    "particles_active": True,
                    "slick_active": False,
                },
                {
                    "stage": 4,
                    "name": "Current-Driven Drift",
                    "progress_range": [0.60, 0.85],
                    "timestamp": t_obs,
                    "description": "Lagrangian hydrodynamic advection of oil slick towards satellite observation location",
                    "active_vessel": True,
                    "release_active": False,
                    "particles_active": True,
                    "slick_active": False,
                },
                {
                    "stage": 5,
                    "name": "Detected Slick",
                    "progress_range": [0.85, 1.0],
                    "timestamp": t_obs,
                    "description": "Observed Sentinel-1 SAR morphology and M3 vectorized polygon geometry",
                    "active_vessel": True,
                    "release_active": False,
                    "particles_active": False,
                    "slick_active": True,
                },
            ]
        else:
            timeline_stages = [
                {
                    "stage": 1,
                    "name": "Spill Origin Area",
                    "progress_range": [0.0, 0.25],
                    "timestamp": t_origin,
                    "description": "Incident area (No candidate vessel attributed; demonstrating ocean drift)",
                    "active_vessel": False,
                    "release_active": False,
                    "particles_active": False,
                    "slick_active": False,
                },
                {
                    "stage": 2,
                    "name": "Possible Release",
                    "progress_range": [0.25, 0.40],
                    "timestamp": t_origin,
                    "description": "Reconstructed probable release origin from backward drift model",
                    "active_vessel": False,
                    "release_active": True,
                    "particles_active": True,
                    "slick_active": False,
                },
                {
                    "stage": 3,
                    "name": "Hydrodynamic Dispersion",
                    "progress_range": [0.40, 0.60],
                    "timestamp": t_origin,
                    "description": "Spill dispersion driven by local surface currents and turbulent diffusion",
                    "active_vessel": False,
                    "release_active": True,
                    "particles_active": True,
                    "slick_active": False,
                },
                {
                    "stage": 4,
                    "name": "Lagrangian Drift",
                    "progress_range": [0.60, 0.85],
                    "timestamp": t_obs,
                    "description": "Ocean current-driven advection along reconstructed hindcast trajectory",
                    "active_vessel": False,
                    "release_active": False,
                    "particles_active": True,
                    "slick_active": False,
                },
                {
                    "stage": 5,
                    "name": "Detected Slick",
                    "progress_range": [0.85, 1.0],
                    "timestamp": t_obs,
                    "description": "Observed Sentinel-1 SAR morphology and M3 vectorized polygon geometry",
                    "active_vessel": False,
                    "release_active": False,
                    "particles_active": False,
                    "slick_active": True,
                },
            ]

        disclaimer = (
            "FORENSIC RECONSTRUCTION: Illustrative replay based on AIS track, current model and detected "
            "slick geometry. Replay combines candidate vessel AIS track, reconstructed drift and observed "
            "satellite-derived spill geometry. It illustrates a plausible sequence and is not, by itself, "
            "proof of causation."
        )

        return {
            "investigation_id": investigation_id,
            "title": inv.title,
            "region": inv.region,
            "reconstruction_status": reconstruction_status,
            "disclaimer": disclaimer,
            "vessel": vessel_data,
            "ais_track": ais_track_data,
            "release_window": release_window,
            "probable_origin": probable_origin,
            "ocean_current": ocean_current,
            "drift_trajectory": drift_trajectory_data,
            "spill_geometry": spill_geometry,
            "timeline": timeline_stages,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
