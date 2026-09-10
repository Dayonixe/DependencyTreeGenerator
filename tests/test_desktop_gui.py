import os
from pathlib import Path
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", reason="Install config/requirements-gui.txt for desktop tests")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QFontDatabase, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from src.call_analyzer import analyze_project
from src.desktop.class_diagram import class_id
from src.desktop.data import build_project_graph, file_id
from src.desktop.window import MainWindow
from src.desktop.theme import configure_application
from src.desktop.worker import AnalysisJob, AnalysisResult


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    configure_application(app)
    if os.name == "nt":
        for name in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name))
    return app


@pytest.fixture
def gui_project(make_project):
    return make_project({
        "app.py": "from pkg import run\nimport os\ndef main():\n    run()\n",
        "pkg/__init__.py": "from .tools import run\n",
        "pkg/tools.py": ("def run():\n    pass\n\n"
                         "class Service:\n    def execute(self, value):\n        return value\n\n"
                         "    def create_worker(self):\n        return Worker()\n\n"
                         "class Worker(Service):\n    @staticmethod\n    def name():\n        return 'worker'\n\n"
                         "    async def execute_async(self, value):\n        return value\n\n"
                         "class Standalone:\n    pass\n"),
        "isolated.py": "",
    })


def wait_for(predicate, timeout=10000):
    start = time.monotonic()
    while not predicate() and (time.monotonic() - start) * 1000 < timeout:
        QTest.qWait(10)
        # qWait's C++ loop can retain the GIL on Windows. Yield it explicitly so
        # Python worker threads can finish between event-processing iterations.
        time.sleep(.001)
    if not predicate():
        import faulthandler
        faulthandler.dump_traceback()
    assert predicate(), "Qt operation did not complete before the timeout"


@pytest.fixture
def window(app, gui_project):
    widget = MainWindow()
    widget.show()
    widget.open_project(str(gui_project))
    wait_for(lambda: widget.job is None)
    assert widget.result is not None
    yield widget
    widget.close()
    if widget.job:
        wait_for(lambda: widget.job is None)
    widget.deleteLater()
    app.processEvents()


def test_worker_ui_matches_shared_analysis(window, gui_project):
    expected = analyze_project(str(gui_project))
    assert window.result.analysis == expected
    assert [label.text() for label in window.stat_labels] == ["4", "3", "1", "0"]
    assert window.calls_table.rowCount() == 1
    assert window.tabs.tabText(1) == "Classes (3)"
    assert len(window.class_diagram.cards) == 3
    assert len(window.class_diagram.edges) == 2
    assert {edge.kind for edge in window.class_diagram.edges} == {"inheritance", "usage"}
    assert len(window.graph.nodes) == 4
    assert window.export_button.isEnabled() and window.analyze_button.isEnabled()
    assert not window.progress.isVisible()


def test_graph_selection_drag_zoom_and_filters(window):
    item = window.graph.nodes[file_id("app.py")]
    point = window.graph.mapFromScene(item.sceneBoundingRect().center())
    QTest.mouseClick(window.graph.viewport(), Qt.MouseButton.LeftButton, pos=point)
    assert window.selected == file_id("app.py")
    assert window.outgoing.count() == 3
    assert "app.py" in window.node_title.text()
    edge = item.edges[0]
    before = edge.path().pointAtPercent(0)
    item.setPos(item.pos() + QPointF(30, 15))
    moved_position = QPointF(item.pos())
    assert edge.path().pointAtPercent(0) != before
    before_zoom = window.graph.transform().m11()
    window.graph.zoom(1.2)
    assert window.graph.transform().m11() > before_zoom
    window.calls_check.setChecked(False)
    assert all(edge.edge.kind != "call" for edge in window.graph.connections)
    assert window.graph.nodes[file_id("app.py")].pos() == moved_position
    window.external_check.setChecked(True)
    assert "external:os" in window.graph.nodes
    window.focus_check.setChecked(True)
    assert file_id("isolated.py") not in window.graph.nodes
    window.calls_check.setChecked(True)
    window.search.setText("TOOLS")
    wait_for(lambda: list(window.graph.nodes) == [file_id("pkg/tools.py")])


def test_tree_and_call_navigation_open_definition(window):
    window.tree.setCurrentItem(window._tree_items[file_id("app.py")])
    assert window.selected == file_id("app.py")
    assert "from pkg import run" in window.source.toPlainText()
    window.tabs.setCurrentIndex(2)
    QTest.qWait(50)
    rect = window.calls_table.visualItemRect(window.calls_table.item(0, 0))
    assert rect.isValid()
    QTest.mouseClick(window.calls_table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    QTest.mouseDClick(window.calls_table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    assert window.selected == file_id("pkg/tools.py")
    assert "def run():" in window.source.toPlainText()
    assert window.detail_tabs.currentIndex() == 1
    assert window.source.textCursor().blockNumber() == 0


def test_class_diagram_is_collapsed_and_opens_methods(window, app):
    window.class_diagram.resetTransform()
    window.class_diagram.scale(2.4, 2.4)
    window.tabs.setCurrentWidget(window.class_page)
    app.processEvents()
    fitted_zoom = window.class_diagram.transform().m11()
    assert fitted_zoom <= 1.3
    window.class_diagram.zoom(1.2)
    chosen_zoom = window.class_diagram.transform().m11()
    window.tabs.setCurrentIndex(0)
    window.tabs.setCurrentWidget(window.class_page)
    app.processEvents()
    assert window.class_diagram.transform().m11() == pytest.approx(chosen_zoom)

    service = window.class_diagram.cards[class_id("pkg/tools.py", "Service")]
    worker = window.class_diagram.cards[class_id("pkg/tools.py", "Worker")]
    standalone = window.class_diagram.cards[class_id("pkg/tools.py", "Standalone")]
    assert not service.expanded and not worker.expanded and not standalone.expanded
    service.setPos(service.pos() + QPointF(80, 45))
    moved_positions = {key: QPointF(card.pos()) for key, card in window.class_diagram.cards.items()}
    collapsed_height = worker.height

    window.detail_tabs.setCurrentIndex(0)
    point = window.class_diagram.mapFromScene(worker.sceneBoundingRect().center())
    QTest.mouseClick(window.class_diagram.viewport(), Qt.MouseButton.LeftButton, pos=point)
    assert worker.expanded
    assert worker.height > collapsed_height
    assert {key: card.pos() for key, card in window.class_diagram.cards.items()} == moved_positions
    assert service.opacity() == 1
    assert worker.opacity() == 1
    assert standalone.opacity() == pytest.approx(.38)
    assert all(edge.opacity() == 1 for edge in window.class_diagram.edges)
    assert "Classe Worker" == window.node_title.text()
    assert window.out_heading.text() == "RELATIONS DE CLASSE · 1"
    assert window.in_heading.text() == "MÉTHODES · 2"
    assert window.source.textCursor().blockNumber() == 10
    assert window.detail_tabs.currentIndex() == 0

    window.detail_tabs.setCurrentIndex(1)
    window._class_selected(service.info)
    assert window.out_heading.text() == "RELATIONS DE CLASSE · 1"
    assert "UTILISE" in window.outgoing.item(0).text()
    assert "Worker" in window.outgoing.item(0).text()
    assert window.detail_tabs.currentIndex() == 1

    window.class_diagram.set_all_expanded(True)
    assert all(card.expanded for card in window.class_diagram.cards.values())
    assert {key: card.pos() for key, card in window.class_diagram.cards.items()} == moved_positions
    window.class_diagram.set_all_expanded(False)
    assert all(not card.expanded for card in window.class_diagram.cards.values())
    assert {key: card.pos() for key, card in window.class_diagram.cards.items()} == moved_positions

    expected = window.class_diagram._automatic_positions()[class_id("pkg/tools.py", "Service")]
    QTest.mouseClick(window.class_relayout_button, Qt.MouseButton.LeftButton)
    assert service.pos() == expected


@pytest.mark.parametrize("kind", ["png", "svg"])
def test_class_diagram_export_uses_the_displayed_state(window, gui_project, kind):
    window.tabs.setCurrentWidget(window.class_page)
    window.class_diagram.set_all_expanded(True)
    target = gui_project / ("classes." + kind)
    window.export_to(str(target), kind)
    if kind == "png":
        assert not QImage(str(target)).isNull()
    else:
        assert b"<svg" in target.read_bytes()


@pytest.mark.parametrize("kind", ["png", "svg", "dot", "txt", "ascii"])
def test_exports_use_snapshot_and_do_not_need_native_graphviz(window, gui_project, monkeypatch, kind):
    monkeypatch.setenv("PATH", "")
    window.path_edit.setText("another/unanalysed/project")
    window.search.setText("app.py")
    window.refresh_graph()
    target = gui_project / ("export.txt" if kind == "ascii" else "export." + kind)
    window.export_to(str(target), kind)
    content = target.read_bytes()
    if kind == "png":
        assert not QImage(str(target)).isNull()
    elif kind == "svg":
        assert b"<svg" in content
    elif kind == "dot":
        assert b"digraph" in content and b"pkg/tools.py" in content
    else:
        assert b"pkg/tools.py" in content and b"another/unanalysed/project" not in content
    assert not list(gui_project.glob(".depviz-*"))


def test_export_failure_preserves_existing_file(window, gui_project, monkeypatch):
    target = gui_project / "export.png"
    target.write_bytes(b"previous content")

    def fail(filename):
        Path(filename).write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(window.graph, "export_image", fail)
    with pytest.raises(OSError, match="disk full"):
        window.export_to(str(target), "png")
    assert target.read_bytes() == b"previous content"
    assert not list(gui_project.glob(".depviz-*"))


def test_invalid_folder_is_actionable_and_does_not_discard_results(window, monkeypatch):
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    previous = window.result
    window.path_edit.setText("")
    window.start_analysis()
    assert messages and window.result is previous and window.job is None


def test_partial_analysis_and_filters_are_reported(window, gui_project):
    (gui_project / "broken.py").write_text("def broken(:", encoding="utf-8")
    window.ignore.setPlainText("pkg\nisolated.py")
    window.depth.setValue(0)
    window.start_analysis()
    wait_for(lambda: window.job is None)
    assert set(window.result.analysis.dependencies) == {"app.py", "broken.py"}
    assert window.result.analysis.calls == []
    assert "broken.py" in window.diagnostics.toPlainText()
    assert window.stat_labels[3].text() == "1"
    assert "partielle" in window.statusBar().currentMessage()


def test_cancel_and_close_are_cooperative(window, monkeypatch):
    import src.desktop.worker as worker

    def slow_analysis(root, depth, ignore, *, on_progress):
        for i in range(300):
            time.sleep(.005)
            on_progress(str(i))
        raise AssertionError("cancellation did not interrupt the worker")

    monkeypatch.setattr(worker, "analyze_project", slow_analysis)
    previous = window.result
    window.start_analysis()
    assert not window.analyze_button.isEnabled()
    QTest.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
    wait_for(lambda: window.job is None)
    assert window.result is previous
    assert "annulée" in window.statusBar().currentMessage()
    window.start_analysis()
    window.close()
    wait_for(lambda: window.job is None)
    assert not window.isVisible()


def test_empty_project_and_large_display_limit(window, gui_project):
    window.ignore.setPlainText("*.py")
    window.start_analysis()
    wait_for(lambda: window.job is None)
    assert window.result.analysis.dependencies == {}
    assert not window.graph.nodes
    assert not window.class_diagram.cards
    assert window.tabs.tabText(1) == "Classes (0)"
    assert window.stat_labels[0].text() == "0"
    from src.models import ProjectAnalysis
    analysis = ProjectAnalysis({f"file{i}.py": [] for i in range(510)}, {}, [])
    graph = build_project_graph(analysis, str(gui_project))
    window.accept_result(AnalysisResult(str(gui_project), analysis, graph, [], .1))
    assert len(window.graph.nodes) == 500
    assert "510" in window.graph_notice.text()
    assert len(window.result.analysis.dependencies) == 510
