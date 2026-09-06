import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from src.call_analyzer import analyze_project
from src.depviz import main
from src.graph_generator import build_dependency_graph, create_dependency_graph
from src.models import ImportReference, ProjectAnalysis
from src.output import format_ascii_report


@pytest.fixture
def call_project(make_project):
    return make_project({
        "app.py": "from pkg import run as execute\ndef main():\n    execute()\n    execute()\n",
        "pkg/__init__.py": "from .tools import run\n",
        "pkg/tools.py": "def run():\n    pass\n",
    })


def test_ascii_indentation_resolved_imports_and_calls(call_project):
    analysis = analyze_project(str(call_project))
    assert format_ascii_report(analysis, str(call_project)) == (
        f"Dependency tree: {call_project}\n"
        "`-- app.py\n"
        "    |-- from pkg import run as execute -> pkg/__init__.py\n"
        "    |   `-- from .tools import run -> pkg/tools.py\n"
        "    `-- calls\n"
        "        `-- main\n"
        "            |-- execute() -> pkg/tools.py:run() [line 3; definition 1]\n"
        "            `-- execute() -> pkg/tools.py:run() [line 4; definition 1]\n"
    )


def test_ascii_covers_cycles_shared_dependencies_and_isolated_files(make_project):
    root = make_project({
        "a.py": "import b\nimport shared\n",
        "b.py": "import a\nimport shared\n",
        "shared.py": "import os\n",
        "isolated.py": "",
        "unknown.py": "from missing_xyz_123 import run\n",
    })
    report = format_ascii_report(analyze_project(str(root)), str(root))
    assert report.count("[cycle]") == 1
    assert report.count("[already shown]") == 1
    assert "import a -> a.py [cycle]" in report
    assert "import shared -> shared.py [already shown]" in report
    assert "import os [external]" in report
    assert "from missing_xyz_123 import run [unresolved]" in report
    assert "|-- isolated.py\n" in report
    assert len(report.splitlines()) == 10


def test_ascii_empty_selection(make_project):
    root = make_project({"app.py": ""})
    report = format_ascii_report(analyze_project(str(root), ignore=["*.py"]), str(root))
    assert report.endswith("\n(no Python files matched)\n")


def test_ascii_deep_chains_do_not_use_python_recursion():
    length = 1050
    dependencies = {f"m{i}.py": [ImportReference(f"m{i + 1}")] for i in range(length - 1)}
    dependencies[f"m{length - 1}.py"] = []
    module_map = {f"m{i}": [f"m{i}.py"] for i in range(length)}
    report = format_ascii_report(ProjectAnalysis(dependencies, module_map, []), ".")
    assert len(report.splitlines()) == length + 1
    assert report.endswith(f"import m{length - 1} -> m{length - 1}.py\n")


@pytest.mark.parametrize("output_format", ["txt", "ascii", "dot"])
def test_cli_includes_calls_and_keeps_stdout_clean(call_project, capsys, output_format):
    assert main(["--path", str(call_project), "--output", output_format]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert "run()" in output.out
    assert "line 3" in output.out and "line 4" in output.out
    if output_format == "dot":
        assert output.out.startswith("// Dependency Graph\ndigraph {")
        assert "style=dashed" in output.out
    else:
        assert "execute() -> pkg/tools.py:run()" in output.out


@pytest.mark.parametrize("export", [False, True])
def test_ascii_works_without_third_party_dependencies(call_project, export):
    script = Path(__file__).resolve().parents[1] / "src/depviz.py"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-B", "-S", str(script), "--path", ".", "--output", "ascii",
         *(["--export", "reports/"] if export else [])],
        cwd=call_project, env=environment, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    if export:
        assert result.stdout == ""
        assert "Generated report:" in result.stderr
        report = (call_project / "reports/dependency_graph.txt").read_text(encoding="utf-8")
    else:
        assert result.stderr == ""
        assert not (call_project / "dependency_graph.png").exists()
        report = result.stdout
    assert "execute() -> pkg/tools.py:run()" in report


def test_graph_separates_import_edges_from_calls_to_actual_definitions(call_project):
    analysis = analyze_project(str(call_project))
    dot = create_dependency_graph(analysis.dependencies, analysis.module_map, str(call_project),
                                  calls=analysis.calls)
    edges = [line for line in dot.body if " -> " in line]
    assert len(edges) == 3
    assert any('"app.py" -> "pkg/__init__.py"' in edge and "style=solid" in edge for edge in edges)
    call_edge = next(edge for edge in edges if "style=dashed" in edge)
    assert '"app.py" -> "pkg/tools.py"' in call_edge
    assert "run() [line 3]" in call_edge and "run() [line 4]" in call_edge


@pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz dot is not installed")
def test_native_graph_with_function_calls_renders(call_project):
    analysis = analyze_project(str(call_project))
    filename = build_dependency_graph(
        analysis.dependencies, analysis.module_map, str(call_project),
        str(call_project / "calls"), "svg", calls=analysis.calls,
    )
    svg = Path(filename).read_text(encoding="utf-8")
    assert "<svg" in svg and "stroke-dasharray" in svg
    assert "run() [line 3]" in svg
