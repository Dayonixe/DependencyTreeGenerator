# tests/test_parser.py

import os
import sys
import pytest

# ➤ Pour permettre d'importer le module src/parser.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from parser import collect_all_dependencies

def test_collect_all_dependencies_on_example_project():
    # Arrange : chemin du projet d'exemple
    project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'examples', 'project1'))

    # Act : collecte des dépendances
    deps = collect_all_dependencies(project_path)

    # Assert : vérifications de base
    assert isinstance(deps, dict), "Le résultat doit être un dictionnaire"

    # Vérifie qu'on a bien trouvé les bons fichiers
    expected_files = {
        os.path.normpath('main.py'),
        os.path.normpath('utils.py'),
        os.path.normpath('helpers/math.py')
    }
    actual_files = {os.path.normpath(path) for path in deps.keys()}
    assert expected_files.issubset(actual_files), f"Fichiers attendus non trouvés : {actual_files}"

    # Vérifie quelques imports
    assert 'utils' in deps['main.py'], "main.py doit importer utils"
    assert 'helpers.math' in deps['main.py'], "main.py doit importer helpers.math"
    assert 'os' in deps['utils.py'], "utils.py doit importer os"
    assert 'math' in deps[os.path.join('helpers', 'math.py')], "helpers/math.py doit importer math"