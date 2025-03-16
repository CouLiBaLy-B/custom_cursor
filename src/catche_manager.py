"""Gestionnaire de cache pour stocker et récupérer des réponses."""
import hashlib
import logging
from pathlib import Path
from typing import Optional

# import os

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CacheManager:
    """Gestionnaire de cache pour stocker et récupérer des réponses."""

    def __init__(self, cache_dir: str, enabled: bool = True):
        """Initialise le gestionnaire de cache avec le répertoire spécifié."""
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled
        if enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cache_key(self, prompt: str, model_name: str) -> str:
        """Génère une clé de cache basée sur le prompt et le modèle"""
        content = f"{model_name}:{prompt}"
        return hashlib.md5(content.encode()).hexdigest()

    def get_from_cache(self, prompt: str, model_name: str) -> Optional[str]:
        """Récupère une réponse du cache si disponible."""
        if not self.enabled:
            return None

        cache_key = self.get_cache_key(prompt, model_name)
        cache_file = self.cache_dir / cache_key

        if cache_file.exists():
            logger.debug(f"Cache hit pour {cache_key[:10]}...")
            return cache_file.read_text(encoding="utf-8")
        return None

    def save_to_cache(self, prompt: str, model_name: str, response: str) -> None:
        """Sauvegarde une réponse dans le cache."""
        if not self.enabled:
            return

        cache_key = self.get_cache_key(prompt, model_name)
        cache_file = self.cache_dir / cache_key

        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(response)
        logger.debug(f"Réponse mise en cache: {cache_key[:10]}...")
