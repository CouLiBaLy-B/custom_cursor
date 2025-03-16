from typing import Dict, Optional, Any
import subprocess
import logging
import requests
import time
import os
import tempfile

from src.catche_manager import CacheManager
# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("cursor_project_creator.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class OllamaClient:
    """Client pour interagir avec Ollama (API ou CLI)"""

    def __init__(self, config: Dict[str, Any]):
        self.model_name = config["model_name"]
        self.api_url = config["ollama_api"]
        self.max_retries = config["max_retries"]
        self.temperature = config["temperature"]

        # Vérifier si ollama est disponible
        self.ollama_cli_available = self._check_ollama_cli()
        self.ollama_api_available = self._check_ollama_api()

        if not (self.ollama_cli_available or self.ollama_api_available):
            logger.error(
                "Ni l'API Ollama ni la ligne de commande Ollama ne sont disponibles."
            )
            raise RuntimeError(
                "Ollama n'est pas accessible. Assurez-vous qu'il est installé et en cours d'exécution."
            )

        logger.info(f"Mode Ollama: {'API' if self.ollama_api_available else 'CLI'}")

        # Initialiser le gestionnaire de cache
        self.cache = CacheManager(config["cache_dir"], enabled=config["cache_enabled"])

    def _check_ollama_cli(self) -> bool:
        """Vérifie si ollama est disponible en ligne de commande"""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (
            FileNotFoundError,
            subprocess.SubprocessError,
            subprocess.TimeoutExpired,
        ):
            return False

    def _check_ollama_api(self) -> bool:
        """Vérifie si l'API ollama est disponible"""
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def generate(self, prompt: str, model_name: Optional[str] = None) -> str:
        """Génère du texte avec Ollama, avec retry et cache"""
        model = model_name or self.model_name

        # Vérifier le cache
        cached_response = self.cache.get_from_cache(prompt, model)
        if cached_response:
            return cached_response

        # Génération avec retries
        for attempt in range(self.max_retries):
            try:
                if self.ollama_api_available:
                    response = self._generate_with_api(prompt, model)
                else:
                    response = self._generate_with_cli(prompt, model)

                # Sauvegarder dans le cache
                self.cache.save_to_cache(prompt, model, response)
                return response

            except Exception as e:
                logger.warning(
                    f"Erreur lors de la génération (tentative {attempt+1}/{self.max_retries}): {e}"
                )
                if attempt + 1 == self.max_retries:
                    logger.error(
                        f"Échec de la génération après {self.max_retries} tentatives"
                    )
                    raise
                time.sleep(2)  # Attendre avant de réessayer

    def _generate_with_api(self, prompt: str, model: str) -> str:
        """Utilise l'API Ollama pour générer du texte"""
        try:
            start_time = time.time()
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "temperature": self.temperature,
            }
            response = requests.post(self.api_url, json=payload, timeout=600)
            response.raise_for_status()
            duration = time.time() - start_time
            logger.debug(f"Génération via API en {duration:.2f}s")
            return response.json()["response"]
        except Exception as e:
            logger.error(f"Erreur API Ollama: {e}")
            raise

    def _generate_with_cli(self, prompt: str, model: str) -> str:
        """Utilise la CLI Ollama pour générer du texte"""
        try:
            # Créer un fichier temporaire pour le prompt
            fd, temp_path = tempfile.mkstemp(text=True)
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(prompt)

                start_time = time.time()
                # Exécuter ollama run avec le fichier de prompt
                result = subprocess.run(
                    [
                        "ollama",
                        "run",
                        model,
                        "--temperature",
                        str(self.temperature),
                        "-f",
                        temp_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )

                duration = time.time() - start_time
                logger.debug(f"Génération via CLI en {duration:.2f}s")

                if result.returncode != 0:
                    logger.error(f"Erreur Ollama CLI: {result.stderr}")
                    raise RuntimeError(f"Erreur Ollama: {result.stderr}")

                return result.stdout
            finally:
                # Supprimer le fichier temporaire
                os.unlink(temp_path)
        except Exception as e:
            logger.error(f"Erreur CLI Ollama: {e}")
            raise
