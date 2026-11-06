"""Import .kof files dropped on the map canvas or the layers panel."""

from pathlib import Path

from qgis.core import Qgis, QgsProcessingException, QgsProcessingFeedback
from qgis.gui import QgsCustomDropHandler

from .crs_detect import detect_crs
from .i18n import tr
from .kof_parser import parse_file

ALGORITHM_ID = "kof:importkof"


class _CollectingFeedback(QgsProcessingFeedback):
    def __init__(self):
        super().__init__()
        self.warnings = []

    def pushWarning(self, warning):  # noqa: N802
        self.warnings.append(warning)
        super().pushWarning(warning)


class KofDropHandler(QgsCustomDropHandler):
    def __init__(self, iface):
        super().__init__()
        self.iface = iface

    def handleFileDrop(self, file):  # noqa: N802
        path = Path(file)
        if path.suffix.lower() != ".kof":
            return False
        import processing

        if not _has_crs(path):
            # Let the user choose a coordinate reference system in the dialog.
            processing.execAlgorithmDialog(ALGORITHM_ID, {"INPUT": str(path)})
            return True

        params = {
            "INPUT": str(path),
            "OUTPUT": "TEMPORARY_OUTPUT",
            "OUTPUT_GROUPS": "TEMPORARY_OUTPUT",
            # Only created if the file has lines or polygons.
            "OUTPUT_LINES": "TEMPORARY_OUTPUT",
            "OUTPUT_POLYGONS": "TEMPORARY_OUTPUT",
            "OUTPUT_VECTORS": "TEMPORARY_OUTPUT",
        }
        feedback = _CollectingFeedback()
        try:
            processing.runAndLoadResults(ALGORITHM_ID, params, feedback=feedback)
        except QgsProcessingException as error:
            self.iface.messageBar().pushMessage(
                "KOF Tools", tr("{file} could not be imported.", file=path.name), str(error),
                level=Qgis.MessageLevel.Critical,
            )
            return True

        bar = self.iface.messageBar()
        count = len(feedback.warnings)
        if count == 1:
            text = tr("{file} imported with 1 warning.", file=path.name)
        else:
            text = tr("{file} imported with {count} warnings.", file=path.name, count=count)
        if count:
            bar.pushMessage("KOF Tools", text, "\n".join(feedback.warnings), level=Qgis.MessageLevel.Warning)
        else:
            bar.pushMessage("KOF Tools", tr("{file} imported.", file=path.name), level=Qgis.MessageLevel.Success)
        return True


def _has_crs(path):
    """Whether the import algorithm can find a coordinate reference system in the file."""
    try:
        result = parse_file(path)
    except OSError:
        # The algorithm reports the error.
        return True
    if result.vectors and not result.points:
        # The algorithm picks a UTM zone from the vectors.
        return True
    sosi_code = result.header.crs_code if result.header else None
    return detect_crs(result.metadata, sosi_code) is not None
