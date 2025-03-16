"""Configuration par défaut pour le projet."""
# Configuration par défaut
DEFAULT_CONFIG = {
    "model_name": "qwen2.5-coder",
    "ollama_api": "http://localhost:11434/api/generate",
    "base_path": "./projects",
    "max_workers": 3,
    "max_retries": 3,
    "cache_enabled": True,
    "cache_dir": "./.cache",
    "templates_dir": "./templates",
    "max_tokens": 4096,
    "temperature": 0.7,
    "setup_venv": True,
    "init_git": True,
    "open_in_cursor": True,
}
