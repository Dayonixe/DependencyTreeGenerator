import os
from pathlib import Path

import pytest

from src.parser import build_module_map, collect_all_dependencies


def selected_files(root, **options):
    """Both consumers must select the same real files, not just the same names."""
    deps = collect_all_dependencies(str(root), **options)
    module_map = build_module_map(str(root), **options)
    assert set(deps) == {path for paths in module_map.values() for path in paths}
    return {path.replace("\\", "/") for path in deps}


@pytest.mark.parametrize("depth,expected", [
    (0, {"main.py"}),
    (1, {"main.py", "pkg/__init__.py", "pkg/tool.py"}),
    (2, {"main.py", "pkg/__init__.py", "pkg/tool.py", "pkg/child/nested.py"}),
    (None, {"main.py", "pkg/__init__.py", "pkg/tool.py", "pkg/child/nested.py"}),
])
def test_max_depth_limits_subdirectories(make_project, depth, expected):
    root = make_project({
        "main.py": "import os\n",
        "pkg/__init__.py": "",
        "pkg/tool.py": "import sys\n",
        "pkg/child/nested.py": "import math\n",
    })
    assert selected_files(root, max_depth=depth) == expected


@pytest.mark.parametrize("patterns,excluded", [
    (["tests"], {"tests/test_main.py", "pkg/tests/test_nested.py"}),
    (["tests/"], {"tests/test_main.py", "pkg/tests/test_nested.py"}),
    (["./tests"], {"tests/test_main.py"}),
    (["test_*.py"], {"test_root.py", "pkg/test_unit.py", "tests/test_main.py", "pkg/tests/test_nested.py"}),
    (["**/test_*.py"], {"test_root.py", "pkg/test_unit.py", "tests/test_main.py", "pkg/tests/test_nested.py"}),
    (["pkg/utils.py"], {"pkg/utils.py"}),
    ([r"pkg\utils.py"], {"pkg/utils.py"}),
    (["pkg/*.py"], {"pkg/__init__.py", "pkg/utils.py", "pkg/test_unit.py"}),
    (["pkg/**"], {"pkg/__init__.py", "pkg/utils.py", "pkg/test_unit.py", "pkg/deep/utils.py", "pkg/tests/test_nested.py"}),
    (["**/tests/**"], {"tests/test_main.py", "pkg/tests/test_nested.py"}),
    (["skip.py", "pkg/utils.py"], {"skip.py", "pkg/utils.py"}),
])
def test_ignore_names_paths_and_globs(make_project, patterns, excluded):
    files = {
        name: "" for name in (
            "main.py", "skip.py", "test_root.py", "pkg/__init__.py", "pkg/utils.py",
            "pkg/test_unit.py", "pkg/deep/utils.py", "tests/test_main.py",
            "pkg/tests/test_nested.py", "tests_extra/keep.py",
        )
    }
    root = make_project(files)
    assert selected_files(root, ignore=patterns) == set(files) - excluded


def test_absolute_ignore_path_only_excludes_that_file(make_project):
    root = make_project({"skip.py": "", "pkg/skip.py": ""})
    assert selected_files(root, ignore=[str(root / "skip.py")]) == {"pkg/skip.py"}


def test_directory_only_glob_does_not_exclude_source_files(make_project):
    root = make_project({"keep.py": "", "generated.py/child.py": ""})
    assert selected_files(root, ignore=["*.py/"]) == {"keep.py"}


@pytest.mark.parametrize("pattern", ["*.py", ".", "./"])
def test_all_files_can_be_excluded(make_project, pattern):
    root = make_project({"main.py": "", "pkg/child.py": ""})
    assert selected_files(root, ignore=[pattern]) == set()


def test_ignored_and_too_deep_directories_are_not_visited(make_project, monkeypatch):
    root = make_project({
        "main.py": "",
        "pkg/tool.py": "",
        "tests/invalid.py": "def invalid(:\n",
        "pkg/deep/invalid.py": "def invalid(:\n",
    })
    forbidden = {root / "tests", root / "pkg/deep"}
    original_scandir = os.scandir

    def checked_scandir(path):
        assert Path(path) not in forbidden, f"Traversed excluded directory: {path}"
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", checked_scandir)
    assert selected_files(root, max_depth=1, ignore=["tests"]) == {"main.py", "pkg/tool.py"}


@pytest.mark.parametrize("analyse", [collect_all_dependencies, build_module_map])
def test_negative_depth_is_rejected_by_python_api(tmp_path, analyse):
    with pytest.raises(ValueError, match="non-negative"):
        analyse(str(tmp_path), max_depth=-1)
