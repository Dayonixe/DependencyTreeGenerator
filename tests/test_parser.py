import os

from src import parser

def test_collect_all_dependencies_on_example_project():
    """
    L'application doit pouvoir récupérer les imports attendus pour les fichiers du projet d’exemple
    L'application doit pouvoir récupérer les clés du dictionnaire (les fichiers trouvés) correctes
    """
    # Arrange : chemin du projet d'exemple
    project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'examples', 'project1'))

    # Act : collecte des dépendances
    deps = parser.collect_all_dependencies(project_path)

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