# Guide manual

Team : Théo Pirouelle

<a href="https://www.python.org/">
  <img src="https://img.shields.io/badge/language-python-blue?style=flat-square" alt="laguage-python" />
</a>

![TestsResult](https://github.com/Dayonixe/DependencyTreeGenerator/actions/workflows/python-tests.yml/badge.svg)

---

## Installation

> [!NOTE]
> For information, the code has been developed and works with the following library versions:
> | Library | Version |
> | --- | --- |
> | pytest | 8.4.2 |
> | graphviz | 0.21 |

Python 3.10 or newer is required. From the repository root, install the Python dependencies:

```bash
python -m pip install -r config/requirements.txt
```

PNG, SVG and PDF exports also require the native [Graphviz application](https://graphviz.org/download/).
On Debian/Ubuntu, install it with `sudo apt install graphviz`. On Windows, install the
Graphviz Windows package and add its `bin` directory to `PATH`. Check the installation
with `dot -V` from a new terminal.

Text analysis uses only Python's standard library. DOT export requires the Python
`graphviz` package, but does not require the native `dot` executable.

---

## User manual

### Graphical desktop application

Depviz also provides a portable Windows desktop application: interactive dependency
graph, search and display filters, project file tree, function-call navigation,
read-only source inspector, cancellable background analysis and PNG/SVG/DOT/TXT/ASCII
exports. The portable ZIP includes Python and Qt and needs no native Graphviz.

```bash
python -m pip install -r config/requirements-gui.txt
python -m src.depviz_gui --path examples/advanced
```

See the [desktop guide](docs/desktop.md) for controls, portable builds and tests.

### Command-line application

Run from the repository root with either entry point:

```bash
python3 src/depviz.py --path examples/project1/ --output txt
python3 -m src.depviz --path examples/project1/ --output txt
python3 src/depviz.py -h
```

Use `python` instead of `python3` if that is your interpreter's command name.
The script also works by absolute path from another directory. The analysis and
export paths are relative to the current working directory.

| Option | Behaviour |
| --- | --- |
| `--path PATH` | Required Python import root or package directory. |
| `--output {dot,png,txt,ascii}` | TXT by default. TXT/ASCII/DOT go to stdout; PNG creates `dependency_graph.png` in the current directory. |
| `--max-depth N` | Non-negative subdirectory depth: 0 = root files, 1 = root and immediate subdirectories. Omit for unlimited depth. |
| `--ignore PATTERN [PATTERN ...]` | Exclude file/directory names, paths or globs. Accepts multiple values and repeated occurrences. |
| `--export PATH` | Write the selected format to a directory or filename without extension instead of stdout/the default PNG destination. |
| `--format {png,svg,pdf,dot}` | Compatibility option for existing commands. Cannot be combined with `--output`. |

Analyse two directory levels, excluding tests and generated Python files:

```bash
python3 src/depviz.py --path . --output txt --max-depth 2 --ignore tests "generated_*.py"
```

Produce DOT for a pipe or shell redirection. Progress and errors use stderr, so
stdout contains only the requested TXT/ASCII report or DOT document:

```bash
python3 src/depviz.py --path examples/project1/ --output dot > dependencies.dot
```

Create a PNG, or save a text report:

```bash
python3 src/depviz.py --path examples/project1/ --output png
python3 src/depviz.py --path examples/project1/ --output png --export output/
python3 src/depviz.py --path examples/project1/ --output txt --export output/report
```

These commands write `dependency_graph.png`, `output/dependency_graph.png`
and `output/report.txt`, respectively. TXT output and export need only Python's
standard library. DOT requires the Python `graphviz` package; PNG also requires
the native `dot` executable.

An existing directory passed to `--export` receives `dependency_graph.<format>`.
To create a new destination directory, end its path with `/`.
Otherwise, the path is a filename without extension. Parent directories are
created automatically. Text files are encoded as UTF-8.

Existing commands such as `--export . --format png` continue to work.
For compatibility, `--export` alone still selects PNG; use `--output txt`
explicitly when saving a text report.

### Depth and exclusions

Depth counts source directories, not dependency-graph hops. For example,
`main.py` has depth 0, `pkg/tool.py` depth 1 and `pkg/sub/tool.py`
depth 2. The same limits apply to file collection and module indexing.
Directories beyond the limit or matched by an exclusion are not traversed.

Ignore patterns supplement the built-in exclusions:

- A bare name such as `tests` matches files or directories with that basename anywhere.
- A root-relative path such as `pkg/generated.py` excludes that specific path.
  Prefix a root-level name with `./` to anchor it, e.g. `./tests`.
- `*`, `?` and character classes match within one path segment.
  `**` spans zero or more directories: `**/test_*.py` also matches root-level tests.
- A trailing `/` matches directories only. Absolute paths are also accepted.
- Quote globs to prevent your shell from expanding them before the CLI receives them.

```bash
python3 src/depviz.py --path . --output dot --max-depth 3 --ignore tests .venv --ignore "pkg/generated/**" --export output/
```

Imports written in retained files remain in the report even when their targets
are outside the selected files. Those targets are unresolved in the graph unless
recognised as standard or installed dependencies. Excluded files have no source
nodes or outgoing edges. An empty selection is a successful empty report.

### Resolution and diagnostics

`--path` defines the import root. For `repo/src/my_package`, choose `--path repo/src`
when imports start with `my_package`. You can also select a package directory that
contains `__init__.py`; its folder name becomes the package prefix.

Absolute imports resolve from that root. Relative imports retain their number of
leading dots and resolve from the importing file's package. Packages map to their
`__init__.py`, and same-named files in unrelated directories are not interchangeable.
Nested standalone scripts must be analysed with their own import root.

Project files are resolved first. Standard modules are recognised by Python's
standard-library name index, and installed dependencies by distribution metadata in
the interpreter running the analyser. No project or dependency package is imported
to discover it. Uninstalled dependencies remain unknown. The graph uses blue for
internal files, yellow for standard/installed modules, and red for unresolved imports.
Solid edges represent imports; purple dashed edges represent resolved function calls.

Virtual environments, version-control directories and common caches are excluded
from both source collection and module indexing. Environments with custom folder
names are also excluded when they contain `pyvenv.cfg`.

Python encoding declarations and UTF-8 BOMs are honoured. Unreadable or invalid files
produce a diagnostic on stderr while the other files are still analysed. Requested
exports can therefore be partial; the command returns exit code 1 if any source
could not be analysed or an export failed, and 0 after a complete successful analysis.
Invalid CLI arguments (including negative depths and unsupported formats) return exit code 2.

This is a static graph of explicit imports and function calls, including imports inside
functions and conditional blocks. Dynamic imports, changes to `sys.path`, custom
import hooks and runtime re-exports are not evaluated. A namespace package without
an `__init__.py` has no single file node, although its concrete submodules resolve.

### Function calls and ASCII view

The analyser follows explicit calls to functions defined in other selected project
files, including `module.function()`, imported functions, aliases and simple alias
assignments. Relative imports and explicit re-exports through `__init__.py` resolve
to the file containing the function definition. Function-local imports, parameters
and local assignments are taken into account when resolving a name.

Try the package example:

```bash
python3 src/depviz.py --path examples/advanced/ --output ascii
python3 src/depviz.py --path examples/advanced/ --output ascii --export output/tree
python3 src/depviz.py --path examples/advanced/ --output png --export output/calls
```

An excerpt of the terminal view:

```text
|-- app.py
|   |-- from toolkit import calculate as compute -> toolkit/__init__.py
|   |   `-- from .operations import calculate -> toolkit/operations.py
|   |       |-- from .helpers import numbers -> toolkit/helpers/numbers.py
|   |       `-- calls
|   |           `-- calculate
|   |               `-- numbers.add() -> toolkit/helpers/numbers.py:add() [line 5; definition 1]
```

ASCII indents dependency branches and groups calls by their containing function
(or `<module>` for top-level code). Each call shows its expression, destination,
source line and definition line. `[cycle]` stops circular branches and
`[already shown]` avoids expanding shared dependencies again. Isolated files are
included. ASCII export writes a UTF-8 `.txt` file, such as `output/tree.txt`, and
requires only Python's standard library. `--output txt` keeps the flat import
listing and adds calls below each source file.

Call resolution is static, not an execution trace. It does not infer instance types,
resolve constructors or methods through objects, expand wildcard imports, or follow
`getattr`, callbacks passed as parameters and other dynamically selected callables.
External function definitions and calls within the same file are omitted from the
inter-module call list. Ambiguous bindings after conditional statements are omitted;
runtime mutation and execution order can still affect the actual targets. Calls to
excluded files are omitted because those definitions are outside the analysis index.

### Python API

`extract_imports_from_file()` now returns `ImportReference` objects instead of strings.
Each reference stores `module`, `name` (for a from-import), `level` (relative depth)
and `alias` (the optional `as` name). `reference.binding` gives its local name.
`collect_all_dependencies()` returns these lists indexed by relative file path.
Use `str(reference)` to display the import statement or `reference.target` for its
qualified target. Module maps consistently use `dict[str, list[str]]`.
Both `collect_all_dependencies()` and `build_module_map()` accept
`max_depth=None` and `ignore=()` keyword arguments for the same source selection.

`create_dependency_graph()` returns a Graphviz `Digraph` for inspection without
rendering. `build_dependency_graph()` exports it and returns the output filename.
Both accept an optional `calls` sequence.

`analyze_project()` in `src.call_analyzer` parses each selected file once and returns
a `ProjectAnalysis` containing `dependencies`, `module_map` and `calls`. Each
`FunctionCall` records `source_file`, `caller`, `expression`, `lineno`, `col_offset`,
`target_file`, `target_function` and `target_lineno`. Lines are one-based; the column
is the AST's zero-based UTF-8 byte offset. It accepts the same `max_depth` and `ignore`
filters. Pass the result to `format_ascii_report(analysis, project_path)` for an ASCII
string, or pass its calls to `format_text_report(dependencies, project_path, calls)`.

### Tests

```bash
python -m pytest tests/
```

The tests cover exact import destinations and graph edges, package discovery,
side-effect-free analysis, call aliases and scopes, relative re-exports, ASCII cycles
and shared branches, encodings, depth limits, ignore patterns, clean stdout/stderr,
argument validation, diagnostics and CLI exports.
PNG/SVG/PDF integration tests are skipped locally when `dot` is unavailable.
CI installs and checks Graphviz before running tests on Linux (Python 3.10–3.12)
and Windows (Python 3.12).

---

## Result

Here is an example of the results achieved with this project:
<img src="docs/graph.png" alt="graph" />
