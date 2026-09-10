"""Interactive class diagram with collapsible method compartments."""

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal, QSignalBlocker
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject, QGraphicsPathItem, QGraphicsScene, QGraphicsView

from ..models import ClassInfo, ClassUsage
from .data import Edge, Node, ProjectGraph, layered_layout
from .graph import BACKGROUND


def class_id(file: str, name: str) -> str:
    return "class:" + file.replace("\\", "/") + ":" + name


class ClassCard(QGraphicsObject):
    toggled = Signal()
    selected = Signal(object)
    WIDTH, HEADER_HEIGHT, METHOD_HEIGHT = 280, 78, 25

    def __init__(self, info: ClassInfo):
        super().__init__()
        self.info = info
        self.expanded = False
        self.edges = []
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Cliquez pour afficher ou masquer les méthodes.\n" + info.file.replace("\\", "/"))
        self.setZValue(2)

    @property
    def height(self):
        return self.HEADER_HEIGHT + (max(1, len(self.info.methods)) * self.METHOD_HEIGHT + 12
                                     if self.expanded else 0)

    def boundingRect(self):
        return QRectF(-2, -2, self.WIDTH + 4, self.height + 4)

    def set_expanded(self, expanded):
        if self.expanded == expanded:
            return
        self.prepareGeometryChange()
        self.expanded = expanded
        self.update()
        self.toggled.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_position = event.screenPos()
            self.selected.emit(self.info)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and (event.screenPos() - getattr(self, "_press_position", event.screenPos())).manhattanLength() < 4):
            self.set_expanded(not self.expanded)
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_path()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = self.isSelected()
        painter.setPen(QPen(QColor("#168878" if selected else "#cfdce4"), 2 if selected else 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(QRectF(0, 0, self.WIDTH, self.height), 9, 9)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#173746" if selected else "#e5f3f0"))
        painter.drawRoundedRect(QRectF(1, 1, self.WIDTH - 2, self.HEADER_HEIGHT - 1), 8, 8)
        painter.setPen(QColor("#ffffff" if selected else "#18796d"))
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        name = painter.fontMetrics().elidedText(self.info.name, Qt.TextElideMode.ElideMiddle, 218)
        painter.drawText(QRectF(38, 11, 226, 23), Qt.AlignmentFlag.AlignVCenter, name)
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#c1d4dd" if selected else "#718793"))
        file = painter.fontMetrics().elidedText(self.info.file.replace("\\", "/"), Qt.TextElideMode.ElideMiddle, 225)
        painter.drawText(QRectF(38, 36, 225, 17), Qt.AlignmentFlag.AlignVCenter, file)
        bases = ", ".join(base.expression for base in self.info.bases)
        bases = "hérite de " + bases if bases else "Aucune classe parente"
        bases = painter.fontMetrics().elidedText(bases, Qt.TextElideMode.ElideRight, 225)
        painter.drawText(QRectF(38, 53, 225, 17), Qt.AlignmentFlag.AlignVCenter, bases)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff" if selected else "#168878"))
        direction = QPolygonF([
            QPointF(17, 31 if self.expanded else 26),
            QPointF(29 if self.expanded else 24, 31 if self.expanded else 33),
            QPointF(24 if self.expanded else 17, 38 if self.expanded else 40),
        ])
        painter.drawPolygon(direction)
        if self.expanded:
            painter.setPen(QPen(QColor("#d9e3e9"), 1))
            painter.drawLine(QPointF(0, self.HEADER_HEIGHT), QPointF(self.WIDTH, self.HEADER_HEIGHT))
            painter.setFont(QFont("Consolas", 8))
            painter.setPen(QColor("#334d5b"))
            methods = self.info.methods or ()
            if not methods:
                painter.setPen(QColor("#8799a5"))
                painter.drawText(QRectF(15, self.HEADER_HEIGHT + 7, self.WIDTH - 30, self.METHOD_HEIGHT),
                                 Qt.AlignmentFlag.AlignVCenter, "(aucune méthode)")
            for index, method in enumerate(methods):
                prefix = {"classmethod": "C", "staticmethod": "S", "property": "P", "async": "A"}.get(method.kind, "ƒ")
                text = f"{prefix}  {method.name}({method.signature})"
                text = painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, self.WIDTH - 28)
                painter.drawText(QRectF(15, self.HEADER_HEIGHT + 7 + index * self.METHOD_HEIGHT,
                                        self.WIDTH - 30, self.METHOD_HEIGHT), Qt.AlignmentFlag.AlignVCenter, text)


class InheritanceEdge(QGraphicsPathItem):
    kind = "inheritance"

    def __init__(self, parent: ClassCard, child: ClassCard):
        super().__init__()
        self.source, self.target = parent, child
        parent.edges.append(self)
        child.edges.append(self)
        self.arrow = QPolygonF()
        self.setZValue(0)
        self.setPen(QPen(QColor("#6c8796"), 1.6))
        self.setToolTip(f"{child.info.name} hérite de {parent.info.name}")
        self.update_path()

    def update_path(self):
        # UML inheritance points from the child to the parent. The layout keeps
        # parents on the left, so the hollow arrowhead ends on the parent's card.
        a = self.target.pos() + QPointF(0, min(38, self.target.height / 2))
        b = self.source.pos() + QPointF(ClassCard.WIDTH, min(38, self.source.height / 2))
        path = QPainterPath(a)
        bend = (b.x() - a.x()) * .5
        path.cubicTo(a + QPointF(bend, 0), b - QPointF(bend, 0), b)
        self.setPath(path)
        previous = path.pointAtPercent(.985)
        angle = math.atan2(b.y() - previous.y(), b.x() - previous.x())
        self.arrow = QPolygonF([b,
            b - QPointF(math.cos(angle - .55) * 13, math.sin(angle - .55) * 13),
            b - QPointF(math.cos(angle + .55) * 13, math.sin(angle + .55) * 13),
        ])
        self.update()

    def boundingRect(self):
        return super().boundingRect().adjusted(-15, -15, 15, 15)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        painter.setPen(self.pen())
        painter.setBrush(QColor(BACKGROUND))
        painter.drawPolygon(self.arrow)


def _connection_path(source: ClassCard, target: ClassCard, offset=10):
    """Connect the closest horizontal or vertical faces of two cards."""
    source_center = source.pos() + QPointF(ClassCard.WIDTH / 2, source.height / 2)
    target_center = target.pos() + QPointF(ClassCard.WIDTH / 2, target.height / 2)
    delta = target_center - source_center
    if abs(delta.x()) >= abs(delta.y()):
        direction = 1 if delta.x() >= 0 else -1
        start = source.pos() + QPointF(
            ClassCard.WIDTH if direction > 0 else 0, source.height / 2 + offset,
        )
        end = target.pos() + QPointF(
            0 if direction > 0 else ClassCard.WIDTH, target.height / 2 + offset,
        )
        bend = (end.x() - start.x()) * .5
        path = QPainterPath(start)
        path.cubicTo(start + QPointF(bend, 0), end - QPointF(bend, 0), end)
    else:
        direction = 1 if delta.y() >= 0 else -1
        start = source.pos() + QPointF(
            ClassCard.WIDTH / 2 + offset, source.height if direction > 0 else 0,
        )
        end = target.pos() + QPointF(
            ClassCard.WIDTH / 2 + offset, 0 if direction > 0 else target.height,
        )
        bend = (end.y() - start.y()) * .5
        path = QPainterPath(start)
        path.cubicTo(start + QPointF(0, bend), end - QPointF(0, bend), end)
    return path, end


class UsageEdge(QGraphicsPathItem):
    kind = "usage"

    def __init__(self, source: ClassCard, target: ClassCard, usages: tuple[ClassUsage, ...]):
        super().__init__()
        self.source, self.target, self.usages = source, target, usages
        source.edges.append(self)
        target.edges.append(self)
        self.arrow = QPolygonF()
        self.setZValue(1)
        pen = QPen(QColor("#7c5bb3"), 1.8, Qt.PenStyle.DashLine)
        pen.setDashPattern([6, 4])
        self.setPen(pen)
        details = "\n".join(
            f"{usage.source_method}() : {usage.expression}() · ligne {usage.lineno}"
            for usage in usages
        )
        self.setToolTip(f"{source.info.name} utilise {target.info.name}\n{details}")
        self.update_path()

    def update_path(self):
        path, end = _connection_path(self.source, self.target)
        self.setPath(path)
        previous = path.pointAtPercent(.985)
        angle = math.atan2(end.y() - previous.y(), end.x() - previous.x())
        self.arrow = QPolygonF([
            end,
            end - QPointF(math.cos(angle - .55) * 10, math.sin(angle - .55) * 10),
            end - QPointF(math.cos(angle + .55) * 10, math.sin(angle + .55) * 10),
        ])
        self.update()

    def boundingRect(self):
        return super().boundingRect().adjusted(-12, -12, 12, 12)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        painter.setPen(self.pen())
        painter.setBrush(self.pen().color())
        painter.drawPolygon(self.arrow)


class ClassDiagramView(QGraphicsView):
    class_selected = Signal(object)
    zoom_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.cards: dict[str, ClassCard] = {}
        self.edges = []
        self.positions = {}
        self.selected_key = ""
        self.all_classes: list[ClassInfo] = []
        self.all_usages: list[ClassUsage] = []
        self.query = ""
        self.matching_count = 0
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor(BACKGROUND))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.scene().selectionChanged.connect(self._selection_changed)

    def set_classes(self, classes, usages=(), query="", *, reset=False):
        classes = list(classes)
        usages = list(usages)
        query = query.strip().casefold()
        if (not reset and classes == self.all_classes and usages == self.all_usages
                and query == self.query):
            return
        expanded = set() if reset else {key for key, card in self.cards.items() if card.expanded}
        if reset:
            self.positions.clear()
            self.selected_key = ""
        else:
            self.positions.update({key: (card.x(), card.y()) for key, card in self.cards.items()})
        self.all_classes = classes
        self.all_usages = usages
        self.query = query
        visible = [item for item in self.all_classes if not self.query or self.query in (
            item.file + " " + item.name + " " + " ".join(method.name for method in item.methods)
            + " " + " ".join(base.expression for base in item.bases)).replace("\\", "/").casefold()]
        self.matching_count = len(visible)
        visible = visible[:300]
        with QSignalBlocker(self.scene()):
            self.scene().clear()
            self.cards, self.edges = {}, []
            for info in visible:
                key = class_id(info.file, info.name)
                card = ClassCard(info)
                card.expanded = key in expanded
                card.toggled.connect(self._geometry_changed)
                card.selected.connect(self._selected)
                self.scene().addItem(card)
                self.cards[key] = card
            for info in visible:
                child = self.cards[class_id(info.file, info.name)]
                for base in info.bases:
                    parent = self.cards.get(class_id(base.target_file, base.target_class)) if base.target_file else None
                    if parent is not None:
                        edge = InheritanceEdge(parent, child)
                        self.scene().addItem(edge)
                        self.edges.append(edge)
            grouped = {}
            for usage in self.all_usages:
                source = self.cards.get(class_id(usage.source_file, usage.source_class))
                target = self.cards.get(class_id(usage.target_file, usage.target_class))
                if source is not None and target is not None and source is not target:
                    grouped.setdefault((source, target), []).append(usage)
            for (source, target), items in grouped.items():
                edge = UsageEdge(source, target, tuple(items))
                self.scene().addItem(edge)
                self.edges.append(edge)
            automatic = self._automatic_positions()
            for key, card in self.cards.items():
                if key in self.positions:
                    card.setPos(*self.positions[key])
                else:
                    card.setPos(automatic[key])
            if self.selected_key in self.cards:
                self.cards[self.selected_key].setSelected(True)
            self._geometry_changed()
        self._emphasize(self.selected_key if self.selected_key in self.cards else "")

    def _selected(self, info):
        key = class_id(info.file, info.name)
        card = self.cards.get(key)
        with QSignalBlocker(self.scene()):
            self.scene().clearSelection()
            if card:
                card.setSelected(True)
        self.selected_key = key if card else ""
        self._emphasize(self.selected_key)
        self.class_selected.emit(info)

    def _selection_changed(self):
        items = self.scene().selectedItems()
        card = items[0] if items and isinstance(items[0], ClassCard) else None
        self.selected_key = class_id(card.info.file, card.info.name) if card else ""
        self._emphasize(self.selected_key)

    def _emphasize(self, selected):
        related = {selected}
        for edge in self.edges:
            source = class_id(edge.source.info.file, edge.source.info.name)
            target = class_id(edge.target.info.file, edge.target.info.name)
            incident = selected in (source, target)
            if incident:
                related.update((source, target))
            edge.setOpacity(1 if not selected or incident else .16)
        for key, card in self.cards.items():
            card.setOpacity(1 if not selected or key in related else .38)

    def _automatic_positions(self):
        graph_edges = []
        for edge in self.edges:
            source = class_id(edge.source.info.file, edge.source.info.name)
            target = class_id(edge.target.info.file, edge.target.info.name)
            graph_edges.append(Edge(source, target, edge.kind, ()))
        neighbors = {key: set() for key in self.cards}
        for edge in graph_edges:
            neighbors[edge.source].add(edge.target)
            neighbors[edge.target].add(edge.source)
        components, unseen = [], set(self.cards)
        while unseen:
            start = min(unseen, key=lambda key: (self.cards[key].info.name, key))
            component, stack = set(), [start]
            unseen.remove(start)
            while stack:
                key = stack.pop()
                component.add(key)
                linked = neighbors[key] & unseen
                unseen.difference_update(linked)
                stack.extend(linked)
            components.append(component)

        layouts = []
        for component in components:
            graph = ProjectGraph(
                {key: Node(key, self.cards[key].info.name, "internal") for key in component},
                [edge for edge in graph_edges if edge.source in component and edge.target in component],
            )
            columns = {}
            for key, (x, y) in layered_layout(graph).items():
                columns.setdefault(x, []).append((y, key))
            positions, width, height = {}, 0.0, 0.0
            for x, column in sorted(columns.items()):
                cursor = 0.0
                horizontal = x / 340 * 360
                for _, key in sorted(column):
                    positions[key] = QPointF(horizontal, cursor)
                    cursor += self.cards[key].height + 40
                width = max(width, horizontal + ClassCard.WIDTH)
                height = max(height, cursor - 40)
            layouts.append((positions, width, height))

        result = {}
        cursor_x = cursor_y = row_height = 0.0
        for positions, width, height in layouts:
            if cursor_x and cursor_x + width > 1400:
                cursor_x = 0.0
                cursor_y += row_height + 70
                row_height = 0.0
            for key, position in positions.items():
                result[key] = position + QPointF(cursor_x, cursor_y)
            cursor_x += width + 70
            row_height = max(row_height, height)
        return result

    def _geometry_changed(self):
        for edge in self.edges:
            edge.update_path()
        self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-60, -60, 60, 60))

    def relayout(self):
        automatic = self._automatic_positions()
        self.positions.clear()
        for key, position in automatic.items():
            self.cards[key].setPos(position)
            self.positions[key] = (position.x(), position.y())
        self._geometry_changed()

    def set_all_expanded(self, expanded):
        for card in self.cards.values():
            card.blockSignals(True)
            card.prepareGeometryChange()
            card.expanded = expanded
            card.blockSignals(False)
            card.update()
        self._geometry_changed()

    def fit_diagram(self):
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        if self.transform().m11() > 1.3:
            self.resetTransform()
            self.scale(1.3, 1.3)
        self.zoom_changed.emit(round(self.transform().m11() * 100))

    def zoom(self, factor):
        current = self.transform().m11()
        wanted = max(.04, min(3, current * factor))
        self.scale(wanted / current, wanted / current)
        self.zoom_changed.emit(round(wanted * 100))

    def wheelEvent(self, event):
        self.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        event.accept()

    def export_image(self, filename: str):
        """Export the displayed diagram, including expanded method compartments."""
        bounds = self.scene().itemsBoundingRect().adjusted(-32, -32, 32, 32)
        scale = min(2, 8192 / max(1, bounds.width(), bounds.height()),
                    math.sqrt(28_000_000 / max(1, bounds.width() * bounds.height())))
        size = QSize(max(1, math.ceil(bounds.width() * scale)), max(1, math.ceil(bounds.height() * scale)))
        if Path(filename).suffix.lower() == ".svg":
            device = QSvgGenerator()
            device.setFileName(filename)
            device.setSize(size)
            device.setViewBox(QRectF(0, 0, size.width(), size.height()))
            device.setTitle("Depviz — Diagramme de classes")
        else:
            device = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
            if device.isNull():
                raise OSError("Image trop grande pour la mémoire disponible.")
            device.fill(QColor(BACKGROUND))
        painter = QPainter()
        if not painter.begin(device):
            raise OSError(f"Impossible d'écrire l'image : {filename}")
        opacity = [(item, item.opacity()) for item in [*self.cards.values(), *self.edges]]
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
