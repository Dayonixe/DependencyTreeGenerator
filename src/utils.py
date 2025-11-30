import importlib.util
import os


def is_standard_or_external(module_name: str) -> bool:
    """
    Determines whether a module is standard (built-in, stdlib) or external (installed via pip).

    :param module_name: Name of the module to be checked (e.g. 'os', 'numpy', 'helpers.utils')

    :return: True if the module is standard or external, False otherwise (potentially internal)
    """
    try:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            return False

        origin = spec.origin

        # Built-in modules
        if origin in (None, 'built-in', 'frozen'):
            return True

        # Standardisation
        origin = origin.lower()

        # Standard or external modules installed
        if any(part in origin for part in [
                'site-packages',
                'dist-packages',
                'python',      # Covers pythonXY.dll, pythonXY.zip, lib-dynload, etc.
                'lib'          # Useful on Windows
            ]):
            return True

        return False

    except Exception:
        return False


def is_internal_module(module_name: str, module_map: dict[str, str]) -> bool:
    """
    Check whether a module is internal to the project (and not standard or external).

    :param module_name: Name of the module to be checked (e.g. 'utils', 'helpers.math')
    :param module_map: Dictionary of detected internal modules (e.g. 'utils' -> 'utils.py')

    :return: True if the module is considered internal, False otherwise
    """
    # If it is standard/external, it is automatically excluded
    if is_standard_or_external(module_name):
        return False

    # Otherwise, we check whether it exists in the map module (in different forms)
    if module_name in module_map:
        return True

    base = module_name.split('.')[0]
    return base in module_map


def resolve_module_name(module_name: str, module_map: dict[str, list[str]], current_file: str | None = None, project_path: str | None = None) -> str | None:
    """
    Resolves a logical module name (e.g. ‘utils’ or ‘helpers.math’) to a Python file path,
    taking into account the context of the calling file.

    :param module_name: Name of the module to be resolved (e.g. 'utils', 'helpers.math')
    :param module_map: Dictionary of detected internal modules (e.g. 'utils' -> ['src/utils.py'])
    :param current_file: Relative path of the calling source file (optional, to evaluate proximity)
    :param project_path: Project root, used to convert paths to absolute paths

    :return: Relative path of the resolved file, or None if not found
    """
    candidates = []

    def add_candidate(name):
        if name in module_map:
            for path in module_map[name]:
                candidates.append((name, path))

    add_candidate(module_name)

    parts = module_name.split('.')
    while len(parts) > 1:
        parts.pop()
        add_candidate('.'.join(parts))

    if not candidates:
        return None

    # If context is provided: choose the closest one
    if current_file and project_path:
        current_dir = os.path.abspath(os.path.join(project_path, os.path.dirname(current_file)))
        best_score = float('inf')
        best_match = None

        for _, rel_path in candidates:
            abs_path = os.path.abspath(os.path.join(project_path, rel_path))
            mod_dir = os.path.dirname(abs_path)

            try:
                distance = os.path.relpath(mod_dir, current_dir).count(os.sep)
            except ValueError:
                distance = float('inf')

            if distance < best_score:
                best_score = distance
                best_match = rel_path

        return best_match

    # Otherwise, return the first one
    return candidates[0][1]
