"""Presentation data and deterministic layout, independent of the GUI toolkit."""

from collections import defaultdict, deque
from dataclasses import dataclass

from ..models import ProjectAnalysis
from ..utils import is_standard_or_external, resolve_import


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    kind: str
    path: str | None = None


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    kind: str
    labels: tuple[str, ...]


@dataclass
class ProjectGraph:
    nodes: dict[str, Node]
    edges: list[Edge]


def file_id(path: str) -> str:
    return "file:" + path.replace("\\", "/")


def build_project_graph(analysis: ProjectAnalysis, root: str) -> ProjectGraph:
    nodes = {file_id(path): Node(file_id(path), path.replace("\\", "/"), "internal", path)
             for path in analysis.dependencies}
    grouped = defaultdict(list)
    for source, imports in analysis.dependencies.items():
        for ref in imports:
            target = resolve_import(ref, analysis.module_map, source, root)
            if target in analysis.dependencies:
                target_id = file_id(target)
            else:
                known = is_standard_or_external(ref.base)
                label = ref.module if known else ref.target
                kind = "external" if known else "unknown"
                target_id = f"{kind}:{label}"
                nodes[target_id] = Node(target_id, label, kind)
            grouped[(file_id(source), target_id, "import")].append(str(ref))
    for call in analysis.calls:
        grouped[(file_id(call.source_file), file_id(call.target_file), "call")].append(
            f"{call.caller} : {call.expression}() → {call.target_function}() · ligne {call.lineno}"
        )
    edges = [Edge(source, target, kind, tuple(dict.fromkeys(labels)))
             for (source, target, kind), labels in sorted(grouped.items())]
    return ProjectGraph(nodes, edges)


def select_graph(graph: ProjectGraph, *, imports=True, calls=True, external=False,
                 query="", focus: str | None = None, limit=500) -> tuple[ProjectGraph, int]:
    """Filter the display only; the full analysis remains available for reports."""
    nodes = {key: node for key, node in graph.nodes.items()
             if external or node.kind == "internal"}
    edges = [edge for edge in graph.edges if (imports if edge.kind == "import" else calls)]
    if focus:
        neighbors = {focus}
        for edge in edges:
            if focus in (edge.source, edge.target):
                neighbors.update((edge.source, edge.target))
        nodes = {key: node for key, node in nodes.items() if key in neighbors}
    if query.strip():
        query = query.strip().casefold()
        nodes = {key: node for key, node in nodes.items() if query in node.label.casefold()}
    total = len(nodes)
    nodes = dict(sorted(nodes.items(), key=lambda item: (item[0] != focus, item[1].label))[:limit])
    edges = [edge for edge in edges if edge.source in nodes and edge.target in nodes]
    return ProjectGraph(nodes, edges), total


def layered_layout(graph: ProjectGraph) -> dict[str, tuple[float, float]]:
    """Condense cycles, then place dependency levels from left to right.

    Iterative Kosaraju traversal avoids recursion limits on long import chains.
    Nodes in a cycle share a column. A few barycenter sweeps reduce edge crossings.
    """
    adjacency = {key: set() for key in graph.nodes}
    reverse = {key: set() for key in graph.nodes}
    for edge in graph.edges:
        adjacency[edge.source].add(edge.target)
        reverse[edge.target].add(edge.source)
    visited, order = set(), []
    for start in sorted(adjacency):
        if start in visited:
            continue
        visited.add(start)
        stack = [(start, iter(sorted(adjacency[start])))]
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                order.append(node)
                stack.pop()
            elif child not in visited:
                visited.add(child)
                stack.append((child, iter(sorted(adjacency[child]))))
    component, groups = {}, []
    for start in reversed(order):
        if start in component:
            continue
        index = len(groups)
        group, stack = [], [start]
        component[start] = index
        while stack:
            node = stack.pop()
            group.append(node)
            for child in sorted(reverse[node]):
                if child not in component:
                    component[child] = index
                    stack.append(child)
        groups.append(sorted(group))
    dag = {index: set() for index in range(len(groups))}
    indegree = {index: 0 for index in dag}
    for source, targets in adjacency.items():
        for target in targets:
            a, b = component[source], component[target]
            if a != b and b not in dag[a]:
                dag[a].add(b)
                indegree[b] += 1
    queue = deque(sorted(index for index, degree in indegree.items() if not degree))
    levels = dict.fromkeys(dag, 0)
    while queue:
        source = queue.popleft()
        for target in sorted(dag[source]):
            levels[target] = max(levels[target], levels[source] + 1)
            indegree[target] -= 1
            if not indegree[target]:
                queue.append(target)
    columns = defaultdict(list)
    for index, group in enumerate(groups):
        columns[levels[index]].extend(group)
    for column in columns.values():
        column.sort(key=lambda key: graph.nodes[key].label)
    for _ in range(3):
        ranks = {node: rank for column in columns.values() for rank, node in enumerate(column)}
        for level in sorted(columns):
            def barycenter(key):
                parents = [ranks[p] for p in reverse[key] if levels[component[p]] < level]
                return (sum(parents) / len(parents) if parents else ranks[key], graph.nodes[key].label)
            columns[level].sort(key=barycenter)
    height = max((len(column) for column in columns.values()), default=0)
    return {key: (level * 340.0, (rank + (height - len(column)) / 2) * 108.0)
            for level, column in sorted(columns.items()) for rank, key in enumerate(column)}
