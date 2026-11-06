import math

import pytest

from conftest import DATA
from kof_tools.kof_parser import parse_file, parse_lines
from kof_tools.kof_vectors import GRS80_A, GRS80_F, ecef_to_geodetic, utm_epsg


@pytest.fixture(scope="module")
def vectors():
    return parse_file(DATA / "topcon_vektorer.kof")


def geodetic_to_ecef(lat, lon, height):
    e2 = GRS80_F * (2 - GRS80_F)
    lat, lon = math.radians(lat), math.radians(lon)
    n = GRS80_A / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    return (
        (n + height) * math.cos(lat) * math.cos(lon),
        (n + height) * math.cos(lat) * math.sin(lon),
        (n * (1 - e2) + height) * math.sin(lat),
    )


def test_reads_vectors_without_warnings(vectors):
    assert vectors.warnings == []
    assert vectors.points == []
    assert len(vectors.vectors) == 2


def test_two_vectors_share_one_start_station(vectors):
    first, second = vectors.vectors
    assert (first.from_name, first.to_name) == ("G010", "GE11")
    assert (second.from_name, second.to_name) == ("G010", "G014")
    assert (second.x, second.y, second.z) == (3172256.5739, 603379.5253, 5482036.1217)
    assert (second.dx, second.dy, second.dz) == (193.5895, -187.5277, -110.0335)
    assert second.line_no == 14


def test_44_and_46_belong_to_the_vector_before(vectors):
    first, second = vectors.vectors
    assert (first.sx, first.sy, first.sz) == (0.0021, 0.0012, 0.0027)
    assert (first.rxy, first.rxz, first.ryz) == (0.2720, 0.4615, 0.0670)
    assert (first.date, first.time) == ("2026-08-21", "12:58:12")
    assert first.info == "47 1.42 543 96"
    assert second.info == "47 1.47 541 96"


def test_length(vectors):
    assert vectors.vectors[0].length == pytest.approx(357.796, abs=1e-3)


def test_vector_without_start_station():
    result = parse_lines([" 43 B   1.0 2.0 3.0 0.000", " 44 0.1 0.1 0.1 1 0 0 1 0 1"])
    assert result.vectors == []
    assert result.warnings == [
        "Line 1: vector (43) without a start station (42), ignored",
        "Line 2: 44 record without a vector (43) before it, ignored",
    ]


def test_unreadable_vector_record():
    result = parse_lines([" 42 A  1.0 x 3.0", " 43 B 1.0 2.0 3.0"])
    assert result.vectors == []
    assert result.warnings[0].startswith("Line 1: could not read GNSS vector record")
    assert result.warnings[1] == "Line 2: vector (43) without a start station (42), ignored"


def test_points_and_vectors_in_one_file():
    result = parse_lines([
        " 05 100        1000     6615798.981  599667.952   98.848",
        " 42 A   3172256.5739  603379.5253 5482036.1217  0.000",
        " 43 B   1.0 2.0 3.0  0.000",
    ])
    assert len(result.points) == 1
    assert len(result.vectors) == 1
    assert result.warnings == []


@pytest.mark.parametrize("lat, lon, height", [
    (59.6667, 10.7667, 120.0),
    (78.2, 15.6, -30.0),
    (-33.9, 151.2, 2000.0),
    (0.0, 0.0, 0.0),
])
def test_ecef_to_geodetic_round_trip(lat, lon, height):
    result = ecef_to_geodetic(*geodetic_to_ecef(lat, lon, height))
    assert result == pytest.approx((lat, lon, height), abs=1e-9)


def test_utm_zone():
    assert utm_epsg(59.67, 10.76) == 25832
    assert utm_epsg(63.4, 12.1) == 25833
    assert utm_epsg(69.6, 30.0) == 25836
    assert utm_epsg(40.0, -74.0) == 32618
    assert utm_epsg(-33.9, 151.2) == 32756


@pytest.mark.parametrize("lat, lon, epsg", [
    (60.39, 5.32, 25832),   # Bergen: 32V is widened west to 3°
    (58.97, 5.73, 25832),   # Stavanger
    (56.5, 3.5, 25832),
    (55.9, 5.0, 25831),     # south of 32V
    (64.5, 5.0, 25831),     # north of 32V
    (78.92, 11.93, 25833),  # Ny-Ålesund: Svalbard has no zone 32X
    (78.22, 15.65, 25833),  # Longyearbyen
    (79.0, 8.0, 25831),
    (77.0, 25.0, 25835),
    (80.0, 35.0, 25837),
])
def test_utm_sone_unntak_i_norge_og_svalbard(lat, lon, epsg):
    assert utm_epsg(lat, lon) == epsg
