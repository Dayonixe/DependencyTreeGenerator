from pathlib import Path
import shutil

import pytest

from src.graph_generator import build_dependency_graph, create_dependency_graph
from src.models import ImportReference
from src.parser import build_module_map, collect_all_dependencies


@pytest.fixture
def graph_project(make_project):
    return make_project({
        "main.py": "import utils\nfrom helpers import math\nimport os\n",
        "utils.py": "import sys\n",
        "helpers/math.py": "import math\n",
    })


def test_graph_contains_the_exact_dependency_edges(graph_project):
    dot = create_dependency_graph(
        collect_all_dependencies(str(graph_project)),
        build_module_map(str(graph_project)), str(graph_project),
    )
    edges = {line.strip().split(" [")[0] for line in dot.body if " -> " in line}
    assert edges == {
        '"main.py" -> "utils.py"',
        '"main.py" -> "helpers/math.py"',
        '"main.py" -> os',
        '"utils.py" -> sys',
        '"helpers/math.py" -> math',
    }
    assert " -> e " not in dot.source


def test_graph_groups_external_symbols_and_preserves_unknowns(make_project):
    root = make_project({"main.py": (
        "from collections import defaultdict, Counter\n"
        "from os import getenv\n"
        "from not_installed_xyz import thing\n"
    )})
    dot = create_dependency_graph(
        collect_all_dependencies(str(root)), build_module_map(str(root)), str(root)
    )
    assert dot.source.count('"main.py" -> collections ') == 1
    assert '"main.py" -> os ' in dot.source
    assert "collections.defaultdict" not in dot.source
    assert "os.getenv" not in dot.source
    assert '"main.py" -> "not_installed_xyz.thing"' in dot.source
    collections_node = next(line for line in dot.body if line.lstrip().startswith("collections ["))
    unknown_node = next(line for line in dot.body if line.lstrip().startswith('"not_installed_xyz.thing" ['))
    assert 'fillcolor="#FECA66"' in collections_node
    assert 'fillcolor="#F18C8C"' in unknown_node


def test_graph_prioritizes_local_files_and_deduplicates_edges(make_project):
    root = make_project({
        "main.py": "import json\nfrom json import VALUE\nimport json\n",
        "json.py": "VALUE = 1\nimport json\n",
    })
    dot = create_dependency_graph(
        collect_all_dependencies(str(root)), build_module_map(str(root)), str(root)
    )
    edges = [line.strip().split(" [")[0] for line in dot.body if " -> " in line]
    assert edges == ['"main.py" -> "json.py"']


def test_graph_distinguishes_relative_and_absolute_imports(make_project):
    root = make_project({
        "utils.py": "",
        "pkg/__init__.py": "",
        "pkg/utils.py": "",
        "pkg/child/__init__.py": "",
        "pkg/child/utils.py": "",
        "pkg/child/client.py": (
            "import utils\nfrom .utils import VALUE\nfrom ..utils import VALUE\n"
        ),
    })
    dot = create_dependency_graph(
        collect_all_dependencies(str(root)), build_module_map(str(root)), str(root)
    )
    edges = {line.strip().split(" [")[0] for line in dot.body if " -> " in line}
    assert edges == {
        '"pkg/child/client.py" -> "utils.py"',
        '"pkg/child/client.py" -> "pkg/child/utils.py"',
        '"pkg/child/client.py" -> "pkg/utils.py"',
    }


def test_windows_paths_are_safe_dot_ids():
    dot = create_dependency_graph(
        {r"pkg\test.py": [ImportReference("pkg.utils")], r"pkg\utils.py": []},
        {"pkg.utils": [r"pkg\utils.py"]}, ".",
    )
    assert '"pkg/test.py" -> "pkg/utils.py"' in dot.source
    assert "\\" not in dot.source


@pytest.mark.parametrize("stem", ["graph", "nested/output/graph"])
def test_dot_export_works_without_native_graphviz(graph_project, tmp_path, monkeypatch, stem):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")
    filename = build_dependency_graph(
        collect_all_dependencies(str(graph_project)),
        build_module_map(str(graph_project)), str(graph_project),
        output_path=stem, output_format="dot",
    )
    output = Path(filename)
    assert output == Path(stem + ".dot")
    source = output.read_text(encoding="utf-8")
    assert "digraph {" in source
    assert '"main.py" -> "utils.py"' in source
    assert '"main.py" -> "helpers/math.py"' in source


@pytest.mark.parametrize("destination", [".", "existing", "existing/", "new/nested/", "absolute"])
def test_directory_export_uses_default_filename(graph_project, tmp_path, monkeypatch, destination):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")
    (tmp_path / "existing").mkdir()
    if destination == "absolute":
        destination = str(tmp_path / "existing")
    filename = build_dependency_graph(
        collect_all_dependencies(str(graph_project)),
        build_module_map(str(graph_project)), str(graph_project),
        output_path=destination, output_format="dot",
    )
    expected = Path(destination) / "dependency_graph.dot"
    assert Path(filename).resolve() == expected.resolve()
    assert '"main.py" -> "utils.py"' in expected.read_text(encoding="utf-8")
    assert not (tmp_path / "..dot").exists()


@pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz dot is not installed")
@pytest.mark.parametrize("output_format", ["png", "svg", "pdf"])
def test_native_graphviz_renders_valid_output(graph_project, tmp_path, output_format):
    filename = build_dependency_graph(
        collect_all_dependencies(str(graph_project)),
        build_module_map(str(graph_project)), str(graph_project),
        str(tmp_path / "rendered" / "graph"), output_format,
    )
    content = Path(filename).read_bytes()
    if output_format == "png":
        assert content.startswith(b"\x89PNG\r\n\x1a\n")
    elif output_format == "pdf":
        assert content.startswith(b"%PDF")
    else:
        assert b"<svg" in content
    assert not (tmp_path / "rendered" / "graph").exists()
