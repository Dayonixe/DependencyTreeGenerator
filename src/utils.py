from functools import lru_cache
from importlib.metadata import packages_distributions
from pathlib import Path
import sys

from .models import ImportReference, ModuleMap


@lru_cache(maxsize=1)
def _installed_module_names() -> frozenset[str]:
    """Read distribution metadata once, without importing installed packages."""
    return frozenset(packages_distributions())


def is_standard_or_external(module_name: str) -> bool:
    """Classify an absolute module by its top-level name, without executing it.

    Callers should resolve against the project map first, so local files take
    precedence. A relative import can never refer to an external dependency.
    """
    if not module_name or module_name.startswith("."):
        return False
    root = module_name.split(".", 1)[0]
    return root in sys.stdlib_module_names or root in _installed_module_names()


def absolute_module_name(
    module_name: str,
    current_file: str | None,
    project_path: str | None,
) -> str | None:
    level = len(module_name) - len(module_name.lstrip("."))
    if not level:
        return module_name
    if current_file is None:
        return None

    # Accept either path separator for callers supplying portable relative paths.
    package = current_file.replace("\\", "/").split("/")[:-1]
    if project_path:
        root = Path(project_path).resolve()
        if (root / "__init__.py").is_file():
            package.insert(0, root.name)
    if level > len(package):
        return None
    base = package[:len(package) - level + 1]
    suffix = module_name[level:]
    return ".".join(base + ([suffix] if suffix else []))


def resolve_module_name(
    module_name: str,
    module_map: ModuleMap,
    current_file: str | None = None,
    project_path: str | None = None,
) -> str | None:
    """Resolve an exact module name, anchored at the current package if relative.

    Absolute imports use the selected project root, never directory proximity.
    Missing prefixes can be namespace packages, but a .py module cannot contain
    submodules. Symbol fallback is handled separately by resolve_import.
    """
    absolute = absolute_module_name(module_name, current_file, project_path)
    if not absolute:
        return None
    parts = absolute.split(".")
    for length in range(1, len(parts)):
        parent = module_map.get(".".join(parts[:length]), [])
        if parent and parent[0].replace("\\", "/").rsplit("/", 1)[-1] != "__init__.py":
            return None
    candidates = module_map.get(absolute, [])
    return candidates[0] if candidates else None


def resolve_import(
    reference: ImportReference,
    module_map: ModuleMap,
    current_file: str | None = None,
    project_path: str | None = None,
) -> str | None:
    """Resolve a from-import to its submodule, or to the module owning its symbol."""
    if reference.name not in (None, "*"):
        target = resolve_module_name(
            reference.target, module_map, current_file, project_path
        )
        if target is not None:
            return target
    return resolve_module_name(reference.base, module_map, current_file, project_path)


def is_internal_module(module_name: str, module_map: ModuleMap) -> bool:
    """Whether an absolute module has an exact, importable project file."""
    return resolve_module_name(module_name, module_map) is not None
