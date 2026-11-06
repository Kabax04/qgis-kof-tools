"""Real KOF files from NGI kof-parser (MIT), see tests/data/ngi/README.md."""

import pytest

from conftest import NGI
from kof_tools.crs_detect import axes_look_swapped, crs_from_text, detect_crs
from kof_tools.kof_parser import parse_file


def epsg_of(result):
    return detect_crs(result.metadata, result.header.crs_code if result.header else None)


@pytest.mark.parametrize(
    "name, epsg",
    [
        ("UTM32_EN.kof", 25832),
        ("UTM32_NE.kof", 25832),
        ("UTM33_EN.kof", 25833),
        ("ED50_UTM32_EN.kof", 23032),
        ("KOF_from_ArcGIS.kof", 5110),  # K.sys 210 = NTM zone 10
        ("import_template.kof", 5110),  # "Spatial Reference ID (SRID): 5110"
        ("15-5-18-Fossegata_windows.kof", None),
    ],
)
def test_crs(name, epsg):
    assert epsg_of(parse_file(NGI / name)) == epsg


@pytest.mark.parametrize(
    "text, epsg",
    [
        ("ETRS_1989_UTM_Zone_32N", 25832),
        ("ETRS_1989_NTM_Zone_10", 5110),
        ("EUREF89 UTM sone 29", 25829),
        ("ED50_UTM32  253851.717242775   6595967.83250844", 23032),
        ("EPSG:25833", 25833),
    ],
)
def test_crs_from_export_text(text, epsg):
    assert crs_from_text(text) == epsg


def test_axis_order_from_header():
    en = parse_file(NGI / "UTM32_EN.kof").points[0]
    ne = parse_file(NGI / "UTM32_NE.kof").points[0]
    assert (en.north, en.east) == (ne.north, ne.east) == (6589107.923, 594137.802)


@pytest.mark.parametrize(
    "name, swapped",
    [
        # The 01 header says east first, but the coordinates are north first.
        ("Innmaalt_UTM32.kof", True),
        # No header, east first without saying so.
        ("import_template.kof", True),
        ("UTM32_EN.kof", False),
        ("KOF_from_ArcGIS.kof", False),
        ("kof-with-tabs.kof", False),
    ],
)
def test_axes_look_swapped(name, swapped):
    result = parse_file(NGI / name)
    assert axes_look_swapped(result.points, epsg_of(result)) is swapped


def test_axes_not_checked_for_local_systems():
    result = parse_file(NGI / "Innmaalt_UTM32.kof")
    assert not axes_look_swapped(result.points, 27393)


def test_missing_coordinates_give_warnings():
    result = parse_file(NGI / "test-no-coordinates.kof")
    assert [p.name for p in result.points] == ["SMPLOC3", "SMPLOC5"]
    assert len(result.warnings) == 5
    assert all("missing north or east" in w for w in result.warnings)


def test_tabs():
    result = parse_file(NGI / "kof-with-tabs.kof")
    assert [(p.name, p.north, p.east) for p in result.points][1] == ("15", 7023231.981, 599001.246)
    # Tabs break the columns, so the points are read word by word, with one warning.
    (warning,) = result.warnings
    assert warning.startswith("3 point(s) do not follow the KOF columns")


def test_09_free_text_from_instrument():
    result = parse_file(NGI / "15-5-18-Fossegata_windows.kof")
    assert result.warnings == []
    assert result.lines == []
    assert len(result.points) == 6
    assert result.points[0].name == "ÆØÅ1"
    assert any(c.startswith("Laget av versjon 5.5.1") for c in result.comments)


def test_arcgis_file():
    result = parse_file(NGI / "KOF_from_ArcGIS.kof")
    assert len(result.points) == 132
    assert result.header.east_first
    assert (result.points[0].north, result.points[0].east) == (1193605.427, 83711.914)


class P:
    def __init__(self, north, east):
        self.north, self.east = north, east


def test_local_coordinates_labelled_as_utm_are_not_swapped():
    # The spec examples use local coordinates around 12 000.
    result = parse_file(NGI.parent / "spec_linjer.kof")
    assert not axes_look_swapped(result.points, 25832)


def test_topcon_is_not_swapped(topcon):
    assert not axes_look_swapped(topcon.points, 25832)


@pytest.mark.parametrize(
    "north, east, epsg, swapped",
    [
        # Bergen in UTM 33 has a negative easting.
        (6_700_000, -55_000, 25833, False),
        (-55_000, 6_700_000, 25833, True),
        # Svalbard in UTM 33.
        (8_700_000, 500_000, 25833, False),
        # Nordkapp in NTM zone 26 (northing about 2.4 million).
        (2_400_000, 100_000, 5126, False),
        (100_000, 2_400_000, 5126, True),
    ],
)
def test_axis_ranges(north, east, epsg, swapped):
    assert axes_look_swapped([P(north, east)], epsg) is swapped
