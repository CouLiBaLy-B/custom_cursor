import subprocess
from pathlib import Path


def show_project_info(project_path: Path) -> None:
    """Affiche les informations sur le projet créé."""
    print(f"\n✅ Projet créé avec succès à: {project_path}")
    print("📂 Structure de fichiers générée et Git initialisé")

    try:
        # Afficher l'arborescence si tree est disponible
        result = subprocess.run(
            ["tree", str(project_path), "-L", "2"], capture_output=True, text=True
        )
        if result.returncode == 0:
            print("\nStructure du projet:")
            print(result.stdout)
        else:
            # Alternative si tree n'est pas disponible
            print("\nFichiers générés:")
            for file in sorted(project_path.rglob("*")):
                if file.is_file():
                    rel_path = file.relative_to(project_path)
                    print(f" - {rel_path}")
    except Exception:
        # Mode alternatif simple
        print("\nDossiers principaux:")
        for item in sorted(project_path.iterdir()):
            if item.is_dir() and not item.name.startswith((".", "__")):
                print(f" - {item.name}/")

        print("\nFichiers principaux:")
        for item in sorted(project_path.iterdir()):
            if item.is_file():
                print(f" - {item.name}")
