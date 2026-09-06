"""Background analysis; all widget mutations remain on the GUI thread."""

from dataclasses import dataclass
import time
import warnings

from PySide6.QtCore import QThread, Signal

from ..call_analyzer import analyze_project
from ..models import ProjectAnalysis
from ..parser import AnalysisWarning
from .data import ProjectGraph, build_project_graph


class AnalysisCancelled(Exception):
    pass


@dataclass
class AnalysisResult:
    root: str
    analysis: ProjectAnalysis
    graph: ProjectGraph
    diagnostics: list[str]
    elapsed: float


class AnalysisJob(QThread):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, root, depth=None, ignore=(), parent=None):
        super().__init__(parent)
        self.root, self.depth, self.ignore = root, depth, tuple(ignore)
        self._last_progress = 0.0

    def checkpoint(self, path=""):
        if self.isInterruptionRequested():
            raise AnalysisCancelled()
        now = time.monotonic()
        if now - self._last_progress > .1:
            self.progress.emit(path)
            self._last_progress = now

    def run(self):
        start = time.monotonic()
        try:
            with warnings.catch_warnings(record=True) as diagnostics:
                warnings.simplefilter("always", AnalysisWarning)
                analysis = analyze_project(self.root, self.depth, self.ignore, on_progress=self.checkpoint)
            self.checkpoint()
            graph = build_project_graph(analysis, self.root)
            self.checkpoint()
            self.completed.emit(AnalysisResult(self.root, analysis, graph,
                                              [str(item.message) for item in diagnostics],
                                              time.monotonic() - start))
        except AnalysisCancelled:
            pass
        except Exception as error:
            self.failed.emit(f"{type(error).__name__} : {error}")
