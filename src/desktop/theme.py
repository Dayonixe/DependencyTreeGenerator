"""Application palette and a small, code-drawn dependency icon."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap


STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #263b4a; }
QMainWindow, QWidget#workspace { background: #edf1f5; }
QFrame#header { background: white; border-bottom: 1px solid #dee5ec; }
QFrame#sidebar { background: #142d3c; border-radius: 10px; }
QFrame#sidebar QLabel { color: #c5d5e0; }
QFrame#sidebar QLabel#section { color: #7fa2b7; font-size: 8pt; font-weight: 700; }
QFrame#sidebar QTreeWidget { background: #142d3c; color: #deebf2; border: none; }
QFrame#sidebar QTreeWidget::item:selected { background: #285266; color: white; }
QFrame#sidebar QTreeWidget::item:hover { background: #1f4053; }
QFrame#sidebar QLineEdit, QFrame#sidebar QPlainTextEdit, QFrame#sidebar QSpinBox {
    background: #203f50; color: #e1edf4; border: 1px solid #365769; border-radius: 5px;
}
QFrame#inspector, QFrame#center { background: white; border: 1px solid #dde5ec; border-radius: 10px; }
QLabel#brand { color: #143a45; font-size: 23pt; font-weight: 800; }
QLabel#title { font-size: 16pt; font-weight: 650; }
QLabel#muted { color: #7c8c98; font-size: 9pt; }
QLabel#section { color: #718694; font-size: 8pt; font-weight: 700; }
QLabel#stat { font-size: 18pt; font-weight: 700; color: #1f4b5b; }
QLabel#badge { background: #e7f5f1; color: #147566; padding: 5px 10px; border-radius: 6px; }
QPushButton, QToolButton { background: #f5f8fa; border: 1px solid #dce5eb; border-radius: 6px; padding: 7px 12px; }
QPushButton:hover, QToolButton:hover { background: #e9f2f4; border-color: #a1c5cc; }
QPushButton:pressed { background: #d9ebe9; }
QPushButton:disabled, QToolButton:disabled { color: #a7b2bb; background: #f1f4f6; border-color: #e4eaee; }
QPushButton#primary { background: #198678; border-color: #198678; color: white; font-weight: 650; }
QPushButton#primary:hover { background: #126f64; }
QPushButton#primary:disabled { background: #416a6c; border-color: #416a6c; color: #9fc0bb; }
QLineEdit, QSpinBox { background: white; border: 1px solid #dbe4ec; border-radius: 6px; padding: 6px 8px; }
QLineEdit:focus, QPlainTextEdit:focus { border-color: #389f92; }
QPlainTextEdit { border: 1px solid #dbe4ec; background: #fafcfd; border-radius: 6px; padding: 6px; }
QTreeWidget, QListWidget, QTableWidget { background: white; border: none; outline: none; }
QTreeWidget::item, QListWidget::item { padding: 5px; }
QListWidget::item:selected, QTableWidget::item:selected { background: #e4f2ef; color: #145c54; }
QHeaderView::section { background: #f4f7f9; padding: 8px; border: none; color: #708694; }
QTabWidget::pane { border: none; }
QTabBar::tab { padding: 10px 13px; color: #80919e; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #157c6e; border-bottom: 2px solid #198678; }
QCheckBox { spacing: 6px; }
QCheckBox::indicator { width: 15px; height: 15px; }
QProgressBar { border: none; background: #24495c; max-height: 4px; border-radius: 2px; }
QProgressBar::chunk { background: #57bfab; }
QSplitter::handle { background: transparent; }
QStatusBar { background: #edf1f5; color: #6e8493; }
QMenu { background: white; border: 1px solid #dce5eb; padding: 5px; }
QMenu::item { padding: 7px 18px; }
QMenu::item:selected { background: #e7f3f0; }
QToolTip { color: #e6eff5; background: #203b4c; border: none; padding: 7px; }
"""


def configure_application(app):
    """Keep native controls readable even when Windows uses a dark accent palette."""
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in {
        QPalette.ColorRole.Window: "#edf1f5", QPalette.ColorRole.WindowText: "#263b4a",
        QPalette.ColorRole.Base: "#ffffff", QPalette.ColorRole.AlternateBase: "#f5f7fa",
        QPalette.ColorRole.Text: "#263b4a", QPalette.ColorRole.Button: "#f5f8fa",
        QPalette.ColorRole.ButtonText: "#263b4a", QPalette.ColorRole.Highlight: "#198678",
        QPalette.ColorRole.HighlightedText: "#ffffff", QPalette.ColorRole.Link: "#198678",
        QPalette.ColorRole.ToolTipBase: "#203b4c", QPalette.ColorRole.ToolTipText: "#e6eff5",
    }.items():
        palette.setColor(role, QColor(color))
    app.setPalette(palette)


def app_icon() -> QIcon:
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#143a45"))
    painter.drawRoundedRect(0, 0, 128, 128, 28, 28)
    painter.setPen(QPen(QColor("#73d5bb"), 6))
    painter.drawLine(QPointF(37, 64), QPointF(89, 35))
    painter.drawLine(QPointF(37, 64), QPointF(89, 93))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#ffffff"))
    for x, y in [(37, 64), (89, 35), (89, 93)]:
        painter.drawEllipse(QPointF(x, y), 12, 12)
    painter.end()
    return QIcon(pixmap)
