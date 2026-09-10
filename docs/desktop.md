# Depviz Desktop 1.1.0

Depviz Desktop is a portable graphical explorer for Python project dependencies.
It uses the same static import and inter-module call analysis as the CLI.

## Windows portable application

Extract the entire `Depviz-1.1.0-windows-amd64-portable.zip` archive, then double-click
`Depviz/Depviz.exe`. Keep the executable and its `_internal` directory together.
Python, Qt and the required Python libraries are included. No installer, administrator
account, network service or native Graphviz installation is needed to use the GUI.
No application settings are written to the registry; the current session stays in
memory. Exported reports are written only to the location you choose.

This build targets Windows 10/11 x64. The Python sources can also be run with Qt on other
desktop systems; this release's packaged executable is for Windows.

## Explore a project

1. Click **Choisir un dossier…**, drop a project folder onto the window, or click
   **Ouvrir l’exemple** to load the included package example.
2. Choose the directory depth: **Illimitée** visits all selected subdirectories;
   **0** visits only the root. Enter one exclusion pattern per line. The syntax
   matches the CLI's `--ignore`, including `tests`, `pkg/generated.py` and `**/test_*.py`.
3. Click **Analyser le projet**. Analysis runs in a background thread. **Annuler
   l’analyse** interrupts it between files and during call-resolution checkpoints.
4. Select files in the tree or graph. The inspector shows outgoing dependencies,
   incoming references and read-only source code. Select a relation to follow it.
5. Open **Classes** to inspect class inheritance. Classes start collapsed; click one
   to display or hide its methods and open its source definition in the inspector.
6. Use **Appels** to inspect resolved function calls. Double-click a row to open the
   function definition and highlight its line in the inspector's **Code** tab.

The project root has the same meaning as `--path` in the CLI: select a Python import
root, or a package directory with `__init__.py`. The analysed code is never imported
or executed. Existing CLI commands remain available.

## Graph controls

| Control | Action |
| --- | --- |
| Mouse wheel / `+` / `−` | Zoom in or out. |
| Drag the background | Pan the view. |
| Drag a node | Reposition it; its arrows follow. |
| **Cadrer** / Ctrl+0 | Fit the visible graph to the viewport. |
| **Réorganiser** | Restore the automatic dependency layout. |
| **Imports** / **Appels** | Toggle solid import edges and purple dashed call edges. |
| **Externes** | Include external libraries and unresolved imports. |
| **Voisinage** | Show the selected node and its direct incoming/outgoing neighbors. |
| Search / Ctrl+F | Filter file and module names, and search the calls table. |
| Ctrl+O / Ctrl+R | Choose a project / analyse again. |

Hover over an edge or inspector relation to see the import statements or call sites.
Green nodes are project files, amber nodes are standard/installed modules, and red
nodes are unresolved imports. Cyclic and disconnected components remain navigable.

The **Classes** tab displays each Python class as a movable card. Hollow grey arrows
point to parent classes. Purple dashed arrows show classes used by methods, including
constructors and calls through a class such as `Formatter.create()`. Hover over a
relation to see the source method, expression and line. Method compartments are collapsed
initially to keep large diagrams compact; use **Tout déplier** and **Tout replier** to
change every card. The first opening frames the complete diagram; later tab changes keep
the chosen zoom. Moving a card, or opening and closing any method compartment, preserves
every manual position. Use **Réorganiser** to restore the automatic layout. Selecting a
class keeps it and its direct relations visible while unrelated cards and arrows are
dimmed. The inspector remains on its current **Relations** or **Code** tab. The shared
search field matches class names, source files, methods and base names. The class view
renders at most 300 matching classes at once.

The graph renders at most **500 nodes at a time**. A notice reports the number shown
and the total matching the view filters. Narrow the search or select a file in the
tree and enable **Voisinage** to explore larger projects. This display limit does not
truncate the analysis or the complete text/DOT exports. The source preview reads up
to 500,000 characters per file, without modifying it.

## Export

The **Exporter** menu offers:

- **PNG / SVG**: the dependency graph or class diagram currently displayed, including
  expanded method compartments, view filters and moved node positions. Qt renders
  these directly; no native `dot` executable is needed.
  Raster output is bounded to 8,192 pixels per side and 28 million pixels overall.
- **DOT**: the complete analysed graph, using the existing CLI graph generator.
- **TXT**: the complete flat import and function-call report.
- **ASCII**: the complete indented dependency tree, saved as UTF-8 `.txt`.

Exports use the last completed analysis, even if the path/options have since been
edited. Source errors produce a partial result with visible diagnostics. Exports of
that result are partial too. An export is replaced only after its new content is
fully written.

The static-analysis limits described in the main README also apply: dynamic imports,
`getattr`, wildcard resolution, callbacks and inferred object types are not evaluated.
External-library classification uses the analyser's own installed distribution
metadata; the portable executable does not inspect a project's virtual environment.

## Run from Python

Python 3.10+:

```bash
python -m pip install -r config/requirements-gui.txt
python -m src.depviz_gui
python src/depviz_gui.py --path examples/advanced
```

On Windows, `launch_gui.pyw` is also a double-click entry point when Python and the
GUI dependencies are installed. The CLI dependencies remain separate: installing
`config/requirements.txt` alone does not install Qt.

## Build the Windows ZIP

Run on Windows x64 with Python 3.12 or newer:

```powershell
python -m venv .venv-gui
.venv-gui/Scripts/python.exe -m pip install -r config/requirements-build.txt
.venv-gui/Scripts/python.exe scripts/build_portable.py
```

The build creates `dist/Depviz/`, a ZIP and a `.zip.sha256` checksum. It packages the
example project, source code, this guide and third-party notices alongside the Qt
libraries. Build inputs and outputs are ignored by Git. PyInstaller bundles the
interpreter for the platform on which it runs; it is not a cross-compiler.
See the [PyInstaller documentation](https://pyinstaller.org/en/stable/operating-mode.html)
and [Qt for Python documentation](https://doc.qt.io/qtforpython-6/gettingstarted.html).
For startup troubleshooting, add `--console` to create a diagnostic console build.
The checked-in `config/depviz.spec` keeps Qt's Windows ICU dependency supplied by
the operating system, avoiding incompatible DLLs from a build interpreter's directory.

The `Build portable desktop` GitHub Actions workflow runs desktop tests, builds the
ZIP, launches the packaged application against its bundled example, checks all five
export formats, and uploads the ZIP and checksum as workflow artifacts. It does not
publish a GitHub release.

## Tests

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.venv-gui/Scripts/python.exe -m pytest tests/
.venv-gui/Scripts/python.exe -m src.depviz_gui --smoke-test output/gui-smoke
```

Desktop tests require the optional Qt dependencies. Existing native Graphviz tests
still require `dot`; the GUI exporters do not. The smoke-test directory contains the
dependency and class diagram exports, `window.png` and `smoke.json`. A frozen build can
run the same check with `dist/Depviz/Depviz.exe --smoke-test output/portable-smoke`.
