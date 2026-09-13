"""Detect a project's source language and dispatch to the matching analyser."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import warnings

from .ada_analyzer import analyze_ada_project
from .call_analyzer import analyze_project as analyze_python_project
from .models import ProjectAnalysis
from .parser import AnalysisWarning, iter_source_files


@dataclass(frozen=True)
class LanguageDetection:
    language: str
    python_files: int
    ada_files: int
    project_files: int


def detect_project_language(
    project_path: str,
    max_depth: int | None = None,
    ignore: Sequence[str] = (),
) -> LanguageDetection:
    """Choose the predominant supported source language without opening source files."""
    paths = list(iter_source_files(
        project_path, (".py", ".ads", ".adb", ".ada", ".gpr"), max_depth, ignore,
    ))
    python_files = sum(path.casefold().endswith(".py") for path in paths)
    ada_files = sum(path.casefold().endswith((".ads", ".adb", ".ada")) for path in paths)
    project_files = sum(path.casefold().endswith(".gpr") for path in paths)
    language = "ada" if (
        ada_files > python_files or (ada_files == python_files and project_files > 0)
    ) else "python"
    return LanguageDetection(language, python_files, ada_files, project_files)


def analyze_project(
    project_path: str,
    max_depth: int | None = None,
    ignore: Sequence[str] = (),
    *,
    language: str = "auto",
    on_progress: Callable[[str], None] | None = None,
) -> ProjectAnalysis:
    """Analyse a Python or Ada project, detecting the language by default."""
    if language not in {"auto", "python", "ada"}:
        raise ValueError("language must be 'auto', 'python' or 'ada'")
    detection = detect_project_language(project_path, max_depth, ignore)
    selected = detection.language if language == "auto" else language
    if language == "auto" and detection.python_files and detection.ada_files:
        warnings.warn(
            "Mixed Python/Ada project detected: analysing "
            f"{selected.title()} ({detection.python_files} Python file(s), "
            f"{detection.ada_files} Ada file(s)). Use --language to override.",
            AnalysisWarning,
            stacklevel=2,
        )
    analyser = analyze_ada_project if selected == "ada" else analyze_python_project
    result = analyser(
        project_path, max_depth, ignore, on_progress=on_progress,
    )
    result.language = selected
    return result
