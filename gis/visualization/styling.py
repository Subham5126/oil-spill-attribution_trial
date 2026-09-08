"""Styling representations and standard presets for GIS map layers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class LayerStyle:
    """Styling properties for vector GeoJSON layers."""

    stroke_color: str = "#ff0000"
    stroke_width: int = 2
    stroke_opacity: float = 1.0
    stroke_dash_array: Optional[str] = None
    fill_color: str = "#ff0000"
    fill_opacity: float = 0.4
    interactive: bool = True

    def to_properties_dict(self) -> Dict[str, Any]:
        """Convert style into standard Leaflet/Mapbox vector feature properties."""
        props: Dict[str, Any] = {
            "stroke": True,
            "color": self.stroke_color,
            "weight": self.stroke_width,
            "opacity": self.stroke_opacity,
            "fill": self.fill_opacity > 0,
            "fillColor": self.fill_color,
            "fillOpacity": self.fill_opacity,
        }
        if self.stroke_dash_array is not None:
            props["dashArray"] = self.stroke_dash_array
        return props


# Standard Visualization Presets
SPILL_STYLE_HIGH_CONFIDENCE = LayerStyle(
    stroke_color="#d90429",
    stroke_width=2,
    stroke_opacity=1.0,
    fill_color="#ef233c",
    fill_opacity=0.6,
)

SPILL_STYLE_MEDIUM_CONFIDENCE = LayerStyle(
    stroke_color="#f77f00",
    stroke_width=2,
    stroke_opacity=1.0,
    fill_color="#fcbf49",
    fill_opacity=0.5,
)

SPILL_STYLE_LOW_CONFIDENCE = LayerStyle(
    stroke_color="#6c757d",
    stroke_width=1,
    stroke_opacity=0.8,
    fill_color="#adb5bd",
    fill_opacity=0.3,
)

VESSEL_TRACK_STYLE = LayerStyle(
    stroke_color="#0077b6",
    stroke_width=3,
    stroke_opacity=0.9,
    fill_color="#0077b6",
    fill_opacity=0.0,
)

DRIFT_TRAJECTORY_STYLE = LayerStyle(
    stroke_color="#7209b7",
    stroke_width=2,
    stroke_opacity=0.8,
    stroke_dash_array="5, 5",
    fill_color="#b5179e",
    fill_opacity=0.2,
)

PROBABLE_ORIGIN_STYLE = LayerStyle(
    stroke_color="#9b5de5",
    stroke_width=2,
    stroke_opacity=1.0,
    fill_color="#f15bb5",
    fill_opacity=0.4,
)

BOUNDING_BOX_STYLE = LayerStyle(
    stroke_color="#2b2d42",
    stroke_width=1,
    stroke_opacity=0.7,
    stroke_dash_array="4, 4",
    fill_color="#8d99ae",
    fill_opacity=0.1,
)


def get_style_for_confidence(confidence: float) -> LayerStyle:
    """Select the appropriate spill polygon style based on confidence score (0.0 to 1.0)."""
    if confidence >= 0.8:
        return SPILL_STYLE_HIGH_CONFIDENCE
    elif confidence >= 0.5:
        return SPILL_STYLE_MEDIUM_CONFIDENCE
    return SPILL_STYLE_LOW_CONFIDENCE
