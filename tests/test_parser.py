import os
import pytest
from src.parser import (collect_all_dependencies, extract_imports_from_file, build_module_map)


@pytest.fixture
def example_project_path():
    """
    Returns the absolute path to the sample project
    """
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'examples', 'project1'))


def test_collect_all_dependencies_on_example_project(example_project_path):
    """
    Tests the collection of global dependencies for the example project.
    """
    deps = collect_all_dependencies(example_project_path)

    assert isinstance(deps, dict), "Le résultat doit être un dictionnaire"

    expected_files = {
        os.path.normpath('main.py'),
        os.path.normpath('utils.py'),
        os.path.normpath('helpers/math.py')
    }
    actual_files = {os.path.normpath(path) for path in deps.keys()}
    assert expected_files.issubset(actual_files), f"Fichiers attendus non trouvés : {actual_files}"

    # Check expected imports
    assert 'utils' in deps['main.py'], "main.py doit importer utils"
    assert 'helpers.math' in deps['main.py'], "main.py doit importer helpers.math"
    assert 'os' in deps['utils.py'], "utils.py doit importer os"
    assert 'math' in deps[os.path.join('helpers', 'math.py')], "helpers/math.py doit importer math"


def test_extract_imports_from_file_individually(example_project_path):
    """
    Check that imports are extracted correctly in each file individually.
    """
    main_file = os.path.join(example_project_path, 'main.py')
    utils_file = os.path.join(example_project_path, 'utils.py')
    math_file = os.path.join(example_project_path, 'helpers', 'math.py')

    main_imports = extract_imports_from_file(main_file)
    assert 'utils' in main_imports, "'utils' doit être importé dans main.py"
    assert 'helpers.math' in main_imports, "'helpers.math' doit être importé dans main.py"

    utils_imports = extract_imports_from_file(utils_file)
    assert 'os' in utils_imports, "'os' doit être importé dans utils.py"

    math_imports = extract_imports_from_file(math_file)
    assert 'math' in math_imports, "'math' doit être importé dans helpers/math.py"


def test_build_module_map(example_project_path):
    """
    Check that the build_module_map function generates the correct module names.
    """
    module_map = build_module_map(example_project_path)

    # Example: helpers.math -> helpers/math.py
    assert 'helpers.math' in module_map
    assert os.path.normpath('helpers/math.py') in map(os.path.normpath, module_map['helpers.math'])

    # Example: utils -> utils.py
    assert 'utils' in module_map
    assert os.path.normpath('utils.py') in map(os.path.normpath, module_map['utils'])

    # Example: main -> main.py
    assert 'main' in module_map
    assert os.path.normpath('main.py') in map(os.path.normpath, module_map['main'])
