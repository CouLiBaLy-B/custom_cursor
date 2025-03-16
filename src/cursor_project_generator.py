from typing import Dict, Any, Optional, Union, List
from pathlib import Path
import os
import json
import yaml
import re
import subprocess
import traceback
import time
import concurrent.futures
from datetime import datetime
import shutil
from tqdm import tqdm

from src.ollama_client import OllamaClient
from config.default_config import DEFAULT_CONFIG

# Configuration du logging
from config.logger_config import logger


class CursorProjectGenerator:
    """Générateur de projets basé sur les modèles d'IA"""

    def __init__(self, config_path: Optional[str] = None):
        # Charger la configuration
        self.config = self._load_config(config_path)

        # Créer le chemin de base pour les projets
        self.base_path = Path(self.config["base_path"]).absolute()
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Initialiser le client Ollama
        self.ollama = OllamaClient(self.config)

        # Créer le dossier de templates
        self.templates_dir = Path(self.config["templates_dir"])
        self.templates_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Générateur initialisé avec le modèle {self.config['model_name']}")

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """Charge la configuration depuis un fichier ou utilise les valeurs par défaut"""
        config = DEFAULT_CONFIG.copy()

        # Si un chemin de config est spécifié, charger depuis ce fichier
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    if config_path.endswith(".json"):
                        file_config = json.load(f)
                    elif config_path.endswith((".yaml", ".yml")):
                        file_config = yaml.safe_load(f)
                    else:
                        logger.warning(
                            f"Format de configuration non reconnu: {config_path}"
                        )
                        file_config = {}

                config.update(file_config)
                logger.info(f"Configuration chargée depuis {config_path}")

            except Exception as e:
                logger.error(f"Erreur lors du chargement de la configuration: {e}")

        # Surcharger avec les variables d'environnement
        for key in config:
            env_key = f"CURSOR_GEN_{key.upper()}"
            if env_key in os.environ:
                env_value = os.environ[env_key]
                # Convertir les valeurs en types appropriés
                if isinstance(config[key], bool):
                    config[key] = env_value.lower() in ("true", "1", "yes", "y")
                elif isinstance(config[key], int):
                    config[key] = int(env_value)
                elif isinstance(config[key], float):
                    config[key] = float(env_value)
                else:
                    config[key] = env_value

        return config

    def extract_json(self, text: str) -> str:
        """Extrait un JSON valide d'une chaîne de caractères"""
        # Rechercher tout ce qui ressemble à un JSON entre accolades
        pattern = r"\{.*\}"
        match = re.search(pattern, text, re.DOTALL)

        if not match:
            logger.error("Aucun JSON trouvé dans le texte")
            raise ValueError("Aucun JSON valide trouvé dans la réponse")

        json_str = match.group(0)

        # Essayer de parser le JSON
        try:
            parsed = json.loads(json_str)
            return json_str
        except json.JSONDecodeError:
            logger.warning("JSON invalide extrait, tentative de correction...")

            # Tentative de correction plus avancée
            corrected = json_str

            # Remplacer les simples quotes par des doubles quotes pour les clés et valeurs
            corrected = re.sub(r"'([^']*)':", r'"\1":', corrected)
            corrected = re.sub(r":\s*\'([^\']*)\'", r': "\1"', corrected)

            # Corriger les virgules invalides
            corrected = re.sub(r",\s*}", "}", corrected)
            corrected = re.sub(r",\s*\]", "]", corrected)

            # Ajouter des guillemets autour des valeurs non quotées
            corrected = re.sub(r':\s*([^"][^,}\]]*)\s*([,}\]])', r': "\1"\2', corrected)

            try:
                json.loads(corrected)
                return corrected
            except json.JSONDecodeError as e:
                logger.error(f"Échec de correction JSON: {str(e)}")
                raise ValueError(
                    f"Impossible de parser le JSON, même après correction: {str(e)}"
                )

    def clean_code_content(self, content: str) -> str:
        """Nettoie le contenu des backticks et annotations de langage"""
        # Supprimer les blocs de code markdown
        content = re.sub(r"```[a-zA-Z]*\n", "", content)
        content = re.sub(r"```\n?$", "", content)

        # Supprimer les explications avant ou après le code
        lines = content.split("\n")
        start_idx = 0
        end_idx = len(lines)

        # Trouver la première ligne de code
        for i, line in enumerate(lines):
            if line.strip() and not line.startswith(("#", "//", "/*", "*", "<!--")):
                start_idx = i
                break

        # Trouver la dernière ligne de code significative
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() and not lines[i].startswith(("Explication:", "Note:")):
                end_idx = i + 1
                break

        return "\n".join(lines[start_idx:end_idx]).strip()

    def generate_project_structure(
        self, description: str, template: Optional[str] = None
    ) -> Dict[str, Any]:
        """Génère une structure de projet basée sur une description et éventuellement un template"""
        template_context = ""
        if template and (self.templates_dir / f"{template}.yaml").exists():
            try:
                with open(self.templates_dir / f"{template}.yaml", "r") as f:
                    template_data = yaml.safe_load(f)
                    template_context = f"""
                    Utilise le template {template}: {template_data.get('description', '')}
                    Structure suggérée:
                    {json.dumps(template_data.get('structure', {}), indent=2)}
                    """
            except Exception as e:
                logger.warning(f"Erreur lors du chargement du template {template}: {e}")

        prompt = f"""
        En tant qu'expert en développement logiciel, génère une structure de projet complète pour: {description}

        {template_context}

        Réponds UNIQUEMENT avec un JSON valide ayant la structure suivante, sans aucun texte explicatif:

        {{
          "name": "nom_du_projet",
          "description": "Description détaillée du projet",
          "folders": [
            "dossier1",
            "dossier2/sousdossier",
            ...
          ],
          "files": [
            {{
              "path": "chemin/relatif/fichier.ext",
              "description": "Description détaillée du contenu et des fonctionnalités"
            }},
            ...
          ],
          "dependencies": [
            "dep1",
            "dep2==version",
            ...
          ],
          "dev_dependencies": [
            "test-framework",
            "linter",
            ...
          ],
          "commands": [
            {{
              "name": "start",
              "command": "commande pour démarrer l'application"
            }},
            {{
              "name": "test",
              "command": "commande pour exécuter les tests"
            }}
          ]
        }}

        Assure-toi que la structure est complète et cohérente pour une application fonctionnelle.
        Inclus tous les fichiers nécessaires (configuration, tests, documentation, etc).
        """

        try:
            response = self.ollama.generate(prompt)
            json_str = self.extract_json(response)
            structure = json.loads(json_str)

            # Vérifier et compléter la structure
            required_keys = ["name", "description", "files", "folders", "dependencies"]
            for key in required_keys:
                if key not in structure:
                    structure[key] = (
                        []
                        if key
                        in [
                            "files",
                            "folders",
                            "dependencies",
                            "dev_dependencies",
                            "commands",
                        ]
                        else ""
                    )

            logger.info(f"Structure générée pour le projet: {structure['name']}")
            return structure
        except Exception as e:
            logger.error(f"Erreur lors de la génération de la structure: {e}")
            traceback.print_exc()
            raise

    def generate_file_content(
        self, file_info: Dict[str, str], project_structure: Dict[str, Any]
    ) -> str:
        """Génère le contenu d'un fichier spécifique"""
        project_name = project_structure["name"]
        project_desc = project_structure.get("description", "")
        file_path = file_info["path"]
        file_description = file_info["description"]

        # Obtenir l'extension du fichier
        _, ext = os.path.splitext(file_path)

        prompt = f"""
        Génère le contenu complet du fichier "{file_path}" pour un projet nommé "{project_name}".

        Description du projet: {project_desc}
        Description du fichier: {file_description}

        Structure du projet:
        {json.dumps(project_structure['folders'], indent=2)}

        Autres fichiers dans le projet:
        {json.dumps([f['path'] for f in project_structure['files']], indent=2)}

        Dépendances principales:
        {json.dumps(project_structure.get('dependencies', []), indent=2)}

        Assure-toi que:
        1. Le code soit complet, fonctionnel et respecte les meilleures pratiques
        2. Le code soit bien commenté et documenté
        3. Le code soit compatible avec les autres fichiers du projet
        4. Le code respecte les conventions propres au langage utilisé
        5. Si c'est un fichier de configuration, il doit être correctement formaté

        Réponds UNIQUEMENT avec le contenu du fichier, sans aucune explication ni markdown.
        """

        try:
            content = self.ollama.generate(prompt)
            cleaned_content = self.clean_code_content(content)
            return cleaned_content
        except Exception as e:
            logger.error(
                f"Erreur lors de la génération du contenu pour {file_path}: {e}"
            )
            return f"# Erreur lors de la génération du contenu\n# {str(e)}"

    def generate_readme(self, project_structure: Dict[str, Any]) -> str:
        """Génère un README.md détaillé pour le projet"""
        project_name = project_structure["name"]
        project_desc = project_structure.get("description", "")
        dependencies = project_structure.get("dependencies", [])
        commands = project_structure.get("commands", [])

        prompt = f"""
        Génère un README.md complet et bien structuré pour le projet "{project_name}".

        Description du projet: {project_desc}

        Structure du projet:
        {json.dumps(project_structure['folders'], indent=2)}

        Fichiers principaux:
        {json.dumps([f['path'] for f in project_structure['files']], indent=2)}

        Dépendances:
        {json.dumps(dependencies, indent=2)}

        Commandes:
        {json.dumps(commands, indent=2)}

        Le README doit inclure:
        1. Un titre et une introduction claire du projet avec badges (si pertinent)
        2. Les prérequis techniques
        3. Les instructions d'installation détaillées
        4. Comment configurer et exécuter le projet
        5. Structure du projet expliquée
        6. API ou fonctionnalités principales (si applicable)
        7. Exemples d'utilisation concrets avec code
        8. Comment contribuer (si open source)
        9. Licence
        10. Crédits et remerciements

        Utilise des sections bien organisées avec des titres de niveau appropriés.
        Inclus des blocs de code formatés avec la syntaxe markdown appropriée.

        Réponds UNIQUEMENT avec le contenu markdown du README, sans aucune explication supplémentaire.
        """

        try:
            content = self.ollama.generate(prompt)
            cleaned_content = self.clean_code_content(content)
            return cleaned_content
        except Exception as e:
            logger.error(f"Erreur lors de la génération du README: {e}")
            return f"# {project_name}\n\n{project_desc}\n\n*Erreur lors de la génération du README complet*"

    def setup_environment(
        self, project_path: Path, project_structure: Dict[str, Any]
    ) -> None:
        """Configure l'environnement de développement (venv, dépendances)"""
        if not self.config["setup_venv"]:
            logger.info("Configuration de l'environnement désactivée")
            return

        try:
            # Création d'un environnement virtuel
            venv_path = project_path / "venv"
            if not venv_path.exists():
                logger.info("Création de l'environnement virtuel...")
                subprocess.run(
                    ["python", "-m", "venv", str(venv_path)],
                    check=True,
                    capture_output=True,
                )

            # Chemin vers pip dans l'environnement virtuel
            if os.name == "nt":  # Windows
                pip_path = venv_path / "Scripts" / "pip"
            else:  # Linux/Mac
                pip_path = venv_path / "bin" / "pip"

            # Installation des dépendances si un requirements.txt existe
            req_file = project_path / "requirements.txt"
            if req_file.exists():
                logger.info("Installation des dépendances...")
                subprocess.run(
                    [str(pip_path), "install", "-r", str(req_file)],
                    check=True,
                    capture_output=True,
                )
                logger.info("Dépendances installées avec succès")
        except Exception as e:
            logger.warning(f"Erreur lors de la configuration de l'environnement: {e}")

    def create_project(
        self, description: str, template: Optional[str] = None
    ) -> Optional[Path]:
        """Crée un projet complet basé sur une description"""
        logger.info(f"Création d'un projet pour: {description}")
        start_time = time.time()

        try:
            # 1. Générer la structure du projet
            project_structure = self.generate_project_structure(description, template)

            project_name = project_structure["name"]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            project_path = self.base_path / f"{project_name}_{timestamp}"

            # 2. Créer le dossier principal
            project_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Projet créé à: {project_path}")

            # 3. Créer les sous-dossiers
            for folder in project_structure.get("folders", []):
                folder_path = project_path / folder
                folder_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Dossier créé: {folder_path}")

            # 4. Créer les fichiers en parallèle
            files_to_generate = project_structure.get("files", [])

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.config["max_workers"]
            ) as executor:
                # Préparer les futures
                future_to_file = {
                    executor.submit(
                        self.generate_file_content, file_info, project_structure
                    ): file_info
                    for file_info in files_to_generate
                }

                # Traiter les résultats avec une barre de progression
                with tqdm(
                    total=len(files_to_generate), desc="Génération des fichiers"
                ) as pbar:
                    for future in concurrent.futures.as_completed(future_to_file):
                        file_info = future_to_file[future]
                        file_path = project_path / file_info["path"]

                        try:
                            # Assurer que le dossier parent existe
                            file_path.parent.mkdir(parents=True, exist_ok=True)

                            # Récupérer le contenu généré
                            content = future.result()

                            # Écrire dans le fichier
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(content)

                            logger.info(f"Fichier créé: {file_path}")
                        except Exception as e:
                            logger.error(
                                f"Erreur lors de la génération de {file_path}: {e}"
                            )

                        pbar.update(1)

            # 5. Créer le README.md s'il n'existe pas déjà
            readme_path = project_path / "README.md"
            if not readme_path.exists():
                readme_content = self.generate_readme(project_structure)
                with open(readme_path, "w", encoding="utf-8") as f:
                    f.write(readme_content)
                logger.info("README.md généré")

            # 6. Créer requirements.txt et dev-requirements.txt
            if project_structure.get("dependencies"):
                with open(
                    project_path / "requirements.txt", "w", encoding="utf-8"
                ) as f:
                    f.write("\n".join(project_structure["dependencies"]))
                logger.info("requirements.txt généré")

            if project_structure.get("dev_dependencies"):
                with open(
                    project_path / "dev-requirements.txt", "w", encoding="utf-8"
                ) as f:
                    f.write("\n".join(project_structure["dev_dependencies"]))
                logger.info("dev-requirements.txt généré")

            # 7. Initialiser Git si configuré
            if self.config["init_git"]:
                try:
                    subprocess.run(
                        ["git", "init"],
                        cwd=str(project_path),
                        check=True,
                        capture_output=True,
                    )

                    # Créer .gitignore
                    gitignore_content = """
# Environnements virtuels
venv/
env/
.env/
.venv/
.vscode/
.idea/
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Fichiers de log
*.log
logs/

# Fichiers de configuration sensibles
*.env
*.env.local
config.json
secrets/

# Données
*.db
*.sqlite3
*.sqlite
data/

# Fichiers IDE
.idea/
.vscode/
*.swp
*.swo
.DS_Store
"""

                    with open(project_path / ".gitignore", "w", encoding="utf-8") as f:
                        f.write(gitignore_content.strip())

                    # Ajouter un .gitattributes basique
                    gitattributes_content = """
# Auto detect text files and perform LF normalization
* text=auto

# Documents
*.md       text diff=markdown
*.txt      text
*.rst      text

# Source code
*.py       text diff=python
*.json     text
*.yaml     text
*.yml      text

# Images (binary)
*.png      binary
*.jpg      binary
*.jpeg     binary
*.gif      binary
*.ico      binary

# Archives
*.gz       binary
*.zip      binary
*.7z       binary
"""
                    with open(
                        project_path / ".gitattributes", "w", encoding="utf-8"
                    ) as f:
                        f.write(gitattributes_content.strip())

                    logger.info("Dépôt Git initialisé")
                except Exception as e:
                    logger.warning(f"Erreur lors de l'initialisation Git: {e}")

            # 8. Configurer l'environnement virtuel et installer les dépendances
            self.setup_environment(project_path, project_structure)

            # 9. Enregistrer la structure du projet en JSON pour référence
            with open(
                project_path / "project_structure.json", "w", encoding="utf-8"
            ) as f:
                json.dump(project_structure, f, indent=2)

            # 10. Ouvrir dans Cursor si disponible et configuré
            if self.config["open_in_cursor"]:
                try:
                    subprocess.run(["cursor", str(project_path)], check=False)
                    logger.info("Projet ouvert dans Cursor")
                except Exception as e:
                    logger.warning(f"Impossible d'ouvrir dans Cursor: {e}")

            duration = time.time() - start_time
            logger.info(f"Projet créé en {duration:.2f} secondes")

            return project_path

        except Exception as e:
            logger.error(f"Erreur lors de la création du projet: {e}")
            traceback.print_exc()
            return None

    def save_as_template(
        self, project_path: Union[str, Path], template_name: str
    ) -> bool:
        """Sauvegarde un projet existant comme template"""
        project_path = Path(project_path)
        if not project_path.exists():
            logger.error(f"Le projet {project_path} n'existe pas")
            return False

        try:
            # Lire la structure existante si disponible
            structure_file = project_path / "project_structure.json"
            if structure_file.exists():
                with open(structure_file, "r", encoding="utf-8") as f:
                    project_structure = json.load(f)
            else:
                # Créer une structure basique
                project_structure = {
                    "name": project_path.name,
                    "description": f"Template basé sur {project_path.name}",
                    "folders": [],
                    "files": [],
                    "dependencies": [],
                }

                # Scanner les dossiers
                for folder in project_path.glob("**"):
                    if folder.is_dir() and folder.name not in [
                        ".git",
                        "venv",
                        "__pycache__",
                    ]:
                        rel_path = folder.relative_to(project_path)
                        project_structure["folders"].append(str(rel_path))

                # Scanner les fichiers
                for file in project_path.glob("**/*"):
                    if file.is_file() and not any(
                        p in str(file) for p in [".git/", "venv/", "__pycache__/"]
                    ):
                        rel_path = file.relative_to(project_path)
                        project_structure["files"].append(
                            {
                                "path": str(rel_path),
                                "description": f"Fichier {rel_path}",
                            }
                        )

                # Vérifier requirements.txt
                req_file = project_path / "requirements.txt"
                if req_file.exists():
                    with open(req_file, "r", encoding="utf-8") as f:
                        dependencies = [line.strip() for line in f if line.strip()]
                    project_structure["dependencies"] = dependencies

            # Sauvegarder comme template
            template_file = self.templates_dir / f"{template_name}.yaml"
            template_data = {
                "name": template_name,
                "description": project_structure.get("description", ""),
                "structure": project_structure,
            }

            with open(template_file, "w", encoding="utf-8") as f:
                yaml.dump(template_data, f, default_flow_style=False)

            logger.info(f"Template '{template_name}' créé avec succès")
            return True

        except Exception as e:
            logger.error(f"Erreur lors de la création du template: {e}")
            return False

    def list_templates(self) -> List[Dict[str, str]]:
        """Liste tous les templates disponibles"""
        templates = []
        try:
            for template_file in self.templates_dir.glob("*.yaml"):
                try:
                    with open(template_file, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        templates.append(
                            {
                                "name": data.get("name", template_file.stem),
                                "description": data.get(
                                    "description", "Pas de description"
                                ),
                                "file": str(template_file),
                            }
                        )
                except Exception as e:
                    logger.warning(
                        f"Erreur lors de la lecture du template {template_file}: {e}"
                    )

            return templates
        except Exception as e:
            logger.error(f"Erreur lors de la liste des templates: {e}")
            return []

    def fix_code(
        self,
        file_path: Union[str, Path],
        error_description: str,
        project_structure: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Corrige le code d'un fichier existant en fonction d'une description d'erreur"""
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"Le fichier {file_path} n'existe pas")
            raise FileNotFoundError(f"Le fichier {file_path} n'existe pas")

        try:
            # Lire le contenu actuel du fichier
            current_content = file_path.read_text(encoding="utf-8")

            # Si project_structure n'est pas fourni, essayer de le trouver
            if project_structure is None:
                project_dir = file_path
                while (
                    project_dir.parent != project_dir
                ):  # Remonter jusqu'à trouver project_structure.json
                    project_dir = project_dir.parent
                    struct_file = project_dir / "project_structure.json"
                    if struct_file.exists():
                        with open(struct_file, "r", encoding="utf-8") as f:
                            project_structure = json.load(f)
                        break

            # Construire le prompt pour la correction
            if project_structure:
                project_name = project_structure["name"]
                project_desc = project_structure.get("description", "")

                # Trouver la description du fichier dans la structure
                file_description = "Fichier du projet"
                rel_path = (
                    file_path.relative_to(project_dir)
                    if "project_dir" in locals()
                    else file_path.name
                )
                for file_info in project_structure.get("files", []):
                    if file_info["path"] == str(rel_path):
                        file_description = file_info["description"]
                        break

                prompt = f"""
            Corrige le code du fichier "{file_path.name}" qui présente le problème suivant:
            {error_description}

            Description du projet: {project_desc}
            Description du fichier: {file_description}

            Voici le code actuel:
            ```
            {current_content}
            ```

            Réponds UNIQUEMENT avec le code corrigé, sans aucune explication ni formatage markdown.
            Assure-toi que la solution corrige spécifiquement le problème décrit, tout en maintenant les autres
            fonctionnalités.
            """
            else:
                # Si nous n'avons pas d'information sur le projet, utiliser un prompt plus simple
                prompt = f"""
            Corrige le code du fichier "{file_path.name}" qui présente le problème suivant:
            {error_description}

            Voici le code actuel:
            ```
            {current_content}
            ```

            Réponds UNIQUEMENT avec le code corrigé, sans aucune explication ni formatage markdown.
            Assure-toi que la solution corrige spécifiquement le problème décrit, tout en maintenant toutes les autres
            fonctionnalités.
            """

            # Générer le contenu corrigé
            corrected_content = self.ollama.generate(prompt)
            cleaned_content = self.clean_code_content(corrected_content)

            return cleaned_content

        except Exception as e:
            logger.error(f"Erreur lors de la correction de {file_path}: {e}")
            raise

    def analyze_project(self, project_path: Union[str, Path]) -> Dict[str, Any]:
        """Analyse un projet pour détecter des problèmes potentiels"""
        project_path = Path(project_path)
        if not project_path.exists():
            logger.error(f"Le projet {project_path} n'existe pas")
            raise FileNotFoundError(f"Le projet {project_path} n'existe pas")

        try:
            # Charger la structure du projet si disponible
            structure_file = project_path / "project_structure.json"
            if structure_file.exists():
                with open(structure_file, "r", encoding="utf-8") as f:
                    project_structure = json.load(f)
            else:
                # Créer une structure basique à partir des fichiers existants
                project_structure = {
                    "name": project_path.name,
                    "description": "Projet existant",
                    "files": [],
                    "folders": [],
                }

                # Scanner les fichiers pertinents
                for file in project_path.rglob("*"):
                    if file.is_file() and not any(
                        p in str(file) for p in [".git/", "venv/", "__pycache__/"]
                    ):
                        rel_path = file.relative_to(project_path)
                        project_structure["files"].append(
                            {
                                "path": str(rel_path),
                                "description": f"Fichier {rel_path}",
                            }
                        )

            # Collecter un échantillon de code (pour les projets plus grands)
            code_samples = []
            sample_count = min(10, len(project_structure.get("files", [])))
            sample_files = project_structure.get("files", [])[:sample_count]

            for file_info in sample_files:
                file_path = project_path / file_info["path"]
                if file_path.exists() and file_path.is_file():
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        # Limiter la taille pour ne pas dépasser la capacité du modèle
                        content = content[:2000] + (
                            "..." if len(content) > 2000 else ""
                        )
                        code_samples.append(
                            {"path": file_info["path"], "content": content}
                        )
                    except Exception as e:
                        logger.warning(f"Erreur lors de la lecture de {file_path}: {e}")

            # Construire le prompt d'analyse
            prompt = f"""
Tu es un expert en code review et en détection de problèmes dans le code. Analyse le projet suivant:

Nom du projet: {project_structure.get('name', 'Projet inconnu')}
Description: {project_structure.get('description', 'Aucune description disponible')}

Structure des fichiers:
{json.dumps([f['path'] for f in project_structure.get('files', [])], indent=2)}

Échantillons de code:
{json.dumps(code_samples, indent=2)}

Identifie tous les problèmes potentiels dans ce code, notamment:
1. Bugs ou erreurs de programmation
2. Problèmes de sécurité
3. Mauvaises pratiques de code
4. Incohérences dans l'architecture
5. Code dupliqué ou redondant
6. Problèmes de performance

Réponds avec un JSON structuré contenant ton analyse:
{{
  "issues": [
    {{
      "file": "chemin/du/fichier.ext",
      "type": "type de problème (bug, sécurité, etc.)",
      "severity": "critical|high|medium|low",
      "description": "Description détaillée du problème",
      "suggestion": "Suggestion pour corriger le problème"
    }},
    ...
  ],
  "recommendations": [
    {{
      "type": "amélioration|refactoring|architecture|test",
      "description": "Description de la recommandation",
      "priority": "high|medium|low"
    }},
    ...
  ],
  "overall_quality": "excellent|good|average|poor",
  "summary": "Résumé global de la qualité du projet et des principaux problèmes"
}}
    """

            # Générer l'analyse
            response = self.ollama.generate(prompt)
            analysis_json = self.extract_json(response)
            analysis = json.loads(analysis_json)

            logger.info(
                f"Analyse du projet {project_path} terminée avec {len(analysis.get('issues', []))} problèmes détectés"
            )
            return analysis

        except Exception as e:
            logger.error(f"Erreur lors de l'analyse du projet {project_path}: {e}")
            raise

    def fix_project(
        self, project_path: Union[str, Path], analysis: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Corrige automatiquement les problèmes détectés dans un projet"""
        project_path = Path(project_path)
        if not project_path.exists():
            logger.error(f"Le projet {project_path} n'existe pas")
            raise FileNotFoundError(f"Le projet {project_path} n'existe pas")

        try:
            # Si aucune analyse n'est fournie, effectuer une analyse automatique
            if analysis is None:
                logger.info(f"Analyse automatique du projet {project_path}")
                analysis = self.analyze_project(project_path)

            # Charger la structure du projet si disponible
            structure_file = project_path / "project_structure.json"
            if structure_file.exists():
                with open(structure_file, "r", encoding="utf-8") as f:
                    project_structure = json.load(f)
            else:
                project_structure = None

            # Résultats des corrections
            results = {"fixed_files": [], "skipped_files": [], "errors": []}

            # Traiter chaque problème identifié
            issues = analysis.get("issues", [])
            if not issues:
                logger.info("Aucun problème à corriger dans le projet")
                return results

            with tqdm(total=len(issues), desc="Correction des problèmes") as pbar:
                for issue in issues:
                    file_rel_path = issue.get("file")
                    if not file_rel_path:
                        results["errors"].append(
                            {
                                "description": "Problème sans fichier spécifié",
                                "issue": issue,
                            }
                        )
                        pbar.update(1)
                        continue

                    file_path = project_path / file_rel_path
                    if not file_path.exists() or not file_path.is_file():
                        results["skipped_files"].append(
                            {"file": file_rel_path, "reason": "Fichier introuvable"}
                        )
                        pbar.update(1)
                        continue

                    try:
                        # Description du problème à corriger
                        error_description = (
                            f"{issue.get('type', 'Bug')}: {issue.get('description', 'Problème non spécifié')}"
                        )
                        if issue.get("suggestion"):
                            error_description += (
                                f"\n\nSuggestion: {issue['suggestion']}"
                            )

                        # Corriger le fichier
                        corrected_content = self.fix_code(
                            file_path, error_description, project_structure
                        )

                        # Sauvegarder une sauvegarde du fichier original
                        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
                        shutil.copy2(file_path, backup_path)

                        # Écrire le contenu corrigé
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(corrected_content)

                        results["fixed_files"].append(
                            {
                                "file": file_rel_path,
                                "issue": issue.get("type", "Bug"),
                                "backup": str(backup_path.relative_to(project_path)),
                            }
                        )
                        logger.info(f"Fichier corrigé: {file_rel_path}")

                    except Exception as e:
                        logger.error(
                            f"Erreur lors de la correction de {file_rel_path}: {e}"
                        )
                        results["errors"].append(
                            {"file": file_rel_path, "error": str(e)}
                        )

                pbar.update(1)

            # Générer un rapport de correction
            report = {
                "project": str(project_path),
                "timestamp": datetime.now().isoformat(),
                "fixed_count": len(results["fixed_files"]),
                "skipped_count": len(results["skipped_files"]),
                "error_count": len(results["errors"]),
                "details": results,
            }

            # Sauvegarder le rapport
            report_path = project_path / "fix_report.json"
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)

            logger.info(
                f"Correction terminée: {report['fixed_count']} fichiers corrigés, {report['error_count']} erreurs"
            )
            return report

        except Exception as e:
            logger.error(f"Erreur lors de la correction du projet {project_path}: {e}")
            raise
