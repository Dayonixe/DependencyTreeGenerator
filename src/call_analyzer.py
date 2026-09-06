"""Resolve explicit calls using AST bindings; never import the analysed code."""

import ast
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import os

from .models import FunctionCall, ImportReference, ModuleMap, ProjectAnalysis
from .parser import (
    extract_imports_from_tree, iter_python_files, module_map_from_files, parse_python_file,
)
from .utils import absolute_module_name, resolve_module_name


@dataclass(frozen=True)
class _Function:
    file: str
    name: str
    line: int


@dataclass(frozen=True)
class _Imported:
    file: str
    reference: ImportReference
    loaded: frozenset[str] = frozenset()


@dataclass(frozen=True)
class _Attribute:
    value: object
    name: str


@dataclass(frozen=True)
class _Module:
    name: str
    loaded: frozenset[str]


@dataclass
class _ObservedCall:
    caller: str
    expression: str
    line: int
    column: int
    value: object


def _expression(node: ast.AST | None, bindings: dict):
    if isinstance(node, ast.Name):
        return bindings.get(node.id)
    if isinstance(node, ast.Attribute):
        value = _expression(node.value, bindings)
        return _Attribute(value, node.attr) if value is not None else None
    return None


def _merge(*branches: dict) -> dict:
    """Keep a binding only if every possible branch agrees."""
    names = set().union(*(branch.keys() for branch in branches))
    return {
        name: branches[0].get(name)
        if all(branch.get(name) == branches[0].get(name) for branch in branches)
        else None
        for name in names
    }


class _LocalNames(ast.NodeVisitor):
    """Python treats assignments anywhere in a function as local bindings."""

    def __init__(self):
        self.bound: set[str] = set()
        self.global_names: set[str] = set()
        self.nonlocal_names: set[str] = set()

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bound.add(node.id)

    def visit_Import(self, node):
        self.bound.update(alias.asname or alias.name.split(".")[0] for alias in node.names)

    def visit_ImportFrom(self, node):
        self.bound.update(alias.asname or alias.name for alias in node.names if alias.name != "*")

    def visit_FunctionDef(self, node):
        self.bound.add(node.name)

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef

    def visit_Lambda(self, node):
        pass

    def visit_Global(self, node):
        self.global_names.update(node.names)

    def visit_Nonlocal(self, node):
        self.nonlocal_names.update(node.names)

    def visit_ExceptHandler(self, node):
        if node.name:
            self.bound.add(node.name)
        self.generic_visit(node)

    def visit_MatchAs(self, node):
        if node.name:
            self.bound.add(node.name)
        self.generic_visit(node)

    visit_MatchStar = visit_MatchAs

    def visit_MatchMapping(self, node):
        if node.rest:
            self.bound.add(node.rest)
        self.generic_visit(node)

    def visit_ListComp(self, node):
        # Targets belong to the comprehension; walrus assignments do not.
        for generator in node.generators:
            self.visit(generator.iter)
            for condition in generator.ifs:
                self.visit(condition)
        for name in ("elt", "key", "value"):
            if hasattr(node, name):
                self.visit(getattr(node, name))

    visit_SetComp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp


class _Scanner:
    def __init__(self, file: str):
        self.file = file
        self.calls: list[_ObservedCall] = []
        self.globals: dict = {}

    def scan(self, tree: ast.Module) -> dict:
        bindings: dict = {}
        deferred: list = []
        self._block(tree.body, bindings, "<module>", deferred)
        self.globals = bindings.copy()
        self._functions(deferred, bindings)
        return bindings

    def _functions(self, deferred, parent):
        for node, name in deferred:
            locals_ = _LocalNames()
            for statement in node.body:
                locals_.visit(statement)
            arguments = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            arguments += [arg for arg in (node.args.vararg, node.args.kwarg) if arg]
            local_names = locals_.bound | {arg.arg for arg in arguments}
            local_names -= locals_.global_names | locals_.nonlocal_names
            bindings = parent.copy()
            bindings.update({key: None for key in local_names})
            bindings.update({key: self.globals.get(key) for key in locals_.global_names})
            nested: list = []
            self._block(node.body, bindings, name, nested)
            self._functions(nested, bindings)

    def _bind(self, target, value, bindings):
        if isinstance(target, ast.Name):
            bindings[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._bind(element, None, bindings)
        elif isinstance(target, ast.Starred):
            self._bind(target.value, None, bindings)
        elif isinstance(target, ast.Attribute):
            # After an attribute mutation, its original imported value is uncertain.
            root = target
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                bindings[root.id] = None

    def _expr(self, node, bindings, caller):
        if node is None:
            return
        if isinstance(node, ast.Call):
            value = _expression(node.func, bindings)
            if value is not None:
                self.calls.append(_ObservedCall(
                    caller, ast.unparse(node.func), node.lineno, node.col_offset, value
                ))
        if isinstance(node, ast.Lambda):
            for default in node.args.defaults + node.args.kw_defaults:
                self._expr(default, bindings, caller)
            inner = bindings.copy()
            args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            args += [arg for arg in (node.args.vararg, node.args.kwarg) if arg]
            inner.update({arg.arg: None for arg in args})
            self._expr(node.body, inner, caller + ".<lambda>")
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            inner = bindings.copy()
            for index, generator in enumerate(node.generators):
                self._expr(generator.iter, bindings if index == 0 else inner, caller)
                self._bind(generator.target, None, inner)
                for condition in generator.ifs:
                    self._expr(condition, inner, caller)
            for name in ("elt", "key", "value"):
                if hasattr(node, name):
                    self._expr(getattr(node, name), inner, caller)
            return
        if isinstance(node, ast.NamedExpr):
            self._expr(node.value, bindings, caller)
            self._bind(node.target, _expression(node.value, bindings), bindings)
            return
        for child in ast.iter_child_nodes(node):
            self._expr(child, bindings, caller)

    def _block(self, statements, bindings, caller, deferred):
        for node in statements:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if isinstance(node, ast.Import):
                        ref = ImportReference(alias.name, alias=alias.asname)
                    else:
                        ref = ImportReference(node.module or "", alias.name, node.level, alias.asname)
                    if ref.name == "*":
                        # A wildcard import may overwrite any existing binding.
                        bindings.update({name: None for name in bindings})
                        continue
                    loaded = frozenset({ref.module}) if ref.name is None else frozenset()
                    previous = bindings.get(ref.binding)
                    if (isinstance(previous, _Imported) and ref.name is None and ref.alias is None
                            and previous.reference.name is None and previous.reference.alias is None):
                        loaded |= previous.loaded
                    bindings[ref.binding] = _Imported(self.file, ref, loaded)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for expression in node.decorator_list + node.args.defaults + node.args.kw_defaults:
                    self._expr(expression, bindings, caller)
                name = node.name if caller == "<module>" else caller + "." + node.name
                bindings[node.name] = _Function(self.file, name, node.lineno)
                deferred.append((node, name))
            elif isinstance(node, ast.ClassDef):
                for expression in node.decorator_list + node.bases + [item.value for item in node.keywords]:
                    self._expr(expression, bindings, caller)
                name = node.name if caller == "<module>" else caller + "." + node.name
                class_bindings = bindings.copy()
                # Methods inherit the enclosing scope, not the class namespace.
                self._block(node.body, class_bindings, name, deferred)
                bindings[node.name] = None
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                self._expr(node.value, bindings, caller)
                if isinstance(node, ast.AnnAssign):
                    self._expr(node.annotation, bindings, caller)
                    if node.value is None:
                        continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value = None if isinstance(node, ast.AugAssign) else _expression(node.value, bindings)
                for target in targets:
                    self._bind(target, value, bindings)
            elif isinstance(node, ast.Delete):
                for target in node.targets:
                    self._bind(target, None, bindings)
            elif isinstance(node, ast.If):
                self._expr(node.test, bindings, caller)
                branches = []
                for body in (node.body, node.orelse):
                    branch = bindings.copy()
                    self._block(body, branch, caller, deferred)
                    branches.append(branch)
                bindings.update(_merge(*branches))
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
                self._expr(node.test if isinstance(node, ast.While) else node.iter, bindings, caller)
                branch = bindings.copy()
                if not isinstance(node, ast.While):
                    self._bind(node.target, None, branch)
                self._block(node.body, branch, caller, deferred)
                bindings.update(_merge(bindings, branch))
                self._block(node.orelse, bindings, caller, deferred)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    self._expr(item.context_expr, bindings, caller)
                    if item.optional_vars:
                        self._bind(item.optional_vars, None, bindings)
                self._block(node.body, bindings, caller, deferred)
            elif isinstance(node, ast.Try) or type(node).__name__ == "TryStar":
                branch = bindings.copy()
                self._block(node.body, branch, caller, deferred)
                handler_start = _merge(bindings, branch)
                self._block(node.orelse, branch, caller, deferred)
                branches = [branch]
                for handler in node.handlers:
                    branch = handler_start.copy()
                    self._expr(handler.type, branch, caller)
                    if handler.name:
                        branch[handler.name] = None
                    self._block(handler.body, branch, caller, deferred)
                    if handler.name:
                        branch[handler.name] = None
                    branches.append(branch)
                bindings.update(_merge(*branches))
                self._block(node.finalbody, bindings, caller, deferred)
            elif isinstance(node, ast.Match):
                self._expr(node.subject, bindings, caller)
                branches = [bindings.copy()]
                for case in node.cases:
                    branch = bindings.copy()
                    names = _LocalNames()
                    names.visit(case.pattern)
                    branch.update({name: None for name in names.bound})
                    self._expr(case.guard, branch, caller)
                    self._block(case.body, branch, caller, deferred)
                    branches.append(branch)
                bindings.update(_merge(*branches))
            else:
                self._expr(node, bindings, caller)


class _Resolver:
    def __init__(self, module_map: ModuleMap, exports: dict[str, dict], project_path: str):
        self.module_map = module_map
        self.exports = exports
        self.project_path = project_path

    def _module_exists(self, name):
        return (resolve_module_name(name, self.module_map) is not None
                or any(module.startswith(name + ".") for module in self.module_map))

    def _member(self, module: _Module, name: str, visiting: frozenset, allow_submodule=False):
        path = resolve_module_name(module.name, self.module_map)
        symbols = self.exports.get(path, {})
        key = (module.name, name)
        child = module.name + "." + name
        if key in visiting:
            # __init__.py may bind its own child with `from . import tools`.
            if allow_submodule and self._module_exists(child):
                return _Module(child, module.loaded | {child})
            return None
        if name in symbols:
            return self.resolve(symbols[name], visiting | {key})
        loaded = any(item == child or item.startswith(child + ".") for item in module.loaded)
        if (allow_submodule or loaded) and self._module_exists(child):
            return _Module(child, module.loaded | {child})
        return None

    def resolve(self, value, visiting=frozenset()):
        if isinstance(value, _Function):
            return value
        if isinstance(value, _Attribute):
            base = self.resolve(value.value, visiting)
            return self._member(base, value.name, visiting) if isinstance(base, _Module) else None
        if isinstance(value, _Imported):
            ref = value.reference
            absolute = absolute_module_name(ref.base, value.file, self.project_path)
            if not absolute:
                return None
            if ref.name is None:
                name = absolute if ref.alias else absolute.split(".")[0]
                return _Module(name, value.loaded)
            return self._member(_Module(absolute, frozenset({absolute})), ref.name, visiting, True)
        return None


def analyze_project(
    project_path: str,
    max_depth: int | None = None,
    ignore: Sequence[str] = (),
    *,
    on_progress: Callable[[str], None] | None = None,
) -> ProjectAnalysis:
    """Parse each selected file once, then resolve calls across the project index."""
    dependencies = {}
    exports = {}
    observed = {}
    for path in iter_python_files(project_path, max_depth, ignore):
        relative = os.path.relpath(path, project_path)
        if on_progress is not None:
            on_progress(relative)
        tree = parse_python_file(path)
        dependencies[relative] = extract_imports_from_tree(tree) if tree is not None else []
        if tree is not None:
            scanner = _Scanner(relative)
            exports[relative] = scanner.scan(tree)
            observed[relative] = scanner.calls

    module_map = module_map_from_files(project_path, list(dependencies))
    resolver = _Resolver(module_map, exports, project_path)
    calls = []
    for source, observations in observed.items():
        if on_progress is not None:
            on_progress(source)
        for call in observations:
            target = resolver.resolve(call.value)
            if isinstance(target, _Function) and target.file != source:
                calls.append(FunctionCall(
                    source, call.caller, call.expression, call.line,
                    target.file, target.name, target.line, call.column,
                ))
    calls.sort(key=lambda call: (call.source_file, call.lineno, call.col_offset))
    return ProjectAnalysis(dependencies, module_map, calls)
