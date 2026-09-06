import os

from graphviz import Digraph

from .models import ImportReference, ModuleMap
from .utils import is_standard_or_external, resolve_import


INTERNAL_STYLE = {
    "shape": "ellipse", "style": "filled", "fillcolor": "#ADD8E6",
    "color": "#82A2AD", "penwidth": "1",
}
EXTERNAL_STYLE = {
    "shape": "box", "style": "filled", "fillcolor": "#FECA66",
    "color": "#BF984D", "penwidth": "1",
}
UNKNOWN_STYLE = {
    "shape": "box", "style": "filled", "fillcolor": "#F18C8C",
    "color": "#B56969", "penwidth": "1",
}


def create_dependency_graph(
    dependencies: dict[str, list[ImportReference]],
    module_map: ModuleMap,
    project_path: str,
    output_format: str = "png",
) -> Digraph:
    """Build an inspectable graph without writing files or invoking Graphviz."""
    dot = Digraph(comment="Dependency Graph", format=output_format)
    dot.attr(rankdir="LR")

    # Forward slashes avoid DOT escape sequences such as \t in Windows paths.
    def file_id(path: str) -> str:
        return path.replace("\\", "/")

    for source in dependencies:
        dot.node(file_id(source), **INTERNAL_STYLE)

    for source, imports in dependencies.items():
        seen_edges = set()
        for reference in imports:
            internal = resolve_import(reference, module_map, source, project_path)
            if internal is not None:
                resolved = file_id(internal)
                node_style = INTERNAL_STYLE
                edge_color = "black"
            elif is_standard_or_external(reference.base):
                resolved = reference.module
                node_style = EXTERNAL_STYLE
                edge_color = "#787878"
            else:
                resolved = reference.target
                node_style = UNKNOWN_STYLE
                edge_color = "#787878"

            source_id = file_id(source)
            if resolved != source_id and resolved not in seen_edges:
                dot.node(resolved, **node_style)
                dot.edge(source_id, resolved, style="solid", color=edge_color)
                seen_edges.add(resolved)
    return dot


def build_dependency_graph(
    dependencies: dict[str, list[ImportReference]],
    module_map: ModuleMap,
    project_path: str,
    output_path: str = "output/dependency_graph",
    output_format: str = "png",
) -> str:
    """Export the graph; DOT source needs no native Graphviz executable.

    output_path is a filename stem or a destination directory. Existing
    directories and paths ending in a separator use the stem dependency_graph.
    Returns the actual output filename and lets the CLI report rendering errors.
    """
    dot = create_dependency_graph(dependencies, module_map, project_path, output_format)
    output_path = os.fspath(output_path)
    separators = (os.sep,) + ((os.altsep,) if os.altsep else ())
    if os.path.isdir(output_path) or output_path.endswith(separators):
        output_path = os.path.join(output_path, "dependency_graph")
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if output_format == "dot":
        return dot.save(filename=output_path + ".dot")
    return dot.render(output_path, cleanup=True)
