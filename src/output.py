import os
from pathlib import Path

from .models import ImportReference


def prepare_output_stem(output_path: str) -> str:
    """Resolve directory destinations and create parents for any output format."""
    stem = os.fspath(output_path)
    if not stem:
        raise ValueError("The export destination must not be empty")
    separators = (os.sep,) + ((os.altsep,) if os.altsep else ())
    if os.path.isdir(stem) or stem.endswith(separators):
        stem = os.path.join(stem, "dependency_graph")
    parent = os.path.dirname(stem)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return stem


def format_text_report(
    dependencies: dict[str, list[ImportReference]], project_path: str
) -> str:
    """Format the same plain-text report for stdout and UTF-8 file exports."""
    lines = [f"Analysis of Python files in: {project_path}"]
    if not dependencies:
        lines.append("\n(no Python files matched)")
    for filename, imports in dependencies.items():
        lines.extend(["", filename.replace("\\", "/")])
        lines.extend(f"  - {reference}" for reference in imports)
        if not imports:
            lines.append("  - (no imports extracted)")
    return "\n".join(lines) + "\n"


def export_text_report(report: str, output_path: str) -> str:
    filename = prepare_output_stem(output_path) + ".txt"
    Path(filename).write_text(report, encoding="utf-8")
    return filename
