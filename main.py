#!/usr/bin/env python3
"""Point d'entrée principal pour l'application."""
import argparse
import json
import shutil
from pathlib import Path

from src.cursor_project_generator import CursorProjectGenerator
from src.display_info import show_project_info


def main():
    """Point d'entrée principal pour l'application."""
    parser = argparse.ArgumentParser(
        description="Générateur avancé de projets basé sur les modèles IA"
    )

    # Options globales
    parser.add_argument(
        "--config", type=str, help="Chemin vers le fichier de configuration"
    )
    parser.add_argument("--model", type=str, help="Modèle Ollama à utiliser")
    parser.add_argument(
        "--path", type=str, help="Chemin de base pour la création des projets"
    )
    parser.add_argument(
        "--no-venv",
        action="store_true",
        help="Ne pas configurer d'environnement virtuel",
    )
    parser.add_argument("--no-git", action="store_true", help="Ne pas initialiser Git")
    parser.add_argument(
        "--no-cursor", action="store_true", help="Ne pas ouvrir dans Cursor"
    )
    parser.add_argument("--no-cache", action="store_true", help="Désactiver le cache")

    # Sous-commandes optionnelles
    subparsers = parser.add_subparsers(dest="command", help="Commande à exécuter")

    # Commande pour créer un projet
    create_parser = subparsers.add_parser("create", help="Créer un nouveau projet")
    create_parser.add_argument(
        "description", type=str, help="Description du projet à créer"
    )
    create_parser.add_argument("--template", "-t", type=str, help="Template à utiliser")

    # Commande pour lister les templates
    subparsers.add_parser("list-templates", help="Lister les templates disponibles")

    # Commande pour créer un template
    save_template_parser = subparsers.add_parser(
        "save-template", help="Sauvegarder un projet comme template"
    )
    save_template_parser.add_argument(
        "project_path", type=str, help="Chemin vers le projet à sauvegarder"
    )
    save_template_parser.add_argument("template_name", type=str, help="Nom du template")

    # Argument pour la compatibilité avec l'ancienne version (sans sous-commande)
    parser.add_argument("description_compat", nargs="?", help=argparse.SUPPRESS)

    # Commande pour analyser un projet
    analyze_parser = subparsers.add_parser(
        "analyze", help="Analyser un projet pour trouver des problèmes"
    )
    analyze_parser.add_argument(
        "project_path", type=str, help="Chemin vers le projet à analyser"
    )
    analyze_parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Fichier de sortie pour le rapport d'analyse (JSON)",
    )

    # Commande pour corriger un fichier spécifique
    fix_file_parser = subparsers.add_parser(
        "fix-file", help="Corriger un fichier spécifique"
    )
    fix_file_parser.add_argument(
        "file_path", type=str, help="Chemin vers le fichier à corriger"
    )
    fix_file_parser.add_argument(
        "error_description", type=str, help="Description du problème à corriger"
    )
    fix_file_parser.add_argument(
        "--backup",
        "-b",
        action="store_true",
        help="Créer une sauvegarde du fichier original",
    )

    # Commande pour corriger un projet entier
    fix_project_parser = subparsers.add_parser(
        "fix-project", help="Corriger automatiquement les problèmes d'un projet"
    )
    fix_project_parser.add_argument(
        "project_path", type=str, help="Chemin vers le projet à corriger"
    )
    fix_project_parser.add_argument(
        "--analysis",
        "-a",
        type=str,
        help="Fichier JSON contenant une analyse existante",
    )

    args = parser.parse_args()

    try:
        # Initialiser le générateur
        generator = CursorProjectGenerator(config_path=args.config)

        # Appliquer les arguments de ligne de commande qui surchargent la config
        if args.model:
            generator.config["model_name"] = args.model
        if args.path:
            generator.config["base_path"] = args.path
        if args.no_venv:
            generator.config["setup_venv"] = False
        if args.no_git:
            generator.config["init_git"] = False
        if args.no_cursor:
            generator.config["open_in_cursor"] = False
        if args.no_cache:
            generator.config["cache_enabled"] = False

        # Déterminer quelle commande exécuter
        if args.command == "create":
            project_path = generator.create_project(
                args.description, getattr(args, "template", None)
            )
            if project_path:
                show_project_info(project_path)
            else:
                print("\n❌ Échec de la création du projet")

        elif args.command == "list-templates":
            templates = generator.list_templates()
            if templates:
                print("\n📋 Templates disponibles:")
                for template in templates:
                    print(f"\n- {template['name']}")
                    print(f"  Description: {template['description']}")
                    print(f"  Fichier: {template['file']}")
            else:
                print("\nAucun template disponible.")
                print(
                    f"Vous pouvez en créer dans le dossier: {generator.templates_dir}"
                )

        elif args.command == "save-template":
            success = generator.save_as_template(args.project_path, args.template_name)
            if success:
                print(f"\n✅ Template '{args.template_name}' créé avec succès")
                print(
                    f"Chemin: {generator.templates_dir / f'{args.template_name}.yaml'}"
                )
            else:
                print(f"\n❌ Échec de la création du template '{args.template_name}'")

        # Mode de compatibilité - si aucune commande n'est spécifiée mais description_compat est fourni
        elif args.description_compat:
            project_path = generator.create_project(args.description_compat)
            if project_path:
                show_project_info(project_path)
            else:
                print("\n❌ Échec de la création du projet")

        elif args.command == "analyze":
            try:
                analysis = generator.analyze_project(args.project_path)
                print("\n📊 Analyse du projet terminée:")
                print(
                    f"- Qualité globale: {analysis.get('overall_quality', 'Non évaluée')}"
                )
                print(f"- Problèmes détectés: {len(analysis.get('issues', []))}")

                # Afficher un résumé
                if analysis.get("issues"):
                    print("\nProblèmes principaux:")
                    for i, issue in enumerate(analysis["issues"][:5]):
                        # Limiter à 5 problèmes
                        print(
                            f"""  {i + 1}. [{issue.get('severity', 'medium')}] {issue.get('file')}:
                            {issue.get('description')}"""
                        )

                    if len(analysis["issues"]) > 5:
                        print(
                            f"  ... et {len(analysis['issues']) - 5} autres problèmes"
                        )

                # Sauvegarder dans un fichier si demandé
                if args.output:
                    with open(args.output, "w", encoding="utf-8") as f:
                        json.dump(analysis, f, indent=2)
                    print(f"\nRapport complet sauvegardé dans: {args.output}")
            except Exception as e:
                print(f"\n❌ Erreur lors de l'analyse: {str(e)}")
                return 1
        elif args.command == "fix-file":
            try:
                file_path = Path(args.file_path)
                if not file_path.exists():
                    print(f"\n❌ Le fichier {file_path} n'existe pas")
                    return 1

                print(f"\n🔍 Correction du fichier: {file_path}")
                # Créer une sauvegarde si demandée
                if args.backup:
                    backup_path = file_path.with_suffix(file_path.suffix + ".bak")
                    shutil.copy2(file_path, backup_path)
                    print(f"📑 Sauvegarde créée: {backup_path}")

                    # Corriger le fichier
                corrected_content = generator.fix_code(
                    file_path, args.error_description
                )

                # Écrire le contenu corrigé
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(corrected_content)

                print("✅ Fichier corrigé avec succès")

            except Exception as e:
                print(f"\n❌ Erreur lors de la correction: {str(e)}")
                return 1
        elif args.command == "fix-project":
            try:
                project_path = Path(args.project_path)
                if not project_path.exists():
                    print(f"\n❌ Le projet {project_path} n'existe pas")
                    return 1

                # Charger une analyse existante si spécifiée
                analysis = None
                if args.analysis:
                    analysis_path = Path(args.analysis)
                    if not analysis_path.exists():
                        print("\n❌ Le fichier d'analyse {analysis_path} n'existe pas")
                        return 1

                    with open(analysis_path, "r", encoding="utf-8") as f:
                        analysis = json.load(f)
                    print(f"📊 Utilisation de l'analyse depuis: {analysis_path}")

                print(f"\n🔍 Correction du projet: {project_path}")

                # Corriger le projet
                report = generator.fix_project(project_path, analysis)

                # Afficher un résumé
                print("\n✅ Correction terminée:")
                print("- Fichiers corrigés: {report['fixed_count']}")
                print(f"- Fichiers ignorés: {report['skipped_count']}")
                print(f"- Erreurs: {report['error_count']}")

                if report["fixed_count"] > 0:
                    print("\nFichiers corrigés:")
                    for fixed in report["details"]["fixed_files"][:5]:
                        # Limiter à 5 fichiers
                        print(f" - {fixed['file']} ({fixed['issue']})")

                    if len(report["details"]["fixed_files"]) > 5:
                        print(
                            f"  ... et {len(report['details']['fixed_files']) - 5} autres fichiers"
                        )

                print(
                    f"\nRapport complet sauvegardé dans: {project_path}/fix_report.json"
                )

            except Exception as e:
                print(f"\n❌ Erreur lors de la correction du projet: {str(e)}")
                return 1

        else:
            parser.print_help()
            print("\nUtilisez --output pour sauvegarder le rapport complet")

    except Exception as e:
        print(f"\n❌ Erreur lors de l'analyse: {str(e)}")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
