"""Portable desktop workspace for exploring Python dependencies."""

import os
from pathlib import Path
import sys
import tempfile
import tokenize

from PySide6.QtCore import Qt, QTimer, QSignalBlocker
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QTextCursor, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from ..graph_generator import create_dependency_graph
from ..output import format_ascii_report, format_text_report
from . import VERSION
from .data import ProjectGraph, file_id, select_graph
from .graph import GraphView
from .theme import STYLE, app_icon
from .worker import AnalysisJob, AnalysisResult


def label(text, name="", wrap=False):
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def example_path():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "examples/advanced"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.result: AnalysisResult | None = None
        self.job: AnalysisJob | None = None
        self.selected = ""
        self._cancelled = False
        self._closing = False
        self._tree_items = {}
        self.setWindowTitle(f"Depviz {VERSION} — Explorateur de dépendances")
        self.setWindowIcon(app_icon())
        self.resize(1480, 920)
        self.setMinimumSize(1100, 700)
        self.setStyleSheet(STYLE)
        self.setAcceptDrops(True)
        self._build_ui()
        self._shortcuts()
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(180)
        self._filter_timer.timeout.connect(self.refresh_graph)
        self.search.textChanged.connect(lambda: self._filter_timer.start())
        self.statusBar().showMessage("Prêt · Choisissez un dossier Python ou ouvrez le projet d’exemple.")
        self.graph.set_graph(ProjectGraph({}, []))

    def _build_ui(self):
        workspace = QWidget()
        workspace.setObjectName("workspace")
        self.setCentralWidget(workspace)
        outer = QVBoxLayout(workspace)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        header = QFrame()
        header.setObjectName("header")
        row = QHBoxLayout(header)
        row.setContentsMargins(22, 12, 22, 12)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(38, 38))
        row.addWidget(logo)
        row.addWidget(label("depviz", "brand"))
        row.addSpacing(18)
        row.addWidget(label("EXPLORATEUR DE DÉPENDANCES", "section"))
        row.addStretch()
        row.addWidget(label("Python · Analyse locale", "badge"))
        self.export_button = QPushButton("Exporter  ▾")
        self.export_button.setEnabled(False)
        menu = QMenu(self)
        for title, kind in [("Image PNG — graphe affiché", "png"), ("Image SVG — graphe affiché", "svg"),
                            ("Graphe DOT — analyse complète", "dot"), ("Rapport texte — analyse complète", "txt"),
                            ("Arbre ASCII — analyse complète", "ascii")]:
            menu.addAction(title, lambda kind=kind: self.choose_export(kind))
        self.export_button.setMenu(menu)
        row.addWidget(self.export_button)
        help_button = QPushButton("Aide")
        help_button.clicked.connect(self.show_help)
        row.addWidget(help_button)
        outer.addWidget(header)

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setChildrenCollapsible(False)
        body.setHandleWidth(12)
        container = QHBoxLayout()
        container.setContentsMargins(16, 16, 16, 10)
        container.addWidget(body)
        outer.addLayout(container, 1)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(238)
        sidebar.setMaximumWidth(340)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 20, 16, 12)
        side.setSpacing(10)
        side.addWidget(label("01  /  PROJET", "section"))
        self.browse_button = QPushButton("Choisir un dossier…")
        self.browse_button.clicked.connect(self.choose_project)
        side.addWidget(self.browse_button)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Chemin du projet Python")
        self.path_edit.setToolTip("Racine des imports Python ou dossier contenant __init__.py")
        self.path_edit.returnPressed.connect(self.start_analysis)
        side.addWidget(self.path_edit)
        self.example_button = QPushButton("Ouvrir l’exemple")
        self.example_button.clicked.connect(lambda: self.open_project(str(example_path())))
        side.addWidget(self.example_button)
        side.addSpacing(10)
        side.addWidget(label("02  /  OPTIONS D’ANALYSE", "section"))
        depth_row = QHBoxLayout()
        depth_row.addWidget(label("Profondeur"))
        self.depth = QSpinBox()
        self.depth.setRange(-1, 9999)
        self.depth.setValue(-1)
        self.depth.setSpecialValueText("Illimitée")
        self.depth.setToolTip("Profondeur des dossiers : 0 = fichiers à la racine.")
        depth_row.addWidget(self.depth)
        side.addLayout(depth_row)
        side.addWidget(label("Exclusions · un motif par ligne"))
        self.ignore = QPlainTextEdit()
        self.ignore.setPlaceholderText("tests\n**/generated_*.py")
        self.ignore.setFixedHeight(80)
        self.ignore.setToolTip("Noms, chemins relatifs et motifs glob. Les environnements et caches sont déjà exclus.")
        side.addWidget(self.ignore)
        self.analyze_button = QPushButton("Analyser le projet")
        self.analyze_button.setObjectName("primary")
        self.analyze_button.clicked.connect(self.start_analysis)
        side.addWidget(self.analyze_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        side.addWidget(self.progress)
        self.cancel_button = QPushButton("Annuler l’analyse")
        self.cancel_button.clicked.connect(self.cancel_analysis)
        self.cancel_button.hide()
        side.addWidget(self.cancel_button)
        side.addSpacing(12)
        self.files_heading = label("03  /  FICHIERS", "section")
        side.addWidget(self.files_heading)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(15)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tree.itemSelectionChanged.connect(self._tree_selection)
        side.addWidget(self.tree, 1)
        side.addWidget(label(f"PORTABLE  /  v{VERSION}", "section"))
        body.addWidget(sidebar)

        center = QFrame()
        center.setObjectName("center")
        layout = QVBoxLayout(center)
        layout.setContentsMargins(18, 16, 18, 10)
        title_row = QHBoxLayout()
        titles = QVBoxLayout()
        self.project_title = label("Explorez votre architecture", "title")
        self.project_path = label("Imports, appels et relations entre vos modules Python.", "muted")
        self.project_path.setMaximumHeight(24)
        titles.addWidget(self.project_title)
        titles.addWidget(self.project_path)
        title_row.addLayout(titles, 1)
        layout.addLayout(title_row)
        stats = QHBoxLayout()
        self.stat_labels = []
        for text in ("FICHIERS", "IMPORTS", "APPELS", "DIAGNOSTICS"):
            column = QVBoxLayout()
            value = label("—", "stat")
            column.addWidget(value)
            column.addWidget(label(text, "section"))
            stats.addLayout(column, 1)
            self.stat_labels.append(value)
        layout.addLayout(stats)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher un fichier ou un module…  Ctrl+F")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        filters = QHBoxLayout()
        self.imports_check = QCheckBox("Imports")
        self.calls_check = QCheckBox("Appels")
        self.external_check = QCheckBox("Externes")
        self.focus_check = QCheckBox("Voisinage")
        self.imports_check.setChecked(True)
        self.calls_check.setChecked(True)
        self.focus_check.setToolTip("Afficher le fichier sélectionné et ses relations directes.")
        self.external_check.setToolTip("Inclure les bibliothèques externes et les imports non résolus.")
        for control in (self.imports_check, self.calls_check, self.external_check, self.focus_check):
            filters.addWidget(control)
            control.toggled.connect(self.refresh_graph)
        filters.addStretch()
        layout.addLayout(filters)
        self.tabs = QTabWidget()
        graph_page = QWidget()
        graph_layout = QVBoxLayout(graph_page)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        self.graph = GraphView()
        self.graph.node_selected.connect(self.select_node)
        graph_layout.addWidget(self.graph, 1)
        self.graph_notice = label("Ouvrez un projet pour commencer.", "muted", True)
        graph_layout.addWidget(self.graph_notice)
        navigation = QHBoxLayout()
        navigation.addWidget(label("● Fichiers   ─ Imports   ┄ Appels", "muted"))
        navigation.addStretch()
        for text, action in [("−", lambda: self.graph.zoom(1 / 1.2)), ("+", lambda: self.graph.zoom(1.2)),
                             ("Cadrer", self.graph.fit_graph), ("Réorganiser", self.relayout)]:
            button = QPushButton(text)
            button.clicked.connect(action)
            navigation.addWidget(button)
        self.zoom_label = label("100 %", "muted")
        self.graph.zoom_changed.connect(lambda value: self.zoom_label.setText(f"{value} %"))
        navigation.addWidget(self.zoom_label)
        graph_layout.addLayout(navigation)
        self.tabs.addTab(graph_page, "Graphe")
        self.calls_table = QTableWidget(0, 4)
        self.calls_table.setHorizontalHeaderLabels(["Fichier source", "Appel", "Définition", "Ligne"])
        self.calls_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.calls_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.calls_table.verticalHeader().hide()
        self.calls_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.calls_table.cellDoubleClicked.connect(self._call_activated)
        self.tabs.addTab(self.calls_table, "Appels")
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        self.tabs.addTab(self.diagnostics, "Diagnostics")
        layout.addWidget(self.tabs, 1)
        body.addWidget(center)

        inspector = QFrame()
        inspector.setObjectName("inspector")
        inspector.setMinimumWidth(260)
        inspector.setMaximumWidth(440)
        detail = QVBoxLayout(inspector)
        detail.setContentsMargins(16, 20, 16, 12)
        detail.addWidget(label("INSPECTEUR", "section"))
        self.node_title = label("Aucune sélection", "title", True)
        detail.addWidget(self.node_title)
        self.node_path = label("Cliquez sur un nœud ou un fichier pour explorer ses relations.", "muted", True)
        self.node_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail.addWidget(self.node_path)
        self.detail_tabs = QTabWidget()
        relations = QWidget()
        relations_layout = QVBoxLayout(relations)
        relations_layout.setContentsMargins(0, 10, 0, 0)
        self.out_heading = label("DÉPENDANCES SORTANTES", "section")
        relations_layout.addWidget(self.out_heading)
        self.outgoing = QListWidget()
        self.outgoing.itemActivated.connect(self._relation_activated)
        self.outgoing.itemClicked.connect(self._relation_activated)
        relations_layout.addWidget(self.outgoing, 1)
        self.in_heading = label("UTILISÉ PAR", "section")
        relations_layout.addWidget(self.in_heading)
        self.incoming = QListWidget()
        self.incoming.itemActivated.connect(self._relation_activated)
        self.incoming.itemClicked.connect(self._relation_activated)
        relations_layout.addWidget(self.incoming, 1)
        self.detail_tabs.addTab(relations, "Relations")
        self.source = QPlainTextEdit()
        self.source.setReadOnly(True)
        self.source.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.source.setFont(QFont("Consolas", 9))
        self.detail_tabs.addTab(self.source, "Code")
        detail.addWidget(self.detail_tabs, 1)
        detail.addWidget(label("Double-cliquez sur un appel pour ouvrir sa définition.", "muted", True))
        body.addWidget(inspector)
        body.setStretchFactor(1, 1)
        body.setSizes([260, 835, 315])

    def _shortcuts(self):
        for sequence, callback in [("Ctrl+O", self.choose_project), ("Ctrl+R", self.start_analysis),
                                   ("Ctrl+F", self.search.setFocus), ("Ctrl+0", self.graph.fit_graph),
                                   ("Ctrl++", lambda: self.graph.zoom(1.2)),
                                   ("Ctrl+-", lambda: self.graph.zoom(1 / 1.2))]:
            action = QAction(self)
            action.setShortcut(QKeySequence(sequence))
            action.triggered.connect(callback)
            self.addAction(action)

    def choose_project(self):
        if self.job:
            return
        path = QFileDialog.getExistingDirectory(self, "Choisir un projet Python", self.path_edit.text())
        if path:
            self.open_project(path)

    def open_project(self, path):
        if self.job:
            return
        self.path_edit.setText(path)
        self.start_analysis()

    def start_analysis(self):
        if self.job:
            return
        raw = self.path_edit.text().strip()
        root = Path(raw).expanduser() if raw else None
        if root is None or not root.is_dir():
            QMessageBox.warning(self, "Dossier invalide", "Choisissez un dossier de projet Python existant.")
            return
        self._cancelled = False
        self.job = AnalysisJob(str(root.resolve()), None if self.depth.value() < 0 else self.depth.value(),
                               [line.strip() for line in self.ignore.toPlainText().splitlines() if line.strip()], self)
        self.job.completed.connect(self.accept_result)
        self.job.failed.connect(self._analysis_failed)
        self.job.progress.connect(lambda path: self.statusBar().showMessage(f"Analyse en cours · {path}"))
        self.job.finished.connect(self._analysis_finished)
        self._set_busy(True)
        self.statusBar().showMessage("Analyse du projet…")
        self.job.start()

    def _set_busy(self, busy):
        for widget in (self.path_edit, self.depth, self.ignore, self.analyze_button,
                       self.browse_button, self.example_button):
            widget.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)

    def cancel_analysis(self):
        if self.job:
            self._cancelled = True
            self.job.requestInterruption()
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage("Annulation en cours…")

    def _analysis_failed(self, message):
        if not self._cancelled and not self._closing:
            QMessageBox.critical(self, "Échec de l’analyse", message)
            self.statusBar().showMessage("L’analyse a échoué.")

    def _analysis_finished(self):
        self.job.deleteLater()
        self.job = None
        self._set_busy(False)
        if self._cancelled:
            self.statusBar().showMessage("Analyse annulée.")
        if self._closing:
            self.close()

    def accept_result(self, result: AnalysisResult):
        if self._cancelled or self._closing:
            return
        self.result = result
        self.selected = ""
        self.search.clear()
        self.project_title.setText(Path(result.root).name)
        self.project_path.setText(result.root)
        self.project_path.setToolTip(result.root)
        analysis = result.analysis
        values = [len(analysis.dependencies), sum(len(refs) for refs in analysis.dependencies.values()),
                  len(analysis.calls), len(result.diagnostics)]
        for widget, value in zip(self.stat_labels, values):
            widget.setText(str(value))
        self.export_button.setEnabled(True)
        self.diagnostics.setPlainText("\n\n".join(result.diagnostics) or "Aucun diagnostic. Tous les fichiers sélectionnés ont été analysés.")
        self.tabs.setTabText(2, f"Diagnostics ({len(result.diagnostics)})")
        self.files_heading.setText(f"03  /  FICHIERS · {values[0]}")
        self._populate_tree()
        self._populate_calls()
        self.refresh_graph(reset=True)
        self.select_node("")
        self.tabs.setCurrentIndex(0)
        partial = "Analyse partielle" if result.diagnostics else "Analyse terminée"
        self.statusBar().showMessage(f"{partial} · {values[0]} fichiers · {result.elapsed:.2f} s")
        QTimer.singleShot(0, self.graph.fit_graph)

    def _populate_tree(self):
        with QSignalBlocker(self.tree):
            self.tree.clear()
            self._tree_items = {}
            directories = {}
            for path in sorted(self.result.analysis.dependencies):
                parts = path.replace("\\", "/").split("/")
                parent = self.tree.invisibleRootItem()
                for index, part in enumerate(parts[:-1]):
                    key = "/".join(parts[:index + 1])
                    if key not in directories:
                        directories[key] = QTreeWidgetItem(parent, [part])
                    parent = directories[key]
                item = QTreeWidgetItem(parent, [parts[-1]])
                item.setData(0, Qt.ItemDataRole.UserRole, file_id(path))
                item.setToolTip(0, path)
                self._tree_items[file_id(path)] = item
            self.tree.expandToDepth(1)

    def _populate_calls(self):
        calls = self.result.analysis.calls
        self.calls_table.setRowCount(len(calls))
        for row, call in enumerate(calls):
            for col, text in enumerate([call.source_file.replace("\\", "/"), call.expression + "()",
                                        call.target_file.replace("\\", "/") + ":" + call.target_function,
                                        str(call.lineno)]):
                item = QTableWidgetItem(text)
                item.setToolTip(f"{call.caller} · {text}\nDouble-clic : définition à la ligne {call.target_lineno}")
                self.calls_table.setItem(row, col, item)
        self.tabs.setTabText(1, f"Appels ({len(calls)})")

    def refresh_graph(self, *args, reset=False):
        if not self.result:
            return
        visible, total = select_graph(self.result.graph, imports=self.imports_check.isChecked(),
                                       calls=self.calls_check.isChecked(), external=self.external_check.isChecked(),
                                       query=self.search.text(), focus=self.selected if self.focus_check.isChecked() else None)
        self.graph.set_graph(visible, self.selected, reset=reset)
        shown = len(visible.nodes)
        message = f"{shown} nœuds · {len(visible.edges)} relations affichées"
        if total > shown:
            message += f" / {total} nœuds correspondants. Limite de 500 : affinez la recherche ou le voisinage."
        else:
            message += " · Molette : zoom · Glisser : déplacer"
        self.graph_notice.setText(message)
        query = self.search.text().strip().casefold()
        for key, item in self._tree_items.items():
            item.setHidden(bool(query) and query not in self.result.graph.nodes[key].label.casefold())
        for row, call in enumerate(self.result.analysis.calls):
            self.calls_table.setRowHidden(row, bool(query) and query not in (
                call.source_file + " " + call.target_file + " " + call.expression).replace("\\", "/").casefold())

    def relayout(self):
        self.refresh_graph(reset=True)
        self.graph.fit_graph()

    def _tree_selection(self):
        items = self.tree.selectedItems()
        if items:
            key = items[0].data(0, Qt.ItemDataRole.UserRole)
            if key:
                self.select_node(key, center=True)

    def select_node(self, key, center=False):
        if not self.result:
            return
        self.selected = key
        node = self.result.graph.nodes.get(key)
        self.outgoing.clear()
        self.incoming.clear()
        if node is None:
            self.node_title.setText("Aucune sélection")
            self.node_path.setText("Cliquez sur un nœud pour afficher ses relations.")
            self.source.clear()
        else:
            self.node_title.setText(node.label.rsplit("/", 1)[-1])
            self.node_path.setText(node.label)
            for edge in self.result.graph.edges:
                if key == edge.source:
                    self._add_relation(self.outgoing, edge, edge.target)
                if key == edge.target:
                    self._add_relation(self.incoming, edge, edge.source)
            self.show_source(node.path)
        self.out_heading.setText(f"DÉPENDANCES SORTANTES · {self.outgoing.count()}")
        self.in_heading.setText(f"UTILISÉ PAR · {self.incoming.count()}")
        with QSignalBlocker(self.tree):
            self.tree.clearSelection()
            if key in self._tree_items:
                self._tree_items[key].setSelected(True)
        if self.focus_check.isChecked():
            self.refresh_graph()
        self.graph.select_node(key, center)

    def _add_relation(self, widget, edge, target):
        node = self.result.graph.nodes[target]
        kind = "APPEL" if edge.kind == "call" else "IMPORT"
        item = QListWidgetItem(f"{kind}  ·  {node.label}")
        item.setToolTip("\n".join(edge.labels))
        item.setData(Qt.ItemDataRole.UserRole, target)
        widget.addItem(item)

    def _relation_activated(self, item):
        key = item.data(Qt.ItemDataRole.UserRole)
        if self.result.graph.nodes[key].kind != "internal":
            self.external_check.setChecked(True)
        self.search.clear()
        self.select_node(key, center=True)

    def _call_activated(self, row, column):
        if self.result:
            call = self.result.analysis.calls[row]
            self.search.clear()
            self.select_node(file_id(call.target_file), center=True)
            self.show_source(call.target_file, call.target_lineno)
            self.detail_tabs.setCurrentIndex(1)

    def show_source(self, relative, line=1):
        self.source.setExtraSelections([])
        if not relative:
            self.source.setPlainText("Le code des bibliothèques externes et des imports non résolus n’est pas chargé.")
            return
        try:
            root = Path(self.result.root).resolve()
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                raise OSError("Le lien pointe hors du dossier analysé.")
            with tokenize.open(path) as source:
                content = source.read(500_001)
            truncated = len(content) > 500_000
            content = content[:500_000]
            self.source.setPlainText("\n".join(f"{index:4}  {text}" for index, text in enumerate(content.splitlines(), 1))
                                     + ("\n… Aperçu limité à 500 000 caractères." if truncated else ""))
            block = self.source.document().findBlockByNumber(max(0, line - 1))
            if block.isValid():
                cursor = QTextCursor(block)
                self.source.setTextCursor(cursor)
                selection = QTextEdit.ExtraSelection()
                selection.cursor = cursor
                selection.format.setBackground(QColor("#dff2eb"))
                selection.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
                self.source.setExtraSelections([selection])
                self.source.centerCursor()
        except (OSError, UnicodeError, LookupError, SyntaxError) as error:
            self.source.setPlainText(f"Impossible de lire le fichier :\n{error}")

    def choose_export(self, kind):
        if not self.result:
            return
        extension = "txt" if kind == "ascii" else kind
        dialog = QFileDialog(self, "Exporter les résultats")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setNameFilter(f"{kind.upper()} (*.{extension})")
        dialog.setDefaultSuffix(extension)
        dialog.selectFile(f"{Path(self.result.root).name}_{kind}.{extension}")
        if dialog.exec() and dialog.selectedFiles():
            try:
                self.export_to(dialog.selectedFiles()[0], kind)
            except Exception as error:
                QMessageBox.critical(self, "Échec de l’export", str(error))

    def export_to(self, filename, kind):
        if not self.result:
            raise ValueError("Aucun projet analysé.")
        target = Path(filename)
        # Publish only a complete export, so an error cannot truncate an older file.
        descriptor, temporary = tempfile.mkstemp(prefix=".depviz-", suffix=target.suffix, dir=target.parent)
        os.close(descriptor)
        try:
            analysis, root = self.result.analysis, self.result.root
            if kind in ("png", "svg"):
                self.graph.export_image(temporary)
            elif kind == "dot":
                content = create_dependency_graph(analysis.dependencies, analysis.module_map, root,
                                                  "dot", analysis.calls).source
                Path(temporary).write_text(content, encoding="utf-8")
            else:
                content = (format_ascii_report(analysis, root) if kind == "ascii" else
                           format_text_report(analysis.dependencies, root, analysis.calls))
                Path(temporary).write_text(content, encoding="utf-8")
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        self.statusBar().showMessage(f"Export enregistré · {target}")

    def show_help(self):
        QMessageBox.information(self, "Utiliser Depviz",
            "1. Choisissez une racine d’imports Python ou un package avec __init__.py.\n"
            "2. Réglez la profondeur et les exclusions, puis lancez l’analyse (Ctrl+R).\n"
            "3. Cliquez sur les fichiers pour explorer leurs relations.\n\n"
            "Molette : zoom · Glisser le fond : déplacer la vue · Glisser un nœud : le repositionner.\n"
            "Ctrl+F : recherche · Ctrl+0 : cadrage · Voisinage : relations directes du fichier sélectionné.\n"
            "L’onglet Appels ouvre les définitions par double-clic.\n\n"
            "PNG/SVG exportent le graphe affiché. DOT/TXT/ASCII exportent l’analyse complète.\n"
            "Le graphe affiche au maximum 500 nœuds à la fois ; utilisez la recherche et le voisinage.\n\n"
            "Analyse statique : le projet n’est pas exécuté. Les appels dynamiques, les imports * et les types "
            "d’objets ne sont pas inférés. La reconnaissance des bibliothèques installées dépend de "
            "l’environnement de l’analyseur.\n\n"
            "Version portable : aucun compte, serveur ou réglage dans le registre. Les fichiers source "
            "sont consultés en lecture seule.")

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if not self.job and len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).is_dir():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls and not self.job:
            self.open_project(urls[0].toLocalFile())
            event.acceptProposedAction()

    def closeEvent(self, event):
        if self.job and self.job.isRunning():
            self._closing = True
            self.cancel_analysis()
            event.ignore()
        else:
            event.accept()
