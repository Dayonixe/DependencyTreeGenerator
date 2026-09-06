# Architecture

The command runs a static pipeline: discover source files, extract structured
imports and calls, resolve them against canonical project module names, then build/export
a directed graph. It does not import the analysed code.

| Module | Responsibility |
| --- | --- |
| `models.py` | Immutable `ImportReference(module, name, level, alias)`, `FunctionCall`, the `ModuleMap` type and `ProjectAnalysis` result. |
| `parser.py` | Shared depth/ignore filtering, declared source encodings, AST extraction, diagnostics and canonical module indexing. |
| `call_analyzer.py` | Parse each selected file once, track lexical bindings and resolve explicit calls through module exports. |
| `utils.py` | Absolute/relative resolution and standard/installed module classification from names and metadata. |
| `output.py` | Shared export paths, TXT and ASCII reports, cycle/shared-branch markers and UTF-8 text exports. |
| `graph_generator.py` | Build an inspectable `Digraph`, normalise Windows paths and export DOT or native Graphviz formats. |
| `depviz.py` | Parse/validate CLI options, route TXT/ASCII/DOT to stdout or files, export PNG and report status/errors on stderr. |

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
