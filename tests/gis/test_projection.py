"""Unit tests for GIS projection module."""

import math
import pytest

from gis.geometry import BoundingBox, LineString, MultiPolygon, Point, Polygon
from gis.projection import (
    CRS,
    CRSError,
    OutOfRangeError,
    ProjectionError,
    get_utm_crs_for_geometry,
    get_utm_epsg,
    get_utm_zone,
    reproject_geometry,
    transform_point,
    utm_to_wgs84,
    web_mercator_to_wgs84,
    wgs84_to_utm,
    wgs84_to_web_mercator,
)


class TestCRS:
    """Tests for Coordinate Reference System model and factories."""

    def test_wgs84_factory(self) -> None:
        crs = CRS.wgs84()
        assert crs.epsg == 4326
        assert crs.is_geographic is True
        assert crs.is_projected is False
        assert crs.is_utm is False
        assert crs.unit == "degree"

    def test_web_mercator_factory(self) -> None:
        crs = CRS.web_mercator()
        assert crs.epsg == 3857
        assert crs.is_geographic is False
        assert crs.is_projected is True
        assert crs.is_utm is False
        assert crs.unit == "metre"

    def test_utm_factory(self) -> None:
        crs_north = CRS.utm(zone=30, hemisphere="N")
        assert crs_north.epsg == 32630
        assert crs_north.is_utm is True
        assert crs_north.is_projected is True
        assert crs_north.zone == 30
        assert crs_north.hemisphere == "N"

        crs_south = CRS.utm(zone=30, hemisphere="S")
        assert crs_south.epsg == 32730
        assert crs_south.is_utm is True
        assert crs_south.hemisphere == "S"

    def test_utm_factory_invalid(self) -> None:
        with pytest.raises(CRSError):
            CRS.utm(zone=0, hemisphere="N")
        with pytest.raises(CRSError):
            CRS.utm(zone=61, hemisphere="N")
        with pytest.raises(CRSError):
            CRS.utm(zone=30, hemisphere="E")

    def test_from_epsg(self) -> None:
        assert CRS.from_epsg(4326) == CRS.wgs84()
        assert CRS.from_epsg(3857) == CRS.web_mercator()
        assert CRS.from_epsg(32633) == CRS.utm(33, "N")
        assert CRS.from_epsg(32719) == CRS.utm(19, "S")

        with pytest.raises(CRSError):
            CRS.from_epsg(99999)


class TestUTMDetection:
    """Tests for automatic UTM zone and EPSG detection."""

    def test_get_utm_zone(self) -> None:
        # Prime Meridian (Greenwich, London) -> Zone 30/31 boundary
        assert get_utm_zone(0.0, 51.5) == 31
        assert get_utm_zone(-0.1, 51.5) == 30

        # Mumbai, India (approx 72.8°E) -> Zone 43
        assert get_utm_zone(72.8, 19.0) == 43

        # New York, USA (approx -74.0°W) -> Zone 18
        assert get_utm_zone(-74.0, 40.7) == 18

        # Sydney, Australia (approx 151.2°E) -> Zone 56
        assert get_utm_zone(151.2, -33.8) == 56

        # Dateline edge cases
        assert get_utm_zone(-180.0, 0.0) == 1
        assert get_utm_zone(179.9, 0.0) == 60

    def test_get_utm_epsg(self) -> None:
        # Northern hemisphere
        assert get_utm_epsg(72.8, 19.0) == 32643
        # Southern hemisphere
        assert get_utm_epsg(151.2, -33.8) == 32756

    def test_get_utm_crs_for_geometry(self) -> None:
        pt = Point(72.8, 19.0)
        crs = get_utm_crs_for_geometry(pt)
        assert crs.epsg == 32643

        poly = Polygon(exterior=[
            Point(10.0, 50.0),
            Point(11.0, 50.0),
            Point(11.0, 51.0),
            Point(10.0, 51.0),
            Point(10.0, 50.0),
        ])
        crs_poly = get_utm_crs_for_geometry(poly)
        assert crs_poly.epsg == 32632

        bbox = BoundingBox(min_x=-75.0, min_y=40.0, max_x=-73.0, max_y=42.0)
        crs_bbox = get_utm_crs_for_geometry(bbox)
        assert crs_bbox.epsg == 32618


class TestTransformations:
    """Tests for forward and inverse coordinate projections."""

    def test_utm_central_meridian_forward_inverse(self) -> None:
        # On central meridian (Zone 31 central meridian is 3°E)
        lon = 3.0
        lat = 0.0  # Equator
        easting, northing = wgs84_to_utm(lon, lat, zone=31, hemisphere="N")

        assert math.isclose(easting, 500000.0, abs_tol=1e-2)
        assert math.isclose(northing, 0.0, abs_tol=1e-2)

        rev_lon, rev_lat = utm_to_wgs84(easting, northing, zone=31, hemisphere="N")
        assert math.isclose(rev_lon, lon, abs_tol=1e-6)
        assert math.isclose(rev_lat, lat, abs_tol=1e-6)

    def test_utm_southern_hemisphere_forward_inverse(self) -> None:
        lon = 18.4241  # Cape Town approx
        lat = -33.9249
        zone = get_utm_zone(lon, lat)  # Zone 34

        easting, northing = wgs84_to_utm(lon, lat, zone=zone, hemisphere="S")
        assert northing > 0

        rev_lon, rev_lat = utm_to_wgs84(easting, northing, zone=zone, hemisphere="S")
        assert math.isclose(rev_lon, lon, abs_tol=1e-5)
        assert math.isclose(rev_lat, lat, abs_tol=1e-5)

    def test_utm_out_of_range(self) -> None:
        with pytest.raises(OutOfRangeError):
            wgs84_to_utm(0.0, 85.0, zone=31, hemisphere="N")
        with pytest.raises(OutOfRangeError):
            wgs84_to_utm(0.0, -82.0, zone=31, hemisphere="S")

    def test_web_mercator_forward_inverse(self) -> None:
        # Equator, Greenwich
        x, y = wgs84_to_web_mercator(0.0, 0.0)
        assert math.isclose(x, 0.0, abs_tol=1e-3)
        assert math.isclose(y, 0.0, abs_tol=1e-3)

        # General point roundtrip
        lon, lat = 72.8777, 19.0760  # Mumbai
        x, y = wgs84_to_web_mercator(lon, lat)
        rev_lon, rev_lat = web_mercator_to_wgs84(x, y)
        assert math.isclose(rev_lon, lon, abs_tol=1e-6)
        assert math.isclose(rev_lat, lat, abs_tol=1e-6)

    def test_web_mercator_out_of_range(self) -> None:
        with pytest.raises(OutOfRangeError):
            wgs84_to_web_mercator(0.0, 86.0)


class TestGeometryReprojection:
    """Tests for reprojecting Point, LineString, Polygon, MultiPolygon, BoundingBox."""

    def test_transform_point(self) -> None:
        pt = Point(72.8, 19.0)
        crs_wgs = CRS.wgs84()
        crs_utm = CRS.from_epsg(32643)

        # WGS84 -> UTM
        pt_utm = transform_point(pt, crs_wgs, crs_utm)
        assert pt_utm.x > 100000.0
        assert pt_utm.y > 100000.0

        # UTM -> WGS84
        pt_wgs = transform_point(pt_utm, crs_utm, crs_wgs)
        assert math.isclose(pt_wgs.x, pt.x, abs_tol=1e-5)
        assert math.isclose(pt_wgs.y, pt.y, abs_tol=1e-5)

        # Identity transformation
        pt_same = transform_point(pt, crs_wgs, crs_wgs)
        assert pt_same.x == pt.x
        assert pt_same.y == pt.y

    def test_reproject_linestring(self) -> None:
        ls = LineString(coordinates=[(10.0, 50.0), (10.1, 50.1)])
        crs_wgs = CRS.wgs84()
        crs_utm = CRS.utm(32, "N")

        ls_utm = reproject_geometry(ls, crs_wgs, crs_utm)
        assert isinstance(ls_utm, LineString)
        assert len(ls_utm.coordinates) == 2

        # Reproject back
        ls_rev = reproject_geometry(ls_utm, crs_utm, crs_wgs)
        assert math.isclose(ls_rev.coordinates[0].x, 10.0, abs_tol=1e-5)
        assert math.isclose(ls_rev.coordinates[0].y, 50.0, abs_tol=1e-5)

    def test_reproject_polygon(self) -> None:
        poly = Polygon(
            exterior=[
                (10.0, 50.0),
                (10.1, 50.0),
                (10.1, 50.1),
                (10.0, 50.1),
                (10.0, 50.0),
            ],
            interiors=[[
                (10.02, 50.02),
                (10.08, 50.02),
                (10.08, 50.08),
                (10.02, 50.08),
                (10.02, 50.02),
            ]],
        )
        crs_wgs = CRS.wgs84()
        crs_utm = CRS.utm(32, "N")

        poly_utm = reproject_geometry(poly, crs_wgs, crs_utm)
        assert isinstance(poly_utm, Polygon)
        assert len(poly_utm.exterior) == 5  # closed
        assert len(poly_utm.interiors) == 1
        assert len(poly_utm.interiors[0]) == 5

        # Reproject back
        poly_rev = reproject_geometry(poly_utm, crs_utm, crs_wgs)
        assert math.isclose(poly_rev.exterior.coordinates[0].x, 10.0, abs_tol=1e-5)

    def test_reproject_multipolygon(self) -> None:
        poly1 = Polygon(exterior=[
            (10.0, 50.0),
            (10.1, 50.0),
            (10.1, 50.1),
            (10.0, 50.1),
            (10.0, 50.0),
        ])
        poly2 = Polygon(exterior=[
            (10.2, 50.2),
            (10.3, 50.2),
            (10.3, 50.3),
            (10.2, 50.3),
            (10.2, 50.2),
        ])
        mp = MultiPolygon(polygons=[poly1, poly2])
        crs_wgs = CRS.wgs84()
        crs_utm = CRS.utm(32, "N")

        mp_utm = reproject_geometry(mp, crs_wgs, crs_utm)
        assert isinstance(mp_utm, MultiPolygon)
        assert len(mp_utm.polygons) == 2

    def test_reproject_bounding_box(self) -> None:
        bbox = BoundingBox(min_x=10.0, min_y=50.0, max_x=10.2, max_y=50.2)
        crs_wgs = CRS.wgs84()
        crs_utm = CRS.utm(32, "N")

        bbox_utm = reproject_geometry(bbox, crs_wgs, crs_utm)
        assert isinstance(bbox_utm, BoundingBox)
        assert bbox_utm.min_x < bbox_utm.max_x
        assert bbox_utm.min_y < bbox_utm.max_y
