import pytest

from kof_tools.kof_parser import parse_lines


def test_topcon_antall_punkter(topcon):
    assert len(topcon.points) == 21
    assert [p.name for p in topcon.points] == [str(n) for n in range(100, 121)]
    assert topcon.warnings == []


def test_topcon_punkt_100(topcon):
    p = topcon.points[0]
    assert p.name == "100"
    assert p.code == ""
    assert p.north == pytest.approx(6615798.981)
    assert p.east == pytest.approx(599667.952)
    assert p.height == pytest.approx(98.848)
    assert p.line_no == 10


def test_topcon_metadata(topcon):
    assert topcon.metadata["Jobbnavn"] == "2026-OVING-3-GRUPPE-2"
    assert topcon.metadata["Projeksjon"] == "NORWAY-EUREF89 UTM 32"
    # Tidspunkt inneholder kolon; bare det første kolonet skal splitte.
    assert topcon.metadata["Eksportdato"] == "2026-08-21 13:30:16"


def test_topcon_tegnkoding(topcon):
    assert topcon.encoding == "cp1252"
    assert "Måleinnstillinger" in topcon.metadata


def test_utf8_med_bom(tmp_path):
    path = tmp_path / "utf8.kof"
    path.write_bytes("﻿ 00 Måling: test\n".encode("utf-8"))
    from kof_tools.kof_parser import parse_file

    result = parse_file(path)
    assert result.encoding == "utf-8-sig"
    assert result.metadata == {"Måling": "test"}


def test_punkt_med_kode():
    line = " 05 P1         8510     6615798.981  599667.952   98.848"
    (p,) = parse_lines([line]).points
    assert (p.name, p.code) == ("P1", "8510")


def test_punkt_uten_hoyde():
    line = " 05 P1                  6615798.981  599667.952"
    (p,) = parse_lines([line]).points
    assert p.height is None
    assert p.east == pytest.approx(599667.952)


def test_avvikende_kolonner_leses_fra_hoyre():
    line = "05 P1 8510 6615798.981 599667.952 98.848"
    (p,) = parse_lines([line]).points
    assert (p.name, p.code) == ("P1", "8510")
    assert p.north == pytest.approx(6615798.981)
    assert p.height == pytest.approx(98.848)


def test_ugyldig_punkt_gir_advarsel():
    result = parse_lines([" 05 P1  tull"])
    assert result.points == []
    assert "Line 1" in result.warnings[0]


def test_ukjent_postkode_gir_advarsel():
    result = parse_lines([" 03 noe", " 77 noe"])
    assert len(result.warnings) == 2


def test_01_post_lagres_raatt():
    result = parse_lines([" 01 Oppdrag 29102026 1 1 22"])
    assert result.headers == ["Oppdrag 29102026 1 1 22"]


# Eksemplene under er hentet fra KOF-spesifikasjonen 2.00 (Norkart, 2005).


def test_linjer_med_minus_hoppes_over():
    result = parse_lines([
        "-05 PPPPPPPPPP KKKKKKKK XXXXXXXX.XXX YYYYYYY.YYY ZZZZ.ZZZ Bk MMMMMMM",
        "-05 TP1        1000       222357.900  -14987.600  147.800",
        " 05 45         4616        59319.054   58196.831  123.321",
    ])
    assert [p.name for p in result.points] == ["45"]
    assert result.disabled == 2
    assert result.warnings == []


def test_punkt_med_bk_og_merknad():
    line = " 05 PP3646     BF         222408.333  -11250.650 1811.123 37 Innmålt"
    (p,) = parse_lines([line]).points
    assert (p.name, p.code) == ("PP3646", "BF")
    assert p.east == pytest.approx(-11250.650)
    assert p.height == pytest.approx(1811.123)
    assert (p.bk, p.remark) == (37, "Innmålt")


def test_punkt_med_merknad_uten_bk():
    line = " 05 1          7003       222408.333  -11250.650  108.122    Enkeltpkt"
    (p,) = parse_lines([line]).points
    assert (p.bk, p.remark) == (None, "Enkeltpkt")


def test_utropstegn_er_kommentar():
    line = " 05 74         4611      6690719.350  299489.141 !hjørne"
    (p,) = parse_lines([line]).points
    assert p.north == pytest.approx(6690719.350)
    assert p.height is None
    assert p.remark == "hjørne"


def test_utropstegn_i_00_er_vanlig_tekst():
    result = parse_lines([" 00 Merk: viktig!"])
    assert result.metadata == {"Merk": "viktig!"}


@pytest.mark.parametrize(
    "line, expected",
    [
        (
            " 01 HURTIGSATS   12012005   2       3  219 $11100000000 Liv Belle",
            ("HURTIGSATS", "12012005", 2, 3, 219, "$11100000000", "Liv Belle"),
        ),
        (
            " 01 SVARTDALEN   09082005 002              $111         FINVÆR",
            ("SVARTDALEN", "09082005", 2, None, None, "$111", "FINVÆR"),
        ),
        (
            " 01 TESTFELT E19 25022005 002      22      $111         FINN VINKEL",
            ("TESTFELT E19", "25022005", 2, 22, None, "$111", "FINN VINKEL"),
        ),
    ],
)
def test_01_hode_versjon_2(line, expected):
    h = parse_lines([line]).header
    assert (h.job, h.date, h.version, h.crs_code, h.municipality, h.units, h.observer) == expected
    assert not h.east_first


def test_01_hode_versjon_1_tolkes_ikke():
    result = parse_lines([" 01 HURTIGSATS   12.10.88     E18          NANNE        AXEL"])
    assert result.header is None
    assert len(result.headers) == 1


def test_01_med_ost_forst_bytter_akser():
    result = parse_lines([
        " 01 OPPDRAG      01012026   2      22      $21100000000",
        " 05 P1                      599667.952 6615798.981   98.848",
    ])
    assert result.header.east_first
    (p,) = result.points
    assert p.north == pytest.approx(6615798.981)
    assert p.east == pytest.approx(599667.952)


def test_unreadable_point_with_tab_is_reported():
    # tr() used to fail when a value was called "text".
    result = parse_lines([" 05 x\ty"])
    assert result.points == []
    assert result.warnings == ["Line 1: could not read point: " + repr("05 x\ty")]
