import ast
from collections.abc import Iterator
import os
from pathlib import Path
import tokenize
import warnings

from .models import ImportReference, ModuleMap


EXCLUDED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", ".env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".nox", "node_modules", "site-packages", "dist-packages",
})


class AnalysisWarning(UserWarning):
    """A source file or directory could not be analysed."""


def _warn_unreadable(error: OSError) -> None:
    warnings.warn(f"Cannot read {error.filename}: {error}", AnalysisWarning, stacklevel=2)


def iter_python_files(project_path: str) -> Iterator[str]:
    """Walk sources deterministically, pruning caches and virtual environments."""
    for root, directories, files in os.walk(project_path, onerror=_warn_unreadable):
        if "pyvenv.cfg" in files:
            directories[:] = []
            continue
        directories[:] = sorted(
            directory for directory in directories
            if directory not in EXCLUDED_DIRECTORIES
        )
        for filename in sorted(files):
            if filename.endswith(".py"):
                yield os.path.join(root, filename)


def extract_imports_from_file(filepath: str) -> list[ImportReference]:
    """Read Python's declared source encoding and extract imports without execution.

    Unreadable or invalid files emit AnalysisWarning and contribute no imports;
    collection continues so one bad file does not discard the rest of a project.
    """
    try:
        with tokenize.open(filepath) as source:
            tree = ast.parse(source.read(), filename=filepath)
    except (OSError, SyntaxError, UnicodeError, LookupError) as error:
        warnings.warn(
            f"Cannot analyse {filepath}: {error}", AnalysisWarning, stacklevel=2
        )
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(ImportReference(alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.extend(
                ImportReference(node.module or "", alias.name, node.level)
                for alias in node.names
            )
    return imports


def collect_all_dependencies(project_path: str) -> dict[str, list[ImportReference]]:
    """Map project-relative source paths to their structured import references."""
    return {
        os.path.relpath(filepath, project_path): extract_imports_from_file(filepath)
        for filepath in iter_python_files(project_path)
    }


def build_module_map(project_path: str) -> ModuleMap:
    """Index canonical module names relative to the chosen import root.

    If the root itself has __init__.py, its directory name is the package prefix.
    Packages map to __init__.py. No basename aliases or runtime imports are used.
    """
    root = Path(project_path).resolve()
    prefix = (root.name,) if (root / "__init__.py").is_file() else ()
    module_map: ModuleMap = {}
    for filepath in iter_python_files(str(root)):
        relative = Path(filepath).relative_to(root)
        parts = relative.with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        name = ".".join(prefix + parts)
        if name:
            module_map.setdefault(name, []).append(str(relative))

    # Python prefers a regular package over a same-named .py module.
    for candidates in module_map.values():
        candidates.sort(key=lambda path: (Path(path).name != "__init__.py", path))
    return module_map
