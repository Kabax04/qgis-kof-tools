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


# Points that do not follow the columns are read word by word, without guessing.

IRREGULAR = "do not follow the KOF columns"


@pytest.mark.parametrize("line, expected", [
    # Numeric code and no height: the code must not become north.
    (" 05 100\t2000 6615798.981 599667.952", ("100", "2000", 6615798.981, 599667.952, None, None, "")),
    # Numeric code, height and calculation code.
    ("05 100 2000 6615798.981 599667.952 98.848 32", ("100", "2000", 6615798.981, 599667.952, 98.848, 32, "")),
    # Remark after the numbers.
    (" 05 P1\t6615798.981\t599667.952\t98.848\tsjekk kum",
     ("P1", "", 6615798.981, 599667.952, 98.848, None, "sjekk kum")),
    # Text code and local coordinates with decimals.
    (" 05 P2 KUM 1000.000 2000.000 50.000", ("P2", "KUM", 1000.0, 2000.0, 50.0, None, "")),
])
def test_uregelmessige_kolonner(line, expected):
    result = parse_lines([line])
    (p,) = result.points
    assert (p.name, p.code, p.north, p.east, p.height, p.bk, p.remark) == pytest.approx(expected)
    (warning,) = result.warnings
    assert warning.startswith("1 point(s) " + IRREGULAR)


def test_tvetydig_punkt_hoppes_over_med_advarsel():
    # "code N E" and "N E H" both fit when no number has decimals.
    result = parse_lines([" 05 P1\t1000 2000 50"])
    assert result.points == []
    (warning,) = result.warnings
    assert warning.startswith("Line 1: point P1 has irregular columns")


def test_advarsel_om_uregelmessige_kolonner_samles():
    result = parse_lines([
        " 05 P1                  6615798.981  599667.952   98.848",
        " 05 P2\t6615798.981\t599667.952",
        " 05 P3\t6615798.981\t599667.952",
    ])
    assert len(result.points) == 3
    assert result.warnings == ["2 point(s) " + IRREGULAR + " and were read word by word. "
                               "Check their code and coordinates. First at line 2."]


# Column 1 is blank in the specification, but not in every file.

STANDARD = " 05 100        2000      6615798.981  599667.952   98.848 32 merk"


@pytest.mark.parametrize("line", [STANDARD[1:], "   " + STANDARD[1:], "\t" + STANDARD[1:]])
def test_postkode_uten_blank_forste_kolonne(line):
    result = parse_lines([line])
    (p,) = result.points
    assert (p.name, p.code, p.height, p.bk, p.remark) == ("100", "2000", pytest.approx(98.848), 32, "merk")
    assert result.warnings == []


def test_01_hode_uten_blank_forste_kolonne():
    header = parse_lines(["01 Oppdrag      06112026   2      22      $11100000000 JB"]).header
    assert (header.job, header.crs_code, header.observer) == ("Oppdrag", 22, "JB")
