import os
from textwrap import dedent

import pytest

from src.call_analyzer import analyze_project
from src.parser import AnalysisWarning


def call_targets(analysis):
    return [(call.source_file.replace("\\", "/"), call.caller, call.expression,
             call.target_file.replace("\\", "/"), call.target_function)
            for call in analysis.calls]


@pytest.mark.parametrize("statement,expression", [
    ("import tools", "tools.run"),
    ("import tools as helper", "helper.run"),
    ("from tools import run", "run"),
    ("from tools import run as execute", "execute"),
    ("from tools import run\nexecute = run", "execute"),
    ("import tools\nexecute = tools.run", "execute"),
])
def test_explicit_calls_and_aliases(make_project, statement, expression):
    root = make_project({
        "app.py": statement + f"\ndef main():\n    {expression}()\n",
        "tools.py": "def run():\n    pass\n",
    })
    analysis = analyze_project(str(root))
    assert call_targets(analysis) == [("app.py", "main", expression, "tools.py", "run")]
    call = analysis.calls[0]
    assert call.lineno == len(statement.splitlines()) + 2
    assert call.col_offset == 4
    assert call.target_lineno == 1


def test_relative_imports_packages_and_reexports(make_project):
    root = make_project({
        "app.py": "from pkg import execute as go\nimport pkg as p\ngo()\np.execute()\np.tools.run()\n",
        "pkg/__init__.py": "from .bridge import execute\nfrom . import tools\n",
        "pkg/bridge.py": "from .tools import run as execute\n",
        "pkg/tools.py": "def run():\n    pass\n",
        "pkg/child/__init__.py": "",
        "pkg/child/client.py": "from ..tools import run\nfrom .. import tools as t\nrun()\nt.run()\n",
    })
    targets = call_targets(analyze_project(str(root)))
    assert targets == [
        ("app.py", "<module>", "go", "pkg/tools.py", "run"),
        ("app.py", "<module>", "p.execute", "pkg/tools.py", "run"),
        ("app.py", "<module>", "p.tools.run", "pkg/tools.py", "run"),
        ("pkg/child/client.py", "<module>", "run", "pkg/tools.py", "run"),
        ("pkg/child/client.py", "<module>", "t.run", "pkg/tools.py", "run"),
    ]
    package = analyze_project(str(root / "pkg"))
    assert [(c.expression, c.target_file) for c in package.calls] == [
        ("run", "tools.py"), ("t.run", "tools.py"),
    ]


def test_multiple_dotted_imports_and_namespace_packages(make_project):
    root = make_project({
        "app.py": "import space.one\nimport space.two\nspace.one.run()\nspace.two.run()\n",
        "space/one.py": "def run(): pass\n",
        "space/two.py": "def run(): pass\n",
    })
    assert [target[3] for target in call_targets(analyze_project(str(root)))] == [
        "space/one.py", "space/two.py",
    ]


@pytest.mark.parametrize("body", [
    "def main(run):\n    run()",
    "def main():\n    run()\n    run = None",
    "def main():\n    run: object\n    run()",
    "def main():\n    def run(): pass\n    run()",
    "run = lambda: None\nrun()",
    "del run\nrun()",
    "if condition:\n    run = None\nrun()",
    "for run in items:\n    run()\nrun()",
    "with manager() as run:\n    run()",
    "try:\n    work()\nexcept Exception as run:\n    run()\nrun()",
    "match value:\n    case {'run': run}:\n        run()\nrun()",
    "from unknown import *\nrun()",
    "callback = lambda run: run()",
    "[run() for run in callbacks]",
])
def test_shadowed_or_ambiguous_names_are_not_attributed_to_imports(make_project, body):
    root = make_project({"app.py": "from tools import run\n" + body + "\n",
                         "tools.py": "def run(): pass\n"})
    assert analyze_project(str(root)).calls == []


def test_module_attribute_mutation_invalidates_binding(make_project):
    root = make_project({"app.py": "import tools\ntools.run = callback\ntools.run()\n",
                         "tools.py": "def run(): pass\n"})
    assert analyze_project(str(root)).calls == []


def test_nested_functions_methods_defaults_and_late_global_imports(make_project):
    root = make_project({"app.py": dedent('''\
        def outer():
            def inner():
                run()
            return inner
        class Client:
            run = None
            def method(self):
                run()
        from tools import run
        def defaults(value=run()):
            global run
            run()
        callback = lambda: run()
        [run() for item in items]
        run()
    '''), "tools.py": "def run(): pass\n"})
    assert [(c.caller, c.lineno) for c in analyze_project(str(root)).calls] == [
        ("outer.inner", 3), ("Client.method", 8), ("<module>", 10),
        ("defaults", 12), ("<module>.<lambda>", 13), ("<module>", 14), ("<module>", 15),
    ]


def test_function_local_import_does_not_leak_and_nonlocal_is_resolved(make_project):
    root = make_project({"app.py": dedent('''\
        def outer():
            from tools import run as work
            def inner():
                nonlocal work
                work()
            work()
        work()
    '''), "tools.py": "def run(): pass\n"})
    assert [(c.caller, c.lineno) for c in analyze_project(str(root)).calls] == [
        ("outer.inner", 5), ("outer", 6),
    ]


def test_async_functions_and_calls_in_branches(make_project):
    root = make_project({"app.py": dedent('''\
        async def main():
            if condition:
                from tools import run as execute
            else:
                from tools import run as execute
            await execute()
    '''), "tools.py": "async def run(): pass\n"})
    assert call_targets(analyze_project(str(root))) == [
        ("app.py", "main", "execute", "tools.py", "run"),
    ]


def test_circular_reexports_terminate_but_real_definitions_still_resolve(make_project):
    root = make_project({
        "app.py": "from a import absent, run\nabsent()\nrun()\n",
        "a.py": "from b import absent\ndef run(): pass\n",
        "b.py": "from a import absent, run\nrun()\n",
    })
    assert call_targets(analyze_project(str(root))) == [
        ("app.py", "<module>", "run", "a.py", "run"),
        ("b.py", "<module>", "run", "a.py", "run"),
    ]


def test_absolute_names_do_not_use_nearby_files_and_modules_cannot_have_children(make_project):
    root = make_project({
        "app.py": "import blocked.child\nblocked.child.run()\n",
        "blocked.py": "",
        "blocked/child.py": "def run(): pass\n",
        "pkg/client.py": "import tools\nfrom ...tools import run\ntools.run()\nrun()\n",
        "pkg/tools.py": "def run(): pass\n",
    })
    assert analyze_project(str(root)).calls == []


@pytest.mark.parametrize("options", [{"ignore": ["pkg"]}, {"max_depth": 0}])
def test_selection_filters_apply_to_call_targets(make_project, options):
    root = make_project({"app.py": "from pkg.tools import run\nrun()\n",
                         "pkg/tools.py": "def run(): pass\n"})
    analysis = analyze_project(str(root), **options)
    assert analysis.calls == []
    assert list(analysis.dependencies) == ["app.py"]
    assert analysis.module_map == {"app": ["app.py"]}


def test_calls_are_static_and_each_file_is_parsed_once(make_project, monkeypatch):
    root = make_project({
        "app.py": "from tools import run\nrun()\nraise RuntimeError('never execute')\n",
        "tools.py": "def run(): raise RuntimeError('never execute')\n",
        "broken.py": "def broken(:\n",
    })
    import src.parser as parser
    opened = []
    original = parser.tokenize.open

    def record(path):
        opened.append(os.path.basename(path))
        return original(path)

    monkeypatch.setattr(parser.tokenize, "open", record)
    with pytest.warns(AnalysisWarning, match="broken.py") as warnings:
        analysis = analyze_project(str(root))
    assert len(warnings) == 1
    assert sorted(opened) == ["app.py", "broken.py", "tools.py"]
    assert len(analysis.calls) == 1
    assert analysis.dependencies["broken.py"] == []


def test_external_dynamic_and_same_file_calls_have_no_inter_module_target(make_project):
    root = make_project({"app.py": dedent('''\
        import os
        import tools
        def local(): pass
        local()
        os.getenv('VALUE')
        getattr(tools, 'run')()
        tools.Client().run()
    '''), "tools.py": "def run(): pass\nclass Client:\n    def run(self): pass\n"})
    assert analyze_project(str(root)).calls == []
