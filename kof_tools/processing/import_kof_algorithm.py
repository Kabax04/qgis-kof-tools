from pathlib import Path

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsFeatureSink,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterDistance,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFile,
    QgsProcessingParameterNumber,
)

from ..crs_detect import axes_look_swapped, crs_from_sosi_code, detect_crs, detect_vertical_crs
from ..duplicates import DEFAULT_HEIGHT_TOLERANCE, DEFAULT_TOLERANCE, find_near_misses, group_points
from ..i18n import tr
from ..kof_parser import parse_file
from ..kof_vectors import ecef_to_geodetic, utm_epsg
from ..layer_builder import (
    LINE_WKB_TYPE,
    POINT_WKB_TYPE,
    POLYGON_WKB_TYPE,
    group_features,
    group_fields,
    line_features,
    line_fields,
    point_features,
    point_fields,
    vector_features,
    vector_fields,
    vector_transform,
)
from ..layer_style import (
    StylePostProcessor,
    style_groups,
    style_lines,
    style_points,
    style_polygons,
    style_vectors,
)

# QGIS 3.36 moved these enums to Qgis. QGIS 4 (Qt6) only has the scoped names.
if Qgis.QGIS_VERSION_INT >= 33600:
    SourceType = Qgis.ProcessingSourceType
    NumberType = Qgis.ProcessingNumberParameterType
    VECTOR_POINT, VECTOR_LINE, VECTOR_POLYGON = (
        SourceType.VectorPoint, SourceType.VectorLine, SourceType.VectorPolygon
    )
else:
    SourceType = QgsProcessing.SourceType
    NumberType = QgsProcessingParameterNumber.Type
    VECTOR_POINT, VECTOR_LINE, VECTOR_POLYGON = (
        SourceType.TypeVectorPoint, SourceType.TypeVectorLine, SourceType.TypeVectorPolygon
    )

FAST_INSERT = QgsFeatureSink.Flag.FastInsert


class ImportKofAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    CRS = "CRS"
    OUTPUT = "OUTPUT"
    TOLERANCE = "TOLERANCE"
    HEIGHT_TOLERANCE = "HEIGHT_TOLERANCE"
    INCLUDE_SINGLES = "INCLUDE_SINGLES"
    OUTPUT_GROUPS = "OUTPUT_GROUPS"
    OUTPUT_LINES = "OUTPUT_LINES"
    OUTPUT_POLYGONS = "OUTPUT_POLYGONS"
    OUTPUT_VECTORS = "OUTPUT_VECTORS"

    def name(self):
        return "importkof"

    def displayName(self):  # noqa: N802
        return tr("Import KOF file")

    def shortHelpString(self):  # noqa: N802
        return tr("HELP")

    def createInstance(self):  # noqa: N802
        return ImportKofAlgorithm()

    def initAlgorithm(self, config=None):  # noqa: N802
        self.addParameter(
            QgsProcessingParameterFile(self.INPUT, tr("KOF file"), extension="kof")
        )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.CRS, tr("Coordinate reference system (empty = from file)"), optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT, tr("KOF points"), VECTOR_POINT
            )
        )
        self.addParameter(
            QgsProcessingParameterDistance(
                self.TOLERANCE,
                tr("Tolerance for repeated measurements (horizontal)"),
                defaultValue=DEFAULT_TOLERANCE,
                parentParameterName=self.CRS,
                minValue=0.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.HEIGHT_TOLERANCE,
                tr("Height tolerance (empty = no limit)"),
                type=NumberType.Double,
                defaultValue=DEFAULT_HEIGHT_TOLERANCE,
                optional=True,
                minValue=0.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.INCLUDE_SINGLES,
                tr("Include points measured only once in the mean layer"),
                defaultValue=True,
            )
        )
        for key, description, layer_type in (
            (self.OUTPUT_GROUPS, tr("Mean of repeated measurements"), VECTOR_POINT),
            (self.OUTPUT_LINES, tr("Lines (09 blocks)"), VECTOR_LINE),
            (self.OUTPUT_POLYGONS, tr("Polygons (closed with 09 96)"), VECTOR_POLYGON),
            (self.OUTPUT_VECTORS, tr("GNSS vectors (42/43 records)"), VECTOR_LINE),
        ):
            self.addParameter(
                QgsProcessingParameterFeatureSink(
                    key, description, layer_type, optional=True, createByDefault=True
                )
            )

    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802
        path = self.parameterAsFile(parameters, self.INPUT, context)
        result = parse_file(path)
        for warning in result.warnings:
            feedback.pushWarning(warning)
        self._log_header(feedback, result)

        crs = self._crs(parameters, context, feedback, result)
        epsg = crs.postgisSrid()
        if axes_look_swapped(result.points, epsg):
            result.swap_axes()
            feedback.pushWarning(tr(
                "The coordinates look like east before north for {crs}. "
                "North and east have been swapped.",
                crs=crs.authid(),
            ))

        fields = point_fields()
        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields, POINT_WKB_TYPE, crs
        )
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))
        for feature in point_features(result, fields):
            if feedback.isCanceled():
                break
            sink.addFeature(feature, FAST_INSERT)

        outputs = {self.OUTPUT: dest_id}
        stem = Path(path).stem
        # A file with only GNSS vectors gives no points, so the empty point and
        # mean layers are not added to the project.
        vectors_only = bool(result.vectors) and not result.points
        if vectors_only:
            self._skip_loading(context, dest_id)
        else:
            self._configure_output(context, dest_id, stem, style_points)
        feedback.pushInfo(tr(
            "{points} points imported, {warnings} warnings, {disabled} lines disabled (encoding {encoding})",
            points=len(result.points), warnings=len(result.warnings),
            disabled=result.disabled, encoding=result.encoding,
        ))

        groups_id = self._write_groups(parameters, context, feedback, result, crs)
        if groups_id is not None:
            outputs[self.OUTPUT_GROUPS] = groups_id
            if vectors_only:
                self._skip_loading(context, groups_id)
            else:
                mean = tr("mean")
                self._configure_output(context, groups_id, f"{stem} ({mean})", style_groups)

        # Line and polygon layers are only created when the file has any, so
        # files with points only do not add empty layers to the project.
        lines = [line for line in result.lines if not line.closed]
        polygons = [line for line in result.lines if line.closed]
        feedback.pushInfo(tr(
            "{lines} lines and {polygons} polygons from 09 blocks",
            lines=len(lines), polygons=len(polygons),
        ))
        for key, items, wkb_type, suffix, style in (
            (self.OUTPUT_LINES, lines, LINE_WKB_TYPE, tr("lines"), style_lines),
            (self.OUTPUT_POLYGONS, polygons, POLYGON_WKB_TYPE, tr("polygons"), style_polygons),
        ):
            if not items:
                continue
            fields = line_fields()
            sink, dest = self.parameterAsSink(parameters, key, context, fields, wkb_type, crs)
            if sink is None:
                continue
            for feature in line_features(items, fields, result.source):
                sink.addFeature(feature, FAST_INSERT)
            outputs[key] = dest
            self._configure_output(context, dest, f"{stem} ({suffix})", style)

        vectors_id = self._write_vectors(parameters, context, feedback, result, crs)
        if vectors_id is not None:
            outputs[self.OUTPUT_VECTORS] = vectors_id
            suffix = tr("GNSS vectors")
            self._configure_output(context, vectors_id, f"{stem} ({suffix})", style_vectors)
        return outputs

    def _write_vectors(self, parameters, context, feedback, result, crs):
        """Line layer with the GNSS vectors. Only created when the file has any."""
        if not result.vectors:
            return None
        fields = vector_fields()
        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT_VECTORS, context, fields, LINE_WKB_TYPE, crs
        )
        if sink is None:
            return None
        transform = vector_transform(crs, context.transformContext())
        for feature in vector_features(result.vectors, fields, transform, result.source):
            sink.addFeature(feature, FAST_INSERT)
        feedback.pushInfo(tr(
            "{count} GNSS vectors imported. The start stations are placed from the coordinates "
            "in the 42 records, read as EUREF89; Z is the ellipsoidal height.",
            count=len(result.vectors),
        ))
        return dest_id

    # At most this many 00 comments are listed in the log.
    MAX_COMMENTS = 20

    def _log_header(self, feedback, result):
        """The 01 header and the 00 comments, which do not end up in any layer."""
        header = result.header
        if header is not None:
            feedback.pushInfo(tr(
                "File header (01): job {job}, date {date}, municipality {municipality}, observer {observer}",
                job=header.job or "-", date=header.date or "-",
                municipality=header.municipality if header.municipality is not None else "-",
                observer=header.observer or "-",
            ))
        elif result.headers:
            feedback.pushInfo(tr("File header (01): {text}", text=result.headers[-1]))
        if result.comments:
            feedback.pushInfo(tr("Comments in the file:"))
            for comment in result.comments[:self.MAX_COMMENTS]:
                feedback.pushInfo(f"  {comment}")
            if len(result.comments) > self.MAX_COMMENTS:
                feedback.pushInfo(tr("  … and {count} more", count=len(result.comments) - self.MAX_COMMENTS))

    @staticmethod
    def _skip_loading(context, dest_id):
        layers = context.layersToLoadOnCompletion()
        layers.pop(dest_id, None)
        context.setLayersToLoadOnCompletion(layers)

    def _crs(self, parameters, context, feedback, result):
        crs = self.parameterAsCrs(parameters, self.CRS, context)
        if crs.isValid():
            feedback.pushInfo(tr("Using selected coordinate reference system {crs}", crs=crs.authid()))
        else:
            sosi_code = result.header.crs_code if result.header else None
            if sosi_code is not None and crs_from_sosi_code(sosi_code) is None:
                feedback.pushWarning(tr(
                    "Unknown coordinate system code {code} in the 01 block, ignored", code=sosi_code
                ))
            epsg = detect_crs(result.metadata, sosi_code)
            if epsg is None and result.vectors and not result.points:
                epsg = vector_crs(result)
                crs = QgsCoordinateReferenceSystem(f"EPSG:{epsg}")
                feedback.pushInfo(tr(
                    "No coordinate reference system in the file. The GNSS vectors are shown in "
                    "the UTM zone of the first station: {crs}",
                    crs=crs.authid(),
                ))
                return crs
            if epsg is None:
                raise QgsProcessingException(
                    tr("No coordinate reference system found in the file. Select one manually.")
                )
            crs = QgsCoordinateReferenceSystem(f"EPSG:{epsg}")
            feedback.pushInfo(tr("Coordinate reference system from file: {crs}", crs=crs.authid()))
        if detect_vertical_crs(result.metadata):
            feedback.pushInfo(tr("Heights are in NN2000"))
        return crs

    def _write_groups(self, parameters, context, feedback, result, crs):
        tolerance = self.parameterAsDouble(parameters, self.TOLERANCE, context)
        # Left out, the default applies; set to nothing (None), there is no limit.
        height_tolerance = None
        if parameters.get(self.HEIGHT_TOLERANCE, DEFAULT_HEIGHT_TOLERANCE) is not None:
            height_tolerance = self.parameterAsDouble(
                parameters, self.HEIGHT_TOLERANCE, context
            )
        include_singles = self.parameterAsBoolean(parameters, self.INCLUDE_SINGLES, context)

        groups = group_points(result.points, tolerance, height_tolerance, feedback.isCanceled)
        repeated = [g for g in groups if len(g.members) > 1]
        feedback.pushInfo(tr(
            "{count} groups of repeated measurements (tolerance {tolerance} m, height {height})",
            count=len(repeated), tolerance=tolerance,
            height=tr("no limit") if height_tolerance is None else f"{height_tolerance} m",
        ))
        for g in repeated:
            feedback.pushInfo(tr(
                "  {names}: largest deviation {deviation:.1f} mm",
                names=",".join(g.names), deviation=g.max_deviation * 1000,
            ))
        misses = find_near_misses(
            result.points, tolerance, height_tolerance, groups=groups, is_canceled=feedback.isCanceled
        )
        for miss in misses:
            feedback.pushWarning(tr(
                "{a} and {b} are {distance:.3f} m apart, just outside the tolerance. "
                "Check whether they are the same point.",
                a=miss.a.name, b=miss.b.name, distance=miss.distance,
            ))

        fields = group_fields()
        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT_GROUPS, context, fields, POINT_WKB_TYPE, crs
        )
        if sink is None:
            return None
        for feature in group_features(groups if include_singles else repeated, fields, result.source):
            sink.addFeature(feature, FAST_INSERT)
        return dest_id

    @staticmethod
    def _configure_output(context, dest_id, name, style_function):
        if context.willLoadLayerOnCompletion(dest_id):
            details = context.layerToLoadOnCompletionDetails(dest_id)
            details.name = name
            details.setPostProcessor(StylePostProcessor.create(style_function))


def vector_crs(result) -> int:
    """EPSG code of the UTM zone of the first GNSS vector's start station."""
    v = result.vectors[0]
    latitude, longitude, _ = ecef_to_geodetic(v.x, v.y, v.z)
    return utm_epsg(latitude, longitude)
