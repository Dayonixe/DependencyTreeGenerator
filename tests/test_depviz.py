import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from graphviz import ExecutableNotFound

from src.depviz import main


def test_cli_exports_dot_with_bare_filename(make_project, monkeypatch, capsys):
    root = make_project({"main.py": "from os import getenv\n"})
    monkeypatch.chdir(root)
    monkeypatch.setenv("PATH", "")
    result = main(["--path", str(root), "--export", "graph", "--format", "dot"])
    assert result == 0
    assert (root / "graph.dot").is_file()
    output = capsys.readouterr()
    assert "from os import getenv" in output.out
    assert "Generated graph:" in output.out
    assert output.err == ""


def test_cli_without_export_explains_how_to_save_a_graph(make_project, monkeypatch, capsys):
    root = make_project({"main.py": "import os\n"})
    monkeypatch.chdir(root)
    assert main(["--path", "."]) == 0
    output = capsys.readouterr()
    assert "import os" in output.out
    assert "To save a graph, add --export ." in output.out
    assert "dependency_graph.png" in output.out
    assert output.err == ""
    assert sorted(path.name for path in root.iterdir()) == ["main.py"]


@pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz dot is not installed")
def test_direct_execution_exports_png_to_current_directory(make_project):
    root = make_project({"examples/project1/main.py": "import os\n"})
    script = Path(__file__).resolve().parents[1] / "src" / "depviz.py"
    result = subprocess.run(
        [sys.executable, "-B", str(script), "--path", "examples/project1/",
         "--export", ".", "--format", "png"],
        cwd=str(root), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Generated graph:" in result.stdout
    assert "dependency_graph.png" in result.stdout
    assert result.stderr == ""
    assert (root / "dependency_graph.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_cli_reports_invalid_directory(tmp_path, capsys):
    assert main(["--path", str(tmp_path / "missing")]) == 1
    assert "not a valid folder" in capsys.readouterr().err


def test_cli_reports_partial_analysis_and_still_exports(make_project, tmp_path, capsys):
    root = make_project({"broken.py": "def broken(:\n", "valid.py": "import os\n"})
    result = main([
        "--path", str(root), "--export", str(tmp_path / "partial"), "--format", "dot",
    ])
    assert result == 1
    output = capsys.readouterr()
    assert "Warning:" in output.err and "broken.py" in output.err
    assert "import os" in output.out
    assert '"valid.py" -> os' in (tmp_path / "partial.dot").read_text(encoding="utf-8")


def test_cli_reports_missing_graphviz_without_traceback(make_project, monkeypatch, capsys):
    root = make_project({"main.py": ""})

    def fail_render(*args, **kwargs):
        raise ExecutableNotFound(["dot"])

    monkeypatch.setattr("src.graph_generator.Digraph.render", fail_render)
    assert main(["--path", str(root), "--export", str(root / "graph")]) == 1
    output = capsys.readouterr()
    assert "Graphviz executable 'dot' was not found" in output.err
    assert "--format dot" in output.err
    assert "Traceback" not in output.err


def test_cli_reports_unwritable_export(make_project, capsys):
    root = make_project({"main.py": "", "occupied": "a file, not a directory"})
    assert main([
        "--path", str(root), "--export", str(root / "occupied" / "graph"), "--format", "dot",
    ]) == 1
    assert "Error exporting graph:" in capsys.readouterr().err


@pytest.mark.parametrize("entrypoint", [("-m", "src.depviz"), ("src/depviz.py",)])
def test_text_analysis_needs_no_third_party_packages_and_handles_legacy_output(make_project, entrypoint):
    root = make_project({"main.py": "import os\n"})
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-B", "-S", *entrypoint, "--path", str(root)],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=environment, capture_output=True, text=True, encoding="cp1252",
    )
    assert result.returncode == 0, result.stderr
    assert "import os" in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize("entrypoint", [("-m", "src.depviz"), ("src/depviz.py",)])
def test_help_works_for_both_entrypoints_without_dependencies(entrypoint):
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-B", "-S", *entrypoint, "-h"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=environment, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    assert "--path" in result.stdout
    assert "--export" in result.stdout
    assert result.stderr == ""


def test_direct_execution_exports_from_another_working_directory(make_project):
    root = make_project({
        "main.py": "import os\n",
        "src/__init__.py": "raise AssertionError('wrong src package imported')\n",
    })
    script = Path(__file__).resolve().parents[1] / "src" / "depviz.py"
    result = subprocess.run(
        [sys.executable, "-B", str(script), "--path", ".",
         "--export", "graph", "--format", "dot"],
        cwd=str(root), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Generated graph:" in result.stdout
    assert result.stderr == ""
    assert '"main.py" -> os' in (root / "graph.dot").read_text(encoding="utf-8")
