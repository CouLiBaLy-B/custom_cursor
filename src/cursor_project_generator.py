import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import time
import traceback
import hashlib
import ast
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from tqdm import tqdm

from config.default_config import DEFAULT_CONFIG

# Configuration du logging
from config.logger_config import logger
from src.ollama_client import OllamaClient


class CursorProjectGenerator:
    """Générateur de projets basé sur les modèles d'IA."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialise le générateur de projets avec un chemin de configuration."""
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
        """Charge la configuration depuis un fichier ou utilise les valeurs par défaut."""
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
        """Extrait un JSON valide d'une chaîne de caractères."""
        # Rechercher tout ce qui ressemble à un JSON entre accolades
        pattern = r"\{.*\}"
        match = re.search(pattern, text, re.DOTALL)

        if not match:
            logger.error("Aucun JSON trouvé dans le texte")
            raise ValueError("Aucun JSON valide trouvé dans la réponse")

        json_str = match.group(0)

        # Essayer de parser le JSON
        try:
            json.loads(json_str)
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
        """Nettoie le contenu des backticks et annotations de langage."""
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
        """Génère une structure de projet basée sur une description et éventuellement un template."""

        # Enrichir la description si elle est trop courte
        if len(description.split()) < 5:
            enriched_prompt = f"""
            La description du projet "{description}" est très courte. 
            Peux-tu l'enrichir en imaginant ce que pourrait être ce projet, 
            ses fonctionnalités principales et son objectif?
            Réponds uniquement avec une description enrichie, sans explications.
            """
            
            try:
                enriched_description = self.ollama.generate(enriched_prompt)
                logger.info(f"Description enrichie: {enriched_description}")
                description = enriched_description
            except Exception as e:
                logger.warning(f"Impossible d'enrichir la description: {e}")
        
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

    def generate_file_content(self, file_info: Dict[str, str], project_structure: Dict[str, Any]) -> str:
        """Génère le contenu d'un fichier spécifique"""
        project_name = project_structure["name"]
        project_desc = project_structure.get("description", "")
        file_path = file_info["path"]
        file_description = file_info["description"]

        # Obtenir l'extension du fichier
        _, ext = os.path.splitext(file_path)
        
        # Adapter le prompt en fonction du type de fichier
        if ext.lower() in ['.py', '.js', '.ts', '.java', '.c', '.cpp', '.cs']:
            # Code source
            prompt_template = """
            Génère le contenu complet du fichier de code "{file_path}" pour un projet nommé "{project_name}".
            
            Description du projet: {project_desc}
            Description du fichier: {file_description}
            
            Structure du projet:
            {project_folders}
            
            Autres fichiers dans le projet:
            {project_files}
            
            Dépendances principales:
            {dependencies}
            
            Assure-toi que:
            1. Le code soit complet, fonctionnel et respecte les meilleures pratiques
            2. Le code soit bien commenté avec docstrings et commentaires explicatifs
            3. Le code soit compatible avec les autres fichiers du projet
            4. Le code respecte les conventions propres au langage utilisé (PEP8 pour Python, etc.)
            5. Le code inclut la gestion des erreurs appropriée
            6. Les imports/dépendances nécessaires sont inclus
            
            Réponds UNIQUEMENT avec le contenu du fichier, sans aucune explication ni markdown.
            """
        elif ext.lower() in ['.md', '.rst', '.txt']:
            # Documentation
            prompt_template = """
            Génère le contenu complet du fichier de documentation "{file_path}" pour un projet nommé "{project_name}".
            
            Description du projet: {project_desc}
            Description du fichier: {file_description}
            
            Structure du projet:
            {project_folders}
            
            Autres fichiers dans le projet:
            {project_files}
            
            Assure-toi que:
            1. La documentation soit claire, complète et bien structurée
            2. Elle inclut tous les détails pertinents pour le type de document
            3. Le format soit approprié ({ext} - Markdown/reStructuredText/texte)
            4. Elle soit cohérente avec le reste du projet
            
            Réponds UNIQUEMENT avec le contenu du fichier, sans aucune explication supplémentaire.
            """
        elif ext.lower() in ['.json', '.yaml', '.yml', '.toml', '.ini', '.cfg']:
            # Fichier de configuration
            prompt_template = """
            Génère le contenu complet du fichier de configuration "{file_path}" pour un projet nommé "{project_name}".
            
            Description du projet: {project_desc}
            Description du fichier: {file_description}
            
            Structure du projet:
            {project_folders}
            
            Autres fichiers dans le projet:
            {project_files}
            
            Dépendances principales:
            {dependencies}
            
            Assure-toi que:
            1. Le fichier de configuration soit valide et bien formaté selon le format {ext}
            2. Il inclut tous les paramètres nécessaires décrits dans la description
            3. Il contient des commentaires explicatifs si le format le permet
            4. Il est cohérent avec la configuration attendue pour ce type de projet
            
            Réponds UNIQUEMENT avec le contenu du fichier, sans aucune explication ni markdown.
            """
        else:
            # Fichier générique
            prompt_template = """
            Génère le contenu complet du fichier "{file_path}" pour un projet nommé "{project_name}".
            
            Description du projet: {project_desc}
            Description du fichier: {file_description}
            
            Structure du projet:
            {project_folders}
            
            Autres fichiers dans le projet:
            {project_files}
            
            Réponds UNIQUEMENT avec le contenu du fichier, sans aucune explication ni markdown.
            """
        
        # Formater le prompt avec les informations du projet
        prompt = prompt_template.format(
            file_path=file_path,
            project_name=project_name,
            project_desc=project_desc,
            file_description=file_description,
            project_folders=json.dumps(project_structure.get('folders', []), indent=2),
            project_files=json.dumps([f['path'] for f in project_structure.get('files', [])], indent=2),
            dependencies=json.dumps(project_structure.get('dependencies', []), indent=2),
            ext=ext
        )
        
        # Ajouter des exemples spécifiques au langage si nécessaire
        if ext.lower() == '.py':
            # Trouver d'autres fichiers Python dans le projet pour référence
            python_files = [f for f in project_structure.get('files', []) if f['path'].endswith('.py')]
            if python_files:
                prompt += f"\n\nAutres fichiers Python dans ce projet: {json.dumps([f['path'] for f in python_files], indent=2)}"
        
        try:
            # Générer le contenu avec un timeout plus long pour les fichiers complexes
            timeout_seconds = 180 if ext.lower() in ['.py', '.js', '.java'] else 60
            content = self.ollama.generate(prompt)
            cleaned_content = self.clean_code_content(content)
            
            # Validation du contenu généré
            if self._validate_generated_content(cleaned_content, ext):
                return cleaned_content
            else:
                # Réessayer avec un prompt simplifié si la validation échoue
                logger.warning(f"Contenu invalide généré pour {file_path}, nouvelle tentative...")
                simplified_prompt = f"""
                Génère le contenu du fichier {file_path} pour un projet {project_name}.
                Description: {file_description}
                
                Le contenu doit être valide et fonctionnel. Réponds UNIQUEMENT avec le code.
                """
                content = self.ollama.generate(simplified_prompt)
                cleaned_content = self.clean_code_content(content)
                return cleaned_content
        except Exception as e:
            logger.error(f"Erreur lors de la génération du contenu pour {file_path}: {e}")
            return f"# Erreur lors de la génération du contenu\n# {str(e)}"

    def _validate_generated_content(self, content: str, extension: str) -> bool:
        """Valide le contenu généré en fonction du type de fichier"""
        if not content or len(content.strip()) < 10:
            return False
            
        try:
            # Validation syntaxique pour différents types de fichiers
            if extension.lower() == '.py':
                # Vérifier la syntaxe Python
                ast.parse(content)
            elif extension.lower() in ['.json']:
                # Vérifier la syntaxe JSON
                json.loads(content)
            elif extension.lower() in ['.yaml', '.yml']:
                # Vérifier la syntaxe YAML
                yaml.safe_load(content)
            # Ajouter d'autres validations selon les besoins
                
            return True
        except Exception as e:
            logger.warning(f"Validation échouée pour le contenu généré: {str(e)}")
            return False


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

    def setup_environment(self, project_path: Path, project_structure: Dict[str, Any]) -> None:
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
                python_path = venv_path / "Scripts" / "python"
            else:  # Linux/Mac
                pip_path = venv_path / "bin" / "pip"
                python_path = venv_path / "bin" / "python"
                
            # Mise à jour de pip
            subprocess.run(
                [str(pip_path), "install", "--upgrade", "pip"],
                check=True,
                capture_output=True,
            )

            # Installation des dépendances depuis requirements.txt
            req_file = project_path / "requirements.txt"
            if req_file.exists():
                logger.info("Installation des dépendances...")
                
                # Installer par lots pour éviter les conflits
                with open(req_file, "r") as f:
                    dependencies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                
                # Installer d'abord les dépendances de base
                base_deps = [dep for dep in dependencies if "==" not in dep]
                if base_deps:
                    try:
                        subprocess.run(
                            [str(pip_path), "install"] + base_deps,
                            check=True,
                            capture_output=True,
                        )
                    except subprocess.CalledProcessError as e:
                        logger.warning(f"Erreur lors de l'installation des dépendances de base: {e}")
                
                # Puis les dépendances avec version spécifique
                version_deps = [dep for dep in dependencies if "==" in dep]
                if version_deps:
                    try:
                        subprocess.run(
                            [str(pip_path), "install"] + version_deps,
                            check=True,
                            capture_output=True,
                        )
                    except subprocess.CalledProcessError as e:
                        logger.warning(f"Erreur lors de l'installation des dépendances versionnées: {e}")
                
                # Vérifier les dépendances installées
                try:
                    result = subprocess.run(
                        [str(pip_path), "freeze"],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    with open(project_path / "installed_dependencies.txt", "w") as f:
                        f.write(result.stdout)
                    logger.info("Dépendances installées avec succès")
                except subprocess.CalledProcessError as e:
                    logger.warning(f"Erreur lors de la vérification des dépendances: {e}")
                    
        except Exception as e:
            logger.warning(f"Erreur lors de la configuration de l'environnement: {e}")


    def create_project(
        self, description: str, template: Optional[str] = None
    ) -> Optional[Path]:
        """Crée un projet complet basé sur une description"""
        logger.info(f"Création d'un projet pour: {description}")
        start_time = time.time()
        # Ajouter un mécanisme de récupération
        recovery_data = {}
        recovery_file = None

        try:
            # Générer un ID unique pour ce projet
            project_id = f"{int(time.time())}_{hashlib.md5(description.encode()).hexdigest()[:8]}"
            recovery_file = self.base_path / f"recovery_{project_id}.json"
            # 1. Générer la structure du projet
            project_structure = self.generate_project_structure(description, template)

            recovery_data["structure"] = project_structure
        
            # Sauvegarder l'état pour récupération
            with open(recovery_file, "w", encoding="utf-8") as f:
                json.dump(recovery_data, f, indent=2)
            
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
            
            # Si nous avons des données de récupération, proposer de les sauvegarder
            if recovery_file and recovery_file.exists():
                logger.info(f"Données de récupération disponibles dans: {recovery_file}")
                logger.info("Vous pouvez reprendre la création avec --recover {recovery_file}")
            
            return None

    def save_as_template(self, project_path: Union[str, Path], template_name: str) -> bool:
        """Sauvegarde un projet existant comme template avec analyse améliorée"""
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
                    if folder.is_dir() and not any(
                        ignored in str(folder) for ignored in [
                            ".git", "venv", "__pycache__", "node_modules", ".idea", ".vscode"
                        ]
                    ):
                        rel_path = str(folder.relative_to(project_path))
                        if rel_path and rel_path != ".":
                            project_structure["folders"].append(rel_path)

                # Scanner les fichiers
                for file in project_path.glob("**/*"):
                    if file.is_file() and not any(
                        ignored in str(file) for ignored in [
                            ".git/", "venv/", "__pycache__/", "node_modules/", ".idea/", ".vscode/"
                        ]
                    ):
                        rel_path = str(file.relative_to(project_path))
                        
                        # Analyser le fichier pour une meilleure description
                        file_description = self._analyze_file_for_template(file)
                        
                        project_structure["files"].append({
                            "path": rel_path,
                            "description": file_description,
                        })

                # Vérifier requirements.txt et package.json pour les dépendances
                req_file = project_path / "requirements.txt"
                if req_file.exists():
                    with open(req_file, "r", encoding="utf-8") as f:
                        dependencies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                    project_structure["dependencies"] = dependencies
                
                package_file = project_path / "package.json"
                if package_file.exists():
                    try:
                        with open(package_file, "r", encoding="utf-8") as f:
                            package_data = json.load(f)
                            js_deps = []
                            for dep_name, version in package_data.get("dependencies", {}).items():
                                js_deps.append(f"{dep_name}@{version}")
                            project_structure["js_dependencies"] = js_deps
                    except json.JSONDecodeError:
                        logger.warning(f"Impossible de parser package.json dans {project_path}")

            # Ajouter des métadonnées supplémentaires
            template_data = {
                "name": template_name,
                "description": project_structure.get("description", ""),
                "structure": project_structure,
                "created_at": datetime.now().isoformat(),
                "created_by": os.environ.get("USER", "unknown"),
                "version": "1.0.0",
            }

            # Sauvegarder comme template
            template_file = self.templates_dir / f"{template_name}.yaml"
            with open(template_file, "w", encoding="utf-8") as f:
                yaml.dump(template_data, f, default_flow_style=False)

            logger.info(f"Template '{template_name}' créé avec succès")
            return True

        except Exception as e:
            logger.error(f"Erreur lors de la création du template: {e}")
            return False


    def _analyze_file_for_template(self, file_path: Path) -> str:
        """Analyse un fichier pour générer une description pertinente pour le template"""
        try:
            # Limiter la taille des fichiers à analyser
            if file_path.stat().st_size > 100000:  # 100KB
                return f"Fichier {file_path.name} (grand fichier)"
                
            # Lire le contenu du fichier
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            
            # Analyser en fonction du type de fichier
            ext = file_path.suffix.lower()
            
            if ext == '.py':
                # Chercher les docstrings et commentaires
                import re
                module_docstring = re.search(r'"""(.*?)"""', content, re.DOTALL)
                if module_docstring:
                    return module_docstring.group(1).strip()
                
                # Chercher les classes et fonctions
                classes = re.findall(r'class\s+(\w+)', content)
                functions = re.findall(r'def\s+(\w+)', content)
                if classes or functions:
                    return f"Module Python avec {len(classes)} classes et {len(functions)} fonctions"
            
            elif ext in ['.js', '.ts']:
                # Chercher les commentaires JSDoc
                import re
                jsdoc = re.search(r'/\*\*(.*?)\*/', content, re.DOTALL)
                if jsdoc:
                    return jsdoc.group(1).strip()
                    
                # Chercher les fonctions et classes
                functions = re.findall(r'function\s+(\w+)', content)
                classes = re.findall(r'class\s+(\w+)', content)
                if classes or functions:
                    return f"Module JavaScript/TypeScript avec {len(classes)} classes et {len(functions)} fonctions"
            
            elif ext in ['.html', '.htm']:
                # Chercher le titre
                import re
                title = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
                if title:
                    return f"Page HTML: {title.group(1)}"
                    
                # Chercher les balises principales
                h1 = re.search(r'<h1>(.*?)</h1>', content, re.IGNORECASE)
                if h1:
                    return f"Page HTML avec titre principal: {h1.group(1)}"
                    
                return "Page HTML"
                
            elif ext in ['.md', '.rst']:
                # Chercher le titre pour les fichiers markdown
                lines = content.split('\n')
                if lines and lines[0].startswith('# '):
                    return f"Documentation: {lines[0][2:]}"
                elif len(lines) > 1 and lines[1].startswith('=='):
                    return f"Documentation: {lines[0]}"
                    
                return "Fichier de documentation"
                
            elif ext in ['.json', '.yaml', '.yml']:
                # Pour les fichiers de configuration, essayer de déterminer leur rôle
                if 'package.json' in str(file_path):
                    return "Configuration de package Node.js"
                elif 'tsconfig.json' in str(file_path):
                    return "Configuration TypeScript"
                elif 'docker-compose' in str(file_path):
                    return "Configuration Docker Compose"
                elif '.github/workflows' in str(file_path):
                    return "Configuration GitHub Actions"
                    
                # Essayer de charger et analyser le contenu
                try:
                    if ext == '.json':
                        data = json.loads(content)
                    else:
                        data = yaml.safe_load(content)
                        
                    # Compter les clés de premier niveau
                    key_count = len(data) if isinstance(data, dict) else 0
                    return f"Fichier de configuration avec {key_count} paramètres principaux"
                except:
                    pass
                    
            elif ext in ['.css', '.scss', '.less']:
                # Compter les sélecteurs CSS
                import re
                selectors = re.findall(r'([^\{\}]+)\{', content)
                return f"Fichier de style avec {len(selectors)} sélecteurs"
                
            elif ext in ['.sql']:
                # Identifier les opérations SQL principales
                content_lower = content.lower()
                if 'create table' in content_lower:
                    return "Script SQL de création de tables"
                elif 'insert into' in content_lower:
                    return "Script SQL d'insertion de données"
                elif 'select' in content_lower:
                    return "Script SQL de requêtes"
                    
                return "Script SQL"
                
            # Analyse générique basée sur la taille et le nom
            file_size = file_path.stat().st_size
            if file_size < 1024:  # Moins de 1KB
                size_desc = "petit"
            elif file_size < 10240:  # Moins de 10KB
                size_desc = "moyen"
            else:
                size_desc = "grand"
                
            return f"Fichier {file_path.name} ({size_desc})"
                
        except Exception as e:
            logger.debug(f"Erreur lors de l'analyse du fichier {file_path}: {e}")
            return f"Fichier {file_path.name}"

    def validate_and_fix_project(self, project_path: Union[str, Path]) -> Dict[str, Any]:
        """Valide et corrige automatiquement un projet nouvellement généré"""
        project_path = Path(project_path)
        if not project_path.exists():
            logger.error(f"Le projet {project_path} n'existe pas")
            raise FileNotFoundError(f"Le projet {project_path} n'existe pas")
            
        logger.info(f"Validation du projet {project_path}")
        results = {
            "validation_status": "success",
            "issues_found": 0,
            "issues_fixed": 0,
            "details": []
        }
        
        try:
            # 1. Vérifier la cohérence des imports
            self._validate_imports(project_path, results)
            
            # 2. Vérifier la syntaxe des fichiers
            self._validate_syntax(project_path, results)
            
            # 3. Vérifier les dépendances
            self._validate_dependencies(project_path, results)
            
            # 4. Vérifier la structure du projet
            self._validate_structure(project_path, results)
            
            # Mettre à jour le statut global
            if results["issues_found"] > 0:
                if results["issues_fixed"] == results["issues_found"]:
                    results["validation_status"] = "fixed"
                else:
                    results["validation_status"] = "issues_remaining"
                    
            # Sauvegarder le rapport de validation
            report_path = project_path / "validation_report.json"
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
                
            logger.info(f"Validation terminée: {results['issues_found']} problèmes trouvés, {results['issues_fixed']} corrigés")
            return results
            
        except Exception as e:
            logger.error(f"Erreur lors de la validation du projet: {e}")
            results["validation_status"] = "error"
            results["error"] = str(e)
            return results
            
    def _validate_imports(self, project_path: Path, results: Dict[str, Any]) -> None:
        """Vérifie la cohérence des imports dans les fichiers Python"""
        python_files = list(project_path.glob("**/*.py"))
        
        # Collecter tous les modules disponibles dans le projet
        available_modules = set()
        for py_file in python_files:
            module_path = str(py_file.relative_to(project_path)).replace("/", ".").replace("\\", ".")[:-3]
            available_modules.add(module_path)
            
        # Vérifier les imports dans chaque fichier
        for py_file in python_files:
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                # Trouver tous les imports
                import re
                imports = re.findall(r'^\s*(?:from|import)\s+([\w\.]+)', content, re.MULTILINE)
                
                for imported in imports:
                    # Ignorer les imports standards et externes
                    if imported.split('.')[0] in ['os', 'sys', 'json', 'time', 'datetime', 'flask', 'django', 'numpy', 'pandas']:
                        continue
                        
                    # Vérifier si l'import correspond à un module du projet
                    is_valid = False
                    for module in available_modules:
                        if imported == module or imported.startswith(module + '.'):
                            is_valid = True
                            break
                            
                    if not is_valid:
                        # Problème d'import détecté
                        issue = {
                            "file": str(py_file.relative_to(project_path)),
                            "type": "import_error",
                            "description": f"Import invalide: {imported}",
                            "fixed": False
                        }
                        
                        # Tenter de corriger l'import
                        try:
                            # Trouver un module similaire
                            similar_modules = [m for m in available_modules if imported.split('.')[-1] in m]
                            
                            if similar_modules:
                                # Remplacer l'import par le module le plus similaire
                                new_import = similar_modules[0]
                                new_content = re.sub(
                                    r'(^\s*(?:from|import)\s+)' + re.escape(imported), 
                                    r'\1' + new_import, 
                                    content, 
                                    flags=re.MULTILINE
                                )
                                
                                # Écrire le contenu corrigé
                                with open(py_file, "w", encoding="utf-8") as f:
                                    f.write(new_content)
                                    
                                issue["fixed"] = True
                                issue["solution"] = f"Remplacé par {new_import}"
                                results["issues_fixed"] += 1
                        except Exception as e:
                            logger.warning(f"Impossible de corriger l'import {imported} dans {py_file}: {e}")
                            
                        results["details"].append(issue)
                        results["issues_found"] += 1
                        
            except Exception as e:
                logger.warning(f"Erreur lors de la validation des imports dans {py_file}: {e}")
                
    def _validate_syntax(self, project_path: Path, results: Dict[str, Any]) -> None:
        """Vérifie la syntaxe des fichiers de code"""
        # Vérifier les fichiers Python
        for py_file in project_path.glob("**/*.py"):
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                try:
                    # Vérifier la syntaxe Python
                    ast.parse(content)
                except SyntaxError as e:
                    # Problème de syntaxe détecté
                    issue = {
                        "file": str(py_file.relative_to(project_path)),
                        "type": "syntax_error",
                        "description": f"Erreur de syntaxe: {str(e)}",
                        "fixed": False
                    }
                    
                    # Tenter de corriger la syntaxe
                    try:
                        error_description = f"Erreur de syntaxe Python à la ligne {e.lineno}, colonne {e.offset}: {e.msg}"
                        corrected_content = self.fix_code(py_file, error_description)
                        
                        # Vérifier si la correction a résolu le problème
                        try:
                            ast.parse(corrected_content)
                            # La correction a fonctionné, sauvegarder
                            with open(py_file, "w", encoding="utf-8") as f:
                                f.write(corrected_content)
                                
                            issue["fixed"] = True
                            issue["solution"] = "Syntaxe corrigée automatiquement"
                            results["issues_fixed"] += 1
                        except SyntaxError:
                            # La correction n'a pas fonctionné
                            pass
                    except Exception as fix_error:
                        logger.warning(f"Impossible de corriger la syntaxe dans {py_file}: {fix_error}")
                        
                    results["details"].append(issue)
                    results["issues_found"] += 1
                    
            except Exception as e:
                logger.warning(f"Erreur lors de la validation de la syntaxe dans {py_file}: {e}")
                
        # Ajouter des validations pour d'autres types de fichiers (JS, JSON, etc.)
        
    def _validate_dependencies(self, project_path: Path, results: Dict[str, Any]) -> None:
        """Vérifie la cohérence des dépendances déclarées"""
        req_file = project_path / "requirements.txt"
        if not req_file.exists():
            return
            
        try:
            # Lire les dépendances déclarées
            with open(req_file, "r", encoding="utf-8") as f:
                dependencies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                
            # Vérifier les imports dans les fichiers Python
            imported_packages = set()
            for py_file in project_path.glob("**/*.py"):
                try:
                    with open(py_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        
                    # Trouver tous les imports
                    import re
                    imports = re.findall(r'^\s*(?:from|import)\s+([\w\.]+)', content, re.MULTILINE)
                    
                    for imported in imports:
                        # Ajouter le package de premier niveau
                        imported_packages.add(imported.split('.')[0])
                except Exception:
                    pass
                    
            # Filtrer les packages standards
            std_libs = [
                'os', 'sys', 'time', 'datetime', 'json', 're', 'math', 'random',
                'collections', 'itertools', 'functools', 'typing', 'pathlib', 'shutil',
                'subprocess', 'argparse', 'logging', 'traceback', 'hashlib', 'tempfile'
            ]
            imported_packages = {pkg for pkg in imported_packages if pkg not in std_libs}
            
            # Vérifier les packages importés mais non déclarés
            declared_packages = {dep.split('==')[0].split('>')[0].split('<')[0].strip() for dep in dependencies}
            missing_packages = imported_packages - declared_packages
            
            if missing_packages:
                # Ajouter les packages manquants
                issue = {
                    "file": "requirements.txt",
                    "type": "missing_dependencies",
                    "description": f"Dépendances manquantes: {', '.join(missing_packages)}",
                    "fixed": False
                }
                
                # Tenter d'ajouter les packages manquants
                try:
                    with open(req_file, "a", encoding="utf-8") as f:
                        f.write("\n# Dépendances ajoutées automatiquement\n")
                        for pkg in missing_packages:
                            f.write(f"{pkg}\n")
                            
                    issue["fixed"] = True
                    issue["solution"] = f"Ajout des dépendances: {', '.join(missing_packages)}"
                    results["issues_fixed"] += 1
                except Exception as e:
                    logger.warning(f"Impossible d'ajouter les dépendances manquantes: {e}")
                    
                results["details"].append(issue)
                results["issues_found"] += 1
                
        except Exception as e:
            logger.warning(f"Erreur lors de la validation des dépendances: {e}")


    def _validate_structure(self, project_path: Path, results: Dict[str, Any]) -> None:
        """Vérifie la cohérence de la structure du projet"""
        # Charger la structure du projet
        structure_file = project_path / "project_structure.json"
        if not structure_file.exists():
            return
            
        try:
            with open(structure_file, "r", encoding="utf-8") as f:
                project_structure = json.load(f)
                
            # Vérifier que tous les dossiers déclarés existent
            for folder in project_structure.get("folders", []):
                folder_path = project_path / folder
                if not folder_path.exists():
                    issue = {
                        "file": folder,
                        "type": "missing_folder",
                        "description": f"Dossier manquant: {folder}",
                        "fixed": False
                    }
                    
                    # Créer le dossier manquant
                    try:
                        folder_path.mkdir(parents=True, exist_ok=True)
                        issue["fixed"] = True
                        issue["solution"] = "Dossier créé"
                        results["issues_fixed"] += 1
                    except Exception as e:
                        logger.warning(f"Impossible de créer le dossier {folder}: {e}")
                        
                    results["details"].append(issue)
                    results["issues_found"] += 1
                    
            # Vérifier que tous les fichiers déclarés existent
            for file_info in project_structure.get("files", []):
                file_path = project_path / file_info["path"]
                if not file_path.exists():
                    issue = {
                        "file": file_info["path"],
                        "type": "missing_file",
                        "description": f"Fichier manquant: {file_info['path']}",
                        "fixed": False
                    }
                    
                    # Tenter de générer le fichier manquant
                    try:
                        # Assurer que le dossier parent existe
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Générer le contenu du fichier
                        content = self.generate_file_content(file_info, project_structure)
                        
                        # Écrire le fichier
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(content)
                            
                        issue["fixed"] = True
                        issue["solution"] = "Fichier généré"
                        results["issues_fixed"] += 1
                    except Exception as e:
                        logger.warning(f"Impossible de générer le fichier {file_info['path']}: {e}")
                        
                    results["details"].append(issue)
                    results["issues_found"] += 1
                    
        except Exception as e:
            logger.warning(f"Erreur lors de la validation de la structure: {e}")

    def generate_project_documentation(self, project_path: Union[str, Path]) -> Dict[str, Any]:
        """Génère une documentation complète pour un projet existant"""
        project_path = Path(project_path)
        if not project_path.exists():
            logger.error(f"Le projet {project_path} n'existe pas")
            raise FileNotFoundError(f"Le projet {project_path} n'existe pas")
            
        logger.info(f"Génération de documentation pour {project_path}")
        results = {
            "status": "success",
            "generated_files": [],
            "errors": []
        }
        
        try:
            # Créer le dossier de documentation
            docs_dir = project_path / "docs"
            docs_dir.mkdir(exist_ok=True)
            
            # Charger la structure du projet si disponible
            structure_file = project_path / "project_structure.json"
            if structure_file.exists():
                with open(structure_file, "r", encoding="utf-8") as f:
                    project_structure = json.load(f)
            else:
                # Créer une structure basique à partir des fichiers existants
                project_structure = {
                    "name": project_path.name,
                    "description": "Documentation du projet",
                    "files": [],
                    "folders": []
                }
                
                # Scanner les fichiers
                for file in project_path.rglob("*"):
                    if file.is_file() and not any(
                        ignored in str(file) for ignored in [
                            ".git/", "venv/", "__pycache__/", "node_modules/", ".idea/", ".vscode/"
                        ]
                    ):
                        rel_path = str(file.relative_to(project_path))
                        project_structure["files"].append({
                            "path": rel_path,
                            "description": f"Fichier {rel_path}"
                        })
                        
                # Scanner les dossiers
                for folder in project_path.glob("*"):
                    if folder.is_dir() and not any(
                        ignored in str(folder) for ignored in [
                            ".git", "venv", "__pycache__", "node_modules", ".idea", ".vscode"
                        ]
                    ):
                        rel_path = str(folder.relative_to(project_path))
                        project_structure["folders"].append(rel_path)
            
            # 1. Générer le README principal s'il n'existe pas
            readme_path = project_path / "README.md"
            if not readme_path.exists():
                try:
                    readme_content = self.generate_readme(project_structure)
                    with open(readme_path, "w", encoding="utf-8") as f:
                        f.write(readme_content)
                    results["generated_files"].append(str(readme_path.relative_to(project_path)))
                except Exception as e:
                    logger.error(f"Erreur lors de la génération du README: {e}")
                    results["errors"].append({"file": "README.md", "error": str(e)})
            
            # 2. Générer la documentation d'architecture
            try:
                architecture_doc = self._generate_architecture_doc(project_path, project_structure)
                arch_path = docs_dir / "architecture.md"
                with open(arch_path, "w", encoding="utf-8") as f:
                    f.write(architecture_doc)
                results["generated_files"].append(str(arch_path.relative_to(project_path)))
            except Exception as e:
                logger.error(f"Erreur lors de la génération de la documentation d'architecture: {e}")
                results["errors"].append({"file": "docs/architecture.md", "error": str(e)})
                
            # 3. Générer la documentation d'API si applicable
            if any(f.endswith(('.py', '.js', '.ts')) for f in [f["path"] for f in project_structure.get("files", [])]):
                try:
                    api_doc = self._generate_api_doc(project_path, project_structure)
                    api_path = docs_dir / "api.md"
                    with open(api_path, "w", encoding="utf-8") as f:
                        f.write(api_doc)
                    results["generated_files"].append(str(api_path.relative_to(project_path)))
                except Exception as e:
                    logger.error(f"Erreur lors de la génération de la documentation d'API: {e}")
                    results["errors"].append({"file": "docs/api.md", "error": str(e)})
                    
            # 4. Générer un guide d'installation
            try:
                install_doc = self._generate_installation_doc(project_path, project_structure)
                install_path = docs_dir / "installation.md"
                with open(install_path, "w", encoding="utf-8") as f:
                    f.write(install_doc)
                results["generated_files"].append(str(install_path.relative_to(project_path)))
            except Exception as e:
                logger.error(f"Erreur lors de la génération du guide d'installation: {e}")
                results["errors"].append({"file": "docs/installation.md", "error": str(e)})
                
            # 5. Générer un index de documentation
            try:
                index_content = self._generate_docs_index(results["generated_files"])
                index_path = docs_dir / "index.md"
                with open(index_path, "w", encoding="utf-8") as f:
                    f.write(index_content)
                results["generated_files"].append(str(index_path.relative_to(project_path)))
            except Exception as e:
                logger.error(f"Erreur lors de la génération de l'index de documentation: {e}")
                results["errors"].append({"file": "docs/index.md", "error": str(e)})
                
            # Mettre à jour le statut en fonction des erreurs
            if results["errors"]:
                results["status"] = "partial" if results["generated_files"] else "failed"
                
            logger.info(f"Documentation générée: {len(results['generated_files'])} fichiers")
            return results
            
        except Exception as e:
            logger.error(f"Erreur lors de la génération de documentation: {e}")
            results["status"] = "failed"
            results["error"] = str(e)
            return results



    def list_templates(self) -> List[Dict[str, str]]:
        """Liste tous les templates disponibles avec des métadonnées enrichies"""
        templates = []
        try:
            for template_file in self.templates_dir.glob("*.yaml"):
                try:
                    with open(template_file, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        
                        # Extraire des statistiques sur le template
                        structure = data.get("structure", {})
                        file_count = len(structure.get("files", []))
                        folder_count = len(structure.get("folders", []))
                        dependency_count = len(structure.get("dependencies", []))
                        
                        # Déterminer les langages principaux
                        file_extensions = [os.path.splitext(f["path"])[1] for f in structure.get("files", [])]
                        extension_counts = {}
                        for ext in file_extensions:
                            if ext:
                                extension_counts[ext] = extension_counts.get(ext, 0) + 1
                        
                        # Trouver les 3 extensions les plus courantes
                        top_extensions = sorted(extension_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                        languages = [ext[1:] for ext, _ in top_extensions]
                        
                        templates.append({
                            "name": data.get("name", template_file.stem),
                            "description": data.get("description", "Pas de description"),
                            "file": str(template_file),
                            "file_count": file_count,
                            "folder_count": folder_count,
                            "dependency_count": dependency_count,
                            "languages": languages,
                            "last_modified": datetime.fromtimestamp(template_file.stat().st_mtime).isoformat(),
                        })
                except Exception as e:
                    logger.warning(f"Erreur lors de la lecture du template {template_file}: {e}")

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
    
    def _run_static_analysis(self, project_path: Path) -> List[Dict[str, Any]]:
        """Exécute des outils d'analyse statique sur le projet"""
        issues = []
        
        # Détecter le type de projet
        is_python = any(project_path.glob("**/*.py"))
        is_javascript = any(project_path.glob("**/*.js")) or any(project_path.glob("**/*.ts"))
        
        # Analyse Python avec pylint ou flake8
        if is_python:
            try:
                # Vérifier si pylint est installé
                result = subprocess.run(
                    ["pylint", "--version"], 
                    capture_output=True, 
                    text=True
                )
                if result.returncode == 0:
                    # Exécuter pylint
                    pylint_result = subprocess.run(
                        ["pylint", "--output-format=json", str(project_path)],
                        capture_output=True,
                        text=True
                    )
                    if pylint_result.returncode != 0 and pylint_result.stdout:
                        try:
                            pylint_issues = json.loads(pylint_result.stdout)
                            for issue in pylint_issues:
                                issues.append({
                                    "file": issue.get("path"),
                                    "type": "code_quality",
                                    "severity": "medium" if issue.get("type") in ["error", "fatal"] else "low",
                                    "description": issue.get("message"),
                                    "suggestion": f"Pylint: {issue.get('message-id')}"
                                })
                        except json.JSONDecodeError:
                            logger.warning("Impossible de parser la sortie de pylint")
            except FileNotFoundError:
                logger.info("Pylint n'est pas installé, analyse statique Python ignorée")
        
        # Analyse JavaScript/TypeScript avec ESLint
        if is_javascript:
            # Code similaire pour ESLint...
            pass
            
        return issues

    def analyze_project(self, project_path: Union[str, Path]) -> Dict[str, Any]:
        """Analyse un projet pour détecter des problèmes potentiels"""
        project_path = Path(project_path)
        if not project_path.exists():
            logger.error(f"Le projet {project_path} n'existe pas")
            raise FileNotFoundError(f"Le projet {project_path} n'existe pas")

        try:
            # Exécuter des outils d'analyse statique si disponibles
            static_analysis_results = self._run_static_analysis(project_path)

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

            # Fusionner les résultats
            if static_analysis_results:
                for issue in static_analysis_results:
                    if issue not in analysis.get("issues", []):
                        analysis.setdefault("issues", []).append(issue)
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
                        error_description = f"""
                        {issue.get('type','Bug')}: {issue.get('description', 'Problème non spécifié')}
                        """
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
