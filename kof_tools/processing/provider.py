from pathlib import Path

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .export_kof_algorithm import ExportKofAlgorithm, ExportKofLayersAlgorithm
from .import_kof_algorithm import ImportKofAlgorithm

ICON = str(Path(__file__).parent.parent / "icon.svg")


class KofProvider(QgsProcessingProvider):
    def id(self):
        return "kof"

    def name(self):
        return "KOF Tools"

    def icon(self):
        return QIcon(ICON)

    def loadAlgorithms(self):  # noqa: N802
        self.addAlgorithm(ImportKofAlgorithm())
        self.addAlgorithm(ExportKofAlgorithm())
        self.addAlgorithm(ExportKofLayersAlgorithm())
