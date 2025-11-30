import argparse
import os
import sys
from .parser import (collect_all_dependencies, build_module_map)
from .graph_generator import build_dependency_graph

def main():
    # Configuring command line arguments
    parser = argparse.ArgumentParser(
        description="Internal dependency analyser for Python projects.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "--path",
        required=True,
        help="Path to the Python project directory to be analysed."
    )

    parser.add_argument(
        "--export",
        metavar="PATH",
        help="Path (without extension) to export the graph (e.g. ./output/dependencies)."
    )

    parser.add_argument(
        "--format",
        default="png",
        choices=["png", "svg", "pdf", "dot"],
        help="Graph output format (default: png)."
    )

    args = parser.parse_args()
    project_path = os.path.abspath(args.path)

    if not os.path.isdir(project_path):
        print(f"❌ The specified path is not a valid folder: {project_path}")
        sys.exit(1)

    # Analyse des dépendances
    print(f"🔍 Analysis of Python files in: {project_path}\n")
    deps = collect_all_dependencies(project_path)
    module_map = build_module_map(project_path)

    # Affichage simple des dépendances
    for file, imports in deps.items():
        print(f"\n📄 {file}")
        if imports:
            for imp in imports:
                print(f"  └── import {imp}")
        else:
            print("  └── (no import)")

    if args.export:
        print("\n🛠️ Graph generation...")
        build_dependency_graph(
            deps,
            module_map,
            project_path,
            output_path=args.export,
            output_format=args.format
        )

if __name__ == "__main__":
    main()
