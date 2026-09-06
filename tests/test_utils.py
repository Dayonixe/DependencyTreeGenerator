import os
import sys

import pytest

from src.models import ImportReference
from src.parser import build_module_map
from src.utils import (
    _installed_module_names,
    is_internal_module,
    is_standard_or_external,
    resolve_import,
    resolve_module_name,
)


@pytest.mark.parametrize("module_name,expected", [
    ("os", True),
    ("math", True),
    ("importlib", True),
    ("collections.defaultdict", True),
    ("os.getenv", True),
    ("pytest", True),
    ("pytest.fixture", True),
    ("nonexistentmodulexyz", False),
    (".os", False),
    ("", False),
])
def test_is_standard_or_external(module_name, expected):
    assert is_standard_or_external(module_name) is expected


def test_analysis_never_imports_project_or_dependency_packages(make_project, monkeypatch):
    root = make_project({
        "review_local/__init__.py": "raise AssertionError('project code executed')\n",
        "review_local/child.py": "",
        "review_dependency/__init__.py": "raise AssertionError('dependency code executed')\n",
        "review_dependency-1.0.dist-info/METADATA": (
            "Metadata-Version: 2.1\nName: review-dependency\nVersion: 1.0\n"
        ),
        "review_dependency-1.0.dist-info/top_level.txt": "review_dependency\n",
    })
    monkeypatch.syspath_prepend(str(root))

    def forbid_find_spec(*args, **kwargs):
        raise AssertionError("find_spec must not be used during static analysis")

    monkeypatch.setattr("importlib.util.find_spec", forbid_find_spec)
    _installed_module_names.cache_clear()
    try:
        module_map = build_module_map(str(root))
        assert module_map["review_local.child"] == [os.path.normpath("review_local/child.py")]
        assert is_standard_or_external("review_local.child") is False
        assert is_standard_or_external("review_dependency.function") is True
        assert "review_local" not in sys.modules
        assert "review_dependency" not in sys.modules
    finally:
        _installed_module_names.cache_clear()


def test_library_folder_name_does_not_make_local_module_external(make_project, monkeypatch):
    root = make_project({"my_python_library/review_internal.py": "VALUE = 1\n"})
    monkeypatch.syspath_prepend(str(root / "my_python_library"))
    assert is_standard_or_external("review_internal") is False
    assert "my_python_library.review_internal" in build_module_map(str(root))


@pytest.fixture
def package_project(make_project):
    return make_project({
        "utils.py": "VALUE = 0\n",
        "pkg/__init__.py": "VALUE = 1\n",
        "pkg/utils.py": "VALUE = 2\n",
        "pkg/child/__init__.py": "",
        "pkg/child/utils.py": "VALUE = 3\n",
        "pkg/child/client.py": "",
    })


@pytest.mark.parametrize("reference,expected", [
    (ImportReference("utils"), "utils.py"),
    (ImportReference("utils", "VALUE", 1), "pkg/child/utils.py"),
    (ImportReference("utils", "VALUE", 2), "pkg/utils.py"),
    (ImportReference("", "utils", 1), "pkg/child/utils.py"),
    (ImportReference("", "utils", 2), "pkg/utils.py"),
    (ImportReference("utils", "*", 1), "pkg/child/utils.py"),
    (ImportReference("pkg"), "pkg/__init__.py"),
    (ImportReference("pkg", "VALUE"), "pkg/__init__.py"),
    (ImportReference("pkg", "utils"), "pkg/utils.py"),
    (ImportReference("pkg.child.utils", "VALUE"), "pkg/child/utils.py"),
    (ImportReference("pkg.missing"), None),
    (ImportReference("pkg.missing", "VALUE"), None),
    (ImportReference("utils", "VALUE", 3), None),
    (ImportReference("os", "getenv", 3), None),
])
def test_import_resolution_is_anchored_to_the_root_and_package(package_project, reference, expected):
    result = resolve_import(
        reference, build_module_map(str(package_project)),
        "pkg/child/client.py", str(package_project),
    )
    assert result == (os.path.normpath(expected) if expected else None)


def test_relative_import_from_package_initializer(package_project):
    result = resolve_import(
        ImportReference("", "utils", 1), build_module_map(str(package_project)),
        "pkg/child/__init__.py", str(package_project),
    )
    assert result == os.path.normpath("pkg/child/utils.py")


def test_relative_import_when_selected_root_is_package(package_project):
    root = package_project / "pkg"
    module_map = build_module_map(str(root))
    assert resolve_import(
        ImportReference("utils", "VALUE", 2), module_map, "child/client.py", str(root)
    ) == "utils.py"
    assert resolve_import(
        ImportReference("", "utils", 1), module_map, "__init__.py", str(root)
    ) == "utils.py"
    assert resolve_import(
        ImportReference("utils", "VALUE", 2), module_map, "__init__.py", str(root)
    ) is None


def test_relative_import_without_package_context_is_unknown():
    module_map = {"utils": ["utils.py"]}
    assert resolve_module_name(".utils", module_map) is None
    assert resolve_module_name(".utils", module_map, "main.py") is None


def test_exact_module_does_not_fall_back_to_package_or_symbol_owner(package_project):
    module_map = build_module_map(str(package_project))
    assert resolve_module_name("pkg.child.utils", module_map) == os.path.normpath("pkg/child/utils.py")
    assert resolve_module_name("pkg.child.utils.VALUE", module_map) is None
    assert resolve_module_name("pkg.nonexistent", module_map) is None


def test_local_modules_take_precedence_over_external_names():
    module_map = {"json": ["json.py"], "pytest": ["pytest.py"]}
    assert is_internal_module("json", module_map) is True
    assert is_internal_module("pytest", module_map) is True
    assert is_internal_module("os", module_map) is False
    assert is_internal_module("unknown", module_map) is False


def test_regular_package_wins_over_same_named_module(make_project):
    root = make_project({"pkg.py": "", "pkg/__init__.py": "", "pkg/child.py": ""})
    module_map = build_module_map(str(root))
    assert resolve_module_name("pkg", module_map) == os.path.normpath("pkg/__init__.py")
    assert resolve_module_name("pkg.child", module_map) == os.path.normpath("pkg/child.py")


def test_module_blocks_same_named_namespace_submodules(make_project):
    root = make_project({"pkg.py": "", "pkg/child.py": ""})
    module_map = build_module_map(str(root))
    assert resolve_module_name("pkg", module_map) == "pkg.py"
    assert resolve_module_name("pkg.child", module_map) is None


def test_namespace_package_can_contain_modules(make_project):
    root = make_project({"namespace/tool.py": "", "namespace/client.py": ""})
    module_map = build_module_map(str(root))
    assert resolve_module_name("namespace.tool", module_map) == os.path.normpath("namespace/tool.py")
    assert resolve_import(
        ImportReference("", "tool", 1), module_map, "namespace/client.py", str(root)
    ) == os.path.normpath("namespace/tool.py")


def test_windows_package_paths_resolve_on_every_platform():
    module_map = {"pkg": [r"pkg\__init__.py"], "pkg.utils": [r"pkg\utils.py"]}
    assert resolve_module_name("pkg.utils", module_map) == r"pkg\utils.py"
