import pytest
import os
from src.utils import (is_standard_or_external, is_internal_module, resolve_module_name)


# ----------------------------------------------------------------------------
# Tests pour is_standard_or_external
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("module_name,expected", [
    ("os", True),                  # module standard
    ("math", True),                # module built-in
    ("importlib", True),           # module standard
    ("pytest", True),              # module externe installé (si dispo)
    ("nonexistentmodulexyz", False),  # module inconnu
])
def test_is_standard_or_external(module_name, expected):
    assert is_standard_or_external(module_name) == expected



# ----------------------------------------------------------------------------
# Tests pour is_internal_module
# ----------------------------------------------------------------------------

def test_is_internal_module_exact_match():
    module_map = {
        "utils": ["src/utils.py"],
        "helpers.math": ["helpers/math.py"],
    }
    assert is_internal_module("utils", module_map) is True
    assert is_internal_module("helpers.math", module_map) is True


def test_is_internal_module_partial_match():
    module_map = {
        "helpers": ["helpers/__init__.py"]
    }
    assert is_internal_module("helpers.math", module_map) is True


def test_is_internal_module_external_module():
    module_map = {
        "utils": ["src/utils.py"]
    }
    assert is_internal_module("os", module_map) is False
    assert is_internal_module("numpy", module_map) is False



# ----------------------------------------------------------------------------
# Tests pour resolve_module_name
# ----------------------------------------------------------------------------

def test_resolve_module_name_basic_match():
    module_map = {
        "utils": ["src/utils.py"]
    }
    result = resolve_module_name("utils", module_map)
    assert result == "src/utils.py"


def test_resolve_module_name_partial_fallback():
    module_map = {
        "helpers": ["helpers/__init__.py"]
    }
    result = resolve_module_name("helpers.math", module_map)
    assert result == "helpers/__init__.py"


def test_resolve_module_name_none():
    module_map = {
        "utils": ["src/utils.py"]
    }
    result = resolve_module_name("unknown", module_map)
    assert result is None


def test_resolve_module_name_context_closest():
    module_map = {
        "utils": ["src/utils.py", "other/utils.py"]
    }
    current_file = "examples/project1/main.py"
    project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    result = resolve_module_name("utils", module_map, current_file=current_file, project_path=project_path)

    assert result in {"src/utils.py", "other/utils.py"}  # L’un des deux doit être sélectionné
