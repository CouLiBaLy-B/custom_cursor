#!/usr/bin/env python3
"""Point d'entrée principal pour l'application."""
import argparse
import json
import shutil
import sys
from pathlib import Path
import markdown

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
    parser.add_argument("--verbose", "-v", action="store_true", help="Mode verbeux")
    parser.add_argument("--quiet", "-q", action="store_true", help="Mode silencieux")

    # Sous-commandes
    subparsers = parser.add_subparsers(dest="command", help="Commande à exécuter")

    # Commande pour créer un projet
    create_parser = subparsers.add_parser("create", help="Créer un nouveau projet")
    create_parser.add_argument(
        "description", type=str, help="Description du projet à créer"
    )
    create_parser.add_argument("--template", "-t", type=str, help="Template à utiliser")
    create_parser.add_argument(
        "--validate", action="store_true", help="Valider et corriger le projet après création"
    )
    create_parser.add_argument(
        "--recover", type=str, help="Reprendre une création à partir d'un fichier de récupération"
    )

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

    # Nouvelle commande pour valider un projet
    validate_parser = subparsers.add_parser(
        "validate", help="Valider et corriger un projet existant"
    )
    validate_parser.add_argument(
        "project_path", type=str, help="Chemin vers le projet à valider"
    )
    validate_parser.add_argument(
        "--fix", action="store_true", help="Corriger automatiquement les problèmes trouvés"
    )

    # Nouvelle commande pour générer la documentation
    docs_parser = subparsers.add_parser(
        "generate-docs", help="Générer la documentation complète d'un projet"
    )
    docs_parser.add_argument(
        "project_path", type=str, help="Chemin vers le projet à documenter"
    )
    docs_parser.add_argument(
        "--format", choices=["markdown", "html"], default="markdown",
        help="Format de la documentation"
    )

    # Argument pour la compatibilité avec l'ancienne version (sans sous-commande)
    parser.add_argument("description_compat", nargs="?", help=argparse.SUPPRESS)

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
        if args.verbose:
            import logging
            logging.getLogger().setLevel(logging.DEBUG)
        if args.quiet:
            import logging
            logging.getLogger().setLevel(logging.WARNING)

        # Déterminer quelle commande exécuter
        if args.command == "create":
            # Vérifier si on reprend une création
            if getattr(args, "recover", None):
                recovery_file = Path(args.recover)
                if not recovery_file.exists():
                    print(f"\n❌ Fichier de récupération {recovery_file} introuvable")
                    return 1
                    
                try:
                    with open(recovery_file, "r", encoding="utf-8") as f:
                        recovery_data = json.load(f)
                    print(f"\n🔄 Reprise de la création à partir de {recovery_file}")
                    # Logique de reprise à implémenter dans la classe CursorProjectGenerator
                    project_path = generator.resume_project_creation(recovery_data)
                except Exception as e:
                    print(f"\n❌ Erreur lors de la reprise de la création: {str(e)}")
                    return 1
            else:
                # Création normale
                project_path = generator.create_project(
                    args.description, getattr(args, "template", None)
                )
                
            if project_path:
                show_project_info(project_path)
                
                # Valider le projet si demandé
                if getattr(args, "validate", False):
                    print("\n🔍 Validation du projet...")
                    validation_results = generator.validate_and_fix_project(project_path)
                    
                    if validation_results["validation_status"] == "success":
                        print("✅ Projet validé avec succès!")
                    elif validation_results["validation_status"] == "fixed":
                        print(f"🔧 {validation_results['issues_fixed']} problèmes corrigés automatiquement")
                    else:
                        print(f"⚠️ {validation_results['issues_found'] - validation_results['issues_fixed']} problèmes non résolus")
                        print("   Consultez le rapport de validation pour plus de détails")
            else:
                print("\n❌ Échec de la création du projet")
                return 1

        elif args.command == "list-templates":
            templates = generator.list_templates()
            if templates:
                print("\n📋 Templates disponibles:")
                for template in templates:
                    print(f"\n- {template['name']}")
                    print(f"  Description: {template['description']}")
                    print(f"  Fichier: {template['file']}")
                    if 'languages' in template and template['languages']:
                        print(f"  Langages: {', '.join(template['languages'])}")
                    if 'file_count' in template:
                        print(f"  Fichiers: {template['file_count']}, Dossiers: {template['folder_count']}")
            else:
                print("\nAucun template disponible.")
                print(f"Vous pouvez en créer dans le dossier: {generator.templates_dir}")

        elif args.command == "save-template":
            success = generator.save_as_template(args.project_path, args.template_name)
            if success:
                print(f"\n✅ Template '{args.template_name}' créé avec succès")
                print(f"Chemin: {generator.templates_dir / f'{args.template_name}.yaml'}")
            else:
                print(f"\n❌ Échec de la création du template '{args.template_name}'")
                return 1

        # Mode de compatibilité - si aucune commande n'est spécifiée mais description_compat est fourni
        elif args.description_compat:
            project_path = generator.create_project(args.description_compat)
            if project_path:
                show_project_info(project_path)
            else:
                print("\n❌ Échec de la création du projet")
                return 1

        elif args.command == "analyze":
            try:
                analysis = generator.analyze_project(args.project_path)
                print("\n📊 Analyse du projet terminée:")
                print(f"- Qualité globale: {analysis.get('overall_quality', 'Non évaluée')}")
                print(f"- Problèmes détectés: {len(analysis.get('issues', []))}")

                # Afficher un résumé
                if analysis.get("issues"):
                    print("\nProblèmes principaux:")
                    for i, issue in enumerate(analysis["issues"][:5]):
                        # Limiter à 5 problèmes
                        print(
                            f"  {i + 1}. [{issue.get('severity', 'medium')}] {issue.get('file')}:"
                        )
                        print(f"     {issue.get('description')}")

                    if len(analysis["issues"]) > 5:
                        print(f"  ... et {len(analysis['issues']) - 5} autres problèmes")

                # Sauvegarder dans un fichier si demandé
                if args.output:
                    with open(args.output, "w", encoding="utf-8") as f:
                        json.dump(analysis, f, indent=2)
                    print(f"\nRapport complet sauvegardé dans: {args.output}")
                else:
                    print("\nUtilisez --output pour sauvegarder le rapport complet")
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
                        print(f"\n❌ Le fichier d'analyse {analysis_path} n'existe pas")
                        return 1

                    with open(analysis_path, "r", encoding="utf-8") as f:
                        analysis = json.load(f)
                    print(f"📊 Utilisation de l'analyse depuis: {analysis_path}")

                print(f"\n🔍 Correction du projet: {project_path}")

                # Corriger le projet
                report = generator.fix_project(project_path, analysis)

                # Afficher un résumé
                print("\n✅ Correction terminée:")
                print(f"- Fichiers corrigés: {report['fixed_count']}")
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
                
        elif args.command == "validate":
            try:
                project_path = Path(args.project_path)
                if not project_path.exists():
                    print(f"\n❌ Le projet {project_path} n'existe pas")
                    return 1
                    
                print(f"\n🔍 Validation du projet: {project_path}")
                
                # Valider le projet
                results = generator.validate_and_fix_project(project_path)
                
                # Afficher les résultats
                print(f"\n📊 Validation terminée: {results['issues_found']} problèmes trouvés")
                
                if results["validation_status"] == "success":
                    print("✅ Aucun problème détecté!")
                elif results["validation_status"] == "fixed":
                    print(f"🔧 Tous les problèmes ({results['issues_fixed']}) ont été corrigés automatiquement")
                elif results["validation_status"] == "issues_remaining":
                    print(f"⚠️ {results['issues_found'] - results['issues_fixed']} problèmes non résolus")
                else:
                    print("❌ Erreur lors de la validation")
                    
                # Afficher les détails
                if results.get("details"):
                    print("\nDétails des problèmes:")
                    for i, issue in enumerate(results["details"][:5]):
                        status = "✅" if issue.get("fixed") else "❌"
                        print(f"  {i+1}. {status} {issue['file']}: {issue['description']}")
                        if issue.get("fixed") and issue.get("solution"):
                            print(f"     Solution: {issue['solution']}")
                            
                    if len(results["details"]) > 5:
                        print(f"  ... et {len(results['details']) - 5} autres problèmes")
                        
                print(f"\nRapport complet sauvegardé dans: {project_path}/validation_report.json")
                
            except Exception as e:
                print(f"\n❌ Erreur lors de la validation: {str(e)}")
                return 1
                
        elif args.command == "generate-docs":
            try:
                project_path = Path(args.project_path)
                if not project_path.exists():
                    print(f"\n❌ Le projet {project_path} n'existe pas")
                    return 1
                    
                print(f"\n📝 Génération de documentation pour: {project_path}")
                
                # Générer la documentation
                results = generator.generate_project_documentation(project_path)
                
                # Afficher les résultats
                if results["status"] == "success":
                    print("✅ Documentation générée avec succès!")
                elif results["status"] == "partial":
                    print("⚠️ Documentation partiellement générée")
                else:
                    print("❌ Échec de la génération de documentation")
                    
                # Afficher les fichiers générés
                if results.get("generated_files"):
                    print("\nFichiers de documentation générés:")
                    for file in results["generated_files"]:
                        print(f"  - {file}")
                        
                # Afficher les erreurs
                if results.get("errors"):
                    print("\nErreurs rencontrées:")
                    for error in results["errors"]:
                        print(f"  - {error['file']}: {error['error']}")
                        
                # Convertir en HTML si demandé
                if args.format == "html" and results.get("generated_files"):
                    try:
                        
                        print("\n🔄 Conversion en HTML...")
                        
                        html_dir = project_path / "docs" / "html"
                        html_dir.mkdir(exist_ok=True)
                        
                        for md_file in results["generated_files"]:
                            md_path = project_path / md_file
                            if md_path.exists() and md_path.suffix == '.md':
                                html_content = markdown.markdown(
                                    md_path.read_text(encoding="utf-8"),
                                    extensions=['extra', 'codehilite']
                                )
                                
                                # Ajouter un style CSS basique
                                                                # Ajouter un style CSS basique
                                html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{md_path.stem}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; padding: 20px; max-width: 900px; margin: 0 auto; color: #333; }}
        h1, h2, h3, h4, h5, h6 {{ margin-top: 24px; margin-bottom: 16px; font-weight: 600; line-height: 1.25; }}
        h1 {{ font-size: 2em; padding-bottom: .3em; border-bottom: 1px solid #eaecef; }}
        h2 {{ font-size: 1.5em; padding-bottom: .3em; border-bottom: 1px solid #eaecef; }}
        a {{ color: #0366d6; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        code, pre {{ font-family: SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace; }}
        pre {{ padding: 16px; overflow: auto; line-height: 1.45; background-color: #f6f8fa; border-radius: 3px; }}
        code {{ padding: 0.2em 0.4em; margin: 0; background-color: rgba(27,31,35,0.05); border-radius: 3px; }}
        pre code {{ background-color: transparent; padding: 0; }}
        blockquote {{ padding: 0 1em; color: #6a737d; border-left: 0.25em solid #dfe2e5; }}
        table {{ border-collapse: collapse; width: 100%; }}
        table th, table td {{ padding: 6px 13px; border: 1px solid #dfe2e5; }}
        table tr {{ background-color: #fff; border-top: 1px solid #c6cbd1; }}
        table tr:nth-child(2n) {{ background-color: #f6f8fa; }}
        img {{ max-width: 100%; }}
    </style>
</head>
<body>
    {html_content}
</body>
</html>"""
                                
                                # Écrire le fichier HTML
                                html_path = html_dir / f"{md_path.stem}.html"
                                with open(html_path, "w", encoding="utf-8") as f:
                                    f.write(html_content)
                                    
                        # Créer un index HTML
                        index_content = "<h1>Documentation du projet</h1>\n<ul>"
                        for md_file in results["generated_files"]:
                            md_path = project_path / md_file
                            if md_path.exists() and md_path.suffix == '.md':
                                html_file = f"{md_path.stem}.html"
                                index_content += f'<li><a href="{html_file}">{md_path.stem}</a></li>\n'
                        index_content += "</ul>"
                        
                        # Ajouter le même style CSS
                        index_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Documentation</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; padding: 20px; max-width: 900px; margin: 0 auto; color: #333; }}
        h1, h2, h3, h4, h5, h6 {{ margin-top: 24px; margin-bottom: 16px; font-weight: 600; line-height: 1.25; }}
        h1 {{ font-size: 2em; padding-bottom: .3em; border-bottom: 1px solid #eaecef; }}
        h2 {{ font-size: 1.5em; padding-bottom: .3em; border-bottom: 1px solid #eaecef; }}
        a {{ color: #0366d6; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        ul {{ padding-left: 2em; }}
    </style>
</head>
<body>
    {index_content}
</body>
</html>"""
                        
                        # Écrire l'index HTML
                        with open(html_dir / "index.html", "w", encoding="utf-8") as f:
                            f.write(index_html)
                            
                        print(f"✅ Documentation HTML générée dans: {html_dir}")
                        
                    except ImportError:
                        print("⚠️ Module 'markdown' non trouvé. Installation avec: pip install markdown")
                    except Exception as e:
                        print(f"⚠️ Erreur lors de la conversion en HTML: {str(e)}")
                
            except Exception as e:
                print(f"\n❌ Erreur lors de la génération de documentation: {str(e)}")
                return 1

        else:
            parser.print_help()

    except KeyboardInterrupt:
        print("\n\n⚠️ Opération annulée par l'utilisateur")
        return 130
    except Exception as e:
        print(f"\n❌ Erreur: {str(e)}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1
        
    return 0


if __name__ == "__main__":
    sys.exit(main())


