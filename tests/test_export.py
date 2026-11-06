"""Tester av eksport til KOF. Krever QGIS, hoppes over ellers."""

import pytest

qgis_core = pytest.importorskip("qgis.core")

from qgis.core import (  # noqa: E402
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsVectorLayer,
)

from conftest import DATA, NGI  # noqa: E402
from kof_tools.kof_parser import parse_file  # noqa: E402
from kof_tools.processing.export_kof_algorithm import ExportKofAlgorithm  # noqa: E402
from kof_tools.processing.import_kof_algorithm import ImportKofAlgorithm  # noqa: E402

pytestmark = pytest.mark.usefixtures("qgis_app")


class CollectingFeedback(QgsProcessingFeedback):
    def __init__(self):
        super().__init__()
        self.warnings = []
        self.infos = []

    def pushWarning(self, warning):  # noqa: N802
        self.warnings.append(warning)
        super().pushWarning(warning)

    def pushInfo(self, info):  # noqa: N802
        self.infos.append(info)
        super().pushInfo(info)


def import_kof(path):
    alg = ImportKofAlgorithm().create()
    context = QgsProcessingContext()
    results, ok = alg.run({"INPUT": str(path), "OUTPUT": "memory:"}, context, QgsProcessingFeedback())
    assert ok
    return context.takeResultLayer(results["OUTPUT"])


def export_kof(layer, path, **params):
    alg = ExportKofAlgorithm().create()
    feedback = CollectingFeedback()
    results, ok = alg.run(
        {"INPUT": layer, "OUTPUT": str(path), **params}, QgsProcessingContext(), feedback
    )
    assert ok
    assert results["OUTPUT"] == str(path)
    return parse_file(path), feedback


def memory_layer(definition, fields="", features=()):
    layer = QgsVectorLayer(f"{definition}?crs=EPSG:25832{fields}", "målepunkter", "memory")
    provider = layer.dataProvider()
    for geometry, attributes in features:
        feature = QgsFeature(layer.fields())
        if geometry is not None:
            feature.setGeometry(geometry)
        feature.setAttributes(attributes)
        provider.addFeatures([feature])
    return layer


@pytest.mark.parametrize(
    "path", [DATA / "topcon_ovingsfil.kof", NGI / "UTM32_EN.kof", NGI / "KOF_from_ArcGIS.kof"], ids=lambda p: p.name
)
def test_import_eksport_import(path, tmp_path):
    original = parse_file(path)
    layer = import_kof(path)
    result, feedback = export_kof(layer, tmp_path / "ut.kof")
    assert feedback.warnings == []
    assert [(p.name, p.code, p.north, p.east, p.height, p.bk, p.remark) for p in result.points] == [
        (p.name, p.code, pytest.approx(p.north), pytest.approx(p.east), p.height, p.bk, p.remark)
        for p in original.points
    ]
    assert import_kof(tmp_path / "ut.kof").crs() == layer.crs()


def test_hode_har_sosi_kode_og_lagnavn(tmp_path):
    layer = memory_layer("Point", features=[(QgsGeometry(QgsPoint(599667.952, 6615798.981)), [])])
    result, _ = export_kof(layer, tmp_path / "ut.kof")
    assert result.header.crs_code == 22
    assert result.header.job == "målepunkter"
    assert result.header.east_first is False
    assert result.encoding == "cp1252"


def test_lag_uten_importfelt_bruker_nummer_og_z(tmp_path):
    layer = memory_layer("PointZ", features=[
        (QgsGeometry(QgsPoint(599667.952, 6615798.981, 98.848)), []),
        (QgsGeometry(QgsPoint(599670.0, 6615800.0, 99.5)), []),
    ])
    result, feedback = export_kof(layer, tmp_path / "ut.kof")
    assert [(p.name, p.north, p.east, p.height) for p in result.points] == [
        ("1", 6615798.981, 599667.952, 98.848),
        ("2", 6615800.0, 599670.0, 99.5),
    ]
    assert "The layer has no field name, not used" in feedback.infos


def test_valgte_felt(tmp_path):
    layer = memory_layer(
        "Point", "&field=id:string&field=tema:integer&field=kote:double&field=notat:string",
        [(QgsGeometry(QgsPoint(599667.952, 6615798.981)), ["K1", 2000, 12.5, "kum"])],
    )
    result, _ = export_kof(
        layer, tmp_path / "ut.kof",
        NAME_FIELD="id", CODE_FIELD="tema", HEIGHT_FIELD="kote", BK_FIELD=None, REMARK_FIELD="notat",
    )
    (p,) = result.points
    assert (p.name, p.code, p.height, p.remark) == ("K1", "2000", 12.5, "kum")


def test_null_verdier(tmp_path):
    layer = memory_layer(
        "Point", "&field=name:string&field=code:string&field=H:double",
        [(QgsGeometry(QgsPoint(599667.952, 6615798.981)), ["P1", None, None])],
    )
    result, feedback = export_kof(layer, tmp_path / "ut.kof")
    (p,) = result.points
    assert (p.name, p.code, p.height) == ("P1", "", None)
    assert feedback.warnings == []


def test_transformerer_til_valgt_crs(tmp_path):
    layer = import_kof(DATA / "topcon_ovingsfil.kof")
    result, feedback = export_kof(layer, tmp_path / "ut.kof", TARGET_CRS="EPSG:25833")
    assert result.header.crs_code == 23
    original = parse_file(DATA / "topcon_ovingsfil.kof").points[0]
    # The same point is further east in zone 32 than in zone 33.
    assert result.points[0].east < original.east
    assert any("EPSG:25833" in info for info in feedback.infos)


def test_geografisk_crs_avvises(tmp_path):
    layer = QgsVectorLayer("Point?crs=EPSG:4326", "wgs84", "memory")
    alg = ExportKofAlgorithm().create()
    with pytest.raises(QgsProcessingException):
        alg.processAlgorithm(
            {"INPUT": layer, "OUTPUT": str(tmp_path / "ut.kof")}, QgsProcessingContext(), QgsProcessingFeedback()
        )


def test_geografisk_lag_med_projisert_maal(tmp_path):
    layer = QgsVectorLayer("Point?crs=EPSG:4326", "wgs84", "memory")
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry(QgsPoint(10.75, 59.91)))
    layer.dataProvider().addFeatures([feature])
    result, _ = export_kof(layer, tmp_path / "ut.kof", TARGET_CRS="EPSG:25832")
    (p,) = result.points
    assert p.north == pytest.approx(6643000, abs=2000)
    assert p.east == pytest.approx(597000, abs=2000)


def test_lag_uten_crs_skrives_uendret_med_advarsel(tmp_path):
    layer = QgsVectorLayer("Point", "uten_crs", "memory")
    layer.setCrs(QgsCoordinateReferenceSystem())
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry(QgsPoint(599667.952, 6615798.981)))
    layer.dataProvider().addFeatures([feature])
    result, feedback = export_kof(layer, tmp_path / "ut.kof", TARGET_CRS="EPSG:25832")
    assert result.header.crs_code == 22
    (p,) = result.points
    assert (p.north, p.east) == pytest.approx((6615798.981, 599667.952))
    assert any("no coordinate reference system" in w for w in feedback.warnings)
    assert not any("Transforming" in info for info in feedback.infos)


def test_crs_uten_sosi_kode_gir_advarsel(tmp_path):
    layer = import_kof(DATA / "topcon_ovingsfil.kof")
    result, feedback = export_kof(layer, tmp_path / "ut.kof", TARGET_CRS="EPSG:3006")
    assert result.header.crs_code is None
    assert result.metadata["EPSG"] == "3006"
    assert any("SOSI" in w for w in feedback.warnings)


def test_multipunkt_og_manglende_geometri(tmp_path):
    layer = memory_layer("MultiPoint", "&field=name:string", [
        (QgsGeometry.fromWkt("MultiPoint ((1000 2000), (1001 2001))"), ["M"]),
        (None, ["tom"]),
    ])
    result, feedback = export_kof(layer, tmp_path / "ut.kof")
    assert [(p.name, p.north, p.east) for p in result.points] == [("M", 2000, 1000), ("M", 2001, 1001)]
    assert feedback.warnings == ["1 point(s) without north or east coordinate were skipped, e.g. 'tom'"]


def test_utf8(tmp_path):
    layer = memory_layer(
        "Point", "&field=name:string", [(QgsGeometry(QgsPoint(1000, 2000)), ["Ω1"])],
    )
    result, feedback = export_kof(layer, tmp_path / "ut.kof", ENCODING=1)
    assert result.encoding == "utf-8-sig"
    assert result.points[0].name == "Ω1"
    assert feedback.warnings == []


def import_lines(path):
    alg = ImportKofAlgorithm().create()
    context = QgsProcessingContext()
    results, ok = alg.run({
        "INPUT": str(path), "CRS": "EPSG:25832", "OUTPUT": "memory:",
        "OUTPUT_LINES": "memory:", "OUTPUT_POLYGONS": "memory:",
    }, context, QgsProcessingFeedback())
    assert ok
    return context.takeResultLayer(results["OUTPUT_LINES"]), context.takeResultLayer(results["OUTPUT_POLYGONS"])


def names_and_coordinates(line):
    return [(p.name, p.code, pytest.approx(p.north), pytest.approx(p.east)) for p in line.points]


def test_linjer_import_eksport_import(tmp_path):
    lines, _ = import_lines(DATA / "spec_linjer.kof")
    result, feedback = export_kof(lines, tmp_path / "linjer.kof")
    assert feedback.warnings == []
    assert result.warnings == []
    assert len(result.lines) == lines.featureCount() == 9

    # Every line keeps its measured points. Arcs go back to 09 93, not their drawn vertices.
    original = {tuple(p.name for p in line.points): line for line in parse_file(DATA / "spec_linjer.kof").lines}
    exported = {tuple(p.name for p in line.points): line for line in result.lines}
    open_lines = [names for names, line in original.items() if not line.closed]
    assert len(open_lines) == 9
    for names in open_lines:
        assert exported[names].pi == (93 if original[names].kind == "arc" else 91)
        assert not exported[names].closed
        assert names_and_coordinates(exported[names]) == [
            (p.name, p.code, p.north, p.east) for p in original[names].points
        ]
    assert sum(line.kind == "arc" for line in result.lines) == 2
    assert any("09 blocks" in info for info in feedback.infos)


def test_flate_import_eksport_import(tmp_path):
    _, polygons = import_lines(DATA / "spec_linjer.kof")
    result, feedback = export_kof(polygons, tmp_path / "flater.kof")
    assert feedback.warnings == []
    (polygon,) = result.lines
    assert polygon.closed
    (original,) = [line for line in parse_file(DATA / "spec_linjer.kof").lines if line.closed]
    assert [(p.name, p.north, p.east, p.height) for p in polygon.points] == [
        (p.name, p.north, p.east, p.height) for p in original.points
    ]


def test_linjelag_uten_punktnavn_nummereres(tmp_path):
    layer = memory_layer("MultiLineStringZ", "&field=code:string", [
        (QgsGeometry.fromWkt("MultiLineStringZ ((0 0 1, 0 10 2), (5 5 3, 5 15 4, 5 25 5))"), ["VEG"]),
    ])
    result, _ = export_kof(layer, tmp_path / "ut.kof")
    first, second = result.lines
    assert [(p.name, p.code, p.north, p.east, p.height) for p in first.points] == [
        ("1", "VEG", 0, 0, 1), ("2", "VEG", 10, 0, 2)
    ]
    assert [p.name for p in second.points] == ["3", "4", "5"]


def test_flate_med_hull_og_bue(tmp_path):
    layer = memory_layer("Polygon", features=[
        (QgsGeometry.fromWkt("Polygon ((0 0, 30 0, 30 30, 0 30, 0 0), (10 10, 20 10, 20 20, 10 10))"), []),
        (QgsGeometry.fromWkt("CurvePolygon (CircularString (100 0, 110 10, 100 20, 90 10, 100 0))"), []),
    ])
    result, feedback = export_kof(layer, tmp_path / "ut.kof")
    outer, hole, circle = result.lines
    assert all(line.closed for line in result.lines)
    assert [(p.north, p.east) for p in outer.points] == [(0, 0), (0, 30), (30, 30), (30, 0)]
    assert len(hole.points) == 3
    assert len(circle.points) > 8
    assert "1 polygon hole(s) were written as separate polygons" in feedback.warnings


def test_tomt_navn_og_hoyde_bruker_nummer_og_z(tmp_path):
    layer = memory_layer("PointZ", "&field=name:string&field=H:double", [
        (QgsGeometry.fromWkt("PointZ (599667.952 6615798.981 12.3)"), [None, None]),
        (QgsGeometry.fromWkt("PointZ (599668 6615799 13)"), ["", 14.0]),
        # The numbers must not take names the layer already has.
        (QgsGeometry.fromWkt("PointZ (599669 6615800 15)"), ["1", None]),
    ])
    result, _ = export_kof(layer, tmp_path / "ut.kof")
    assert [(p.name, p.height) for p in result.points] == [("2", 12.3), ("3", 14.0), ("1", 15.0)]


def test_utropstegn_i_navn_rapporteres(tmp_path):
    layer = memory_layer("PointZ", "&field=name:string", [
        (QgsGeometry.fromWkt("PointZ (599667.952 6615798.981 12.3)"), ["Ab!c"]),
    ])
    result, feedback = export_kof(layer, tmp_path / "ut.kof")
    assert [p.name for p in result.points] == ["Ab_c"]
    assert any("'!'" in w for w in feedback.warnings)


def test_kurver_varsles(tmp_path):
    layer = memory_layer("CompoundCurveZ", "&field=code:string", [
        (QgsGeometry.fromWkt("CircularStringZ (0 0 1, 10 10 2, 20 0 3)"), ["VEG"]),
    ])
    result, feedback = export_kof(layer, tmp_path / "ut.kof")
    (line,) = result.lines
    assert len(line.points) > 3
    assert any("curved feature" in w for w in feedback.warnings)


def import_all(path):
    alg = ImportKofAlgorithm().create()
    context = QgsProcessingContext()
    results, ok = alg.run({
        "INPUT": str(path), "CRS": "EPSG:25832", "OUTPUT": "memory:",
        "OUTPUT_LINES": "memory:", "OUTPUT_POLYGONS": "memory:",
    }, context, QgsProcessingFeedback())
    assert ok
    return [context.takeResultLayer(results[key]) for key in ("OUTPUT", "OUTPUT_LINES", "OUTPUT_POLYGONS")]


def export_layers(layers, path, **params):
    from kof_tools.processing.export_kof_algorithm import ExportKofLayersAlgorithm

    alg = ExportKofLayersAlgorithm().create()
    feedback = CollectingFeedback()
    results, ok = alg.run({"LAYERS": layers, "OUTPUT": str(path), **params}, QgsProcessingContext(), feedback)
    assert ok
    return parse_file(path), feedback


def records(result):
    return sorted((p.name, round(p.north, 3), round(p.east, 3)) for p in result.points)


def lines_of(result):
    return sorted((line.kind, line.closed, tuple(p.name for p in line.points)) for line in result.lines)


def test_hel_import_tilbake_til_en_fil(tmp_path):
    points, lines, polygons = import_all(DATA / "spec_linjer.kof")
    result, feedback = export_layers([points, lines, polygons], tmp_path / "alt.kof")
    original = parse_file(DATA / "spec_linjer.kof")

    # Every point once, and the same lines, polygons and arcs.
    assert records(result) == records(original)
    assert lines_of(result) == lines_of(original)
    assert result.warnings == []
    assert feedback.warnings == []
    in_lines = sum(len(line.points) for line in original.lines)
    assert any(info.startswith(f"{in_lines} points that are also in lines") for info in feedback.infos)


def test_flere_punktlag_numereres_uten_kollisjon(tmp_path):
    first = memory_layer("PointZ", "&field=name:string", [
        (QgsGeometry.fromWkt("PointZ (599667 6615798 1)"), ["1"]),
        (QgsGeometry.fromWkt("PointZ (599668 6615799 2)"), [None]),
    ])
    second = memory_layer("PointZ", "", [
        (QgsGeometry.fromWkt("PointZ (599669 6615800 3)"), []),
    ])
    result, _ = export_layers([first, second], tmp_path / "ut.kof")
    assert [(p.name, p.height) for p in result.points] == [("1", 1), ("2", 2), ("3", 3)]


def test_samme_navn_annen_posisjon_skrives_begge_steder(tmp_path):
    points = memory_layer("PointZ", "&field=name:string", [
        (QgsGeometry.fromWkt("PointZ (5 5 1)"), ["A"]),
    ])
    lines = memory_layer("LineStringZ", "&field=points:string", [
        (QgsGeometry.fromWkt("LineStringZ (0 0 1, 0 10 2)"), ["A,B"]),
    ])
    result, _ = export_layers([points, lines], tmp_path / "ut.kof")
    assert [p.name for p in result.points] == ["A", "A", "B"]


def test_uten_lag_feiler(tmp_path):
    from kof_tools.processing.export_kof_algorithm import ExportKofLayersAlgorithm

    alg = ExportKofLayersAlgorithm().create()
    with pytest.raises(QgsProcessingException):
        alg.processAlgorithm({"LAYERS": [], "OUTPUT": str(tmp_path / "ut.kof")},
                             QgsProcessingContext(), QgsProcessingFeedback())


def test_qgis_versjon_uten_utgivelsesnavn(tmp_path):
    import re

    layer = memory_layer("PointZ", "", [(QgsGeometry.fromWkt("PointZ (599667 6615798 1)"), [])])
    result, feedback = export_kof(layer, tmp_path / "ut.kof")
    # The release name may have letters cp1252 cannot store, e.g. "3.22.16-Białowieża".
    assert re.fullmatch(r"Exported from QGIS \d+\.\d+\.\d+ with KOF Tools", result.comments[0])
    assert feedback.warnings == []
