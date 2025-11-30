from graphviz import Digraph
import os
from .utils import (is_standard_or_external, resolve_module_name)


def build_dependency_graph(dependencies: dict[str, list[str]], module_map: dict[str, str], project_path: str, output_path: str = "output/dependency_graph", output_format: str = "png") -> None:
    """
    Generates a visual dependency graph from a dictionary of dependencies between Python files.

    This function uses Graphviz to create a directed graph representing the relationships between a project's
    files (internal nodes) and their imports (internal, standard, or external). Imports are visually
    distinguished by specific styles and colours.

    :param dependencies: Dictionary of internal dependencies.
                         Key = relative source file (e.g. 'main.py'),
                         Value = list of imported modules (e.g. ['utils', 'os'])
    :param module_map: Dictionary associating each internal module with its source path (e.g. {'utils': 'examples/project1/utils.py'})
    :param project_path: Root path of the analysed project, used to resolve internal modules
    :param output_path: Output file path (without extension) for the generated graph (default: 'output/dependency_graph')
    :param output_format: Graph output format (e.g. 'png', 'svg', 'dot') (default: 'png')
    """
    dot = Digraph(comment="Dependency Graph", format=output_format)
    dot.attr(rankdir='LR')

    # Create nodes for all source files
    for source in dependencies:
        dot.node(
            source,
            shape="ellipse",
            style="filled",
            fillcolor="#ADD8E6",
            color="#82A2AD",
            penwidth="1"
        )

    # For each file and its imports
    for source, imports in dependencies.items():
        seen_edges = set()  # To avoid duplicates

        for imp in imports:
            if is_standard_or_external(imp):  # Standard or external import
                resolved = imp
                node_style = {
                    "shape": "box",
                    "style": "filled",
                    "fillcolor": "#FECA66",
                    "color": "#BF984D",
                    "penwidth": "1"
                }
                edge_style = {
                    "style": "solid",
                    "color": "#787878"
                }

            else:  # Internal import
                resolved = resolve_module_name(imp, module_map, current_file=source, project_path=project_path)
                if resolved:
                    node_style = {
                        "shape": "ellipse",
                        "style": "filled",
                        "fillcolor": "#ADD8E6",
                        "color": "#82A2AD",
                        "penwidth": "1"
                    }
                    edge_style = {
                        "style": "solid",
                        "color": "black"
                    }
                else:  # Unknown import
                    resolved = imp
                    node_style = {
                        "shape": "box",
                        "style": "filled",
                        "fillcolor": "#F18C8C",
                        "color": "#B56969",
                        "penwidth": "1"
                    }
                    edge_style = {
                        "style": "solid",
                        "color": "#787878"
                    }

            if resolved != source and (source, resolved) not in seen_edges:
                dot.node(resolved, **node_style)
                dot.edge(source, resolved, **edge_style)
                seen_edges.add((source, resolved))

    # Backup
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    dot.render(output_path, cleanup=True)
    print(f"✅ Generated graph: {output_path}.{output_format}")
