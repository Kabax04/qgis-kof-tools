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
    QgsProcessingParameterMultipleLayers,
    QgsVectorLayer,
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

# Parameters for the fields, and the field names the import uses.
NAME_FIELD = "NAME_FIELD"
CODE_FIELD = "CODE_FIELD"
HEIGHT_FIELD = "HEIGHT_FIELD"
BK_FIELD = "BK_FIELD"
REMARK_FIELD = "REMARK_FIELD"
VERTEX_NAMES_FIELD = "VERTEX_NAMES_FIELD"
FIELD_KEYS = (NAME_FIELD, CODE_FIELD, HEIGHT_FIELD, BK_FIELD, REMARK_FIELD, VERTEX_NAMES_FIELD)
DEFAULT_FIELDS = {
    NAME_FIELD: "name", CODE_FIELD: "code", HEIGHT_FIELD: "H", BK_FIELD: "calc_code",
    REMARK_FIELD: "remark", VERTEX_NAMES_FIELD: "points",
}


def qgis_version() -> str:
    """The QGIS version number without the release name.

    The name can have letters that Windows-1252 cannot store, such as the
    "ł" in "3.22.16-Białowieża", which would end up as "?" in the file.
    """
    return Qgis.version().split("-")[0]


def _plain(value):
    """The value, or None for NULL. Whole numbers stored as decimals lose the ".0"."""
    # QGIS 3 returns NULL as an invalid QVariant, QGIS 4 as None.
    if value is None or (hasattr(value, "isNull") and value.isNull()):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _value(feature, index):
    """The attribute, or None for NULL or a missing field (index -1)."""
    return None if index < 0 else _plain(feature.attribute(index))


def _text(value) -> str:
    return "" if value is None else str(value)


def _epsg(crs):
    return crs.postgisSrid() if crs.authid().upper().startswith("EPSG:") else None


def _point_key(name, vertex):
    """Identifies a point by name and position to the millimetre."""
    return name, round(vertex.y(), 3), round(vertex.x(), 3)


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
    NAME_FIELD = NAME_FIELD
    CODE_FIELD = CODE_FIELD
    HEIGHT_FIELD = HEIGHT_FIELD
    BK_FIELD = BK_FIELD
    REMARK_FIELD = REMARK_FIELD
    VERTEX_NAMES_FIELD = VERTEX_NAMES_FIELD
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
        for key, description in (
            (NAME_FIELD, tr("Point name field (empty = number the points)")),
            (CODE_FIELD, tr("Code field")),
            (HEIGHT_FIELD, tr("Height field (empty = Z of the geometry)")),
            (BK_FIELD, tr("Calculation code field")),
            (REMARK_FIELD, tr("Remark field")),
            (VERTEX_NAMES_FIELD, tr("Point names of lines and polygons (comma-separated field)")),
        ):
            self.addParameter(
                QgsProcessingParameterField(
                    key, description, defaultValue=DEFAULT_FIELDS[key], parentLayerParameterName=self.INPUT,
                    type=FIELD_ANY, optional=True,
                )
            )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.TARGET_CRS, tr("Coordinate reference system in the file (empty = the layer's)"),
                optional=True,
            )
        )
        self._add_output_parameters()

    def _add_output_parameters(self):
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
        crs = self._target_crs(parameters, context, source.sourceCrs(), feedback)
        self._report_transform(source.sourceCrs(), crs, feedback)

        names = {key: self.parameterAsString(parameters, key, context) for key in FIELD_KEYS}
        indexes = self._indexes(source.fields(), names, feedback)

        self._start()
        self._used = self._names_in(source, indexes)
        writer = self._writer(source.sourceName(), crs)
        request = QgsFeatureRequest().setDestinationCrs(crs, context.transformContext())
        total = source.featureCount()
        for current, feature in enumerate(source.getFeatures(request)):
            if feedback.isCanceled():
                break
            blocks = self._blocks(feature, indexes)
            if blocks is None:
                self._write_points(writer, feature, indexes)
            for block in blocks or ():
                self._write_block(writer, block)
            # featureCount() is -1 when the provider does not know it.
            if total > 0:
                feedback.setProgress(100 * (current + 1) / total)
        self._finish(writer, path, encoding, feedback)
        return {self.OUTPUT: path}

    # Shared by the export of one layer and of several layers.

    def _target_crs(self, parameters, context, layer_crs, feedback):
        """The selected CRS, or the layer's. Must be projected."""
        crs = self.parameterAsCrs(parameters, self.TARGET_CRS, context)
        if not crs.isValid():
            crs = layer_crs
        if not crs.isValid() or crs.isGeographic():
            raise QgsProcessingException(tr(
                "KOF files hold projected coordinates (north and east in metres), but {crs} is not projected. "
                "Select a projected coordinate reference system for the file, e.g. EUREF89 UTM 32 (EPSG:25832).",
                crs=crs.authid() or crs.description() or "?",
            ))
        epsg = _epsg(crs)
        if epsg is None or sosi_code_from_epsg(epsg) is None:
            feedback.pushWarning(tr(
                "{crs} has no SOSI coordinate system code. The 01 block is written without one, "
                "and some instruments may not recognise the coordinate reference system.",
                crs=crs.authid(),
            ))
        return crs

    @staticmethod
    def _report_transform(layer_crs, crs, feedback):
        if not layer_crs.isValid():
            feedback.pushWarning(tr(
                "The layer has no coordinate reference system. The coordinates are written unchanged "
                "and labelled as {crs}.",
                crs=crs.authid(),
            ))
        elif crs != layer_crs:
            feedback.pushInfo(tr(
                "Transforming from {source} to {target}",
                source=layer_crs.authid(), target=crs.authid(),
            ))

    @staticmethod
    def _indexes(fields, names, feedback=None):
        """Field index for each of FIELD_KEYS (-1 if not used), plus "type" from the import.

        With `feedback`, a named field the layer does not have is reported.
        """
        indexes = {}
        for key in FIELD_KEYS:
            name = names.get(key)
            index = fields.lookupField(name) if name else -1
            if name and index < 0 and feedback is not None:
                feedback.pushInfo(tr("The layer has no field {field}, not used", field=name))
            indexes[key] = index
        # Set by the import: "arc" for lines from 09 93.
        indexes["type"] = fields.lookupField("type")
        return indexes

    @staticmethod
    def _writer(job, crs):
        writer = KofWriter()
        writer.comment(f"Exported from QGIS {qgis_version()} with KOF Tools")
        writer.header(job=job, epsg=_epsg(crs))
        return writer

    def _start(self):
        self._number = 0
        self._used = set()
        self._holes = 0
        self._curves = 0

    def _finish(self, writer, path, encoding, feedback):
        for warning in writer.save(path, encoding):
            feedback.pushWarning(warning)
        if self._holes:
            feedback.pushWarning(tr("{count} polygon hole(s) were written as separate polygons", count=self._holes))
        if self._curves:
            feedback.pushWarning(tr(
                "{count} curved feature(s) were written as straight lines through points along the curve",
                count=self._curves,
            ))
        feedback.pushInfo(tr(
            "{count} points written to {path} ({encoding})",
            count=writer.points, path=path, encoding=encoding,
        ))
        if writer.lines or writer.polygons:
            feedback.pushInfo(tr(
                "{lines} lines and {polygons} polygons written as 09 blocks",
                lines=writer.lines, polygons=writer.polygons,
            ))

    @staticmethod
    def _names_in(source, indexes):
        """Point names the layer already has, so numbered points do not take them."""
        names = set()
        index = indexes[NAME_FIELD]
        if index >= 0:
            names.update(_text(_plain(v)).strip() for v in source.uniqueValues(index))
        index = indexes[VERTEX_NAMES_FIELD]
        if index >= 0:
            for value in source.uniqueValues(index):
                names.update(n.strip() for n in _text(_plain(value)).split(","))
        names.discard("")
        return names

    def _next_name(self) -> str:
        """The next number not used as a point name."""
        self._number += 1
        while str(self._number) in self._used:
            self._number += 1
        return str(self._number)

    def _write_points(self, writer, feature, indexes, skip=None) -> int:
        """One 05 record per point. A multipoint gives one per part, all with the same name.

        A point without a name (no name field, or NULL or empty) is numbered,
        and one without a height value takes Z from the geometry. No geometry
        gives one record without coordinates, which the writer reports.
        Points for which `skip(name, vertex)` is true are left out; returns
        how many.
        """
        name = _text(_value(feature, indexes[NAME_FIELD])).strip()
        code = _text(_value(feature, indexes[CODE_FIELD]))
        bk = _value(feature, indexes[BK_FIELD])
        remark = _text(_value(feature, indexes[REMARK_FIELD]))
        vertices = list(feature.geometry().vertices()) if feature.hasGeometry() else []
        skipped = 0
        for vertex in vertices or [None]:
            if skip is not None and vertex is not None and skip(name, vertex):
                skipped += 1
                continue
            height = _value(feature, indexes[HEIGHT_FIELD])
            if height is None and vertex is not None and vertex.is3D():
                height = vertex.z()
            writer.point(
                name or self._next_name(),
                code,
                vertex.y() if vertex is not None else None,
                vertex.x() if vertex is not None else None,
                height,
                bk,
                remark,
            )
        return skipped

    def _blocks(self, feature, indexes):
        """The 09 blocks of a line or polygon feature, or None for a point feature.

        Each block is (pi, closed, code, remark, [(name, vertex), ...]). The
        point names are taken from the vertex names field (as made by the
        import) when it has one name per vertex; otherwise the points are
        numbered. An arc from the import becomes 09 93 with its measured
        points only, not the vertices it was drawn with.
        """
        geometry = feature.geometry()
        if not feature.hasGeometry() or geometry.type() not in (LINE_GEOMETRY, POLYGON_GEOMETRY):
            return None
        self._curves += QgsWkbTypes.isCurvedType(geometry.wkbType())
        code = _text(_value(feature, indexes[CODE_FIELD]))
        remark = _text(_value(feature, indexes[REMARK_FIELD]))
        vertex_names = [n.strip() for n in _text(_value(feature, indexes[VERTEX_NAMES_FIELD])).split(",")]
        blocks = []
        for vertices, closed, hole in _rings(geometry):
            self._holes += hole
            names, pi = vertex_names, 91
            if len(names) != len(vertices):
                is_arc = not closed and _value(feature, indexes["type"]) == "arc"
                step = measured_arc_step(len(vertices), len(names)) if is_arc else None
                if step:
                    vertices, pi = vertices[::step], 93
                else:
                    names = [self._next_name() for _ in vertices]
            blocks.append((pi, closed, code, remark, list(zip(names, vertices))))
        return blocks

    @staticmethod
    def _write_block(writer, block):
        """A 09 block with one 05 record per vertex. Heights come from Z."""
        pi, closed, code, remark, points = block
        writer.start_line(pi)
        for i, (name, vertex) in enumerate(points):
            writer.point(
                name, code, vertex.y(), vertex.x(), vertex.z() if vertex.is3D() else None,
                remark=remark if i == 0 else "",
            )
        writer.end_line(closed)


class ExportKofLayersAlgorithm(ExportKofAlgorithm):
    """Several layers in one KOF file, e.g. the point, line and polygon layers of an import.

    The fields are found by the names the import uses. Points that are also
    vertices of an exported line or polygon (same name and position to the
    millimetre) are written only in its 09 block, so a whole import can be
    written back without points appearing twice.
    """

    LAYERS = "LAYERS"

    def name(self):
        return "exportkoflayers"

    def displayName(self):  # noqa: N802
        return tr("Export layers to one KOF file")

    def shortHelpString(self):  # noqa: N802
        return tr("HELP_EXPORT_LAYERS")

    def createInstance(self):  # noqa: N802
        return ExportKofLayersAlgorithm()

    def initAlgorithm(self, config=None):  # noqa: N802
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.LAYERS, tr("Layers to export (points, lines and polygons)"), VECTOR_ANY_GEOMETRY
            )
        )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.TARGET_CRS, tr("Coordinate reference system in the file (empty = the first layer's)"),
                optional=True,
            )
        )
        self._add_output_parameters()

    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802
        layers = [
            layer for layer in self.parameterAsLayerList(parameters, self.LAYERS, context)
            if isinstance(layer, QgsVectorLayer) and layer.isSpatial()
        ]
        if not layers:
            raise QgsProcessingException(tr("Select at least one point, line or polygon layer."))
        path = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
        encoding = ENCODINGS[self.parameterAsEnum(parameters, self.ENCODING, context)][1]
        crs = self._target_crs(parameters, context, layers[0].crs(), feedback)

        self._start()
        prepared = []
        for layer in layers:
            self._report_transform(layer.crs(), crs, feedback)
            indexes = self._indexes(layer.fields(), DEFAULT_FIELDS)
            self._used |= self._names_in(layer, indexes)
            prepared.append((layer, indexes))

        # Read all layers first, so the points of lines and polygons are known.
        request = QgsFeatureRequest().setDestinationCrs(crs, context.transformContext())
        blocks, points = [], []
        for layer, indexes in prepared:
            for feature in layer.getFeatures(request):
                if feedback.isCanceled():
                    return {self.OUTPUT: None}
                feature_blocks = self._blocks(feature, indexes)
                if feature_blocks is None:
                    points.append((feature, indexes))
                else:
                    blocks.extend(feature_blocks)
        in_blocks = {_point_key(name, vertex) for *_, block_points in blocks for name, vertex in block_points}

        writer = self._writer(", ".join(layer.name() for layer in layers), crs)
        skipped = 0
        for feature, indexes in points:
            skipped += self._write_points(
                writer, feature, indexes, skip=lambda name, vertex: _point_key(name, vertex) in in_blocks
            )
        for block in blocks:
            self._write_block(writer, block)
        if skipped:
            feedback.pushInfo(tr(
                "{count} points that are also in lines or polygons were written in their 09 blocks only",
                count=skipped,
            ))
        self._finish(writer, path, encoding, feedback)
        return {self.OUTPUT: path}
