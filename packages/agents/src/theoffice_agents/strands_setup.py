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
    host = os.environ.get("OLLAMA_API_BASE", "http://127.0.0.1:11434")
    model_id = os.environ.get("OLLAMA_MODEL", "llama3.2")
    return TheOfficeOllamaModel(host=host, model_id=model_id)


def native_ollama_model_from_litellm_id(litellm_model_id: str) -> OllamaModel:
    """Map ``ollama/<tag>`` (LiteLLM-style id) to Strands ``TheOfficeOllamaModel``.

    Strands' ``LiteLLMModel`` + Ollama often yields empty assistant text for some models;
    the native Ollama client does not.
    """
    if not litellm_model_id.lower().startswith("ollama/"):
        raise ValueError(f"Expected ollama/... model id, got {litellm_model_id!r}")
    tag = litellm_model_id.split("/", 1)[1]
    host = (os.environ.get("OLLAMA_API_BASE") or "").strip() or "http://127.0.0.1:11434"
    return TheOfficeOllamaModel(host=host, model_id=tag)
