from datetime import date

import pytest

from conftest import DATA, NGI
from kof_tools import i18n
from kof_tools.crs_detect import EPSG_TO_SOSI, SOSI_TO_EPSG, detect_crs
from kof_tools.kof_parser import (
    COL_BK,
    COL_CODE,
    COL_EAST,
    COL_HEIGHT,
    COL_NAME,
    COL_NORTH,
    COL_REMARK,
    parse_file,
    parse_lines,
)
from kof_tools.kof_writer import KofWriter

KOF_FILES = sorted(DATA.glob("*.kof")) + sorted(NGI.glob("*.kof"))


def written(writer):
    return writer.text().split("\r\n")[:-1]


def reparse(writer):
    return parse_lines(written(writer))


def test_epsg_til_sosi_er_omvendt_tabell():
    assert len(EPSG_TO_SOSI) == len(SOSI_TO_EPSG)
    assert EPSG_TO_SOSI[25832] == 22
    assert EPSG_TO_SOSI[5110] == 210
    assert EPSG_TO_SOSI[27393] == 3


def test_punkt_i_faste_kolonner():
    writer = KofWriter()
    writer.point("100", "2000", 6615798.981, 599667.952, 98.848, 37, "kum")
    (line,) = written(writer)
    assert line[:4] == " 05 "
    assert line[COL_NAME] == "100       "
    assert line[COL_CODE] == "2000    "
    assert line[COL_NORTH] == " 6615798.981"
    assert line[COL_EAST] == " 599667.952"
    assert line[COL_HEIGHT] == "  98.848"
    assert line[COL_BK] == " 37 "
    assert line[COL_REMARK] == "kum"


def test_punkt_leses_tilbake():
    writer = KofWriter()
    writer.point("P1", "KUM", 6615798.981, 599667.952, -1.5, 30, "lokk")
    (p,) = reparse(writer).points
    assert (p.name, p.code, p.north, p.east, p.height, p.bk, p.remark) == (
        "P1", "KUM", 6615798.981, 599667.952, -1.5, 30, "lokk"
    )


def test_uten_hoyde_bk_og_merknad():
    writer = KofWriter()
    writer.point("1", "", 1000.0, 2000.0)
    assert written(writer) == [" 05 1" + " " * 23 + "1000.000    2000.000"]
    (p,) = reparse(writer).points
    assert p.height is None and p.bk is None and p.remark == ""


@pytest.mark.parametrize("height", [None, float("nan"), "", "abc"])
def test_manglende_hoyde_blir_tom(height):
    writer = KofWriter()
    writer.point("1", "", 1000.0, 2000.0, height)
    assert reparse(writer).points[0].height is None
    assert writer.warnings == []


def test_merknad_uten_bk():
    writer = KofWriter()
    writer.point("1", "", 1000.0, 2000.0, 5.0, None, "12 kommentar")
    (p,) = reparse(writer).points
    assert p.bk is None
    assert p.remark == "12 kommentar"


def test_lange_navn_og_koder_kortes_med_advarsel():
    writer = KofWriter()
    writer.point("ABCDEFGHIJKLM", "123456789", 1000.0, 2000.0)
    (p,) = reparse(writer).points
    assert (p.name, p.code) == ("ABCDEFGHIJ", "12345678")
    assert writer.warnings == [
        "1 point name(s) longer than 10 characters were shortened, e.g. 'ABCDEFGHIJKLM'",
        "1 code(s) longer than 8 characters were shortened, e.g. '123456789'",
    ]


def test_advarsler_samles_med_tre_eksempler():
    writer = KofWriter()
    for n in range(5):
        writer.point(f"LANGTNAVN-{n}", "", 1000.0, 2000.0)
    assert writer.warnings == [
        "5 point name(s) longer than 10 characters were shortened, "
        "e.g. 'LANGTNAVN-0', 'LANGTNAVN-1', 'LANGTNAVN-2'"
    ]


def test_linjeskift_og_tab_fjernes():
    writer = KofWriter()
    writer.point("A\tB", "K\nL", 1000.0, 2000.0, None, None, "en\r\nto")
    (line,) = written(writer)
    assert "\t" not in line
    (p,) = reparse(writer).points
    assert (p.name, p.code, p.remark) == ("A B", "K L", "en to")


@pytest.mark.parametrize("north, east", [(None, 2000.0), (1000.0, float("nan")), ("x", 1.0)])
def test_mangler_nord_eller_ost(north, east):
    writer = KofWriter()
    assert writer.point("1", "", north, east) is False
    assert writer.records == []
    assert writer.warnings == ["1 point(s) without north or east coordinate were skipped, e.g. '1'"]


def test_for_store_koordinater_hoppes_over():
    writer = KofWriter()
    # Geographic or wrong CRS: e.g. web mercator far from Norway, or degrees times 1e6.
    assert writer.point("1", "", 12345678901.0, 2000.0) is False
    assert writer.point("2", "", 1000.0, 123456789.0) is False
    assert writer.points == 0
    assert writer.warnings == [
        "2 point(s) with north or east too large for the KOF columns were skipped, "
        "e.g. '1', '2'. Check the coordinate reference system."
    ]


def test_norske_koordinater_far_plass():
    writer = KofWriter()
    # Northernmost Svalbard in UTM, negative east in zone 33, NTM.
    for north, east in ((9_100_000.0, 1_400_000.0), (6_500_000.0, -300_000.0), (1_200_000.0, 100_000.0)):
        assert writer.point("1", "", north, east, 2469.0)
    assert writer.warnings == []
    assert [(p.north, p.east) for p in reparse(writer).points] == [
        (9_100_000.0, 1_400_000.0), (6_500_000.0, -300_000.0), (1_200_000.0, 100_000.0)
    ]


def test_store_hoyder_mister_desimaler_for_de_utelates():
    writer = KofWriter()
    writer.point("1", "", 1000.0, 2000.0, 12345.678)
    writer.point("2", "", 1000.0, 2000.0, -1234567.4)
    writer.point("3", "", 1000.0, 2000.0, 123456789.0)
    heights = [p.height for p in reparse(writer).points]
    assert heights == [12345.68, -1234567.0, None]
    assert writer.warnings == [
        "1 height(s) too large for the KOF column were left empty, e.g. for point '3'"
    ]


@pytest.mark.parametrize("bk, expected", [(37, 37), (0, 0), ("30", 30), (31.0, 31)])
def test_bk(bk, expected):
    writer = KofWriter()
    writer.point("1", "", 1000.0, 2000.0, 1.0, bk)
    assert reparse(writer).points[0].bk == expected
    assert writer.warnings == []


@pytest.mark.parametrize("bk", [100, -1, 3.5, "x"])
def test_ugyldig_bk_utelates(bk):
    writer = KofWriter()
    writer.point("1", "", 1000.0, 2000.0, 1.0, bk, "merknad")
    (p,) = reparse(writer).points
    assert p.bk is None and p.remark == "merknad"
    assert len(writer.warnings) == 1


def test_hode_med_sosi_kode_og_epsg():
    writer = KofWriter()
    writer.header(job="Oppmåling", epsg=25832, date=date(2026, 10, 30), observer="JB")
    result = reparse(writer)
    header = result.header
    assert (header.job, header.date, header.version, header.crs_code, header.observer) == (
        "Oppmåling", "30102026", 2, 22, "JB"
    )
    assert header.units == "$11100000000"
    assert header.east_first is False
    assert result.metadata["EPSG"] == "25832"
    assert detect_crs(result.metadata, header.crs_code) == 25832


def test_hode_uten_sosi_kode_bruker_epsg_kommentar():
    writer = KofWriter()
    writer.header(epsg=5972, height_system="NN2000")
    result = reparse(writer)
    assert result.header.crs_code is None
    assert detect_crs(result.metadata, result.header.crs_code) == 5972
    assert result.metadata["Høydesystem"] == "NN2000"


def test_langt_jobbnavn_kortes():
    writer = KofWriter()
    writer.header(job="Et svært langt jobbnavn")
    assert reparse(writer).header.job == "Et svært lan"


def test_kommentarer():
    writer = KofWriter()
    writer.comment("Eksportert fra QGIS\nLag: punkter ! med utropstegn")
    result = reparse(writer)
    assert result.comments == ["Eksportert fra QGIS", "Lag: punkter ! med utropstegn"]


def test_lagres_som_cp1252_med_crlf(tmp_path):
    path = tmp_path / "ut.kof"
    writer = KofWriter()
    writer.comment("Måling ved Ærfuglvågen")
    writer.point("Å1", "", 1000.0, 2000.0)
    assert writer.save(path) == []
    data = path.read_bytes()
    assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")
    assert "Ærfuglvågen".encode("cp1252") in data
    result = parse_file(path)
    assert result.encoding == "cp1252"
    assert result.points[0].name == "Å1"


def test_lagres_som_utf8(tmp_path):
    path = tmp_path / "ut.kof"
    writer = KofWriter()
    writer.point("Ω1", "", 1000.0, 2000.0)
    assert writer.save(path, encoding="utf-8") == []
    result = parse_file(path)
    assert result.encoding == "utf-8-sig"
    assert result.points[0].name == "Ω1"


def test_tegn_som_cp1252_ikke_kan_lagre(tmp_path):
    path = tmp_path / "ut.kof"
    writer = KofWriter()
    writer.point("1", "", 1000.0, 2000.0)
    writer.point("Ω2", "", 1000.0, 2000.0)
    assert writer.save(path) == [
        "1 line(s) have characters that cp1252 cannot store, written as '?'. First at line 2."
    ]
    assert parse_file(path).points[1].name == "?2"


def test_advarsler_pa_norsk():
    i18n.set_language("nb")
    writer = KofWriter()
    writer.point("1", "", None, 2000.0)
    assert writer.warnings == ["1 punkt(er) uten nord- eller østkoordinat ble hoppet over, f.eks. '1'"]


def point_tuple(p):
    return (p.name, p.code, p.north, p.east, p.height, p.bk, p.remark)


@pytest.mark.parametrize("path", KOF_FILES, ids=lambda p: p.name)
def test_rundtur(path, tmp_path):
    """Import -> export -> import gives the same points and CRS."""
    original = parse_file(path)
    writer = KofWriter()
    epsg = detect_crs(original.metadata, original.header.crs_code if original.header else None)
    writer.header(job=original.header.job if original.header else "", epsg=epsg)
    for p in original.points:
        writer.point(p.name, p.code, p.north, p.east, p.height, p.bk, p.remark)
    out = tmp_path / "rundtur.kof"
    writer.save(out)
    again = parse_file(out)

    # Names and codes longer than the columns are shortened, as warned.
    expected = [
        (p.name[:10], p.code[:8], p.north, p.east, p.height, p.bk, p.remark)
        for p in original.points
    ]
    assert [point_tuple(p) for p in again.points] == expected
    assert again.warnings == []
    assert detect_crs(again.metadata, again.header.crs_code) == epsg


def test_rundtur_dekker_alle_testfilene():
    assert len(KOF_FILES) >= 12
    assert sum(len(parse_file(p).points) for p in KOF_FILES) > 100


def test_linje_og_flate_leses_tilbake():
    writer = KofWriter()
    writer.start_line()
    writer.point("L1", "7002", 1000.0, 2000.0, 1.0)
    writer.point("L2", "7002", 1010.0, 2000.0, 2.0)
    assert writer.end_line() is True
    writer.start_line()
    for name, north, east in (("F1", 0.0, 0.0), ("F2", 10.0, 0.0), ("F3", 10.0, 10.0)):
        writer.point(name, "", north, east)
    assert writer.end_line(closed=True) is True
    assert written(writer)[0] == " 09 91"
    assert written(writer)[3] == " 09 99"
    assert written(writer)[-1] == " 09 96"
    assert (writer.lines, writer.polygons, writer.points) == (1, 1, 5)

    result = reparse(writer)
    assert result.warnings == []
    line, polygon = result.lines
    assert [p.name for p in line.points] == ["L1", "L2"] and not line.closed
    assert [p.name for p in polygon.points] == ["F1", "F2", "F3"] and polygon.closed


def test_for_kort_linje_fjernes_med_advarsel():
    writer = KofWriter()
    writer.point("P", "", 5.0, 5.0)
    writer.start_line()
    writer.point("A", "", 1000.0, 2000.0)
    writer.point("B", "", None, 2000.0)
    assert writer.end_line() is False
    writer.start_line()
    writer.point("C", "", 0.0, 0.0)
    writer.point("D", "", 1.0, 0.0)
    assert writer.end_line(closed=True) is False
    assert written(writer) == [" 05 P" + " " * 23 + "   5.000       5.000"]
    assert (writer.lines, writer.polygons, writer.points) == (0, 0, 1)
    assert "2 line(s) or polygon(s) with too few points were skipped, e.g. starting at point 'A', 'C'" in (
        writer.warnings
    )


def test_ny_linje_avslutter_forrige():
    writer = KofWriter()
    writer.start_line()
    writer.point("A", "", 0.0, 0.0)
    writer.point("B", "", 1.0, 0.0)
    writer.start_line()
    writer.point("C", "", 2.0, 0.0)
    writer.point("D", "", 3.0, 0.0)
    writer.end_line()
    result = reparse(writer)
    assert [[p.name for p in line.points] for line in result.lines] == [["A", "B"], ["C", "D"]]
    assert result.warnings == []


def test_rundtur_linjer_fra_spesifikasjonen():
    """Every line and polygon in the spec examples comes back with the same points, written as 09 91."""
    original = parse_file(DATA / "spec_linjer.kof")
    writer = KofWriter()
    for line in original.lines:
        writer.start_line()
        for p in line.points:
            writer.point(p.name, p.code, p.north, p.east, p.height, p.bk, p.remark)
        writer.end_line(line.closed)
    again = reparse(writer)
    assert again.warnings == []
    assert [([point_tuple(p) for p in line.points], line.closed) for line in again.lines] == [
        ([point_tuple(p) for p in line.points], line.closed) for line in original.lines
    ]


def test_utropstegn_i_navn_og_kode_byttes_ut():
    writer = KofWriter()
    writer.point("Ab!c", "K!1", 6615798.981, 599667.952, 98.848, remark="merk")
    (p,) = reparse(writer).points
    assert (p.name, p.code, p.height, p.remark) == ("Ab_c", "K_1", 98.848, "merk")
    (warning,) = writer.warnings
    assert warning.startswith("2 point name(s) or code(s) had '!'")
