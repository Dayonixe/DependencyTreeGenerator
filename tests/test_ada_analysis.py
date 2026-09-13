from textwrap import dedent
import warnings

from src.ada_analyzer import analyze_ada_project
from src.depviz import main
from src.desktop.data import build_project_graph, file_id
from src.output import format_ascii_report, format_text_report
from src.parser import AnalysisWarning
from src.project_analyzer import analyze_project, detect_project_language


def normal(path):
    return path.replace("\\", "/")


def path_key(mapping, expected):
    return next(path for path in mapping if normal(path) == expected)


def ada_project(make_project):
    return make_project({
        "demo.gpr": 'project Demo is\n   for Source_Dirs use ("src");\nend Demo;\n',
        "src/base.ads": dedent('''\
            package Base is
               type Root is abstract tagged null record;
               procedure Visit (Self : in Root);
            end Base;
        '''),
        "src/base.adb": dedent('''\
            package body Base is
               procedure Visit (Self : in Root) is
                  pragma Unreferenced (Self);
               begin
                  null;
               end Visit;
            end Base;
        '''),
        "src/models.ads": dedent('''\
            limited private with Base;
            package Models is
               type Child is new Base.Root with null record;
               overriding procedure Visit (Self : in Child);
               function Create return Child;
            end Models;
        '''),
        "src/models.adb": dedent('''\
            package body Models is
               procedure Visit (Self : in Child) is
                  pragma Unreferenced (Self);
               begin
                  null;
               end Visit;

               function Create return Child is
               begin
                  return (Base.Root with null record);
               end Create;
            end Models;
        '''),
        "src/renderers.ads": dedent('''\
            with Base;
            package Renderers is
               type Renderer is tagged null record;
               procedure Render (Self : Renderer; Item : Base.Root'Class);
            end Renderers;
        '''),
        "src/renderers.adb": dedent('''\
            with Models;
            package body Renderers is
               procedure Render (Self : Renderer; Item : Base.Root'Class) is
                  pragma Unreferenced (Self, Item);
                  Value : Models.Child := Models.Create;
               begin
                  Models.Visit (Value);
               end Render;
            end Renderers;
        '''),
        "src/main.adb": dedent('''\
            with Models;
            with Renderers;
            procedure Main is
               View  : Renderers.Renderer;
               Value : Models.Child := Models.Create;
            begin
               Renderers.Render (View, Value);
            end Main;
        '''),
    })


def test_detects_and_resolves_ada_project(make_project):
    root = ada_project(make_project)
    detection = detect_project_language(str(root))
    assert (detection.language, detection.python_files, detection.ada_files, detection.project_files) == (
        "ada", 0, 7, 1,
    )
    analysis = analyze_project(str(root))
    assert analysis.language == "ada"
    assert len(analysis.dependencies) == 7

    references = analysis.dependencies[path_key(analysis.dependencies, "src/models.ads")]
    assert len(references) == 1
    assert str(references[0]) == "limited private with Base"
    assert normal(references[0].resolved_file) == "src/base.ads"

    body = analysis.dependencies[path_key(analysis.dependencies, "src/models.adb")]
    assert [(str(item), normal(item.resolved_file or "")) for item in body] == [
        ("body of Models", "src/models.ads"),
    ]


def test_extracts_tagged_types_inheritance_methods_calls_and_usages(make_project):
    analysis = analyze_ada_project(str(ada_project(make_project)))
    classes = {item.name: item for item in analysis.classes}
    assert set(classes) == {"Root", "Child", "Renderer"}
    assert [(base.expression, normal(base.target_file or ""), base.target_class)
            for base in classes["Child"].bases] == [("Base.Root", "src/base.ads", "Root")]
    assert [(item.name, item.kind) for item in classes["Child"].methods] == [
        ("Visit", "procedure"), ("Create", "function"),
    ]

    calls = [(normal(item.source_file), item.caller, item.expression,
              normal(item.target_file), item.target_function) for item in analysis.calls]
    assert calls == [
        ("src/main.adb", "Main", "Models.Create", "src/models.adb", "Create"),
        ("src/main.adb", "Main", "Renderers.Render", "src/renderers.adb", "Render"),
        ("src/renderers.adb", "Render", "Models.Create", "src/models.adb", "Create"),
        ("src/renderers.adb", "Render", "Models.Visit", "src/models.adb", "Visit"),
    ]
    assert {(item.source_class, item.target_class, item.source_method)
            for item in analysis.class_usages} == {("Renderer", "Child", "Render")}


def test_ada_graph_reports_runtime_and_text_outputs(make_project):
    root = make_project({
        "console.adb": dedent('''\
            with Ada.Text_IO;
            procedure Console is
            begin
               Ada.Text_IO.Put_Line ("with Fake.Unit;"); -- with Other.Unit;
            end Console;
        '''),
    })
    analysis = analyze_project(str(root))
    graph = build_project_graph(analysis, str(root))
    assert "external:Ada.Text_IO" in graph.nodes
    assert [(edge.source, edge.target, edge.kind) for edge in graph.edges] == [
        (file_id("console.adb"), "external:Ada.Text_IO", "import"),
    ]
    text = format_text_report(
        analysis.dependencies, str(root), analysis.calls, language=analysis.language,
    )
    assert "Analysis of Ada files" in text
    assert "with Ada.Text_IO" in text
    assert "Fake.Unit" not in text and "Other.Unit" not in text
    assert "console.adb" in format_ascii_report(analysis, str(root))


def test_use_clause_resolves_unqualified_call(make_project):
    root = make_project({
        "tools.ads": "package Tools is\n   procedure Run;\nend Tools;\n",
        "tools.adb": ("package body Tools is\n   procedure Run is begin null; end Run;\n"
                      "end Tools;\n"),
        "main.adb": ("with Tools; use Tools;\nprocedure Main is\nbegin\n   Run;\n"
                     "end Main;\n"),
    })
    calls = analyze_project(str(root)).calls
    assert [(item.expression, normal(item.target_file), item.target_function) for item in calls] == [
        ("Run", "tools.adb", "Run"),
    ]


def test_interfaces_and_case_insensitive_type_extensions(make_project):
    root = make_project({
        "contracts.ads": dedent('''\
            package Contracts is
               type Root is tagged null record;
               type Printable is interface;
               type Document is new root and PRINTABLE with null record;
            end Contracts;
        '''),
    })
    classes = {item.name: item for item in analyze_project(str(root)).classes}
    assert set(classes) == {"Root", "Printable", "Document"}
    assert [(base.expression, base.target_class) for base in classes["Document"].bases] == [
        ("root", "Root"), ("PRINTABLE", "Printable"),
    ]


def test_generic_formals_are_not_units_and_combined_ada_files_are_supported(make_project):
    root = make_project({
        "generic_box.ada": dedent('''\
            generic
               with procedure Notify;
               type Value is tagged private;
            package Generic_Box is
               type Box is tagged null record;
            end Generic_Box;
        '''),
    })
    analysis = analyze_project(str(root))
    assert analysis.language == "ada"
    assert set(analysis.module_map) == {"generic_box"}
    assert analysis.dependencies == {"generic_box.ada": []}
    assert [item.name for item in analysis.classes] == ["Box"]


def test_language_override_mixed_projects_and_ada_diagnostics(make_project):
    root = make_project({
        "one.py": "import os\n",
        "a.ads": "package A is\nend A;\n",
        "a.adb": "package body A is\nend A;\n",
        "broken.adb": "procedure Broken is\nbegin\n   Put_Line ((\"oops\");\nend Broken;\n",
    })
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", AnalysisWarning)
        analysis = analyze_project(str(root))
    assert analysis.language == "ada"
    assert any("Mixed Python/Ada" in str(item.message) for item in caught)
    assert any("unclosed parenthesis" in str(item.message) for item in caught)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", AnalysisWarning)
        python = analyze_project(str(root), language="python")
    assert python.language == "python"
    assert list(python.dependencies) == ["one.py"]
    assert not caught


def test_gpr_is_an_ada_hint_and_filters_apply(make_project):
    root = make_project({
        "empty.gpr": "project Empty is end Empty;\n",
        "main.adb": "procedure Main is begin null; end Main;\n",
        "generated/hidden.ads": "package Hidden is end Hidden;\n",
    })
    assert detect_project_language(str(root), max_depth=0).language == "ada"
    analysis = analyze_project(str(root), max_depth=0)
    assert list(analysis.dependencies) == ["main.adb"]
    assert {normal(path): refs for path, refs in
            analyze_project(str(root), ignore=["*.adb"]).dependencies.items()} == {
        "generated/hidden.ads": []
    }


def test_cli_detects_ada_and_supports_the_existing_outputs(make_project, capsys):
    root = make_project({
        "library.ads": "package Library is\n   procedure Run;\nend Library;\n",
        "main.adb": ("with Library;\nprocedure Main is\nbegin\n   Library.Run;\n"
                     "end Main;\n"),
    })
    assert main(["--path", str(root), "--output", "txt"]) == 0
    text = capsys.readouterr()
    assert "Analysis of Ada files" in text.out
    assert "with Library" in text.out
    assert text.err == ""

    assert main(["--path", str(root), "--output", "dot", "--language", "ada"]) == 0
    dot = capsys.readouterr()
    assert '"main.adb" -> "library.ads"' in dot.out
    assert dot.err == ""
