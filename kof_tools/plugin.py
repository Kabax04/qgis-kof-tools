from pathlib import Path

from qgis.core import Qgis, QgsApplication, QgsVectorLayer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .drop_handler import ALGORITHM_ID, KofDropHandler
from .i18n import tr
from .processing.provider import KofProvider

MENU = "&KOF Tools"
ICON = str(Path(__file__).parent / "icon.svg")
EXPORT_ALGORITHM_ID = "kof:exportkof"
EXPORT_LAYERS_ALGORITHM_ID = "kof:exportkoflayers"
# The plugin's name before 1.2.0. It registers a provider with the same id,
# so only one of the two can provide the KOF algorithms.
OLD_PLUGIN = "kof_import"


class KofToolsPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.export_action = None
        self.export_layers_action = None
        self.provider = None
        self.drop_handler = None

    def initProcessing(self):  # noqa: N802
        self.provider = KofProvider()
        if not QgsApplication.processingRegistry().addProvider(self.provider):
            # Another provider has the id, most likely the old KOF Import plugin.
            self.provider = None

    def initGui(self):  # noqa: N802
        self.initProcessing()
        self.action = QAction(QIcon(ICON), tr("Import KOF file…"), self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToVectorMenu(MENU, self.action)
        self.iface.addToolBarIcon(self.action)
        self.export_action = QAction(tr("Export to KOF…"), self.iface.mainWindow())
        self.export_action.triggered.connect(self.run_export)
        self.iface.addPluginToVectorMenu(MENU, self.export_action)
        self.export_layers_action = QAction(tr("Export layers to KOF…"), self.iface.mainWindow())
        self.export_layers_action.triggered.connect(self.run_export_layers)
        self.iface.addPluginToVectorMenu(MENU, self.export_layers_action)
        self.drop_handler = KofDropHandler(self.iface)
        self.iface.registerCustomDropHandler(self.drop_handler)
        self._warn_old_plugin()

    def _warn_old_plugin(self):
        try:
            from qgis.utils import active_plugins
        except ImportError:
            return
        if OLD_PLUGIN in active_plugins or self.provider is None:
            self.iface.messageBar().pushMessage(
                "KOF Tools",
                tr("The old KOF Import plugin is still installed, and the two cannot run together. "
                   "Uninstall KOF Import in Plugins → Manage and Install Plugins, then restart QGIS."),
                level=Qgis.MessageLevel.Warning,
                duration=0,
            )

    def unload(self):
        if self.action:
            self.iface.removePluginVectorMenu(MENU, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None
        if self.export_action:
            self.iface.removePluginVectorMenu(MENU, self.export_action)
            self.export_action = None
        if self.export_layers_action:
            self.iface.removePluginVectorMenu(MENU, self.export_layers_action)
            self.export_layers_action = None
        if self.drop_handler:
            self.iface.unregisterCustomDropHandler(self.drop_handler)
            self.drop_handler = None
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

    def run(self):
        import processing

        processing.execAlgorithmDialog(ALGORITHM_ID)

    def run_export(self):
        import processing

        # Start with the active layer when it has geometry.
        layer = self.iface.activeLayer()
        params = {}
        if isinstance(layer, QgsVectorLayer) and layer.isSpatial():
            params["INPUT"] = layer
        processing.execAlgorithmDialog(EXPORT_ALGORITHM_ID, params)

    def run_export_layers(self):
        import processing

        # Start with the selected layers in the layers panel that have geometry.
        layers = [
            layer for layer in self.iface.layerTreeView().selectedLayers()
            if isinstance(layer, QgsVectorLayer) and layer.isSpatial()
        ]
        params = {"LAYERS": layers} if layers else {}
        processing.execAlgorithmDialog(EXPORT_LAYERS_ALGORITHM_ID, params)
