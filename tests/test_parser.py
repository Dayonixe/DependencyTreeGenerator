import os
import pytest
from src.models import ImportReference
from src.parser import AnalysisWarning
from src.parser import (collect_all_dependencies, extract_imports_from_file, build_module_map)


@pytest.fixture
def example_project_path():
    """
    Returns the absolute path to the sample project
    """
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'examples', 'project1'))


def test_collect_all_dependencies_on_example_project(example_project_path):
    """
    Tests the collection of global dependencies for the example project.
    """
    deps = collect_all_dependencies(example_project_path)

    assert isinstance(deps, dict), "Le résultat doit être un dictionnaire"

    expected_files = {
        os.path.normpath('main.py'),
        os.path.normpath('utils.py'),
        os.path.normpath('helpers/math.py')
    }
    actual_files = {os.path.normpath(path) for path in deps.keys()}
    assert expected_files.issubset(actual_files), f"Fichiers attendus non trouvés : {actual_files}"

    # Check expected imports
    assert ImportReference('utils') in deps['main.py']
    assert ImportReference('helpers', 'math') in deps['main.py']
    assert ImportReference('os') in deps['utils.py']
    assert ImportReference('math') in deps[os.path.join('helpers', 'math.py')]


def test_extract_imports_from_file_individually(example_project_path):
    """
    Check that imports are extracted correctly in each file individually.
    """
    main_file = os.path.join(example_project_path, 'main.py')
    utils_file = os.path.join(example_project_path, 'utils.py')
    math_file = os.path.join(example_project_path, 'helpers', 'math.py')

    main_imports = extract_imports_from_file(main_file)
    assert ImportReference('utils') in main_imports
    assert ImportReference('helpers', 'math') in main_imports

    utils_imports = extract_imports_from_file(utils_file)
    assert ImportReference('os') in utils_imports

    math_imports = extract_imports_from_file(math_file)
    assert ImportReference('math') in math_imports


def test_build_module_map(example_project_path):
    """
    Check that the build_module_map function generates the correct module names.
    """
    module_map = build_module_map(example_project_path)

    # Example: helpers.math -> helpers/math.py
    assert 'helpers.math' in module_map
    assert os.path.normpath('helpers/math.py') in map(os.path.normpath, module_map['helpers.math'])

    # Example: utils -> utils.py
    assert 'utils' in module_map
    assert os.path.normpath('utils.py') in map(os.path.normpath, module_map['utils'])

    # Example: main -> main.py
    assert 'main' in module_map
    assert os.path.normpath('main.py') in map(os.path.normpath, module_map['main'])


def test_imports_preserve_symbols_aliases_and_relative_levels(make_project):
    root = make_project({"main.py": (
        "import os as operating_system, sys\n"
        "from collections import defaultdict as factory\n"
        "from .utils import VALUE\n"
        "from ..utils import VALUE\n"
        "from . import utils\n"
        "from .. import sibling\n"
        "from .utils import *\n"
    )})
    imports = extract_imports_from_file(str(root / "main.py"))
    assert imports == [
        ImportReference("os"), ImportReference("sys"),
        ImportReference("collections", "defaultdict"),
        ImportReference("utils", "VALUE", 1),
        ImportReference("utils", "VALUE", 2),
        ImportReference("", "utils", 1),
        ImportReference("", "sibling", 2),
        ImportReference("utils", "*", 1),
    ]
    assert [reference.target for reference in imports[3:]] == [
        ".utils.VALUE", "..utils.VALUE", ".utils", "..sibling", ".utils",
    ]


@pytest.mark.parametrize("content", [
    b"# coding: latin-1\n# caf\xe9\nimport os\n",
    b"\xef\xbb\xbfimport os\n",
    "# cafe with accent: \u00e9\nimport os\n".encode("utf-8"),
])
def test_source_encodings(make_project, content):
    root = make_project({"main.py": content})
    assert extract_imports_from_file(str(root / "main.py")) == [ImportReference("os")]


@pytest.mark.parametrize("content", [
    b"import os\ndef broken(:\n",
    b"# coding: no-such-encoding\nimport os\n",
    b"# coding: utf-8\n# \xff\nimport os\n",
])
def test_invalid_files_warn_and_collection_continues(make_project, content):
    root = make_project({"broken.py": content, "valid.py": "import sys\n"})
    with pytest.warns(AnalysisWarning, match="broken.py"):
        deps = collect_all_dependencies(str(root))
    assert deps["broken.py"] == []
    assert deps["valid.py"] == [ImportReference("sys")]


def test_unreadable_file_warns(tmp_path, monkeypatch):
    def deny_read(*args):
        raise PermissionError("access denied")
    monkeypatch.setattr("src.parser.tokenize.open", deny_read)
    with pytest.warns(AnalysisWarning, match="access denied"):
        assert extract_imports_from_file(str(tmp_path / "private.py")) == []


def test_walk_excludes_environments_and_caches_from_both_indexes(make_project):
    root = make_project({
        "app.py": "import os\n",
        ".venv/Lib/site-packages/vendor.py": "import sys\n",
        "venv/ignored.py": "",
        ".git/ignored.py": "",
        "__pycache__/ignored.py": "",
        "custom_environment/pyvenv.cfg": "home = /python\n",
        "custom_environment/lib/ignored.py": "",
    })
    assert collect_all_dependencies(str(root)) == {"app.py": [ImportReference("os")]}
    assert build_module_map(str(root)) == {"app": ["app.py"]}


def test_map_indexes_packages_without_short_name_aliases(make_project):
    root = make_project({
        "pkg/__init__.py": "",
        "pkg/utils.py": "",
        "pkg/child/__init__.py": "",
        "pkg/child/utils.py": "",
        "namespace/tool.py": "",
    })
    module_map = build_module_map(str(root))
    assert module_map == {
        "pkg": [os.path.normpath("pkg/__init__.py")],
        "pkg.utils": [os.path.normpath("pkg/utils.py")],
        "pkg.child": [os.path.normpath("pkg/child/__init__.py")],
        "pkg.child.utils": [os.path.normpath("pkg/child/utils.py")],
        "namespace.tool": [os.path.normpath("namespace/tool.py")],
    }


def test_selected_root_can_be_a_package(make_project):
    root = make_project({"pkg/__init__.py": "", "pkg/utils.py": ""}) / "pkg"
    assert build_module_map(str(root)) == {"pkg": ["__init__.py"], "pkg.utils": ["utils.py"]}
