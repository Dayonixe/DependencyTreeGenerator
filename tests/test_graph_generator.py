import os
import shutil
import tempfile
import pytest
from src.graph_generator import build_dependency_graph


@pytest.fixture
def test_data():
    """
    Fixture : données simulées pour tester la génération du graphe.
    """
    dependencies = {
        'main.py': ['utils', 'os', 'helpers.math'],
        'utils.py': ['sys'],
        os.path.join('helpers', 'math.py'): ['math']
    }

    module_map = {
        'utils': 'examples/project1/utils.py',
        'helpers.math': 'examples/project1/helpers/math.py'
    }

    project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'examples', 'project1'))

    return dependencies, module_map, project_path


@pytest.fixture
def temp_output_dir():
    """
    Fixture : crée un répertoire temporaire pour stocker les fichiers de sortie.
    """
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


def test_graph_generation_creates_output_file(test_data, temp_output_dir):
    """
    Test : vérifie que le fichier de graphe est bien généré sans erreur.
    """
    dependencies, module_map, project_path = test_data
    output_path = os.path.join(temp_output_dir, "test_graph")

    # Action
    build_dependency_graph(
        dependencies=dependencies,
        module_map=module_map,
        project_path=project_path,
        output_path=output_path,
        output_format="png"
    )

    # Assertion : vérifie que le fichier a bien été généré
    generated_file = output_path + ".png"
    assert os.path.exists(generated_file), f"Le fichier de graphe n’a pas été trouvé : {generated_file}"
