"""Unit tests for the GIS Geometry module.

Tests primitives, topological validation, GeoJSON conversion,
and domain-specific oil spill geometry models.
"""

from datetime import datetime, timezone
import pytest

from gis.geometry import (
    BoundingBox,
    Coordinate,
    EmptyGeometryError,
    GeometryError,
    InvalidCoordinateError,
    InvalidGeometryError,
    LineString,
    LinearRing,
    MultiPolygon,
    OilSpillGeometry,
    Point,
    Polygon,
    SelfIntersectionError,
    from_geojson,
    from_shapely,
    signed_ring_area,
    to_geojson,
    to_shapely,
    validate_coordinate_values,
)


class TestCoordinatesAndBounds:
    def test_coordinate_valid(self):
        coord = Coordinate(12.5, 45.2, 0.0)
        assert coord.x == 12.5
        assert coord.y == 45.2
        assert coord.z == 0.0
        assert coord.lon == 12.5
        assert coord.lat == 45.2
        assert coord.to_tuple() == (12.5, 45.2, 0.0)

    def test_coordinate_wgs84_bounds(self):
        # Valid edge coordinates
        validate_coordinate_values(-180.0, -90.0)
        validate_coordinate_values(180.0, 90.0)

        # Out of bounds longitude
        with pytest.raises(InvalidCoordinateError, match="Longitude"):
            validate_coordinate_values(180.1, 0.0)

        with pytest.raises(InvalidCoordinateError, match="Longitude"):
            validate_coordinate_values(-180.5, 0.0)

        # Out of bounds latitude
        with pytest.raises(InvalidCoordinateError, match="Latitude"):
            validate_coordinate_values(0.0, 90.1)

        with pytest.raises(InvalidCoordinateError, match="Latitude"):
            validate_coordinate_values(0.0, -91.0)

    def test_coordinate_non_finite(self):
        with pytest.raises(InvalidCoordinateError):
            validate_coordinate_values(float("nan"), 0.0)

        with pytest.raises(InvalidCoordinateError):
            validate_coordinate_values(0.0, float("inf"))

    def test_bounding_box_properties(self):
        bbox = BoundingBox(10.0, 20.0, 30.0, 50.0)
        assert bbox.width == 20.0
        assert bbox.height == 30.0
        assert bbox.center == (20.0, 35.0)
        assert bbox.to_tuple() == (10.0, 20.0, 30.0, 50.0)

    def test_bounding_box_invalid(self):
        with pytest.raises(InvalidGeometryError):
            BoundingBox(30.0, 20.0, 10.0, 50.0)  # min_x > max_x

        with pytest.raises(InvalidGeometryError):
            BoundingBox(10.0, 60.0, 30.0, 50.0)  # min_y > max_y


class TestPoint:
    def test_point_creation(self):
        pt1 = Point(10.5, 20.5)
        assert pt1.x == 10.5
        assert pt1.y == 20.5
        assert pt1.lon == 10.5
        assert pt1.lat == 20.5
        assert pt1.bounds == BoundingBox(10.5, 20.5, 10.5, 20.5)

        pt2 = Point([10.5, 20.5])
        assert pt1 == pt2

    def test_point_invalid(self):
        with pytest.raises(InvalidCoordinateError):
            Point(200.0, 0.0)


class TestLineString:
    def test_line_string_valid(self):
        coords = [(0.0, 0.0), (1.0, 2.0), (3.0, 4.0)]
        line = LineString(coords)
        assert len(line) == 3
        assert line.bounds == BoundingBox(0.0, 0.0, 3.0, 4.0)
        assert line.to_tuples() == [(0.0, 0.0), (1.0, 2.0), (3.0, 4.0)]

    def test_line_string_insufficient_points(self):
        with pytest.raises(InvalidGeometryError, match="at least 2 coordinate points"):
            LineString([(1.0, 2.0)])

    def test_line_string_empty(self):
        with pytest.raises(EmptyGeometryError):
            LineString([])


class TestLinearRing:
    def test_linear_ring_valid(self):
        # Counter-clockwise square
        coords = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)]
        ring = LinearRing(coords)
        assert len(ring) == 5
        assert ring.is_ccw is True
        assert ring.signed_area > 0

    def test_linear_ring_unclosed(self):
        coords = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
        with pytest.raises(InvalidGeometryError, match="must be closed"):
            LinearRing(coords)

    def test_linear_ring_too_few_points(self):
        coords = [(0.0, 0.0), (1.0, 1.0), (0.0, 0.0)]
        with pytest.raises(InvalidGeometryError, match="at least 4 coordinate positions"):
            LinearRing(coords)

    def test_linear_ring_collinear(self):
        coords = [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0), (0.0, 0.0)]
        with pytest.raises(InvalidGeometryError, match="zero area"):
            LinearRing(coords)

    def test_linear_ring_self_intersection(self):
        # Bowtie / figure-8 polygon
        coords = [(0.0, 0.0), (2.0, 2.0), (2.0, 0.0), (0.0, 2.0), (0.0, 0.0)]
        with pytest.raises(SelfIntersectionError, match="self-intersects"):
            LinearRing(coords)


class TestPolygon:
    def test_polygon_simple(self):
        ext = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0), (0.0, 0.0)]
        poly = Polygon(ext)
        assert len(poly.exterior) == 5
        assert len(poly.interiors) == 0
        assert poly.bounds == BoundingBox(0.0, 0.0, 4.0, 4.0)

    def test_polygon_with_hole(self):
        ext = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0), (0.0, 0.0)]
        hole = [(1.0, 1.0), (1.0, 2.0), (2.0, 2.0), (2.0, 1.0), (1.0, 1.0)]
        poly = Polygon(exterior=ext, interiors=[hole])
        assert len(poly.interiors) == 1

    def test_polygon_hole_outside_exterior(self):
        ext = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)]
        hole_outside = [(5.0, 5.0), (5.0, 6.0), (6.0, 6.0), (6.0, 5.0), (5.0, 5.0)]
        with pytest.raises(InvalidGeometryError, match="outside the exterior boundary"):
            Polygon(exterior=ext, interiors=[hole_outside])


class TestMultiPolygon:
    def test_multipolygon_valid(self):
        poly1 = Polygon([(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)])
        poly2 = Polygon([(10.0, 10.0), (12.0, 10.0), (12.0, 12.0), (10.0, 12.0), (10.0, 10.0)])
        mp = MultiPolygon([poly1, poly2])
        assert len(mp) == 2
        assert mp.bounds == BoundingBox(0.0, 0.0, 12.0, 12.0)

    def test_multipolygon_empty(self):
        with pytest.raises(EmptyGeometryError):
            MultiPolygon([])


class TestOilSpillGeometry:
    def test_oil_spill_geometry_valid(self):
        poly = Polygon([(55.0, 25.0), (55.5, 25.0), (55.5, 25.5), (55.0, 25.5), (55.0, 25.0)])
        dt = datetime(2026, 9, 7, 10, 0, 0, tzinfo=timezone.utc)
        spill = OilSpillGeometry(
            spill_id="SPILL-2026-001",
            geometry=poly,
            detection_timestamp=dt,
            source_sensor="Sentinel-1 SAR",
            confidence=0.92,
            properties={"slick_type": "crude", "estimated_volume_m3": 120.0},
        )
        assert spill.spill_id == "SPILL-2026-001"
        assert spill.confidence == 0.92
        assert spill.source_sensor == "Sentinel-1 SAR"
        assert spill.bounds == BoundingBox(55.0, 25.0, 55.5, 25.5)

        feat = spill.to_feature_dict()
        assert feat["type"] == "Feature"
        assert feat["id"] == "SPILL-2026-001"
        assert feat["properties"]["confidence"] == 0.92
        assert feat["properties"]["slick_type"] == "crude"

    def test_oil_spill_naive_timestamp(self):
        poly = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)])
        naive_dt = datetime(2026, 9, 7, 10, 0, 0)  # No timezone
        with pytest.raises(ValueError, match="timezone-aware"):
            OilSpillGeometry("SPILL-1", poly, naive_dt)

    def test_oil_spill_invalid_confidence(self):
        poly = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)])
        dt = datetime(2026, 9, 7, 10, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="Confidence"):
            OilSpillGeometry("SPILL-1", poly, dt, confidence=1.5)


class TestGeoJSON:
    def test_point_round_trip(self):
        pt = Point(12.34, 56.78)
        geo = to_geojson(pt)
        assert geo == {"type": "Point", "coordinates": [12.34, 56.78]}

        parsed = from_geojson(geo)
        assert isinstance(parsed, Point)
        assert parsed == pt

    def test_linestring_round_trip(self):
        line = LineString([(0.0, 0.0), (1.0, 1.0), (2.0, 3.0)])
        geo = to_geojson(line)
        assert geo["type"] == "LineString"

        parsed = from_geojson(geo)
        assert isinstance(parsed, LineString)
        assert parsed == line

    def test_polygon_round_trip(self):
        poly = Polygon([(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)])
        geo = to_geojson(poly)
        assert geo["type"] == "Polygon"

        parsed = from_geojson(geo)
        assert isinstance(parsed, Polygon)
        assert parsed == poly

    def test_multipolygon_round_trip(self):
        poly1 = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)])
        poly2 = Polygon([(3.0, 3.0), (4.0, 3.0), (4.0, 4.0), (3.0, 4.0), (3.0, 3.0)])
        mp = MultiPolygon([poly1, poly2])
        geo = to_geojson(mp)
        assert geo["type"] == "MultiPolygon"

        parsed = from_geojson(geo)
        assert isinstance(parsed, MultiPolygon)
        assert parsed == mp

    def test_oil_spill_feature_round_trip(self):
        poly = Polygon([(10.0, 20.0), (12.0, 20.0), (12.0, 22.0), (10.0, 22.0), (10.0, 20.0)])
        dt = datetime(2026, 9, 7, 12, 30, 0, tzinfo=timezone.utc)
        spill = OilSpillGeometry(
            spill_id="TEST-SPILL-99",
            geometry=poly,
            detection_timestamp=dt,
            source_sensor="Sentinel-1",
            confidence=0.88,
        )
        geo = to_geojson(spill)
        assert geo["type"] == "Feature"

        parsed = from_geojson(geo)
        assert isinstance(parsed, OilSpillGeometry)
        assert parsed.spill_id == "TEST-SPILL-99"
        assert parsed.confidence == 0.88
        assert parsed.detection_timestamp == dt

    def test_malformed_geojson(self):
        with pytest.raises(InvalidGeometryError):
            from_geojson({"type": "UnknownType", "coordinates": []})

        with pytest.raises(InvalidGeometryError):
            from_geojson("not a dict")  # type: ignore


class TestShapelyInterop:
    def test_shapely_handling(self):
        poly = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)])
        try:
            import shapely  # noqa: F401
            shp = to_shapely(poly)
            assert shp.geom_type == "Polygon"
            back = from_shapely(shp)
            assert isinstance(back, Polygon)
            assert back == poly
        except ImportError:
            # If shapely is not installed, must raise informative ImportError
            with pytest.raises(ImportError, match="Shapely is not installed"):
                to_shapely(poly)
