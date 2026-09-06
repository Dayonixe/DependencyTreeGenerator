import os
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from .models import FunctionCall, ImportReference, ProjectAnalysis
from .utils import is_standard_or_external, resolve_import


def prepare_output_stem(output_path: str) -> str:
    """Resolve directory destinations and create parents for any output format."""
    stem = os.fspath(output_path)
    if not stem:
        raise ValueError("The export destination must not be empty")
    separators = (os.sep,) + ((os.altsep,) if os.altsep else ())
    if os.path.isdir(stem) or stem.endswith(separators):
        stem = os.path.join(stem, "dependency_graph")
    parent = os.path.dirname(stem)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return stem


def format_text_report(
    dependencies: dict[str, list[ImportReference]], project_path: str,
    calls: Sequence[FunctionCall] = (),
) -> str:
    """Format the same plain-text report for stdout and UTF-8 file exports."""
    lines = [f"Analysis of Python files in: {project_path}"]
    if not dependencies:
        lines.append("\n(no Python files matched)")
    calls_by_file = defaultdict(list)
    for call in calls:
        calls_by_file[call.source_file].append(call)
    for filename, imports in dependencies.items():
        lines.extend(["", filename.replace("\\", "/")])
        lines.extend(f"  - {reference}" for reference in imports)
        if not imports:
            lines.append("  - (no imports extracted)")
        if calls_by_file[filename]:
            lines.append("  Calls:")
            lines.extend(f"    - {call.caller}: {_call_label(call)}" for call in calls_by_file[filename])
    return "\n".join(lines) + "\n"


def _call_label(call: FunctionCall) -> str:
    target = call.target_file.replace("\\", "/")
    return (
        f"{call.expression}() -> {target}:{call.target_function}() "
        f"[line {call.lineno}; definition {call.target_lineno}]"
    )


def format_ascii_report(analysis: ProjectAnalysis, project_path: str) -> str:
    """Render imports as a forest, expanding each file once and marking cycles."""
    lines = [f"Dependency tree: {project_path}"]
    if not analysis.dependencies:
        return lines[0] + "\n(no Python files matched)\n"

    # Entries carry an optional target file; the traversal itself is iterative so
    # even long dependency chains do not exhaust Python's recursion limit.
    entries = {}
    incoming = set()
    calls_by_file = defaultdict(lambda: defaultdict(list))
    for call in analysis.calls:
        calls_by_file[call.source_file][call.caller].append(call)
    for source, imports in analysis.dependencies.items():
        children = []
        for ref in imports:
            target = resolve_import(ref, analysis.module_map, source, project_path)
            if target in analysis.dependencies:
                label = f"{ref} -> " + target.replace("\\", "/")
                if target != source:
                    incoming.add(target)
            else:
                target = None
                kind = "external" if is_standard_or_external(ref.base) else "unresolved"
                label = f"{ref} [{kind}]"
            children.append((label, target, ()))
        groups = calls_by_file[source]
        if groups:
            children.append(("calls", None, [
                (caller, None, [(_call_label(call), None, ()) for call in calls])
                for caller, calls in sorted(groups.items())
            ]))
        entries[source] = children

    # Select roots first, then cover components consisting entirely of cycles.
    roots = []
    covered = set()
    candidates = sorted(set(entries) - incoming) + sorted(incoming)
    for source in candidates:
        if source in covered:
            continue
        roots.append(source)
        pending = [source]
        while pending:
            current = pending.pop()
            if current in covered:
                continue
            covered.add(current)
            pending.extend(target for _, target, _ in entries[current] if target is not None)

    expanded = set()
    stack = [
        (root.replace("\\", "/"), root, (), "", index == len(roots) - 1, frozenset())
        for index, root in reversed(list(enumerate(roots)))
    ]
    while stack:
        label, target, children, prefix, last, ancestors = stack.pop()
        if target is not None:
            if target in ancestors:
                label += " [cycle]"
            elif target in expanded:
                label += " [already shown]"
            else:
                expanded.add(target)
                children = entries[target]
                ancestors = ancestors | {target}
        lines.append(prefix + ("`-- " if last else "|-- ") + label)
        child_prefix = prefix + ("    " if last else "|   ")
        for index in range(len(children) - 1, -1, -1):
            text, child_target, grandchildren = children[index]
            stack.append((text, child_target, grandchildren, child_prefix,
                          index == len(children) - 1, ancestors))
    return "\n".join(lines) + "\n"


def export_text_report(report: str, output_path: str) -> str:
    filename = prepare_output_stem(output_path) + ".txt"
    Path(filename).write_text(report, encoding="utf-8")
    return filename
