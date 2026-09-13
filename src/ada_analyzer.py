"""Static Ada dependency, call and tagged-type analysis without compiling code."""

from bisect import bisect_right
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import warnings

from .models import (
    ClassBase, ClassInfo, ClassMethod, ClassUsage, FunctionCall, ImportReference,
    ProjectAnalysis,
)
from .parser import AnalysisWarning, iter_source_files


ADA_EXTENSIONS = (".ads", ".adb", ".ada")
ADA_RUNTIME_ROOTS = frozenset({"ada", "interfaces", "system", "gnat"})
_TOKEN_RE = re.compile(
    r'--[^\r\n]*|"(?:""|[^"])*"|\'[^\'\r\n]\'|'
    r'[A-Za-z][A-Za-z0-9_]*|:=|=>|/=|<=|>=|\.\.|[^\s]',
)
_SPACE_RE = re.compile(r"\s+")
_NON_CALL_NAMES = frozenset({
    "accept", "begin", "case", "declare", "delay", "else", "elsif", "end",
    "entry", "exception", "exit", "for", "generic", "goto", "if", "is", "loop",
    "new", "null", "package", "pragma", "procedure", "raise", "record", "renames",
    "return", "select", "separate", "subtype", "task", "terminate", "type", "until",
    "use", "when", "while", "with",
})


@dataclass(frozen=True)
class _Token:
    value: str
    lower: str
    start: int
    end: int
    line: int
    column: int


@dataclass
class _TypeDecl:
    file: str
    unit: str
    name: str
    line: int
    bases: tuple[str, ...]
    explicit: bool
    derived: bool


@dataclass
class _Subprogram:
    file: str
    unit: str
    name: str
    line: int
    column: int
    signature: str
    kind: str
    header_start: int
    header_end: int
    body_start: int | None
    body_end: int | None
    header_identifiers: frozenset[str]
    class_keys: tuple[tuple[str, str], ...] = ()


@dataclass
class _AdaFile:
    path: str
    text: str
    tokens: list[_Token]
    unit: str
    unit_start: int
    dependencies: list[tuple[str, str]]
    uses: set[str]
    types: list[_TypeDecl] = field(default_factory=list)
    subprograms: list[_Subprogram] = field(default_factory=list)


def _tokens(source: str) -> list[_Token]:
    starts = [0]
    starts.extend(match.end() for match in re.finditer("\n", source))
    result = []
    for match in _TOKEN_RE.finditer(source):
        value = match.group()
        if value.startswith("--") or value.startswith('"') or (
            len(value) == 3 and value.startswith("'") and value.endswith("'")
        ):
            continue
        line_index = bisect_right(starts, match.start()) - 1
        result.append(_Token(
            value, value.casefold(), match.start(), match.end(),
            line_index + 1, match.start() - starts[line_index],
        ))
    return result


def _identifier(token: _Token | None) -> bool:
    return token is not None and token.value[:1].isalpha()


def _dotted(tokens: Sequence[_Token], start: int) -> tuple[str | None, int]:
    if start >= len(tokens) or not _identifier(tokens[start]):
        return None, start
    parts = [tokens[start].value]
    index = start + 1
    while index + 1 < len(tokens) and tokens[index].value == "." and _identifier(tokens[index + 1]):
        parts.append(tokens[index + 1].value)
        index += 2
    return ".".join(parts), index


def _fallback_unit(path: str) -> str:
    return Path(path).stem.replace("-", ".")


def _unit_name(tokens: Sequence[_Token], fallback: str) -> tuple[str, int, bool]:
    separate_parent = None
    for index, token in enumerate(tokens[:40]):
        if token.lower == "separate" and index + 2 < len(tokens) and tokens[index + 1].value == "(":
            separate_parent, _ = _dotted(tokens, index + 2)
            break
    for index, token in enumerate(tokens):
        if token.lower == "package":
            if index and tokens[index - 1].lower == "with":
                continue
            cursor = index + 1
            if cursor < len(tokens) and tokens[cursor].lower == "body":
                cursor += 1
            name, end = _dotted(tokens, cursor)
            if name and end < len(tokens) and tokens[end].lower in {"is", "renames", "with"}:
                if separate_parent and "." not in name:
                    name = separate_parent + "." + name
                return name, token.start, True
        if token.lower in {"procedure", "function"}:
            if index and tokens[index - 1].lower in {"access", "with"}:
                continue
            name, end = _dotted(tokens, index + 1)
            if name and end < len(tokens):
                return name, token.start, True
    return fallback, tokens[0].start if tokens else 0, False


def _validate_source(path: str, source: str, found_unit: bool) -> None:
    """Report safe lexical diagnostics without requiring an Ada compiler."""
    depth = 0
    in_string = False
    index = 0
    line = 1
    while index < len(source):
        character = source[index]
        if character == "\n":
            line += 1
        if in_string:
            if character == '"':
                if index + 1 < len(source) and source[index + 1] == '"':
                    index += 2
                    continue
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            index += 1
            continue
        if character == "-" and index + 1 < len(source) and source[index + 1] == "-":
            newline = source.find("\n", index + 2)
            if newline < 0:
                break
            index = newline
            continue
        if character == "'" and index + 2 < len(source) and source[index + 2] == "'":
            index += 3
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                warnings.warn(
                    f"Cannot fully analyse {path}: unexpected ')' at line {line}",
                    AnalysisWarning, stacklevel=2,
                )
                return
        index += 1
    if in_string:
        warnings.warn(
            f"Cannot fully analyse {path}: unterminated string literal",
            AnalysisWarning, stacklevel=2,
        )
    elif depth:
        warnings.warn(
            f"Cannot fully analyse {path}: {depth} unclosed parenthesis group(s)",
            AnalysisWarning, stacklevel=2,
        )
    elif source.strip() and not found_unit:
        warnings.warn(
            f"Cannot identify an Ada compilation unit in {path}",
            AnalysisWarning, stacklevel=2,
        )


def _context_dependencies(tokens: Sequence[_Token], stop: int) -> list[tuple[str, str]]:
    dependencies = []
    index = 0
    while index < len(tokens) and tokens[index].start < stop:
        if tokens[index].lower != "with":
            index += 1
            continue
        flags = []
        for previous in tokens[max(0, index - 2):index]:
            if previous.lower in {"limited", "private"}:
                flags.append(previous.lower)
        cursor = index + 1
        if cursor < len(tokens) and tokens[cursor].lower in {"function", "package", "procedure", "type"}:
            index += 1
            continue
        while cursor < len(tokens) and tokens[cursor].value != ";":
            name, end = _dotted(tokens, cursor)
            if name is None:
                cursor += 1
                continue
            prefix = " ".join(flags + ["with"])
            dependencies.append((name, f"{prefix} {name}"))
            cursor = end
            if cursor < len(tokens) and tokens[cursor].value == ",":
                cursor += 1
        index = cursor + 1
    return dependencies


def _use_clauses(tokens: Sequence[_Token]) -> set[str]:
    result = set()
    index = 0
    while index < len(tokens):
        if tokens[index].lower != "use":
            index += 1
            continue
        cursor = index + 1
        if cursor < len(tokens) and tokens[cursor].lower in {"all", "type"}:
            if tokens[cursor].lower == "all":
                cursor += 1
            if cursor < len(tokens) and tokens[cursor].lower == "type":
                while cursor < len(tokens) and tokens[cursor].value != ";":
                    cursor += 1
                index = cursor + 1
                continue
        while cursor < len(tokens) and tokens[cursor].value != ";":
            name, end = _dotted(tokens, cursor)
            if name:
                result.add(name.casefold())
                cursor = end
            else:
                cursor += 1
        index = cursor + 1
    return result


def _find_delimiter(tokens: Sequence[_Token], start: int) -> tuple[int | None, str | None]:
    depth = 0
    for index in range(start, min(len(tokens), start + 300)):
        value = tokens[index].value
        if value == "(":
            depth += 1
        elif value == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and (value == ";" or tokens[index].lower == "is"):
            return index, tokens[index].lower
    return None, None


def _matching_parenthesis(tokens: Sequence[_Token], start: int, stop: int) -> int | None:
    depth = 0
    for index in range(start, stop):
        if tokens[index].value == "(":
            depth += 1
        elif tokens[index].value == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _parse_types(file: _AdaFile) -> list[_TypeDecl]:
    result = []
    tokens = file.tokens
    for index, token in enumerate(tokens):
        if (token.lower != "type" or token.start < file.unit_start
                or index + 1 >= len(tokens) or not _identifier(tokens[index + 1])):
            continue
        name_token = tokens[index + 1]
        delimiter, _ = _find_delimiter(tokens, index + 2)
        if delimiter is None:
            continue
        is_index = next((cursor for cursor in range(index + 2, delimiter + 1)
                         if tokens[cursor].lower == "is"), None)
        if is_index is None:
            continue
        definition = tokens[is_index + 1:min(len(tokens), is_index + 80)]
        lowered = [item.lower for item in definition]
        boundary = next((position for position, value in enumerate(lowered)
                         if value in {"record", "private", ";"}), len(lowered))
        header = lowered[:boundary + 1]
        explicit = "tagged" in header or "interface" in header
        derived = "new" in header
        extension = derived and "with" in header
        bases = []
        if derived:
            new_index = is_index + 1 + lowered.index("new") + 1
            base, cursor = _dotted(tokens, new_index)
            if base:
                bases.append(base)
            while cursor < len(tokens) and tokens[cursor].lower not in {"with", "record"} and tokens[cursor].value != ";":
                if tokens[cursor].lower == "and":
                    base, end = _dotted(tokens, cursor + 1)
                    if base:
                        bases.append(base)
                        cursor = end
                        continue
                cursor += 1
        if "interface" in header:
            cursor = is_index + 1 + lowered.index("interface") + 1
            while cursor < len(tokens) and tokens[cursor].value != ";":
                if tokens[cursor].lower == "and":
                    base, end = _dotted(tokens, cursor + 1)
                    if base:
                        bases.append(base)
                        cursor = end
                        continue
                cursor += 1
        if explicit or extension or derived:
            result.append(_TypeDecl(
                file.path, file.unit, name_token.value, name_token.line,
                tuple(dict.fromkeys(bases)), explicit or extension, derived,
            ))
    return result


def _normalise_signature(text: str) -> str:
    return _SPACE_RE.sub(" ", text.strip())


def _body_end(tokens: Sequence[_Token], start: int, name: str, source_length: int) -> int:
    expected = name.casefold().rsplit(".", 1)[-1]
    for index in range(start, len(tokens) - 2):
        if (tokens[index].lower == "end" and tokens[index + 1].lower == expected
                and tokens[index + 2].value == ";"):
            return tokens[index].start
    return source_length


def _parse_subprograms(file: _AdaFile) -> list[_Subprogram]:
    result = []
    tokens = file.tokens
    for index, token in enumerate(tokens):
        if token.lower not in {"procedure", "function"}:
            continue
        previous = tokens[index - 1].lower if index else ""
        if previous in {"access", "end", "with"}:
            continue
        name, name_end = _dotted(tokens, index + 1)
        if not name:
            continue
        delimiter, delimiter_kind = _find_delimiter(tokens, name_end)
        if delimiter is None:
            continue
        open_paren = next((cursor for cursor in range(name_end, delimiter)
                           if tokens[cursor].value == "("), None)
        signature = ""
        if open_paren is not None:
            close_paren = _matching_parenthesis(tokens, open_paren, delimiter)
            if close_paren is not None:
                signature = _normalise_signature(
                    file.text[tokens[open_paren].end:tokens[close_paren].start]
                )
        identifiers = frozenset(
            item.lower for item in tokens[name_end:delimiter] if _identifier(item)
        )
        body_start = tokens[delimiter].end if delimiter_kind == "is" else None
        body_end = (_body_end(tokens, delimiter + 1, name, len(file.text))
                    if body_start is not None else None)
        result.append(_Subprogram(
            file.path, file.unit, name.rsplit(".", 1)[-1], token.line, token.column,
            signature, token.lower, token.start, tokens[delimiter].end,
            body_start, body_end, identifiers,
        ))
    return result


def _read_file(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        warnings.warn(f"Cannot analyse {path}: {error}", AnalysisWarning, stacklevel=2)
        return None


def _prefer_source(path: str) -> tuple[int, str]:
    return (0 if path.casefold().endswith(".ads") else 1, path.casefold())


def _resolve_type(
    expression: str,
    source: _AdaFile,
    class_keys: set[tuple[str, str]],
    by_name: dict[str, set[tuple[str, str]]],
) -> tuple[str, str] | None:
    cleaned = expression.replace("'Class", "").replace("'class", "")
    parts = cleaned.split(".")
    type_name = parts[-1].casefold()
    if len(parts) > 1:
        candidate = (".".join(parts[:-1]).casefold(), type_name)
        return candidate if candidate in class_keys else None
    local = (source.unit.casefold(), type_name)
    if local in class_keys:
        return local
    matches = {key for key in by_name.get(type_name, ()) if key[0] in source.uses}
    if len(matches) == 1:
        return next(iter(matches))
    return None


def _call_target(
    parts: Sequence[str], source: _AdaFile,
    definitions: dict[tuple[str, str], list[_Subprogram]],
) -> _Subprogram | None:
    name = parts[-1].casefold()
    if len(parts) > 1:
        candidates = definitions.get((".".join(parts[:-1]).casefold(), name), [])
    else:
        units = {source.unit.casefold()} | source.uses
        candidates = [item for unit in units for item in definitions.get((unit, name), [])]
    if not candidates:
        return None
    if len(parts) == 1 and len({item.unit.casefold() for item in candidates}) > 1:
        return None
    profiles = {(item.kind, item.signature.casefold()) for item in candidates}
    if len(profiles) > 1:
        return None
    candidates = sorted(candidates, key=lambda item: (
        item.body_start is None,
        not item.file.casefold().endswith(".adb"),
        item.file.casefold(), item.line,
    ))
    return candidates[0]


def _enclosing_subprogram(file: _AdaFile, offset: int) -> _Subprogram | None:
    bodies = [item for item in file.subprograms
              if item.body_start is not None and item.body_start <= offset < item.body_end]
    return max(bodies, key=lambda item: item.body_start) if bodies else None


def analyze_ada_project(
    project_path: str,
    max_depth: int | None = None,
    ignore: Sequence[str] = (),
    *,
    on_progress: Callable[[str], None] | None = None,
) -> ProjectAnalysis:
    """Analyse Ada units, ``with`` clauses, calls and tagged types statically."""
    files = []
    for absolute in iter_source_files(project_path, ADA_EXTENSIONS, max_depth, ignore):
        relative = os.path.relpath(absolute, project_path)
        if on_progress is not None:
            on_progress(relative)
        source = _read_file(absolute)
        if source is None:
            continue
        tokens = _tokens(source)
        unit, unit_start, found_unit = _unit_name(tokens, _fallback_unit(relative))
        _validate_source(relative, source, found_unit)
        item = _AdaFile(
            relative, source, tokens, unit, unit_start,
            _context_dependencies(tokens, unit_start), _use_clauses(tokens),
        )
        item.types = _parse_types(item)
        item.subprograms = _parse_subprograms(item)
        files.append(item)

    by_unit = defaultdict(list)
    for file in files:
        by_unit[file.unit.casefold()].append(file.path)
    module_map = {
        unit: sorted(paths, key=_prefer_source) for unit, paths in sorted(by_unit.items())
    }
    dependencies = {}
    files_by_path = {file.path: file for file in files}
    for file in files:
        references = []
        for name, display in file.dependencies:
            candidates = module_map.get(name.casefold(), [])
            target = candidates[0] if candidates else None
            references.append(ImportReference(
                name, resolved_file=target,
                external=name.split(".", 1)[0].casefold() in ADA_RUNTIME_ROOTS,
                display=display,
            ))
        if file.path.casefold().endswith(".adb"):
            specifications = [path for path in module_map.get(file.unit.casefold(), [])
                              if path.casefold().endswith(".ads")]
            if specifications:
                references.append(ImportReference(
                    file.unit, resolved_file=specifications[0], external=False,
                    display=f"body of {file.unit}",
                ))
        dependencies[file.path] = references

    all_types = [declaration for file in files for declaration in file.types]
    declarations = defaultdict(list)
    for item in all_types:
        declarations[(item.unit.casefold(), item.name.casefold())].append(item)
    by_name = defaultdict(set)
    for key in declarations:
        by_name[key[1]].add(key)
    class_keys = {key for key, items in declarations.items() if any(item.explicit for item in items)}
    changed = True
    while changed:
        changed = False
        for key, items in declarations.items():
            if key in class_keys or not any(item.derived for item in items):
                continue
            source = files_by_path[items[0].file]
            if any(_resolve_type(base, source, class_keys, by_name)
                   for item in items for base in item.bases):
                class_keys.add(key)
                changed = True

    representatives = {}
    for key in class_keys:
        representatives[key] = sorted(
            declarations[key], key=lambda item: (_prefer_source(item.file), item.line)
        )[0]

    for file in files:
        for subprogram in file.subprograms:
            owned = []
            for key in class_keys:
                if key[0] == file.unit.casefold() and key[1] in subprogram.header_identifiers:
                    owned.append(key)
            subprogram.class_keys = tuple(sorted(owned))

    methods = defaultdict(dict)
    for file in files:
        for subprogram in file.subprograms:
            method = ClassMethod(
                subprogram.name, subprogram.signature, subprogram.line, subprogram.kind,
            )
            for key in subprogram.class_keys:
                identity = (method.name.casefold(), method.signature.casefold(), method.kind)
                previous = methods[key].get(identity)
                if previous is None or _prefer_source(subprogram.file) < _prefer_source(previous[0]):
                    methods[key][identity] = (subprogram.file, method)

    classes = []
    for key, representative in representatives.items():
        source = files_by_path[representative.file]
        base_expressions = tuple(dict.fromkeys(
            base for item in declarations[key] for base in item.bases
        ))
        bases = []
        for expression in base_expressions:
            target_key = _resolve_type(expression, source, class_keys, by_name)
            target = representatives.get(target_key)
            bases.append(ClassBase(
                expression,
                target.file if target else None,
                target.name if target else None,
            ))
        class_methods = tuple(
            item[1] for _, item in sorted(methods[key].items(), key=lambda entry: (
                entry[1][1].lineno, entry[1][1].name.casefold(), entry[0],
            ))
        )
        classes.append(ClassInfo(
            representative.file, representative.name, representative.line,
            tuple(bases), class_methods,
        ))
    classes.sort(key=lambda item: (item.file.casefold(), item.lineno, item.name.casefold()))

    definitions = defaultdict(list)
    for file in files:
        for subprogram in file.subprograms:
            definitions[(file.unit.casefold(), subprogram.name.casefold())].append(subprogram)

    calls = []
    class_usages = []
    seen_calls = set()
    seen_usages = set()
    for file in files:
        if on_progress is not None:
            on_progress(file.path)
        header_ranges = [(item.header_start, item.header_end) for item in file.subprograms]
        index = 0
        while index < len(file.tokens):
            token = file.tokens[index]
            if not _identifier(token) or token.lower in _NON_CALL_NAMES:
                index += 1
                continue
            name, end = _dotted(file.tokens, index)
            parts = name.split(".") if name else []
            follows_call_syntax = (
                end < len(file.tokens)
                and (file.tokens[end].value == "(" or file.tokens[end].value == ";")
            )
            in_header = any(start <= token.start < stop for start, stop in header_ranges)
            if not follows_call_syntax or in_header:
                index = max(index + 1, end)
                continue
            target = _call_target(parts, file, definitions)
            if target is None:
                index = max(index + 1, end)
                continue
            caller_subprogram = _enclosing_subprogram(file, token.start)
            caller = caller_subprogram.name if caller_subprogram else f"<{file.unit}>"
            expression = ".".join(parts)
            if target.unit.casefold() != file.unit.casefold():
                identity = (file.path, token.start, target.file, target.name.casefold())
                if identity not in seen_calls:
                    calls.append(FunctionCall(
                        file.path, caller, expression, token.line,
                        target.file, target.name, target.line, token.column,
                    ))
                    seen_calls.add(identity)
            if caller_subprogram:
                for source_key in caller_subprogram.class_keys:
                    for target_key in target.class_keys:
                        if source_key == target_key:
                            continue
                        source_class = representatives[source_key]
                        target_class = representatives[target_key]
                        identity = (source_key, target_key, token.start)
                        if identity not in seen_usages:
                            class_usages.append(ClassUsage(
                                source_class.file, source_class.name, caller_subprogram.name,
                                expression, token.line, target_class.file, target_class.name,
                                token.column,
                            ))
                            seen_usages.add(identity)
            index = max(index + 1, end)

    calls.sort(key=lambda call: (call.source_file.casefold(), call.lineno, call.col_offset))
    class_usages.sort(key=lambda usage: (
        usage.source_file.casefold(), usage.lineno, usage.col_offset,
    ))
    return ProjectAnalysis(
        dependencies, module_map, calls, classes, class_usages, language="ada",
    )
