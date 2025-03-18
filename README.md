# Cursor Project Generator
## Description
Cursor Project Generator est un outil avancé qui automatise la création de structures de projets logiciels en utilisant des modèles d'IA. Il permet de générer rapidement des projets complets à partir d'une simple description, en créant tous les fichiers, dossiers et configurations nécessaires pour démarrer immédiatement le développement.

## Fonctionnalités principales
-    Génération complète de projets à partir d'une simple description textuelle
-    Utilisation de templates pour des structures de projets réutilisables
-    Analyse et correction automatique des problèmes dans le code généré
-    Génération de documentation complète pour les projets
-    Intégration avec Ollama (API ou CLI) pour la génération de contenu
-    Système de cache pour améliorer les performances
-    Configuration d'environnement (venv, Git) automatique
## Installation
### Prérequis
- Python 3.10 ou supérieur
- Accès à Ollama (API ou CLI)
### Installation des dépendances
```bash	
pip install requests tqdm pyyaml markdown
```

### Configuration d'Ollama
Assurez-vous qu'Ollama est installé et configuré sur votre système. L'application tentera d'utiliser l'API Ollama par défaut, et se rabattra sur la CLI si l'API n'est pas disponible.

## Utilisation
### Création d'un projet
```bash
python main.py create "Description détaillée de votre projet"
```

### Avec un template:
```bash
python main.py create "Description du projet" --template nom_du_template
```

### Avec validation automatique:
```bash
python main.py create "Description du projet" --validate
```

## Gestion des templates
### Lister les templates disponibles:
```bash	
python main.py list-templates
```

### Créer un template à partir d'un projet existant:
```bash
python main.py save-template /chemin/vers/projet nom_du_template
```

## Analyse et correction
### Analyser un projet pour détecter des problèmes:
```bash
python main.py analyze /chemin/vers/projet --output rapport.json
```

### Corriger un fichier spécifique:
```bash	
python main.py fix-file /chemin/vers/fichier.py "Description du problème à corriger"
```

### Corriger automatiquement un projet entier:
```bash
python main.py fix-project /chemin/vers/projet
```

### Valider et corriger un projet:
```bash
python main.py validate /chemin/vers/projet --fix
```

## Génération de documentation
### Générer une documentation complète pour un projet:
```bash
python main.py generate-docs /chemin/vers/projet
```

### Générer une documentation au format HTML:
```bash
python main.py generate-docs /chemin/vers/projet --format html
```




## Options globales
```md
--config : Chemin vers un fichier de configuration personnalisé
--model : Modèle Ollama à utiliser
--path : Chemin de base pour la création des projets
--no-venv : Ne pas configurer d'environnement virtuel
--no-git : Ne pas initialiser Git
--no-cursor : Ne pas ouvrir dans Cursor
--no-cache : Désactiver le cache
--verbose : Mode verbeux (plus de détails dans les logs)
--quiet : Mode silencieux (moins de messages)
```
## Configuration
L'application peut être configurée via un fichier JSON ou YAML. La configuration par défaut peut être surchargée par des variables d'environnement préfixées par CURSOR_GEN_.

### Exemple de configuration:
```python
model_name: codellama:7b
base_path: ./projects
templates_dir: ./templates
cache_dir: ./.cache
cache_enabled: true
setup_venv: true
init_git: true
open_in_cursor: true
max_workers: 4
max_retries: 3
temperature: 0.7
ollama_api: http://localhost:11434/api/generate
```

### Exemples d'utilisation avancée
### Workflow complet de développement
```bash
# Créer un projet avec validation
python main.py create "Application web de gestion de tâches avec authentification" --validate

# Générer la documentation
python main.py generate-docs ./projects/task_manager_20230615_120000 --format html

# Analyser le projet pour détecter des problèmes
python main.py analyze ./projects/task_manager_20230615_120000 --output analyse.json

# Corriger automatiquement les problèmes
python main.py fix-project ./projects/task_manager_20230615_120000 --analysis analyse.json
```

## Création d'un template réutilisable
### Créer un projet initial
```bash
python main.py create "API REST Flask avec authentification JWT et base de données SQLite"
```
### Sauvegarder comme template
```bash
python main.py save-template ./projects/flask_api_20230615_120000 flask_api_template
```
### Utiliser le template pour un nouveau projet
```bash
python main.py create "API de gestion de bibliothèque" --template flask_api_template
```

## Dépannage
Si vous rencontrez des problèmes:

- Vérifiez que Ollama est correctement installé et accessible
- Utilisez l'option --verbose pour obtenir plus d'informations de débogage
- Consultez les logs dans cursor_project_creator.log
## Contribution
Les contributions sont les bienvenues! N'hésitez pas à soumettre des pull requests ou à créer des issues pour signaler des bugs ou proposer des fonctionnalités.

## Licence
Ce projet est sous licence MIT. Voir le fichier LICENSE pour plus de détails.

## Crédits
Développé par Ibrahim avec le support de l'équipe Ollama API.