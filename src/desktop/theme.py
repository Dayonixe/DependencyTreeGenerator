"""Application themes and a small, code-drawn dependency icon."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap

from .settings import load_theme_preference


THEMES = {
    "light": {
        "window": "#edf1f5", "panel": "#ffffff", "canvas": "#f5f7fa",
        "sidebar": "#142d3c", "sidebar_field": "#203f50", "sidebar_border": "#365769",
        "text": "#263b4a", "muted": "#718694", "subtle": "#7c8c98",
        "border": "#dde5ec", "control": "#f5f8fa", "control_hover": "#e9f2f4",
        "control_pressed": "#d9ebe9", "disabled": "#a7b2bb",
        "primary": "#198678", "primary_hover": "#126f64", "brand": "#143a45",
        "selection": "#e4f2ef", "selection_text": "#145c54", "grid": "#dce4ec",
        "card": "#ffffff", "card_border": "#d8e1e8", "selected_card": "#132c3a",
        "selected_border": "#158578", "card_text": "#243746", "card_muted": "#7d8d9a",
        "selected_text": "#ffffff", "selected_muted": "#b4c9d3",
        "class_header": "#e5f3f0", "class_selected_header": "#173746",
        "class_text": "#18796d", "class_method": "#334d5b", "class_separator": "#d9e3e9",
        "internal": "#158578", "external": "#b57a22", "unknown": "#c65e64",
        "import_edge": "#7c91a0", "call_edge": "#7c5bb3", "inheritance_edge": "#6c8796",
        "highlight_line": "#dff2eb", "tooltip": "#203b4c", "tooltip_text": "#e6eff5",
    },
    "dark": {
        "window": "#0e171e", "panel": "#16232c", "canvas": "#101b23",
        "sidebar": "#101e27", "sidebar_field": "#1d3441", "sidebar_border": "#385566",
        "text": "#e4edf2", "muted": "#9bb0bc", "subtle": "#91a6b2",
        "border": "#2e414d", "control": "#1d2c36", "control_hover": "#263b46",
        "control_pressed": "#21453f", "disabled": "#687a84",
        "primary": "#21a08f", "primary_hover": "#2bb5a1", "brand": "#79dac4",
        "selection": "#20413e", "selection_text": "#dffaf4", "grid": "#263640",
        "card": "#182630", "card_border": "#344854", "selected_card": "#0d3537",
        "selected_border": "#31b6a4", "card_text": "#e7eff3", "card_muted": "#9aadb7",
        "selected_text": "#ffffff", "selected_muted": "#bcd2da",
        "class_header": "#1d3738", "class_selected_header": "#0d4141",
        "class_text": "#7cddc8", "class_method": "#d7e4e9", "class_separator": "#344854",
        "internal": "#2bb6a2", "external": "#d3a04c", "unknown": "#df757a",
        "import_edge": "#8299a8", "call_edge": "#ae8ade", "inheritance_edge": "#8aa0ad",
        "highlight_line": "#244b45", "tooltip": "#dce9ef", "tooltip_text": "#15252e",
    },
}


def theme_colors(name: str) -> dict[str, str]:
    return THEMES["dark" if name == "dark" else "light"]


def system_theme(app) -> str:
    """Resolve Qt's current system color scheme when the platform exposes it."""
    try:
        return "dark" if app.styleHints().colorScheme() == Qt.ColorScheme.Dark else "light"
    except (AttributeError, RuntimeError):
        return "light"


def resolved_theme(app, preference: str) -> str:
    return system_theme(app) if preference == "system" else preference


def stylesheet(name: str) -> str:
    c = theme_colors(name)
    return f"""
QWidget {{ font-family: 'Segoe UI'; font-size: 10pt; color: {c['text']}; }}
QMainWindow, QWidget#workspace {{ background: {c['window']}; }}
QFrame#header {{ background: {c['panel']}; border-bottom: 1px solid {c['border']}; }}
QFrame#sidebar {{ background: {c['sidebar']}; border-radius: 10px; }}
QFrame#sidebar QLabel {{ color: #c5d5e0; }}
QFrame#sidebar QLabel#section {{ color: #7fa2b7; font-size: 8pt; font-weight: 700; }}
QFrame#sidebar QTreeWidget {{ background: {c['sidebar']}; color: #deebf2; border: none; }}
QFrame#sidebar QTreeWidget::item:selected {{ background: #285266; color: white; }}
QFrame#sidebar QTreeWidget::item:hover {{ background: #1f4053; }}
QFrame#sidebar QLineEdit, QFrame#sidebar QPlainTextEdit, QFrame#sidebar QSpinBox {{
    background: {c['sidebar_field']}; color: #e1edf4; border: 1px solid {c['sidebar_border']}; border-radius: 5px;
}}
QFrame#inspector, QFrame#center {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 10px; }}
QFrame#legendBar {{ background: {c['control']}; border: 1px solid {c['border']}; border-radius: 8px; }}
QFrame#legendItem {{ background: transparent; border: none; }}
QLabel#legendTitle {{ color: {c['text']}; font-size: 9pt; font-weight: 650; }}
QLabel#legendDetail {{ color: {c['subtle']}; font-size: 8pt; }}
QLabel#brand {{ color: {c['brand']}; font-size: 23pt; font-weight: 800; }}
QLabel#title {{ font-size: 16pt; font-weight: 650; }}
QLabel#muted {{ color: {c['subtle']}; font-size: 9pt; }}
QLabel#section {{ color: {c['muted']}; font-size: 8pt; font-weight: 700; }}
QLabel#stat {{ font-size: 18pt; font-weight: 700; color: {c['brand']}; }}
QLabel#badge {{ background: {c['selection']}; color: {c['selection_text']}; padding: 5px 10px; border-radius: 6px; }}
QPushButton, QToolButton {{ background: {c['control']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 7px 12px; }}
QPushButton:hover, QToolButton:hover {{ background: {c['control_hover']}; border-color: {c['primary']}; }}
QPushButton:pressed {{ background: {c['control_pressed']}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {c['disabled']}; background: {c['control']}; border-color: {c['border']}; }}
QPushButton#primary {{ background: {c['primary']}; border-color: {c['primary']}; color: white; font-weight: 650; }}
QPushButton#primary:hover {{ background: {c['primary_hover']}; }}
QPushButton#primary:disabled {{ background: #416a6c; border-color: #416a6c; color: #9fc0bb; }}
QLineEdit, QSpinBox {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 6px 8px; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {c['primary']}; }}
QPlainTextEdit {{ border: 1px solid {c['border']}; background: {c['canvas']}; border-radius: 6px; padding: 6px; }}
QTreeWidget, QListWidget, QTableWidget {{ background: {c['panel']}; border: none; outline: none; }}
QTreeWidget::item, QListWidget::item {{ padding: 5px; }}
QListWidget::item:selected, QTableWidget::item:selected {{ background: {c['selection']}; color: {c['selection_text']}; }}
QHeaderView::section {{ background: {c['control']}; padding: 8px; border: none; color: {c['muted']}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ padding: 10px 13px; color: {c['subtle']}; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {c['primary']}; border-bottom: 2px solid {c['primary']}; }}
QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; }}
QProgressBar {{ border: none; background: #24495c; max-height: 4px; border-radius: 2px; }}
QProgressBar::chunk {{ background: #57bfab; }}
QSplitter::handle {{ background: transparent; }}
QStatusBar {{ background: {c['window']}; color: {c['muted']}; }}
QMenu {{ background: {c['panel']}; border: 1px solid {c['border']}; padding: 5px; }}
QMenu::item {{ padding: 7px 22px; }}
QMenu::item:selected {{ background: {c['selection']}; color: {c['selection_text']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 5px 10px; }}
QToolTip {{ color: {c['tooltip_text']}; background: {c['tooltip']}; border: none; padding: 7px; }}
"""


def apply_application_theme(app, preference: str) -> str:
    """Apply a light, dark or system-derived palette and return its resolved name."""
    name = resolved_theme(app, preference)
    colors = theme_colors(name)
    app.setStyle("Fusion")
    palette = QPalette()
    for role, key in {
        QPalette.ColorRole.Window: "window", QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "panel", QPalette.ColorRole.AlternateBase: "canvas",
        QPalette.ColorRole.Text: "text", QPalette.ColorRole.Button: "control",
        QPalette.ColorRole.ButtonText: "text", QPalette.ColorRole.Highlight: "primary",
        QPalette.ColorRole.HighlightedText: "selected_text", QPalette.ColorRole.Link: "primary",
        QPalette.ColorRole.ToolTipBase: "tooltip", QPalette.ColorRole.ToolTipText: "tooltip_text",
    }.items():
        palette.setColor(role, QColor(colors[key]))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(name))
    app.setProperty("depvizThemePreference", preference)
    app.setProperty("depvizResolvedTheme", name)
    return name


def configure_application(app, preference: str | None = None):
    """Configure Qt and restore the saved preference before the window appears."""
    return apply_application_theme(app, preference or load_theme_preference())


# Kept for callers importing the former static stylesheet.
STYLE = stylesheet("light")


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
