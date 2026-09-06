# Architecture

The command runs a static pipeline: discover source files, extract structured
imports, resolve them against canonical project module names, then build/export
a directed graph. It does not import the analysed code.

| Module | Responsibility |
| --- | --- |
| `models.py` | Immutable `ImportReference(module, name, level)` and the `ModuleMap` type. |
| `parser.py` | Shared depth/ignore filtering, declared source encodings, AST extraction, diagnostics and canonical module indexing. |
| `utils.py` | Absolute/relative resolution and standard/installed module classification from names and metadata. |
| `output.py` | Shared export paths, plain-text report formatting and UTF-8 TXT exports. |
| `graph_generator.py` | Build an inspectable `Digraph`, normalise Windows paths and export DOT or native Graphviz formats. |
| `depviz.py` | Parse/validate CLI options, route TXT/DOT to stdout or files, export PNG and report status/errors on stderr. |

The analysis root determines import names. A selected package root retains its
directory name as a prefix. `pkg/__init__.py` maps to `pkg`; nested files never get
global basename aliases. Regular packages win over same-named `.py` files, and a
plain module cannot contain submodules. Namespace directories can contain modules
without having their own file node.

`import pkg.module` resolves only that module. `from pkg import name` first looks
for a concrete submodule, then attributes the dependency to the package/module
that owns the imported symbol. Relative depth is preserved throughout resolution.
No directory-distance heuristic or runtime `find_spec()` lookup is used.

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

`--output txt` uses only the standard library. `--output dot` emits a standalone
DOT document on stdout unless an export destination is supplied. `--output png`
creates a PNG file by default. Diagnostics and file-generation notices go to
stderr so text and DOT output can be redirected without log contamination.
The legacy `--format` option is mutually exclusive with `--output`; `--export`
continues to select the destination and defaults to PNG when no format is given.
