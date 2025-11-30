import ast
import os
from collections import defaultdict
from .utils import is_standard_or_external


def extract_imports_from_file(filepath: str) -> list[str]:
    """
    Analyses a Python file to extract imported modules.

    :param filepath: Path to the Python file to be analysed

    :return: List of imported modules (paths as strings)
    """
    # Using 'ast' to transform Python code into a syntax tree
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError:
            return []

    imports = []

    # Traverses all nodes in the tree
    for node in ast.walk(tree):

        # Recording of 'Imports'
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)

        # Recording 'From ... Import ...'
        elif isinstance(node, ast.ImportFrom):
            base = node.module if node.module else ""
            level = node.level if hasattr(node, 'level') else 0

            # Reconstruct the path with the points (e.g. .parser = parser with level=1)
            if level > 0:
                dots = "." * level
                base = f"{dots}{base}"

            for alias in node.names:
                name = alias.name
                # E.g.: .parser -> .parser.collect_all_dependencies
                full_name = f"{base}.{name}" if name != "*" else base
                imports.append(full_name.lstrip("."))

    return imports


def collect_all_dependencies(project_path: str) -> dict[str, list[str]]:
    """
    Analyses all Python files in a folder to build a dependency map for each file.

    :param project_path: Path to the directory of the project to be analysed

    :return: Relative file dictionary -> list of imported modules
    """
    dependencies = {}

    # Browse all subfolders of the folder passed as a parameter
    for root, _, files in os.walk(project_path):
        for file in files:
            # Processing Python files
            if file.endswith(".py"):
                # Calculating the absolute path and the relative path to the project
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, project_path)

                # Obtaining file imports and storing them in the dictionary
                imports = extract_imports_from_file(full_path)
                dependencies[rel_path] = imports

    return dependencies


def build_module_map(project_path: str) -> dict[str, list[str]]:
    """
    Creates a correspondence between internal module names and Python files in the project.

    :param project_path: Path to the project directory

    :return: Dictionary module_name -> list of relative paths to the corresponding files
    """
    module_map = defaultdict(list)

    for root, _, files in os.walk(project_path):
        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, project_path)

                module_name = os.path.splitext(rel_path)[0].replace(os.sep, ".")

                short_name = os.path.splitext(file)[0]
                base_folder = os.path.basename(os.path.dirname(full_path))
                with_base = f"{base_folder}.{short_name}"

                def add(name):
                    if not is_standard_or_external(name):
                        module_map[name].append(rel_path)

                add(module_name)
                add(short_name)
                add(with_base)

    return dict(module_map)
