# Architecture

The command runs a static pipeline: discover source files, extract structured
imports and calls, resolve them against canonical project module names, then build/export
a directed graph. It does not import the analysed code.

| Module | Responsibility |
| --- | --- |
| `models.py` | Immutable import, function-call, class and inter-class usage records, the `ModuleMap` type and `ProjectAnalysis` result. |
| `parser.py` | Shared depth/ignore filtering, declared source encodings, AST extraction, diagnostics and canonical module indexing. |
| `call_analyzer.py` | Parse each selected file once, track lexical bindings and resolve explicit calls through module exports. |
| `utils.py` | Absolute/relative resolution and standard/installed module classification from names and metadata. |
| `output.py` | Shared export paths, TXT and ASCII reports, cycle/shared-branch markers and UTF-8 text exports. |
| `graph_generator.py` | Build an inspectable `Digraph`, normalise Windows paths and export DOT or native Graphviz formats. |
| `depviz.py` | Parse/validate CLI options, route TXT/ASCII/DOT to stdout or files, export PNG and report status/errors on stderr. |
| `desktop/data.py` | GUI graph data, display filtering and an iterative layout that condenses cycles. |
| `desktop/graph.py` | Movable Qt nodes and directed edges, pan/zoom, selection and native PNG/SVG scene exports. |
| `desktop/class_diagram.py` | Collapsible class cards, resolved inheritance arrows, layout, filtering and native PNG/SVG exports. |
| `desktop/worker.py` | Cancellable background execution of the shared analyser; delivers immutable-by-convention result snapshots. |
| `desktop/window.py` | Project controls, file tree, graph, calls table, source inspector, diagnostics and export dialogs. |
| `depviz_gui.py` | Optional Qt entry point, packaged startup and smoke verification. |

The analysis root determines import names. A selected package root retains its
directory name as a prefix. `pkg/__init__.py` maps to `pkg`; nested files never get
global basename aliases. Regular packages win over same-named `.py` files, and a
plain module cannot contain submodules. Namespace directories can contain modules
without having their own file node.

`import pkg.module` resolves only that module. `from pkg import name` first looks
for a concrete submodule, then attributes the dependency to the package/module
that owns the imported symbol. Relative depth is preserved throughout resolution.
No directory-distance heuristic or runtime `find_spec()` lookup is used.

Call analysis tracks imported bindings and simple aliases per scope. Function
bodies are visited after their enclosing scope is indexed so late global imports
and closures can resolve. Local assignments and arguments mask outer imports;
branches retain only bindings on which all alternatives agree. Re-export resolution
follows explicit imports to their function definitions, with guards for circular
references. Only calls with known definitions in other selected files are emitted.
This does not execute code or infer object types and dynamic call targets.

The same AST scan records class definitions, their direct methods and their written
base expressions. Base bindings resolve through local definitions, explicit imports,
aliases and package re-exports; generic bases such as `Base[T]` resolve to `Base`.
Calls made inside methods are also matched to known project classes, including direct
construction and calls through a class attribute. Each resulting usage keeps its
source class, method, expression and line. Calls from module scope and self-references
do not create class-usage relations. Unresolved and external parents stay visible as
labels but do not create project-class arrows. Nested class names retain their enclosing
scope.

ASCII walks the import graph iteratively, expanding each file once. Active ancestors
are marked `[cycle]`; previously expanded targets are marked `[already shown]`.
Disconnected components and isolated files remain visible. Calls are grouped by
source function below each file. Graphviz uses solid import edges and purple dashed
call edges, with labels identifying functions and call-site lines.

Unresolved absolute imports are classified using `sys.stdlib_module_names` and
cached `importlib.metadata.packages_distributions()` data. Relative imports never
become external dependencies. Internal source matches take precedence.

Tests inspect exact DOT edges independently of rendering. DOT export writes the
source directly, while PNG/SVG/PDF integration tests invoke `dot` when available.

Source depth is the number of subdirectories below the analysis root (root = 0).
Both source collection and module indexing use the same walker and filters.
Ignore rules match basenames or anchored paths; glob matching is segment-based,
with `**` spanning zero or more segments. Directory exclusions and depth limits
prune traversal before nested source files are opened.

`--output txt` and `--output ascii` use only the standard library and export `.txt`
files. `--output dot` emits a standalone
DOT document on stdout unless an export destination is supplied. `--output png`
creates a PNG file by default. Diagnostics and file-generation notices go to
stderr so text and DOT output can be redirected without log contamination.
The legacy `--format` option is mutually exclusive with `--output`; `--export`
continues to select the destination and defaults to PNG when no format is given.

The CLI never imports Qt. The optional desktop entry point consumes `ProjectAnalysis`
from `analyze_project()` with an optional `on_progress` callback for cancellation
checkpoints. A `QThread` owns analysis work; widgets are updated through queued Qt
signals on the main thread. Cancelling or closing requests interruption and waits
for the next checkpoint instead of terminating a thread during parsing.

Display filters affect the Qt views, not the analysis snapshot. The dependency scene
is bounded to 500 nodes and the class scene to 300 cards; both use the shared iterative
layout. Directory selection, depth and ignore rules are shared with the CLI. PNG/SVG
exports render the active Qt scene directly; full DOT/TXT/ASCII exports reuse the
existing report generators. The portable Windows build is a PyInstaller folder ZIP,
with Qt libraries, example data, sources and third-party notices alongside the app.
