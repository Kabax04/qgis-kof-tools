"""Tester som krever QGIS. Hoppes over når qgis ikke kan importeres.

Kjør med QGIS sin Python, f.eks. `python-qgis-ltr.bat -m pytest`.
"""

import pytest

qgis_core = pytest.importorskip("qgis.core")

from qgis.core import (  # noqa: E402
    QgsCoordinateReferenceSystem,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsWkbTypes,
)

from conftest import DATA  # noqa: E402
from kof_tools.layer_builder import build_point_layer  # noqa: E402
from kof_tools.processing.import_kof_algorithm import ImportKofAlgorithm  # noqa: E402


pytestmark = pytest.mark.usefixtures("qgis_app")


def run_algorithm(params):
    alg = ImportKofAlgorithm().create()
    context = QgsProcessingContext()
    feedback = QgsProcessingFeedback()
    params = {"OUTPUT": "memory:", **params}
    results, ok = alg.run(params, context, feedback)
    assert ok
    # Ta over eierskapet, ellers slettes laget sammen med konteksten.
    return context.takeResultLayer(results["OUTPUT"])


def test_build_point_layer(topcon):
    layer = build_point_layer(topcon, QgsCoordinateReferenceSystem("EPSG:25832"))
    assert layer.isValid()
    assert layer.featureCount() == 21
    assert QgsWkbTypes.hasZ(layer.wkbType())


def test_x_er_ost_y_er_nord(topcon):
    layer = build_point_layer(topcon, QgsCoordinateReferenceSystem("EPSG:25832"))
    feature = next(layer.getFeatures())
    point = feature.geometry().constGet()
    assert feature["name"] == "100"
    assert point.x() == pytest.approx(599667.952)
    assert point.y() == pytest.approx(6615798.981)
    assert point.z() == pytest.approx(98.848)


def test_algoritme_finner_crs_fra_filen():
    layer = run_algorithm({"INPUT": str(DATA / "topcon_ovingsfil.kof")})
    assert layer.crs().authid() == "EPSG:25832"
    assert layer.featureCount() == 21


def test_algoritme_valgt_crs_overstyrer():
    layer = run_algorithm(
        {"INPUT": str(DATA / "topcon_ovingsfil.kof"), "CRS": "EPSG:25833"}
    )
    assert layer.crs().authid() == "EPSG:25833"


def test_algoritme_uten_crs_feiler(tmp_path):
    path = tmp_path / "uten_crs.kof"
    path.write_text(" 05 P1                  6615798.981  599667.952   98.848\n")
    alg = ImportKofAlgorithm().create()
    with pytest.raises(QgsProcessingException):
        alg.processAlgorithm(
            {"INPUT": str(path), "OUTPUT": "memory:"},
            QgsProcessingContext(),
            QgsProcessingFeedback(),
        )


def run_algorithm_all(params):
    alg = ImportKofAlgorithm().create()
    context = QgsProcessingContext()
    params = {"OUTPUT": "memory:", "OUTPUT_GROUPS": "memory:", **params}
    results, ok = alg.run(params, context, QgsProcessingFeedback())
    assert ok
    return results, context


def test_middellag_med_enkeltpunkter():
    results, context = run_algorithm_all({"INPUT": str(DATA / "topcon_ovingsfil.kof")})
    layer = context.takeResultLayer(results["OUTPUT_GROUPS"])
    assert layer.featureCount() == 11
    assert QgsWkbTypes.hasZ(layer.wkbType())
    group = next(f for f in layer.getFeatures() if f["name"] == "104")
    assert group["names"] == "104,105,106"
    assert group["count"] == 3
    assert group.geometry().constGet().x() == pytest.approx(group["E"])


def test_middellag_bare_gjentatte():
    results, context = run_algorithm_all(
        {"INPUT": str(DATA / "topcon_ovingsfil.kof"), "INCLUDE_SINGLES": False}
    )
    layer = context.takeResultLayer(results["OUTPUT_GROUPS"])
    assert layer.featureCount() == 5


def test_hoydetoleranse_splitter_grupper():
    # Høydene i 115/117/120 spriker 32 mm, så 1 cm høydetoleranse deler gruppen.
    results, context = run_algorithm_all(
        {
            "INPUT": str(DATA / "topcon_ovingsfil.kof"),
            "INCLUDE_SINGLES": False,
            "HEIGHT_TOLERANCE": 0.01,
        }
    )
    layer = context.takeResultLayer(results["OUTPUT_GROUPS"])
    names = {f["names"] for f in layer.getFeatures()}
    assert "115,117,120" not in names


def test_middellag_kan_droppes():
    alg = ImportKofAlgorithm().create()
    context = QgsProcessingContext()
    params = {
        "INPUT": str(DATA / "topcon_ovingsfil.kof"),
        "OUTPUT": "memory:",
        "OUTPUT_GROUPS": None,
    }
    results, ok = alg.run(params, context, QgsProcessingFeedback())
    assert ok
    assert "OUTPUT_GROUPS" not in results


def test_linjer_og_flater_fra_spesifikasjonen():
    results, context = run_algorithm_all({
        "INPUT": str(DATA / "spec_linjer.kof"),
        "CRS": "EPSG:25832",
        "OUTPUT_LINES": "memory:",
        "OUTPUT_POLYGONS": "memory:",
    })
    lines = context.takeResultLayer(results["OUTPUT_LINES"])
    polygons = context.takeResultLayer(results["OUTPUT_POLYGONS"])
    assert lines.featureCount() == 9
    assert polygons.featureCount() == 1

    by_name = {f["name"]: f for f in lines.getFeatures()}
    assert by_name["9–15"]["points"] == "9,11,13,15"
    assert by_name["9–15"]["code"] == "7002"
    arc = by_name["41–44"]
    assert arc["type"] == "arc"
    # Buen er segmentert, men går gjennom alle de målte punktene.
    assert arc.geometry().constGet().numPoints() > 4

    (polygon,) = polygons.getFeatures()
    assert polygon["type"] == "polygon"
    assert polygon.geometry().area() == pytest.approx(100.0)
    assert QgsWkbTypes.hasZ(polygons.wkbType())


def test_ingen_linjelag_uten_linjer():
    results, _ = run_algorithm_all({
        "INPUT": str(DATA / "topcon_ovingsfil.kof"),
        "OUTPUT_LINES": "memory:",
        "OUTPUT_POLYGONS": "memory:",
    })
    assert "OUTPUT_LINES" not in results
    assert "OUTPUT_POLYGONS" not in results


def test_swapped_axes_are_corrected():
    from conftest import NGI

    layer = run_algorithm({"INPUT": str(NGI / "Innmaalt_UTM32.kof")})
    point = next(layer.getFeatures()).geometry().constGet()
    assert (point.x(), point.y()) == pytest.approx((595870.665, 6644804.528))


def test_gnss_vectors_without_crs_use_utm_zone():
    results, context = run_algorithm_all({
        "INPUT": str(DATA / "topcon_vektorer.kof"),
        "OUTPUT_VECTORS": "memory:",
    })
    layer = context.takeResultLayer(results["OUTPUT_VECTORS"])
    assert layer.crs().authid() == "EPSG:25832"
    assert QgsWkbTypes.hasZ(layer.wkbType())
    assert layer.featureCount() == 2

    by_name = {f["name"]: f for f in layer.getFeatures()}
    vector = by_name["G010–G014"]
    assert vector["from"] == "G010"
    assert vector["date"] == "2026-08-21"
    assert vector["sX"] == pytest.approx(0.0021)
    line = vector.geometry().constGet()
    start, end = line.pointN(0), line.pointN(1)
    # The NMBU network in Ås, UTM 32.
    assert 597000 < start.x() < 600000
    assert 6614000 < start.y() < 6617000
    # The vector is short, so its length in the map is close to the 3D length.
    length_3d = ((end.x() - start.x()) ** 2 + (end.y() - start.y()) ** 2 + (end.z() - start.z()) ** 2) ** 0.5
    assert length_3d == pytest.approx(vector["length"], rel=1e-3)


def test_gnss_vectors_follow_selected_crs():
    results, context = run_algorithm_all({
        "INPUT": str(DATA / "topcon_vektorer.kof"),
        "CRS": "EPSG:25833",
        "OUTPUT_VECTORS": "memory:",
    })
    layer = context.takeResultLayer(results["OUTPUT_VECTORS"])
    assert layer.crs().authid() == "EPSG:25833"
    assert layer.featureCount() == 2


def test_skip_loading_removes_layer_from_load_list():
    from qgis.core import QgsProcessingContext as Context

    context = Context()
    context.addLayerToLoadOnCompletion("layer", Context.LayerDetails("x", None, "OUTPUT"))
    assert context.willLoadLayerOnCompletion("layer")
    ImportKofAlgorithm._skip_loading(context, "layer")
    assert not context.willLoadLayerOnCompletion("layer")


KUM = [
    " 05 lokk          KUM      6600000.000  600000.000  100.000",
    " 05 bunn          KUM      6600000.010  600000.000   97.500",
    " 05 lokk2         KUM      6600000.000  600000.010  100.020",
]


@pytest.mark.parametrize("params, expected", [
    # The default height tolerance (10 cm) keeps the bottom of the manhole apart.
    ({}, {"lokk,lokk2"}),
    # None (not set in the dialog) means no height limit.
    ({"HEIGHT_TOLERANCE": None}, {"lokk,bunn,lokk2"}),
])
def test_standard_hoydetoleranse(tmp_path, params, expected):
    path = tmp_path / "kum.kof"
    path.write_text("\n".join([" 00 EPSG: 25832"] + KUM) + "\n", encoding="utf-8")
    results, context = run_algorithm_all({"INPUT": str(path), "INCLUDE_SINGLES": False, **params})
    layer = context.takeResultLayer(results["OUTPUT_GROUPS"])
    assert {f["names"] for f in layer.getFeatures()} == expected


def test_filhode_og_kommentarer_i_loggen():
    class Log(QgsProcessingFeedback):
        def __init__(self):
            super().__init__()
            self.infos = []

        def pushInfo(self, info):  # noqa: N802
            self.infos.append(info)

    alg = ImportKofAlgorithm().create()
    log = Log()
    results, ok = alg.run({"INPUT": str(DATA / "topcon_ovingsfil.kof"), "OUTPUT": "memory:"},
                          QgsProcessingContext(), log)
    assert ok
    assert any(i.startswith("Comments in the file:") for i in log.infos)
    assert any("Projeksjon" in i for i in log.infos)
