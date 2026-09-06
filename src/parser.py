import ast
from collections.abc import Iterator, Sequence
from fnmatch import fnmatchcase
from functools import lru_cache
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


def _ignore_rules(project_path: str, patterns: Sequence[str]) -> list[tuple[str, bool, bool]]:
    rules = []
    for pattern in patterns:
        if not pattern:
            raise ValueError("Ignore patterns must not be empty")
        directory_only = pattern.endswith(("/", "\\"))
        rooted = os.path.isabs(pattern) or "/" in pattern.replace("\\", "/").rstrip("/")
        if os.path.isabs(pattern):
            try:
                pattern = os.path.relpath(pattern, project_path)
            except ValueError:  # An absolute path on another Windows drive cannot match.
                continue
        pattern = os.path.normcase(pattern).replace("\\", "/")
        while pattern.startswith("./"):
            pattern = pattern[2:]
        pattern = pattern.rstrip("/") or "."
        rules.append((pattern, directory_only, rooted))
    return rules


def _glob_matches(path: str, pattern: str) -> bool:
    """Match root-relative path segments; ** spans zero or more directories."""
    path_parts = path.split("/")
    pattern_parts = pattern.split("/")

    @lru_cache(maxsize=None)
    def match(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)
        if pattern_parts[pattern_index] == "**":
            return match(path_index, pattern_index + 1) or (
                path_index < len(path_parts) and match(path_index + 1, pattern_index)
            )
        return (
            path_index < len(path_parts)
            and fnmatchcase(path_parts[path_index], pattern_parts[pattern_index])
            and match(path_index + 1, pattern_index + 1)
        )

    return match(0, 0)


def _is_ignored(relative_path: str, rules: list[tuple[str, bool, bool]], is_directory: bool) -> bool:
    path = os.path.normcase(relative_path).replace("\\", "/")
    for pattern, directory_only, rooted in rules:
        if directory_only and not is_directory:
            continue
        if not rooted:
            if fnmatchcase(path.rsplit("/", 1)[-1], pattern):
                return True
        elif _glob_matches(path, pattern):
            return True
    return False


def iter_python_files(
    project_path: str,
    max_depth: int | None = None,
    ignore: Sequence[str] = (),
) -> Iterator[str]:
    """Walk selected sources. Root files have depth 0; None means unlimited.

    Bare ignore patterns match basenames anywhere. Patterns containing slashes
    match paths relative to the analysis root. Ignored directories are pruned.
    """
    if max_depth is not None and max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    rules = _ignore_rules(project_path, ignore)
    for root, directories, files in os.walk(project_path, onerror=_warn_unreadable):
        relative_root = os.path.relpath(root, project_path)
        if "pyvenv.cfg" in files or _is_ignored(relative_root, rules, True):
            directories[:] = []
            continue
        depth = 0 if relative_root == "." else len(Path(relative_root).parts)
        if max_depth is not None and depth >= max_depth:
            directories[:] = []
        else:
            directories[:] = sorted(
                directory for directory in directories
                if directory not in EXCLUDED_DIRECTORIES
                and not _is_ignored(
                    os.path.relpath(os.path.join(root, directory), project_path), rules, True
                )
            )
        for filename in sorted(files):
            full_path = os.path.join(root, filename)
            if filename.endswith(".py") and not _is_ignored(
                os.path.relpath(full_path, project_path), rules, False
            ):
                yield full_path


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


def collect_all_dependencies(
    project_path: str,
    max_depth: int | None = None,
    ignore: Sequence[str] = (),
) -> dict[str, list[ImportReference]]:
    """Map project-relative source paths to their structured import references."""
    return {
        os.path.relpath(filepath, project_path): extract_imports_from_file(filepath)
        for filepath in iter_python_files(project_path, max_depth, ignore)
    }


def build_module_map(
    project_path: str,
    max_depth: int | None = None,
    ignore: Sequence[str] = (),
) -> ModuleMap:
    """Index canonical module names relative to the chosen import root.

    If the root itself has __init__.py, its directory name is the package prefix.
    Packages map to __init__.py. No basename aliases or runtime imports are used.
    """
    root = Path(project_path).resolve()
    prefix = (root.name,) if (root / "__init__.py").is_file() else ()
    module_map: ModuleMap = {}
    for filepath in iter_python_files(project_path, max_depth, ignore):
        relative = Path(os.path.relpath(filepath, project_path))
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
