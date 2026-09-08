"""Unit and integration tests for the GIS Measurement module.

Tests geodetic distance, perimeter, spherical polygon area, centroid,
shape characteristics, and comprehensive oil spill measurements.
"""

import math
from datetime import datetime, timezone
import pytest

from gis.geometry import (
    BoundingBox,
    Coordinate,
    LineString,
    LinearRing,
    MultiPolygon,
    OilSpillGeometry,
    Point,
    Polygon,
)
from gis.measurements import (
    EARTH_RADIUS_METERS,
    CalculationError,
    MeasurementError,
    SpillMeasurement,
    calculate_bounding_dimensions,
    calculate_compactness,
    calculate_linestring_centroid,
    calculate_multipolygon_area,
    calculate_multipolygon_centroid,
    calculate_path_length,
    calculate_perimeter,
    calculate_polygon_area,
    calculate_polygon_centroid,
    calculate_ring_geodesic_area,
    calculate_ring_perimeter,
    calculate_spill_area,
    calculate_spill_centroid,
    haversine_distance,
    measure_oil_spill,
)


class TestDistanceAndPerimeter:
    def test_haversine_identical_points(self):
        pt1 = Coordinate(55.0, 25.0)
        pt2 = Coordinate(55.0, 25.0)
        assert haversine_distance(pt1, pt2) == 0.0

    def test_haversine_equator_one_degree(self):
        # 1 degree of longitude along the equator should equal (2 * pi * R) / 360
        expected = (2.0 * math.pi * EARTH_RADIUS_METERS) / 360.0  # ~111,195 m
        calculated = haversine_distance((0.0, 0.0), (1.0, 0.0))
        assert math.isclose(calculated, expected, rel_tol=1e-4)

    def test_haversine_poles(self):
        # North pole to South pole is pi * R ~ 20,015 km
        expected = math.pi * EARTH_RADIUS_METERS
        calculated = haversine_distance((0.0, 90.0), (0.0, -90.0))
        assert math.isclose(calculated, expected, rel_tol=1e-4)

    def test_calculate_path_length(self):
        line = LineString([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
        dist_m = calculate_path_length(line, in_km=False)
        dist_km = calculate_path_length(line, in_km=True)

        expected_single = (2.0 * math.pi * EARTH_RADIUS_METERS) / 360.0
        assert math.isclose(dist_m, expected_single * 2.0, rel_tol=1e-4)
        assert math.isclose(dist_km, (expected_single * 2.0) / 1000.0, rel_tol=1e-4)

    def test_calculate_ring_perimeter(self):
        # 1 deg square at equator
        coords = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
        ring = LinearRing(coords)
        perim = calculate_ring_perimeter(ring)
        assert perim > 400_000.0  # ~444 km

    def test_calculate_perimeter_polygon_with_holes(self):
        ext = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0), (0.0, 0.0)]
        hole = [(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0), (1.0, 1.0)]
        poly = Polygon(exterior=ext, interiors=[hole])

        ext_only = calculate_perimeter(poly, include_holes=False)
        with_holes = calculate_perimeter(poly, include_holes=True)

        assert with_holes > ext_only
        hole_perim = calculate_ring_perimeter(LinearRing(hole))
        assert math.isclose(with_holes, ext_only + hole_perim, rel_tol=1e-5)

    def test_calculate_perimeter_multipolygon(self):
        p1 = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)])
        p2 = Polygon([(10.0, 10.0), (11.0, 10.0), (11.0, 11.0), (10.0, 11.0), (10.0, 10.0)])
        mp = MultiPolygon([p1, p2])

        total_perim = calculate_perimeter(mp)
        expected = calculate_perimeter(p1) + calculate_perimeter(p2)
        assert math.isclose(total_perim, expected, rel_tol=1e-5)


class TestAreaCalculation:
    def test_equatorial_one_degree_square_area(self):
        # Theoretical spherical area: R^2 * Delta_lambda * sin(Delta_phi)
        delta_lambda = math.radians(1.0)
        delta_phi = math.radians(1.0)
        expected_area = (EARTH_RADIUS_METERS**2) * delta_lambda * math.sin(delta_phi)

        coords = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
        ring = LinearRing(coords)
        calc_area = calculate_ring_geodesic_area(ring)

        assert math.isclose(calc_area, expected_area, rel_tol=1e-4)

    def test_polygon_area_with_hole(self):
        ext = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0), (0.0, 0.0)]
        hole = [(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0), (1.0, 1.0)]
        poly = Polygon(exterior=ext, interiors=[hole])

        net_area = calculate_polygon_area(poly)
        ext_area = calculate_ring_geodesic_area(poly.exterior)
        hole_area = calculate_ring_geodesic_area(LinearRing(hole))

        assert math.isclose(net_area, ext_area - hole_area, rel_tol=1e-5)

    def test_multipolygon_area(self):
        p1 = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)])
        p2 = Polygon([(5.0, 5.0), (6.0, 5.0), (6.0, 6.0), (5.0, 6.0), (5.0, 5.0)])
        mp = MultiPolygon([p1, p2])

        total_area_m2 = calculate_multipolygon_area(mp, in_sq_km=False)
        total_area_km2 = calculate_multipolygon_area(mp, in_sq_km=True)

        assert math.isclose(total_area_km2, total_area_m2 / 1_000_000.0)
        expected = calculate_polygon_area(p1) + calculate_polygon_area(p2)
        assert math.isclose(total_area_m2, expected, rel_tol=1e-5)

    def test_calculate_spill_area(self):
        poly = Polygon([(55.0, 25.0), (55.1, 25.0), (55.1, 25.1), (55.0, 25.1), (55.0, 25.0)])
        spill = OilSpillGeometry(
            spill_id="SP-01",
            geometry=poly,
            detection_timestamp=datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc),
        )

        area_m2 = calculate_spill_area(spill, in_sq_km=False)
        area_km2 = calculate_spill_area(spill, in_sq_km=True)
        assert area_m2 > 0.0
        assert math.isclose(area_km2, area_m2 / 1_000_000.0)


class TestCentroidCalculation:
    def test_symmetric_square_centroid(self):
        # Square centered at (50.0, 20.0)
        coords = [
            (49.0, 19.0),
            (51.0, 19.0),
            (51.0, 21.0),
            (49.0, 21.0),
            (49.0, 19.0),
        ]
        poly = Polygon(coords)
        centroid = calculate_polygon_centroid(poly)

        assert math.isclose(centroid.x, 50.0, abs_tol=1e-7)
        assert math.isclose(centroid.y, 20.0, abs_tol=1e-7)

    def test_polygon_with_hole_centroid(self):
        # Symmetric exterior with hole offset to the right
        ext = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0), (0.0, 0.0)]
        hole_right = [(2.5, 1.5), (3.5, 1.5), (3.5, 2.5), (2.5, 2.5), (2.5, 1.5)]
        poly = Polygon(exterior=ext, interiors=[hole_right])

        centroid = calculate_polygon_centroid(poly)
        # Without hole, centroid is (2.0, 2.0). With hole on the right, centroid shifts left (x < 2.0)
        assert centroid.x < 2.0
        assert math.isclose(centroid.y, 2.0, abs_tol=1e-5)

    def test_multipolygon_weighted_centroid(self):
        # poly1 is 2x2 centered at (1, 1), poly2 is 1x1 centered at (10.5, 10.5)
        poly1 = Polygon([(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)])
        poly2 = Polygon([(10.0, 10.0), (11.0, 10.0), (11.0, 11.0), (10.0, 11.0), (10.0, 10.0)])
        mp = MultiPolygon([poly1, poly2])

        c = calculate_multipolygon_centroid(mp)
        # Area of poly1 is 4, poly2 is 1. Composite x: (1*4 + 10.5*1) / 5 = 14.5 / 5 = 2.9
        assert math.isclose(c.x, 2.9, abs_tol=1e-5)
        assert math.isclose(c.y, 2.9, abs_tol=1e-5)

    def test_linestring_centroid(self):
        line = LineString([(0.0, 0.0), (2.0, 0.0)])
        c = calculate_linestring_centroid(line)
        assert math.isclose(c.x, 1.0, abs_tol=1e-5)
        assert math.isclose(c.y, 0.0, abs_tol=1e-5)


class TestShapeCharacteristicsAndSpillMeasurement:
    def test_compactness_values(self):
        # Square compactness: 4 * pi * s^2 / (4s)^2 = pi / 4 ~ 0.785
        square_area = 100.0
        square_perim = 40.0
        c_square = calculate_compactness(square_area, square_perim)
        assert math.isclose(c_square, math.pi / 4.0, abs_tol=1e-3)

        # Thin elongated strip: area = 10, perim = 202 -> compactness very small
        c_thin = calculate_compactness(10.0, 202.0)
        assert c_thin < 0.01

    def test_bounding_dimensions_and_aspect_ratio(self):
        bbox = BoundingBox(min_x=55.0, min_y=25.0, max_x=55.1, max_y=25.2)
        width_m, height_m, ratio = calculate_bounding_dimensions(bbox)
        assert width_m > 0
        assert height_m > 0
        assert ratio >= 1.0

    def test_measure_oil_spill_complete(self):
        poly = Polygon([(55.0, 25.0), (55.2, 25.0), (55.2, 25.1), (55.0, 25.1), (55.0, 25.0)])
        spill = OilSpillGeometry(
            spill_id="SPILL-PERSIAN-GULF-01",
            geometry=poly,
            detection_timestamp=datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc),
            confidence=0.96,
        )

        measurement = measure_oil_spill(spill)
        assert isinstance(measurement, SpillMeasurement)
        assert measurement.spill_id == "SPILL-PERSIAN-GULF-01"
        assert measurement.area_sq_km > 0.0
        assert measurement.perimeter_km > 0.0
        assert isinstance(measurement.centroid, Point)
        assert measurement.compactness > 0.0
        assert measurement.aspect_ratio >= 1.0

        # Test dictionary serialization
        d = measurement.to_dict()
        assert d["spill_id"] == "SPILL-PERSIAN-GULF-01"
        assert "area" in d
        assert "sq_kilometers" in d["area"]
        assert "centroid" in d
        assert "shape_characteristics" in d


class TestImportCompatibility:
    def test_both_import_styles_work(self):
        import gis.measurements as m_plural
        import gis.measurement as m_singular

        assert m_plural.haversine_distance is m_singular.haversine_distance
        assert m_plural.measure_oil_spill is m_singular.measure_oil_spill
        assert m_plural.SpillMeasurement is m_singular.SpillMeasurement


class TestErrorHandling:
    def test_invalid_object_perimeter(self):
        with pytest.raises(CalculationError):
            calculate_perimeter("not a geometry")  # type: ignore

    def test_invalid_object_area(self):
        with pytest.raises(CalculationError):
            calculate_spill_area(12345)  # type: ignore

    def test_invalid_object_centroid(self):
        with pytest.raises(CalculationError):
            calculate_spill_centroid(None)  # type: ignore
