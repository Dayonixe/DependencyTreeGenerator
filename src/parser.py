import ast
import os

def extract_imports_from_file(filepath):
    """
    Récupération d'une liste de modules importés dans un fichier donné
    :param filepath: Chemin vers le fichier à analyser
    :return: Liste des imports du fichier
    """
    # Utilisation de `ast` pour transformer le code Python en arbre syntaxique
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError:
            return []

    imports = []

    # Parcourt de tous les nœuds de l'arbre
    for node in ast.walk(tree):

        # Enregistrement des "Import"
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)

        # Enregistrement des "From ... Import ..."
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                base = node.module
                for alias in node.names:
                    full_name = f"{base}.{alias.name}" if alias.name != "*" else base
                    imports.append(full_name)

    return imports


def collect_all_dependencies(project_path):
    """
    Récupération d'un dictionnaire de fichier/modules importés, qui représente les dépendances internes (et externes) du projet
    :param project_path: Chemin vers le projet à analyser
    :return: Dictionnaire des fichiers/modules importés
    """
    dependencies = {}

    # Parcourt de tous les sous-dossiers du dossier passé en paramètre
    for root, _, files in os.walk(project_path):
        for file in files:
            # Traitement des fichiers Python
            if file.endswith(".py"):
                # Calcule du chemin absolu et du chemin relatif au projet
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, project_path)

                # Obtention des imports du fichier et stockage dans le dictionnaire
                imports = extract_imports_from_file(full_path)
                dependencies[rel_path] = imports

    return dependencies