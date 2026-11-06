from qgis.core import (
    Qgis,
    QgsFeatureRequest,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFileDestination,
    QgsWkbTypes,
)

from ..crs_detect import sosi_code_from_epsg
from ..i18n import tr
from ..kof_lines import measured_arc_step
from ..kof_writer import KofWriter

# QGIS 3.36 moved these enums to Qgis. QGIS 4 (Qt6) only has the scoped names.
if Qgis.QGIS_VERSION_INT >= 33600:
    VECTOR_ANY_GEOMETRY = Qgis.ProcessingSourceType.VectorAnyGeometry
    FIELD_ANY = Qgis.ProcessingFieldParameterDataType.Any
else:
    VECTOR_ANY_GEOMETRY = QgsProcessing.SourceType.TypeVectorAnyGeometry
    FIELD_ANY = QgsProcessingParameterField.DataType.Any

# QGIS 3.30 moved geometry types to Qgis.
if Qgis.QGIS_VERSION_INT >= 33000:
    LINE_GEOMETRY, POLYGON_GEOMETRY = Qgis.GeometryType.Line, Qgis.GeometryType.Polygon
else:
    LINE_GEOMETRY, POLYGON_GEOMETRY = QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry

# (label, Python codec) for the ENCODING parameter.
ENCODINGS = (("Windows-1252", "cp1252"), ("UTF-8", "utf-8"))


def _value(feature, index):
    """The attribute, or None for NULL. Whole numbers stored as decimals lose the ".0"."""
    if index < 0:
        return None
    value = feature.attribute(index)
    # QGIS 3 returns NULL as an invalid QVariant, QGIS 4 as None.
    if value is None or (hasattr(value, "isNull") and value.isNull()):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _text(value) -> str:
    return "" if value is None else str(value)


def _rings(geometry):
    """(vertices, closed, hole) for each line or polygon ring in the geometry.

    Curves are segmented. A polygon ring loses its closing vertex, since
    09 96 closes it. Holes become rings of their own.
    """
    polygon = geometry.type() == POLYGON_GEOMETRY
    for part in geometry.asGeometryCollection():
        if QgsWkbTypes.isCurvedType(part.wkbType()):
            part = QgsGeometry(part.constGet().segmentize())
        if not polygon:
            yield list(part.vertices()), False, False
            continue
        surface = part.constGet()
        yield list(surface.exteriorRing().vertices())[:-1], True, False
        for i in range(surface.numInteriorRings()):
            yield list(surface.interiorRing(i).vertices())[:-1], True, True


class ExportKofAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    NAME_FIELD = "NAME_FIELD"
    CODE_FIELD = "CODE_FIELD"
    HEIGHT_FIELD = "HEIGHT_FIELD"
    BK_FIELD = "BK_FIELD"
    REMARK_FIELD = "REMARK_FIELD"
    VERTEX_NAMES_FIELD = "VERTEX_NAMES_FIELD"
    TARGET_CRS = "TARGET_CRS"
    ENCODING = "ENCODING"
    OUTPUT = "OUTPUT"

    def name(self):
        return "exportkof"

    def displayName(self):  # noqa: N802
        return tr("Export to KOF file")

    def shortHelpString(self):  # noqa: N802
        return tr("HELP_EXPORT")

    def createInstance(self):  # noqa: N802
        return ExportKofAlgorithm()

    def initAlgorithm(self, config=None):  # noqa: N802
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT, tr("Layer to export (points, lines or polygons)"), [VECTOR_ANY_GEOMETRY]
            )
        )
        # The defaults match the fields of layers made by the import.
        for key, description, default in (
            (self.NAME_FIELD, tr("Point name field (empty = number the points)"), "name"),
            (self.CODE_FIELD, tr("Code field"), "code"),
            (self.HEIGHT_FIELD, tr("Height field (empty = Z of the geometry)"), "H"),
            (self.BK_FIELD, tr("Calculation code field"), "calc_code"),
            (self.REMARK_FIELD, tr("Remark field"), "remark"),
            (self.VERTEX_NAMES_FIELD, tr("Point names of lines and polygons (comma-separated field)"), "points"),
        ):
            self.addParameter(
                QgsProcessingParameterField(
                    key, description, defaultValue=default, parentLayerParameterName=self.INPUT,
                    type=FIELD_ANY, optional=True,
                )
            )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.TARGET_CRS, tr("Coordinate reference system in the file (empty = the layer's)"),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.ENCODING, tr("Encoding"), options=[label for label, _ in ENCODINGS], defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterFileDestination(self.OUTPUT, tr("KOF file"), tr("KOF files (*.kof)"))
        )

    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))
        path = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
        encoding = ENCODINGS[self.parameterAsEnum(parameters, self.ENCODING, context)][1]

        crs = self.parameterAsCrs(parameters, self.TARGET_CRS, context)
        if not crs.isValid():
            crs = source.sourceCrs()
        if not crs.isValid() or crs.isGeographic():
            raise QgsProcessingException(tr(
                "KOF files hold projected coordinates (north and east in metres), but {crs} is not projected. "
                "Select a projected coordinate reference system for the file, e.g. EUREF89 UTM 32 (EPSG:25832).",
                crs=crs.authid() or crs.description() or "?",
            ))
        epsg = crs.postgisSrid() if crs.authid().upper().startswith("EPSG:") else None
        if epsg is None or sosi_code_from_epsg(epsg) is None:
            feedback.pushWarning(tr(
                "{crs} has no SOSI coordinate system code. The 01 block is written without one, "
                "and some instruments may not recognise the coordinate reference system.",
                crs=crs.authid(),
            ))
        if not source.sourceCrs().isValid():
            feedback.pushWarning(tr(
                "The layer has no coordinate reference system. The coordinates are written unchanged "
                "and labelled as {crs}.",
                crs=crs.authid(),
            ))
        elif crs != source.sourceCrs():
            feedback.pushInfo(tr(
                "Transforming from {source} to {target}",
                source=source.sourceCrs().authid(), target=crs.authid(),
            ))

        fields = source.fields()
        indexes = {}
        for key in (
            self.NAME_FIELD, self.CODE_FIELD, self.HEIGHT_FIELD, self.BK_FIELD, self.REMARK_FIELD,
            self.VERTEX_NAMES_FIELD,
        ):
            name = self.parameterAsString(parameters, key, context)
            index = fields.lookupField(name) if name else -1
            if name and index < 0:
                feedback.pushInfo(tr("The layer has no field {field}, not used", field=name))
            indexes[key] = index
        # Set by the import: "arc" for lines from 09 93.
        indexes["type"] = fields.lookupField("type")

        writer = KofWriter()
        writer.comment(f"Exported from QGIS {Qgis.version()} with KOF Tools")
        writer.header(job=source.sourceName(), epsg=epsg)

        request = QgsFeatureRequest().setDestinationCrs(crs, context.transformContext())
        total = source.featureCount()
        self._number = 0
        holes = 0
        for current, feature in enumerate(source.getFeatures(request)):
            if feedback.isCanceled():
                break
            geometry = feature.geometry()
            if feature.hasGeometry() and geometry.type() in (LINE_GEOMETRY, POLYGON_GEOMETRY):
                for vertices, closed, hole in _rings(geometry):
                    holes += hole
                    self._write_line(writer, feature, indexes, vertices, closed)
            else:
                self._write_points(writer, feature, indexes)
            if total:
                feedback.setProgress(100 * (current + 1) / total)

        for warning in writer.save(path, encoding):
            feedback.pushWarning(warning)
        if holes:
            feedback.pushWarning(tr("{count} polygon hole(s) were written as separate polygons", count=holes))
        feedback.pushInfo(tr(
            "{count} points written to {path} ({encoding})",
            count=writer.points, path=path, encoding=encoding,
        ))
        if writer.lines or writer.polygons:
            feedback.pushInfo(tr(
                "{lines} lines and {polygons} polygons written as 09 blocks",
                lines=writer.lines, polygons=writer.polygons,
            ))
        return {self.OUTPUT: path}

    def _next_name(self) -> str:
        self._number += 1
        return str(self._number)

    def _write_points(self, writer, feature, indexes):
        """One 05 record per point. A multipoint gives one per part, all with the same name.

        No geometry gives one record without coordinates, which the writer reports.
        """
        name = _text(_value(feature, indexes[self.NAME_FIELD]))
        code = _text(_value(feature, indexes[self.CODE_FIELD]))
        bk = _value(feature, indexes[self.BK_FIELD])
        remark = _text(_value(feature, indexes[self.REMARK_FIELD]))
        vertices = list(feature.geometry().vertices()) if feature.hasGeometry() else []
        for vertex in vertices or [None]:
            number = self._next_name()
            if indexes[self.HEIGHT_FIELD] >= 0:
                height = _value(feature, indexes[self.HEIGHT_FIELD])
            elif vertex is not None and vertex.is3D():
                height = vertex.z()
            else:
                height = None
            writer.point(
                name if indexes[self.NAME_FIELD] >= 0 else number,
                code,
                vertex.y() if vertex is not None else None,
                vertex.x() if vertex is not None else None,
                height,
                bk,
                remark,
            )

    def _write_line(self, writer, feature, indexes, vertices, closed):
        """A 09 block with one 05 record per vertex. Heights come from Z.

        The point names are taken from the vertex names field (as made by the
        import) when it has one name per vertex; otherwise the points are numbered.
        An arc from the import is written back as 09 93 with its measured
        points only, not the vertices it was drawn with.
        """
        code = _text(_value(feature, indexes[self.CODE_FIELD]))
        remark = _text(_value(feature, indexes[self.REMARK_FIELD]))
        names = [n.strip() for n in _text(_value(feature, indexes[self.VERTEX_NAMES_FIELD])).split(",")]
        pi = 91
        if len(names) != len(vertices):
            is_arc = not closed and _value(feature, indexes["type"]) == "arc"
            step = measured_arc_step(len(vertices), len(names)) if is_arc else None
            if step:
                vertices, pi = vertices[::step], 93
            else:
                names = [self._next_name() for _ in vertices]
        writer.start_line(pi)
        for i, (name, vertex) in enumerate(zip(names, vertices)):
            writer.point(
                name, code, vertex.y(), vertex.x(), vertex.z() if vertex.is3D() else None,
                remark=remark if i == 0 else "",
            )
        writer.end_line(closed)
