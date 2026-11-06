"""Default style and labels for the layers from the KOF import."""

from qgis.core import (
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProcessingLayerPostProcessorInterface,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtGui import QColor


def _labeling(field: str) -> QgsVectorLayerSimpleLabeling:
    text_format = QgsTextFormat()
    text_format.setSize(8)
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.8)
    buffer.setColor(QColor("white"))
    text_format.setBuffer(buffer)

    settings = QgsPalLayerSettings()
    settings.fieldName = field
    settings.setFormat(text_format)
    settings.dist = 1.0
    return QgsVectorLayerSimpleLabeling(settings)


def style_points(layer) -> None:
    """Small dark circles labelled with the point name."""
    symbol = QgsMarkerSymbol.createSimple(
        {"name": "circle", "size": "1.8", "color": "40,40,40", "outline_color": "white"}
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setLabeling(_labeling("name"))
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()


def style_groups(layer) -> None:
    """Red crosses labelled with the names of all measurements in the group."""
    symbol = QgsMarkerSymbol.createSimple(
        {"name": "cross2", "size": "3", "color": "200,30,30", "outline_width": "0.4"}
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setLabeling(_labeling("names"))
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()


def style_lines(layer) -> None:
    """Blue lines."""
    symbol = QgsLineSymbol.createSimple({"line_color": "30,90,200", "line_width": "0.5"})
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.triggerRepaint()


def style_vectors(layer) -> None:
    """Green lines labelled with from–to."""
    symbol = QgsLineSymbol.createSimple({"line_color": "20,140,70", "line_width": "0.5"})
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setLabeling(_labeling("name"))
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()


def style_polygons(layer) -> None:
    """Semi-transparent blue fill with outline."""
    symbol = QgsFillSymbol.createSimple(
        {"color": "30,90,200,60", "outline_color": "30,90,200", "outline_width": "0.4"}
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.triggerRepaint()


class StylePostProcessor(QgsProcessingLayerPostProcessorInterface):
    """Styles a layer when Processing loads it into the project."""

    # Processing does not take ownership of the Python object, so we keep it
    # alive until it has been used. Each instance is used once.
    _instances = []

    def __init__(self, style_function):
        super().__init__()
        self.style_function = style_function

    def postProcessLayer(self, layer, context, feedback):  # noqa: N802
        try:
            self.style_function(layer)
        finally:
            # Released after the call; Processing does not use it again.
            if self in StylePostProcessor._instances:
                StylePostProcessor._instances.remove(self)

    @classmethod
    def create(cls, style_function):
        instance = cls(style_function)
        cls._instances.append(instance)
        return instance
