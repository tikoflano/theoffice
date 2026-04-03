"""Default Strands model configuration (Ollama for local dev)."""

import os

from strands.models import OllamaModel


class TheOfficeOllamaModel(OllamaModel):
    """OllamaModel with a readable ``__str__`` for logging (``str`` / JSON extras)."""

    def __str__(self) -> str:
        cfg = self.get_config()
        model_id = cfg.get("model_id", "?")
        host = self.host or "?"
        return f"{model_id} @ {host}"


def build_ollama_model() -> OllamaModel:
    """Construct an Ollama-backed Strands model from environment."""
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    model_id = os.environ.get("OLLAMA_MODEL", "llama3.2")
    return TheOfficeOllamaModel(host=host, model_id=model_id)
