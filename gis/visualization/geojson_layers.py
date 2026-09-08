"""GeoJSON layer generation with map styling and metadata for the frontend."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Union

from gis.geometry.geojson import to_geojson
from gis.geometry.models import BoundingBox, LineString, MultiPolygon, OilSpillGeometry, Polygon
from gis.measurements.models import SpillMeasurement, measure_oil_spill
from gis.visualization.styling import (
    BOUNDING_BOX_STYLE,
    DRIFT_TRAJECTORY_STYLE,
    VESSEL_TRACK_STYLE,
    LayerStyle,
    get_style_for_confidence,
)


def create_spill_layer(
    spill: OilSpillGeometry,
    measurement: Optional[SpillMeasurement] = None,
    style: Optional[LayerStyle] = None,
) -> Dict[str, Any]:
    """Create a styled GeoJSON Feature for an oil spill detection."""
    if measurement is None:
        measurement = measure_oil_spill(spill)

    if style is None:
        style = get_style_for_confidence(spill.confidence)

    style_props = style.to_properties_dict()

    props: Dict[str, Any] = {
        "layer_type": "oil_spill",
        "spill_id": spill.spill_id,
        "detection_timestamp": spill.detection_timestamp.isoformat(),
        "source_sensor": spill.source_sensor,
        "confidence": round(spill.confidence, 4),
        "area_sq_m": round(measurement.area_sq_m, 2),
        "area_sq_km": round(measurement.area_sq_km, 4),
        "perimeter_m": round(measurement.perimeter_m, 2),
        "perimeter_km": round(measurement.perimeter_km, 4),
        "compactness": round(measurement.compactness, 4),
        "centroid": {
            "longitude": round(measurement.centroid.x, 6),
            "latitude": round(measurement.centroid.y, 6),
        },
        **style_props,
        **spill.properties,
    }

    # Generate descriptive tooltip / popup text
    props["popup_html"] = (
        f"<b>Oil Spill:</b> {spill.spill_id}<br/>"
        f"<b>Sensor:</b> {spill.source_sensor}<br/>"
        f"<b>Detected:</b> {spill.detection_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}<br/>"
        f"<b>Confidence:</b> {spill.confidence * 100:.1f}%<br/>"
        f"<b>Area:</b> {measurement.area_sq_km:.3f} km²<br/>"
        f"<b>Perimeter:</b> {measurement.perimeter_km:.3f} km"
    )

    return {
        "type": "Feature",
        "id": spill.spill_id,
        "geometry": to_geojson(spill.geometry),
        "properties": props,
    }


def create_vessel_track_layer(
    trajectory: LineString,
    vessel_info: Optional[Dict[str, Any]] = None,
    style: Optional[LayerStyle] = None,
) -> Dict[str, Any]:
    """Create a styled GeoJSON Feature for a candidate vessel AIS trajectory."""
    if style is None:
        style = VESSEL_TRACK_STYLE

    info = vessel_info.copy() if vessel_info else {}
    mmsi = info.get("mmsi", "Unknown")
    vessel_name = info.get("vessel_name", "Unknown Vessel")
    score = info.get("attribution_score", None)

    style_props = style.to_properties_dict()
    props: Dict[str, Any] = {
        "layer_type": "vessel_track",
        "mmsi": mmsi,
        "vessel_name": vessel_name,
        **style_props,
        **info,
    }

    popup_parts = [
        f"<b>Vessel:</b> {vessel_name} (MMSI: {mmsi})",
    ]
    if score is not None:
        popup_parts.append(f"<b>Attribution Score:</b> {score:.3f}")
    if "speed_knots" in info:
        popup_parts.append(f"<b>Speed:</b> {info['speed_knots']} kts")

    props["popup_html"] = "<br/>".join(popup_parts)

    return {
        "type": "Feature",
        "id": f"vessel_{mmsi}",
        "geometry": to_geojson(trajectory),
        "properties": props,
    }


def create_drift_cone_layer(
    drift_geometry: Union[Polygon, MultiPolygon],
    simulation_info: Optional[Dict[str, Any]] = None,
    style: Optional[LayerStyle] = None,
) -> Dict[str, Any]:
    """Create a styled GeoJSON Feature for a hindcast or forecast drift dispersion zone."""
    if style is None:
        style = DRIFT_TRAJECTORY_STYLE

    info = simulation_info.copy() if simulation_info else {}
    run_id = info.get("run_id", "drift_simulation")

    style_props = style.to_properties_dict()
    props: Dict[str, Any] = {
        "layer_type": "drift_dispersion",
        "run_id": run_id,
        **style_props,
        **info,
    }

    props["popup_html"] = (
        f"<b>Drift Model:</b> {info.get('model_name', 'Lagrangian')}<br/>"
        f"<b>Mode:</b> {info.get('simulation_mode', 'Hindcast')}<br/>"
        f"<b>Duration:</b> {info.get('hours', 'N/A')} hours"
    )

    return {
        "type": "Feature",
        "id": f"drift_{run_id}",
        "geometry": to_geojson(drift_geometry),
        "properties": props,
    }


def create_bbox_layer(
    bbox: BoundingBox,
    label: str = "Bounding Envelope",
    style: Optional[LayerStyle] = None,
) -> Dict[str, Any]:
    """Create a styled GeoJSON Feature representing a bounding box envelope."""
    if style is None:
        style = BOUNDING_BOX_STYLE

    poly_geom = Polygon(
        exterior=[
            (bbox.min_x, bbox.min_y),
            (bbox.max_x, bbox.min_y),
            (bbox.max_x, bbox.max_y),
            (bbox.min_x, bbox.max_y),
            (bbox.min_x, bbox.min_y),
        ]
    )

    style_props = style.to_properties_dict()
    props: Dict[str, Any] = {
        "layer_type": "bounding_box",
        "label": label,
        "bbox": bbox.to_tuple(),
        **style_props,
        "popup_html": f"<b>{label}</b><br/>Bounds: {bbox.to_tuple()}",
    }

    return {
        "type": "Feature",
        "geometry": to_geojson(poly_geom),
        "properties": props,
    }


def combine_feature_collection(
    features: Sequence[Dict[str, Any]],
    crs: str = "EPSG:4326",
) -> Dict[str, Any]:
    """Combine multiple GeoJSON features into a single FeatureCollection."""
    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": crs},
        },
        "features": list(features),
    }
