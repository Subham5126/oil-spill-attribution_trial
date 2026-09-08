"""GIS Visualization module for styled GeoJSON layers and map configuration."""

from gis.visualization.export import (
    get_feature_bounds,
    get_layer_bounds,
    to_map_view_config,
)
from gis.visualization.geojson_layers import (
    combine_feature_collection,
    create_bbox_layer,
    create_drift_cone_layer,
    create_spill_layer,
    create_vessel_track_layer,
)
from gis.visualization.styling import (
    BOUNDING_BOX_STYLE,
    DRIFT_TRAJECTORY_STYLE,
    PROBABLE_ORIGIN_STYLE,
    SPILL_STYLE_HIGH_CONFIDENCE,
    SPILL_STYLE_LOW_CONFIDENCE,
    SPILL_STYLE_MEDIUM_CONFIDENCE,
    VESSEL_TRACK_STYLE,
    LayerStyle,
    get_style_for_confidence,
)

__all__ = [
    # Styling models & presets
    "LayerStyle",
    "SPILL_STYLE_HIGH_CONFIDENCE",
    "SPILL_STYLE_MEDIUM_CONFIDENCE",
    "SPILL_STYLE_LOW_CONFIDENCE",
    "VESSEL_TRACK_STYLE",
    "DRIFT_TRAJECTORY_STYLE",
    "PROBABLE_ORIGIN_STYLE",
    "BOUNDING_BOX_STYLE",
    "get_style_for_confidence",
    # Layer generators
    "create_spill_layer",
    "create_vessel_track_layer",
    "create_drift_cone_layer",
    "create_bbox_layer",
    "combine_feature_collection",
    # Export & viewport helpers
    "get_feature_bounds",
    "get_layer_bounds",
    "to_map_view_config",
]
