"""Unit tests for GIS visualization module."""

import math
from datetime import datetime, timezone
import pytest

from gis.geometry import BoundingBox, LineString, OilSpillGeometry, Point, Polygon
from gis.measurements import measure_oil_spill
from gis.visualization import (
    BOUNDING_BOX_STYLE,
    DRIFT_TRAJECTORY_STYLE,
    PROBABLE_ORIGIN_STYLE,
    SPILL_STYLE_HIGH_CONFIDENCE,
    SPILL_STYLE_LOW_CONFIDENCE,
    SPILL_STYLE_MEDIUM_CONFIDENCE,
    VESSEL_TRACK_STYLE,
    LayerStyle,
    combine_feature_collection,
    create_bbox_layer,
    create_drift_cone_layer,
    create_spill_layer,
    create_vessel_track_layer,
    get_feature_bounds,
    get_layer_bounds,
    get_style_for_confidence,
    to_map_view_config,
)


@pytest.fixture
def sample_spill() -> OilSpillGeometry:
    poly = Polygon(
        exterior=[
            (10.0, 50.0),
            (10.1, 50.0),
            (10.1, 50.1),
            (10.0, 50.1),
            (10.0, 50.0),
        ]
    )
    return OilSpillGeometry(
        spill_id="SPILL-2026-001",
        geometry=poly,
        detection_timestamp=datetime(2026, 9, 8, 8, 30, 0, tzinfo=timezone.utc),
        source_sensor="Sentinel-1 SAR",
        confidence=0.92,
        properties={"slick_type": "crude", "estimated_thickness_um": 50},
    )


class TestLayerStyle:
    """Tests for LayerStyle model and presets."""

    def test_default_style_properties(self) -> None:
        style = LayerStyle()
        props = style.to_properties_dict()
        assert props["stroke"] is True
        assert props["color"] == "#ff0000"
        assert props["weight"] == 2
        assert props["fill"] is True
        assert props["fillColor"] == "#ff0000"
        assert "dashArray" not in props

    def test_custom_dash_array(self) -> None:
        style = LayerStyle(stroke_dash_array="5, 5")
        props = style.to_properties_dict()
        assert props["dashArray"] == "5, 5"

    def test_get_style_for_confidence(self) -> None:
        assert get_style_for_confidence(0.95) == SPILL_STYLE_HIGH_CONFIDENCE
        assert get_style_for_confidence(0.70) == SPILL_STYLE_MEDIUM_CONFIDENCE
        assert get_style_for_confidence(0.30) == SPILL_STYLE_LOW_CONFIDENCE


class TestGeoJSONLayers:
    """Tests for styled GeoJSON layer generation."""

    def test_create_spill_layer_auto_measurement(self, sample_spill: OilSpillGeometry) -> None:
        layer = create_spill_layer(sample_spill)

        assert layer["type"] == "Feature"
        assert layer["id"] == "SPILL-2026-001"
        assert layer["geometry"]["type"] == "Polygon"

        props = layer["properties"]
        assert props["layer_type"] == "oil_spill"
        assert props["spill_id"] == "SPILL-2026-001"
        assert props["confidence"] == 0.92
        assert props["area_sq_m"] > 0
        assert props["area_sq_km"] > 0
        assert props["perimeter_km"] > 0
        assert props["compactness"] > 0
        assert "longitude" in props["centroid"]
        assert "latitude" in props["centroid"]
        assert "popup_html" in props
        assert "Sentinel-1 SAR" in props["popup_html"]
        assert props["slick_type"] == "crude"

        # Check applied style (high confidence)
        assert props["color"] == SPILL_STYLE_HIGH_CONFIDENCE.stroke_color

    def test_create_spill_layer_custom_style(self, sample_spill: OilSpillGeometry) -> None:
        custom_style = LayerStyle(stroke_color="#00ff00", fill_color="#00ff00")
        layer = create_spill_layer(sample_spill, style=custom_style)

        assert layer["properties"]["color"] == "#00ff00"
        assert layer["properties"]["fillColor"] == "#00ff00"

    def test_create_vessel_track_layer(self) -> None:
        ls = LineString(coordinates=[(10.0, 50.0), (10.2, 50.2), (10.4, 50.3)])
        vessel_info = {
            "mmsi": "123456789",
            "vessel_name": "SEA GLORY",
            "attribution_score": 0.875,
            "speed_knots": 14.2,
        }

        layer = create_vessel_track_layer(ls, vessel_info=vessel_info)

        assert layer["type"] == "Feature"
        assert layer["id"] == "vessel_123456789"
        assert layer["geometry"]["type"] == "LineString"

        props = layer["properties"]
        assert props["layer_type"] == "vessel_track"
        assert props["vessel_name"] == "SEA GLORY"
        assert props["attribution_score"] == 0.875
        assert "SEA GLORY" in props["popup_html"]
        assert "0.875" in props["popup_html"]

    def test_create_drift_cone_layer(self) -> None:
        poly = Polygon(
            exterior=[
                (9.9, 49.9),
                (10.3, 49.9),
                (10.3, 50.3),
                (9.9, 50.3),
                (9.9, 49.9),
            ]
        )
        sim_info = {
            "run_id": "SIM-2026-HINDCAST-01",
            "model_name": "OpenDrift / Lagrangian",
            "simulation_mode": "Hindcast",
            "hours": 12,
        }

        layer = create_drift_cone_layer(poly, simulation_info=sim_info)

        assert layer["type"] == "Feature"
        assert layer["id"] == "drift_SIM-2026-HINDCAST-01"
        assert layer["geometry"]["type"] == "Polygon"

        props = layer["properties"]
        assert props["layer_type"] == "drift_dispersion"
        assert props["run_id"] == "SIM-2026-HINDCAST-01"
        assert "OpenDrift" in props["popup_html"]

    def test_create_bbox_layer(self) -> None:
        bbox = BoundingBox(min_x=10.0, min_y=50.0, max_x=10.5, max_y=50.5)
        layer = create_bbox_layer(bbox, label="Target AOI")

        assert layer["type"] == "Feature"
        assert layer["geometry"]["type"] == "Polygon"
        assert layer["properties"]["layer_type"] == "bounding_box"
        assert layer["properties"]["label"] == "Target AOI"


class TestExportAndViewport:
    """Tests for FeatureCollection bundling and map view configuration."""

    def test_combine_feature_collection(self, sample_spill: OilSpillGeometry) -> None:
        spill_layer = create_spill_layer(sample_spill)
        bbox_layer = create_bbox_layer(sample_spill.bounds)

        fc = combine_feature_collection([spill_layer, bbox_layer])

        assert fc["type"] == "FeatureCollection"
        assert len(fc["features"]) == 2
        assert fc["crs"]["properties"]["name"] == "EPSG:4326"

    def test_get_layer_bounds_and_view_config(self, sample_spill: OilSpillGeometry) -> None:
        spill_layer = create_spill_layer(sample_spill)
        fc = combine_feature_collection([spill_layer])

        bounds = get_layer_bounds(fc)
        assert bounds is not None
        assert math.isclose(bounds.min_x, 10.0, abs_tol=1e-5)
        assert math.isclose(bounds.max_x, 10.1, abs_tol=1e-5)
        assert math.isclose(bounds.min_y, 50.0, abs_tol=1e-5)
        assert math.isclose(bounds.max_y, 50.1, abs_tol=1e-5)

        map_config = to_map_view_config(fc, default_zoom=12)
        assert map_config["zoom"] == 12
        assert len(map_config["center"]) == 2
        assert math.isclose(map_config["center"][0], 50.05, abs_tol=1e-3)  # Latitude
        assert math.isclose(map_config["center"][1], 10.05, abs_tol=1e-3)  # Longitude
        assert map_config["bounds"] is not None

    def test_empty_feature_collection_viewport(self) -> None:
        fc = combine_feature_collection([])
        bounds = get_layer_bounds(fc)
        assert bounds is None

        map_config = to_map_view_config(fc)
        assert map_config["center"] == [0.0, 0.0]
        assert map_config["zoom"] == 2
        assert map_config["bounds"] is None
