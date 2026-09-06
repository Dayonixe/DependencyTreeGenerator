"""Interactive Qt scene: movable files, directed edges, zoom and image export."""

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal, QSignalBlocker
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject, QGraphicsPathItem, QGraphicsScene, QGraphicsView

from .data import Edge, Node, ProjectGraph, layered_layout


COLORS = {"internal": "#158578", "external": "#b57a22", "unknown": "#c65e64"}
BACKGROUND = "#f5f7fa"


class FileItem(QGraphicsObject):
    WIDTH, HEIGHT = 240, 68

    def __init__(self, node: Node):
        super().__init__()
        self.node = node
        self.edges = []
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(node.label)
        self.setZValue(2)

    def boundingRect(self):
        return QRectF(-2, -2, self.WIDTH + 4, self.HEIGHT + 4)

    def paint(self, painter, option, widget=None):
        selected = self.isSelected()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#158578" if selected else "#d8e1e8"), 2 if selected else 1))
        painter.setBrush(QColor("#132c3a" if selected else "#ffffff"))
        painter.drawRoundedRect(QRectF(0, 0, self.WIDTH, self.HEIGHT), 9, 9)
        color = QColor(COLORS[self.node.kind])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(13, 17, 32, 32), 7, 7)
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        badge = "PK" if self.node.label.endswith("__init__.py") else (
            "PY" if self.node.kind == "internal" else "EX" if self.node.kind == "external" else "?"
        )
        painter.drawText(QRectF(13, 17, 32, 32), Qt.AlignmentFlag.AlignCenter, badge)
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        painter.setPen(QColor("#ffffff" if selected else "#243746"))
        label = self.node.label.rsplit("/", 1)[-1]
        label = painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideMiddle, 172)
        painter.drawText(QRectF(56, 12, 174, 23), Qt.AlignmentFlag.AlignVCenter, label)
        parent = self.node.label.rsplit("/", 1)[0] if "/" in self.node.label else {
            "internal": "Racine du projet", "external": "Bibliothèque externe", "unknown": "Import non résolu",
        }[self.node.kind]
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#b4c9d3" if selected else "#7d8d9a"))
        parent = painter.fontMetrics().elidedText(parent, Qt.TextElideMode.ElideMiddle, 172)
        painter.drawText(QRectF(56, 36, 174, 19), Qt.AlignmentFlag.AlignVCenter, parent)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_path()
        return super().itemChange(change, value)


class ConnectionItem(QGraphicsPathItem):
    def __init__(self, edge: Edge, source: FileItem, target: FileItem):
        super().__init__()
        self.edge, self.source, self.target = edge, source, target
        source.edges.append(self)
        target.edges.append(self)
        self.arrow = QPolygonF()
        self.setZValue(0)
        self.setPen(QPen(QColor("#9375c5" if edge.kind == "call" else "#9caebc"), 1.5,
                         Qt.PenStyle.DashLine if edge.kind == "call" else Qt.PenStyle.SolidLine))
        self.setToolTip(("Appels" if edge.kind == "call" else "Imports") + "\n" + "\n".join(edge.labels))
        self.update_path()

    def update_path(self):
        offset = 10 if self.edge.kind == "call" else -7
        a = self.source.pos() + QPointF(FileItem.WIDTH / 2 + offset, FileItem.HEIGHT)
        b = self.target.pos() + QPointF(FileItem.WIDTH / 2 + offset, 0)
        path = QPainterPath(a)
        if self.source is self.target:
            b = self.target.pos() + QPointF(FileItem.WIDTH, FileItem.HEIGHT / 2)
            path.cubicTo(a + QPointF(160, 75), b + QPointF(90, 0), b)
        else:
            bend = max(45, abs(b.y() - a.y()) * .5)
            path.cubicTo(a + QPointF(0, bend), b - QPointF(0, bend), b)
        self.setPath(path)
        previous = path.pointAtPercent(.985)
        angle = math.atan2(b.y() - previous.y(), b.x() - previous.x())
        self.arrow = QPolygonF([b, b - QPointF(math.cos(angle - .45) * 10, math.sin(angle - .45) * 10),
                               b - QPointF(math.cos(angle + .45) * 10, math.sin(angle + .45) * 10)])
        self.update()

    def boundingRect(self):
        return super().boundingRect().adjusted(-12, -12, 12, 12)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.pen().color())
        painter.drawPolygon(self.arrow)


class GraphView(QGraphicsView):
    node_selected = Signal(str)
    zoom_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.nodes: dict[str, FileItem] = {}
        self.connections: list[ConnectionItem] = []
        self.positions = {}
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor(BACKGROUND))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.scene().selectionChanged.connect(self._selection_changed)

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor(BACKGROUND))
        # Avoid generating millions of dots when a large graph is zoomed out.
        step = max(24, math.ceil(12 / max(.03, self.transform().m11()) / 24) * 24)
        painter.setPen(QPen(QColor("#dce4ec"), 1))
        for x in range(math.floor(rect.left() / step) * step, math.ceil(rect.right()), step):
            for y in range(math.floor(rect.top() / step) * step, math.ceil(rect.bottom()), step):
                painter.drawPoint(QPointF(x, y))

    def set_graph(self, graph: ProjectGraph, selected="", *, reset=False):
        if reset:
            self.positions.clear()
        else:
            self.positions.update({key: (item.x(), item.y()) for key, item in self.nodes.items()})
        with QSignalBlocker(self.scene()):
            self.scene().clear()
            self.nodes, self.connections = {}, []
            # The desktop canvas is taller than a horizontal import chain. Turn
            # dependency levels into rows so file names remain readable at fit.
            positions = {key: (y / 108 * 290, x / 340 * 140)
                         for key, (x, y) in layered_layout(graph).items()}
            for key, node in graph.nodes.items():
                item = FileItem(node)
                self.scene().addItem(item)
                item.setPos(*self.positions.get(key, positions[key]))
                self.nodes[key] = item
            for edge in graph.edges:
                connection = ConnectionItem(edge, self.nodes[edge.source], self.nodes[edge.target])
                self.scene().addItem(connection)
                self.connections.append(connection)
            if not self.nodes:
                text = self.scene().addText("Aucun fichier à afficher.\nOuvrez un projet ou ajustez les filtres.")
                text.setDefaultTextColor(QColor("#778b9a"))
                text.setFont(QFont("Segoe UI", 13))
            if selected in self.nodes:
                self.nodes[selected].setSelected(True)
            self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-70, -70, 70, 70))
        self._emphasize(selected if selected in self.nodes else "")

    def _emphasize(self, selected):
        related = {selected}
        for item in self.connections:
            incident = selected in (item.edge.source, item.edge.target)
            if incident:
                related.update((item.edge.source, item.edge.target))
            item.setOpacity(1 if not selected or incident else .16)
        for key, item in self.nodes.items():
            item.setOpacity(1 if not selected or key in related else .38)

    def _selection_changed(self):
        items = self.scene().selectedItems()
        key = items[0].node.id if items and isinstance(items[0], FileItem) else ""
        self._emphasize(key)
        self.node_selected.emit(key)

    def select_node(self, key, center=False):
        with QSignalBlocker(self.scene()):
            self.scene().clearSelection()
            if key in self.nodes:
                self.nodes[key].setSelected(True)
                if center:
                    self.centerOn(self.nodes[key])
        self._emphasize(key)

    def fit_graph(self):
        self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-50, -50, 50, 50))
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        if self.transform().m11() > 1.35:
            self.resetTransform()
            self.scale(1.35, 1.35)
        self.zoom_changed.emit(round(self.transform().m11() * 100))

    def zoom(self, factor):
        current = self.transform().m11()
        wanted = max(.03, min(3, current * factor))
        self.scale(wanted / current, wanted / current)
        self.zoom_changed.emit(round(wanted * 100))

    def wheelEvent(self, event):
        self.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        event.accept()

    def export_image(self, filename: str):
        """Export the filtered scene with its current positions, without Graphviz."""
        bounds = self.scene().itemsBoundingRect().adjusted(-32, -32, 32, 32)
        scale = min(2, 8192 / max(bounds.width(), bounds.height()),
                    math.sqrt(28_000_000 / max(1, bounds.width() * bounds.height())))
        size = QSize(max(1, math.ceil(bounds.width() * scale)), max(1, math.ceil(bounds.height() * scale)))
        if Path(filename).suffix.lower() == ".svg":
            device = QSvgGenerator()
            device.setFileName(filename)
            device.setSize(size)
            device.setViewBox(QRectF(0, 0, size.width(), size.height()))
            device.setTitle("Depviz — Arbre de dépendances")
        else:
            device = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
            if device.isNull():
                raise OSError("Image trop grande pour la mémoire disponible.")
            device.fill(QColor(BACKGROUND))
        painter = QPainter()
        if not painter.begin(device):
            raise OSError(f"Impossible d'écrire l'image : {filename}")
        opacity = [(item, item.opacity()) for item in [*self.nodes.values(), *self.connections]]
        try:
            for item, _ in opacity:
                item.setOpacity(1)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.scene().render(painter, QRectF(0, 0, size.width(), size.height()), bounds)
        finally:
            painter.end()
            for item, value in opacity:
                item.setOpacity(value)
        if isinstance(device, QImage) and not device.save(filename, "PNG"):
            raise OSError(f"Impossible d'écrire l'image : {filename}")
