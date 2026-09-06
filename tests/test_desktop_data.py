from src.call_analyzer import analyze_project
from src.desktop.data import Edge, Node, ProjectGraph, build_project_graph, file_id, layered_layout, select_graph


def test_gui_graph_shares_cli_resolution_and_distinguishes_calls(make_project):
    root = make_project({"app.py": "from pkg import run\nimport os\nfrom missing_xyz import value\nrun()\n",
                         "pkg/__init__.py": "from .tools import run\n", "pkg/tools.py": "def run(): pass\n"})
    graph = build_project_graph(analyze_project(str(root)), str(root))
    assert graph.nodes["external:os"].kind == "external"
    assert graph.nodes["unknown:missing_xyz.value"].kind == "unknown"
    assert {(edge.target, edge.kind) for edge in graph.edges if edge.source == "file:app.py"} == {
        ("file:pkg/__init__.py", "import"), ("file:pkg/tools.py", "call"),
        ("external:os", "import"), ("unknown:missing_xyz.value", "import"),
    }


def test_display_filters_and_limit_preserve_analysis_and_isolated_nodes():
    nodes = {key: Node(key, key, "internal") for key in ("a", "b", "isolated")}
    nodes["os"] = Node("os", "os", "external")
    graph = ProjectGraph(nodes, [Edge("a", "b", "import", ()), Edge("b", "a", "call", ()), Edge("a", "os", "import", ())])
    assert set(select_graph(graph)[0].nodes) == {"a", "b", "isolated"}
    assert [edge.kind for edge in select_graph(graph, imports=False)[0].edges] == ["call"]
    assert set(select_graph(graph, focus="a", external=True)[0].nodes) == {"a", "b", "os"}
    assert list(select_graph(graph, query="ISOLATED")[0].nodes) == ["isolated"]
    visible, total = select_graph(graph, limit=1, focus="b")
    assert list(visible.nodes) == ["b"] and total == 2
    assert len(graph.nodes) == 4 and len(graph.edges) == 3


def test_layout_handles_cycles_self_edges_and_disconnected_files():
    graph = ProjectGraph({key: Node(key, key, "internal") for key in "abcde"}, [
        Edge("a", "b", "import", ()), Edge("b", "c", "import", ()),
        Edge("c", "b", "call", ()), Edge("c", "d", "import", ()), Edge("e", "e", "import", ()),
    ])
    positions = layered_layout(graph)
    assert positions == layered_layout(graph)
    assert len(set(positions.values())) == 5
    assert positions["a"][0] < positions["b"][0] == positions["c"][0] < positions["d"][0]
    assert layered_layout(ProjectGraph({}, [])) == {}


def test_layout_of_long_chain_is_iterative():
    count = 1200
    graph = ProjectGraph({str(i): Node(str(i), str(i), "internal") for i in range(count)},
                         [Edge(str(i), str(i + 1), "import", ()) for i in range(count - 1)])
    positions = layered_layout(graph)
    assert len(positions) == count
    assert positions["0"][0] < positions[str(count - 1)][0]
    assert file_id("pkg\\tools.py") == "file:pkg/tools.py"
