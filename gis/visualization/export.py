"""Map export helpers and viewport calculations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from gis.geometry.models import BoundingBox


def get_feature_bounds(feature: Dict[str, Any]) -> Optional[BoundingBox]:
    """Calculate the bounding box envelope of a GeoJSON Feature."""
    geom = feature.get("geometry")
    if not geom:
        return None

    coords = geom.get("coordinates")
    if not coords:
        return None

    all_points: List[Tuple[float, float]] = []

    def _extract_points(c: Any) -> None:
        if isinstance(c, (list, tuple)) and len(c) >= 2 and isinstance(c[0], (int, float)):
            all_points.append((float(c[0]), float(c[1])))
        elif isinstance(c, (list, tuple)):
            for item in c:
                _extract_points(item)

    _extract_points(coords)
    if not all_points:
        return None

    min_x = min(p[0] for p in all_points)
    max_x = max(p[0] for p in all_points)
    min_y = min(p[1] for p in all_points)
    max_y = max(p[1] for p in all_points)

    return BoundingBox(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)


def get_layer_bounds(feature_collection: Dict[str, Any]) -> Optional[BoundingBox]:
    """Calculate the overall bounding envelope for a FeatureCollection."""
    features = feature_collection.get("features", [])
    if not features:
        return None

    bboxes = [get_feature_bounds(f) for f in features]
    valid_bboxes = [b for b in bboxes if b is not None]

    if not valid_bboxes:
        return None

    min_x = min(b.min_x for b in valid_bboxes)
    max_x = max(b.max_x for b in valid_bboxes)
    min_y = min(b.min_y for b in valid_bboxes)
    max_y = max(b.max_y for b in valid_bboxes)

    return BoundingBox(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)


def to_map_view_config(
    feature_collection: Dict[str, Any],
    default_zoom: int = 10,
) -> Dict[str, Any]:
    """Generate map view center, zoom, and bounds configuration for frontend rendering."""
    bounds = get_layer_bounds(feature_collection)
    if bounds is None:
        return {
            "center": [0.0, 0.0],
            "zoom": 2,
            "bounds": None,
        }

    center_lon, center_lat = bounds.center
    return {
        "center": [center_lat, center_lon],
        "zoom": default_zoom,
        "bounds": [
            [bounds.min_y, bounds.min_x],  # [south, west]
            [bounds.max_y, bounds.max_x],  # [north, east]
        ],
    }
