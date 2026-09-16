import numpy as np
import pytest
from datetime import datetime, timezone

from demo.end_to_end_real_workflow_demo import run_m3_geometry
from gis.geometry.geojson import to_geojson
from gis.geometry.models import Polygon, MultiPolygon, OilSpillGeometry
from gis.measurements.models import measure_oil_spill


def test_m3_geometry_extracts_irregular_slick():
    # Construct a synthetic 100x100 raster with an irregular L-shaped oil spill
    mask = np.zeros((100, 100), dtype=np.uint8)
    # L-shape: vertical bar (20..80, 20..35) and horizontal bar (60..80, 35..75)
    mask[20:80, 20:35] = 1
    mask[60:80, 35:75] = 1

    # Affine transform: pixel (0,0) at (50.0, 20.0), scale 0.001 deg/pixel
    transform = (0.001, 0.0, 50.0, 0.0, -0.001, 25.0)

    slick_geom, measurement, mask_shapes = run_m3_geometry(
        binary_mask=mask,
        transform=transform,
        crs_str="EPSG:4326",
        spill_id="TEST-SPILL-01",
        observation_time=datetime.now(timezone.utc),
        max_prob=0.95,
    )

    # 1. Geometry is not a 5-point rectangle box
    geojson_geom = to_geojson(slick_geom.geometry)
    assert geojson_geom["type"] in ("Polygon", "MultiPolygon")

    if geojson_geom["type"] == "Polygon":
        exterior_coords = geojson_geom["coordinates"][0]
        # An L-shape has at least 6-8 boundary vertices, definitely not a 4-corner box (5 points)
        assert len(exterior_coords) > 5
    else:
        assert len(geojson_geom["coordinates"]) >= 1

    # 2. Measurement bounding box is tight to the spill coordinates, not full raster extent
    # Full raster bounds would be lon: [50.0, 50.1], lat: [24.9, 25.0]
    bbox = measurement.bounding_box
    assert bbox.min_x >= 50.02  # starts around pixel 20
    assert bbox.max_x <= 50.08  # ends around pixel 75
    assert bbox.min_y >= 24.919 # bottom around pixel 80 (25.0 - 0.080 = 24.92)
    assert bbox.max_y <= 24.981 # top around pixel 20 (25.0 - 0.020 = 24.98)


def test_multipolygon_support_in_measurement_and_geojson():
    # Two distinct patches
    p1 = Polygon([(54.1, 25.1), (54.2, 25.1), (54.2, 25.2), (54.1, 25.2), (54.1, 25.1)])
    p2 = Polygon([(54.3, 25.3), (54.4, 25.3), (54.4, 25.4), (54.3, 25.4), (54.3, 25.3)])
    mp = MultiPolygon([p1, p2])

    spill = OilSpillGeometry(
        spill_id="MULTI-01",
        geometry=mp,
        detection_timestamp=datetime.now(timezone.utc),
    )
    measurement = measure_oil_spill(spill)

    # MultiPolygon area is sum of both components
    assert measurement.area_sq_km > 0
    # Bounding box spans both patches
    assert measurement.bounding_box.min_x == 54.1
    assert measurement.bounding_box.max_x == 54.4

    # GeoJSON serialization retains MultiPolygon
    gj = to_geojson(spill.geometry)
    assert gj["type"] == "MultiPolygon"
    assert len(gj["coordinates"]) == 2


def test_pipeline_service_synthesize_does_not_fake_rectangles():
    from backend.services.pipeline_service import PipelineService

    result_payload = {
        "gis_measurement": {
            "centroid": {"latitude": 25.5, "longitude": 54.5},
            "bounding_box": {"min_lon": 53.0, "min_lat": 24.0, "max_lon": 56.0, "max_lat": 27.0},
            "scene_bounding_box": {"min_lon": 53.0, "min_lat": 24.0, "max_lon": 56.0, "max_lat": 27.0},
        }
    }

    layers = PipelineService._synthesize_geojson_layers(result_payload, "INV-TEST")
    features = layers["features"]

    # Spill feature must NOT be a Polygon rectangle
    spill_feat = next(f for f in features if f["properties"]["layer_type"] == "oil_spill")
    assert spill_feat["geometry"]["type"] == "Point"  # honest centroid fallback, not fake rectangle!
    assert spill_feat["geometry"]["coordinates"] == [54.5, 25.5]

    # Scene footprint feature is separate
    scene_feat = next(f for f in features if f["properties"]["layer_type"] == "scene_footprint")
    assert scene_feat["geometry"]["type"] == "Polygon"
