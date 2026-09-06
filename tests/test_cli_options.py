from pathlib import Path
import subprocess
import sys

import pytest

from src.depviz import main


@pytest.mark.parametrize("output_format", ["txt", "dot", "ascii"])
def test_output_formats_apply_depth_and_multiple_ignore_options(make_project, capsys, output_format):
    root = make_project({
        "main.py": "import os\n",
        "skip.py": "def invalid(:\n",
        "pkg/tool.py": "import math\n",
        "pkg/generated.py": "def invalid(:\n",
        "pkg/deep/hidden.py": "def invalid(:\n",
        "tests/test_main.py": "def invalid(:\n",
    })
    assert main([
        "--path", str(root), "--output", output_format, "--max-depth", "1",
        "--ignore", "tests", "skip.py", "--ignore", "pkg/generated.py",
    ]) == 0
    output = capsys.readouterr()
    assert "main.py" in output.out and "pkg/tool.py" in output.out
    for filename in ("skip.py", "generated.py", "hidden.py", "test_main.py"):
        assert filename not in output.out
    assert output.err == ""
    if output_format == "dot":
        assert output.out.startswith("// Dependency Graph\ndigraph {")
        assert '"main.py" -> os' in output.out
        assert "Analysis of Python files" not in output.out
        assert "Generated graph" not in output.out
    else:
        assert "import os" in output.out
        assert "import math" in output.out


@pytest.mark.parametrize("output_format", ["txt", "dot", "ascii"])
def test_exported_text_matches_stdout(make_project, capsys, output_format):
    root = make_project({"main.py": "import os\n"})
    arguments = ["--path", str(root), "--output", output_format]
    assert main(arguments) == 0
    stdout = capsys.readouterr()
    assert stdout.err == ""

    assert main(arguments + ["--export", str(root / "reports") + "/"]) == 0
    exported = capsys.readouterr()
    assert exported.out == ""
    assert "Generated" in exported.err
    extension = "txt" if output_format == "ascii" else output_format
    report = root / "reports" / f"dependency_graph.{extension}"
    assert report.read_text(encoding="utf-8") == stdout.out


def test_dot_stdout_is_clean_even_when_analysis_is_partial(make_project, capsys):
    root = make_project({"main.py": "import os\n", "broken.py": "def invalid(:\n"})
    assert main(["--path", str(root), "--output", "dot"]) == 1
    output = capsys.readouterr()
    assert output.out.startswith("// Dependency Graph\ndigraph {")
    assert '"main.py" -> os' in output.out
    assert "Warning:" not in output.out
    assert "Warning:" in output.err and "broken.py" in output.err


def test_all_sources_excluded_is_a_successful_empty_report(make_project, capsys):
    root = make_project({"main.py": "def invalid(:\n"})
    assert main(["--path", str(root), "--output", "txt", "--ignore", "*.py"]) == 0
    output = capsys.readouterr()
    assert "no Python files matched" in output.out
    assert output.err == ""


def test_zero_depth_is_honoured_by_cli(make_project, capsys):
    root = make_project({"main.py": "import os\n", "pkg/invalid.py": "def invalid(:\n"})
    assert main(["--path", str(root), "--output", "txt", "--max-depth", "0"]) == 0
    output = capsys.readouterr()
    assert "main.py" in output.out
    assert "invalid.py" not in output.out
    assert output.err == ""


def test_txt_export_uses_utf8_without_third_party_packages(make_project):
    root = make_project({
        "main.py": "from caf\u00e9 import cr\u00e8me\n",
        "ignored.py": "def invalid(:\n",
        "nested/invalid.py": "def invalid(:\n",
    })
    script = Path(__file__).resolve().parents[1] / "src" / "depviz.py"
    result = subprocess.run(
        [sys.executable, "-B", "-S", str(script), "--path", ".", "--output", "txt",
         "--export", "reports/", "--max-depth", "0", "--ignore", "ignored.py"],
        cwd=str(root), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert "Generated report:" in result.stderr
    content = (root / "reports" / "dependency_graph.txt").read_bytes()
    assert "from caf\u00e9 import cr\u00e8me".encode("utf-8") in content
    assert b"invalid.py" not in content and b"ignored.py" not in content


def test_txt_export_reports_destination_errors(make_project, capsys):
    root = make_project({"main.py": "", "occupied": "a file"})
    assert main([
        "--path", str(root), "--output", "txt", "--export", str(root / "occupied/report"),
    ]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "Error exporting report:" in output.err


@pytest.mark.parametrize("arguments,option", [
    (["--output", "jpeg"], "--output"),
    (["--output", "txt", "--format", "png"], "--format"),
    (["--max-depth", "-1"], "--max-depth"),
    (["--max-depth", "1.5"], "--max-depth"),
    (["--max-depth", "invalid"], "--max-depth"),
    (["--max-depth"], "--max-depth"),
    (["--ignore"], "--ignore"),
    (["--ignore", ""], "--ignore"),
    (["--export", ""], "--export"),
])
def test_invalid_cli_arguments_fail_before_analysis(tmp_path, capsys, arguments, option):
    with pytest.raises(SystemExit) as error:
        main(["--path", str(tmp_path), *arguments])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert option in output.err
    assert "error:" in output.err
