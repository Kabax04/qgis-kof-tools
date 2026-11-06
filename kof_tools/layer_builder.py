"""Build QGIS objects from the parser result.

This is where KOF's N/E becomes QGIS x = E, y = N.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, List, Optional

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsLineString,
    QgsPolygon,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

from .duplicates import PointGroup
from .kof_lines import KofLine, arc_vertices
from .kof_parser import KofResult
from .kof_vectors import KofVector, ecef_to_geodetic

# QGIS 3.30 moved the geometry types to Qgis.WkbType. QGIS 4 (Qt6) only
# has the scoped names.
if Qgis.QGIS_VERSION_INT >= 33000:
    WkbType = Qgis.WkbType
else:
    from qgis.core import QgsWkbTypes

    WkbType = QgsWkbTypes.Type

POINT_WKB_TYPE = WkbType.PointZ
LINE_WKB_TYPE = WkbType.LineStringZ
POLYGON_WKB_TYPE = WkbType.PolygonZ

# QGIS 3.38 moved from QVariant to QMetaType for field types.
if Qgis.QGIS_VERSION_INT >= 33800:
    from qgis.PyQt.QtCore import QMetaType

    STRING, DOUBLE, INT = QMetaType.Type.QString, QMetaType.Type.Double, QMetaType.Type.Int
else:
    from qgis.PyQt.QtCore import QVariant

    STRING, DOUBLE, INT = QVariant.String, QVariant.Double, QVariant.Int


def point_fields() -> QgsFields:
    fields = QgsFields()
    fields.append(QgsField("name", STRING))
    fields.append(QgsField("code", STRING))
    fields.append(QgsField("N", DOUBLE))
    fields.append(QgsField("E", DOUBLE))
    fields.append(QgsField("H", DOUBLE))
    fields.append(QgsField("calc_code", INT))
    fields.append(QgsField("remark", STRING))
    fields.append(QgsField("line_no", INT))
    fields.append(QgsField("source_file", STRING))
    return fields


def point_features(result: KofResult, fields: QgsFields) -> Iterator[QgsFeature]:
    source = Path(result.source).name if result.source else None
    for p in result.points:
        feature = QgsFeature(fields)
        z = p.height if p.height is not None else float("nan")
        feature.setGeometry(QgsGeometry(QgsPoint(p.east, p.north, z)))
        feature.setAttributes([
            p.name, p.code, p.north, p.east, p.height, p.bk, p.remark, p.line_no, source
        ])
        yield feature


def group_fields() -> QgsFields:
    fields = QgsFields()
    fields.append(QgsField("group", INT))
    fields.append(QgsField("name", STRING))
    fields.append(QgsField("names", STRING))
    fields.append(QgsField("count", INT))
    fields.append(QgsField("N", DOUBLE))
    fields.append(QgsField("E", DOUBLE))
    fields.append(QgsField("H", DOUBLE))
    fields.append(QgsField("std_N", DOUBLE))
    fields.append(QgsField("std_E", DOUBLE))
    fields.append(QgsField("std_H", DOUBLE))
    fields.append(QgsField("max_dev", DOUBLE))
    fields.append(QgsField("source_file", STRING))
    return fields


def group_features(
    groups: List[PointGroup], fields: QgsFields, source: Optional[str] = None
) -> Iterator[QgsFeature]:
    """One feature per group, placed at the mean point. `name` is the first measurement."""
    source = Path(source).name if source else None
    for number, g in enumerate(groups, start=1):
        feature = QgsFeature(fields)
        z = g.height if g.height is not None else float("nan")
        feature.setGeometry(QgsGeometry(QgsPoint(g.east, g.north, z)))
        feature.setAttributes([
            number,
            g.members[0].name,
            ",".join(g.names),
            len(g.members),
            g.north,
            g.east,
            g.height,
            g.std_north,
            g.std_east,
            g.std_height,
            g.max_deviation,
            source,
        ])
        yield feature


def line_fields() -> QgsFields:
    """Fields shared by the line and polygon layers."""
    fields = QgsFields()
    fields.append(QgsField("name", STRING))
    fields.append(QgsField("type", STRING))
    fields.append(QgsField("code", STRING))
    fields.append(QgsField("count", INT))
    fields.append(QgsField("points", STRING))
    fields.append(QgsField("pi", INT))
    fields.append(QgsField("line_no", INT))
    fields.append(QgsField("source_file", STRING))
    return fields


def _vertex(p) -> QgsPoint:
    return QgsPoint(p.east, p.north, p.height if p.height is not None else float("nan"))


def line_geometry(line: KofLine) -> QgsGeometry:
    """LineStringZ through the points. Arcs (09 93) are drawn as a segmented
    circular arc that passes through every measured point, see arc_vertices.
    """
    if line.kind != "arc" or len(line.points) < 3:
        return QgsGeometry(QgsLineString([_vertex(p) for p in line.points]))
    return QgsGeometry(QgsLineString([
        QgsPoint(x, y, z if z is not None else float("nan")) for x, y, z in arc_vertices(line.points)
    ]))


def polygon_geometry(line: KofLine) -> QgsGeometry:
    vertices = [_vertex(p) for p in line.points]
    polygon = QgsPolygon()
    polygon.setExteriorRing(QgsLineString(vertices + [vertices[0]]))
    return QgsGeometry(polygon)


def line_features(
    lines: List[KofLine], fields: QgsFields, source: Optional[str] = None
) -> Iterator[QgsFeature]:
    source = Path(source).name if source else None
    for line in lines:
        feature = QgsFeature(fields)
        feature.setGeometry(polygon_geometry(line) if line.closed else line_geometry(line))
        names = [p.name for p in line.points]
        feature.setAttributes([
            f"{names[0]}–{names[-1]}",
            "polygon" if line.closed else line.kind,
            line.points[0].code,
            len(names),
            ",".join(names),
            line.pi,
            line.line_no,
            source,
        ])
        yield feature


# Geographic EUREF89/ETRS89. The vector coordinates are converted from
# geocentric to latitude, longitude and height on GRS80 before QGIS projects them.
VECTOR_SOURCE_CRS = "EPSG:4258"


def vector_fields() -> QgsFields:
    fields = QgsFields()
    for name, field_type in (
        ("name", STRING), ("from", STRING), ("to", STRING),
        ("dX", DOUBLE), ("dY", DOUBLE), ("dZ", DOUBLE), ("length", DOUBLE),
        ("sX", DOUBLE), ("sY", DOUBLE), ("sZ", DOUBLE),
        ("rXY", DOUBLE), ("rXZ", DOUBLE), ("rYZ", DOUBLE),
        ("date", STRING), ("time", STRING), ("info", STRING),
        ("line_no", INT), ("source_file", STRING),
    ):
        fields.append(QgsField(name, field_type))
    return fields


def vector_transform(crs: QgsCoordinateReferenceSystem) -> QgsCoordinateTransform:
    return QgsCoordinateTransform(
        QgsCoordinateReferenceSystem(VECTOR_SOURCE_CRS), crs, QgsProject.instance()
    )


def _projected(transform: QgsCoordinateTransform, x: float, y: float, z: float) -> QgsPoint:
    """Geocentric point -> point in the target CRS, with ellipsoidal height as Z."""
    lat, lon, height = ecef_to_geodetic(x, y, z)
    point = transform.transform(QgsPointXY(lon, lat))
    return QgsPoint(point.x(), point.y(), height)


def vector_features(
    vectors: List[KofVector],
    fields: QgsFields,
    transform: QgsCoordinateTransform,
    source: Optional[str] = None,
) -> Iterator[QgsFeature]:
    """One straight LineStringZ per GNSS vector, from the start station to start + vector."""
    source = Path(source).name if source else None
    for v in vectors:
        feature = QgsFeature(fields)
        start = _projected(transform, v.x, v.y, v.z)
        end = _projected(transform, *v.end)
        feature.setGeometry(QgsGeometry(QgsLineString([start, end])))
        feature.setAttributes([
            f"{v.from_name}–{v.to_name}", v.from_name, v.to_name,
            v.dx, v.dy, v.dz, v.length,
            v.sx, v.sy, v.sz, v.rxy, v.rxz, v.ryz,
            v.date, v.time, v.info, v.line_no, source,
        ])
        yield feature


def build_point_layer(
    result: KofResult, crs: QgsCoordinateReferenceSystem, name: str = "KOF points"
) -> QgsVectorLayer:
    """Create a temporary PointZ layer with all points."""
    layer = QgsVectorLayer(f"PointZ?crs={crs.authid()}", name, "memory")
    fields = point_fields()
    provider = layer.dataProvider()
    provider.addAttributes(list(fields))
    layer.updateFields()
    provider.addFeatures(list(point_features(result, layer.fields())))
    layer.updateExtents()
    return layer
