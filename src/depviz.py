import argparse
import os
import sys
import warnings

# Direct execution has no package context. Anchor imports to this repository,
# including when the script is launched by absolute path from another directory.
if __name__ == "__main__" and not __package__:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
    __package__ = "src"

from .call_analyzer import analyze_project
from .output import export_text_report, format_ascii_report, format_text_report
from .parser import AnalysisWarning


def _non_empty(value: str) -> str:
    if not value:
        raise argparse.ArgumentTypeError("must not be empty")
    return value


def _non_negative_integer(value: str) -> int:
    try:
        depth = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a non-negative integer") from None
    if depth < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return depth


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Static dependency analyser for Python projects.",
        allow_abbrev=False,
        epilog=(
            "TXT, ASCII and DOT go to stdout unless --export is supplied. PNG writes "
            "dependency_graph.png in the current directory by default. "
            "Quote ignore globs so the shell does not expand them."
        ),
    )
    parser.add_argument(
        "--path", required=True, type=_non_empty,
        help="Python import root or package directory to analyse.",
    )
    formats = parser.add_mutually_exclusive_group()
    formats.add_argument(
        "--output", choices=["dot", "png", "txt", "ascii"],
        help="Output format (txt by default; --export alone keeps the legacy png default).",
    )
    formats.add_argument(
        "--format", dest="legacy_format", choices=["png", "svg", "pdf", "dot"],
        help="Compatibility option for graph formats; use --output for dot/png/txt/ascii.",
    )
    parser.add_argument(
        "--max-depth", type=_non_negative_integer, metavar="N",
        help="Maximum subdirectory depth: 0 = root files only; omitted = unlimited.",
    )
    parser.add_argument(
        "--ignore", nargs="+", action="extend", default=[], type=_non_empty,
        metavar="PATTERN",
        help=(
            "File/directory names, root-relative paths or globs to exclude. "
            "Accepts multiple values and can be repeated."
        ),
    )
    parser.add_argument(
        "--export", metavar="PATH", type=_non_empty,
        help="Destination directory or filename without extension (e.g. . or output/dependencies).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_argument_parser().parse_args(argv)
    output_format = args.output or args.legacy_format or ("png" if args.export else "txt")
    destination = args.export
    if destination is None and output_format not in ("txt", "dot", "ascii"):
        destination = "."

    project_path = os.path.abspath(args.path)
    if not os.path.isdir(project_path):
        print(f"Error: not a valid folder: {project_path}", file=sys.stderr)
        return 1

    with warnings.catch_warnings(record=True) as diagnostics:
        warnings.simplefilter("always", AnalysisWarning)
        analysis = analyze_project(project_path, args.max_depth, args.ignore)
        deps, module_map = analysis.dependencies, analysis.module_map

    for diagnostic in diagnostics:
        print(f"Warning: {diagnostic.message}", file=sys.stderr)

    if output_format in ("txt", "ascii"):
        report = (
            format_ascii_report(analysis, project_path) if output_format == "ascii"
            else format_text_report(deps, project_path, analysis.calls)
        )
        if destination is None:
            sys.stdout.write(report)
        else:
            try:
                output = export_text_report(report, destination)
            except OSError as error:
                print(f"Error exporting report: {error}", file=sys.stderr)
                return 1
            print(f"Generated report: {output}", file=sys.stderr)
    else:
        # TXT and ASCII use only Python's standard library.
        try:
            from graphviz import CalledProcessError, ExecutableNotFound
            from .graph_generator import build_dependency_graph, create_dependency_graph
        except ImportError:
            print(
                "Error: graph output requires the graphviz Python package. "
                "Run: python -m pip install -r config/requirements.txt",
                file=sys.stderr,
            )
            return 1
        try:
            if destination is None:  # DOT on stdout must remain a valid DOT document.
                dot = create_dependency_graph(deps, module_map, project_path, "dot", analysis.calls)
                sys.stdout.write(dot.source)
            else:
                output = build_dependency_graph(
                    deps, module_map, project_path, destination, output_format, analysis.calls
                )
                print(f"Generated graph: {output}", file=sys.stderr)
        except ExecutableNotFound:
            print(
                "Error: Graphviz executable 'dot' was not found. Install Graphviz "
                "and add its bin directory to PATH, or use --output dot.",
                file=sys.stderr,
            )
            return 1
        except (OSError, CalledProcessError) as error:
            print(f"Error exporting graph: {error}", file=sys.stderr)
            return 1

    # A partial analysis is useful, but must not look like a complete success.
    return 1 if diagnostics else 0


if __name__ == "__main__":
    sys.exit(main())
