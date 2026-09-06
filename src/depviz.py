import argparse
import os
import sys
import warnings

# Direct execution has no package context. Anchor imports to this repository,
# including when the script is launched by absolute path from another directory.
if __name__ == "__main__" and not __package__:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
    __package__ = "src"

from .parser import AnalysisWarning, build_module_map, collect_all_dependencies


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Static dependency analyser for Python projects.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--path", required=True,
        help="Python import root or package directory to analyse.",
    )
    parser.add_argument(
        "--export", metavar="PATH",
        help=(
            "Destination directory or filename without extension "
            "(e.g. . or output/dependencies). Omit for terminal output only."
        ),
    )
    parser.add_argument(
        "--format", default="png", choices=["png", "svg", "pdf", "dot"],
        help="Graph output format; DOT does not require the Graphviz executable.",
    )
    args = parser.parse_args(argv)
    project_path = os.path.abspath(args.path)
    if not os.path.isdir(project_path):
        print(f"Error: not a valid folder: {project_path}", file=sys.stderr)
        return 1

    print(f"Analysis of Python files in: {project_path}")
    with warnings.catch_warnings(record=True) as diagnostics:
        warnings.simplefilter("always", AnalysisWarning)
        deps = collect_all_dependencies(project_path)
        module_map = build_module_map(project_path) if args.export else {}

    for diagnostic in diagnostics:
        print(f"Warning: {diagnostic.message}", file=sys.stderr)
    for filename, imports in deps.items():
        print(f"\n{filename}")
        if imports:
            for reference in imports:
                print(f"  - {reference}")
        else:
            print("  - (no imports extracted)")

    if args.export:
        # Text-only analysis works even without the optional graphviz package.
        try:
            from graphviz import CalledProcessError, ExecutableNotFound
            from .graph_generator import build_dependency_graph
        except ImportError:
            print(
                "Error: graph export requires the graphviz Python package. "
                "Run: python -m pip install -r config/requirements.txt",
                file=sys.stderr,
            )
            return 1
        try:
            output = build_dependency_graph(
                deps, module_map, project_path, args.export, args.format
            )
        except ExecutableNotFound:
            print(
                "Error: Graphviz executable 'dot' was not found. Install Graphviz "
                "and add its bin directory to PATH, or use --format dot.",
                file=sys.stderr,
            )
            return 1
        except (OSError, CalledProcessError) as error:
            print(f"Error exporting graph: {error}", file=sys.stderr)
            return 1
        print(f"Generated graph: {output}")
    else:
        print(
            "\nTo save a graph, add --export . "
            f"(output: dependency_graph.{args.format})."
        )

    # A partial analysis is useful, but must not look like a complete success.
    return 1 if diagnostics else 0


if __name__ == "__main__":
    sys.exit(main())
