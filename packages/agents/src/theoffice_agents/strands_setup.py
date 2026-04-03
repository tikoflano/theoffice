"""Default Strands model configuration (Ollama for local dev)."""

import os

from strands.models import OllamaModel


def build_ollama_model() -> OllamaModel:
    """Construct an Ollama-backed Strands model from environment."""
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    model_id = os.environ.get("OLLAMA_MODEL", "llama3.2")
    return OllamaModel(host=host, model_id=model_id)
