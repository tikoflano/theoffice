"""Construct and cache Strands model instances (native Ollama vs LiteLLM)."""

from __future__ import annotations

import json
import os
from typing import Any

from strands.models import LiteLLMModel
from strands.models.model import Model

from theoffice_agents.strands_setup import native_ollama_model_from_litellm_id


class LiteLLMModelFactory:
    """Build ``Model`` instances keyed by logical model id (e.g. ``ollama/llama3.2``)."""

    def __init__(self, *, max_cached: int = 32) -> None:
        self._max_cached = max_cached
        self._cache: dict[str, Model] = {}
        self._order: list[str] = []

    def get(self, model_id: str) -> Model:
        if model_id in self._cache:
            return self._cache[model_id]

        if model_id.lower().startswith("ollama/"):
            model: Model = native_ollama_model_from_litellm_id(model_id)
        else:
            client_args: dict[str, Any] = dict(_load_litellm_client_args() or {})
            model = LiteLLMModel(
                client_args=client_args if client_args else None,
                model_id=model_id,
            )

        self._cache[model_id] = model
        self._order.append(model_id)
        self._evict_if_needed()
        return model

    def _evict_if_needed(self) -> None:
        while len(self._order) > self._max_cached:
            oldest = self._order.pop(0)
            self._cache.pop(oldest, None)


def _load_litellm_client_args() -> dict[str, Any] | None:
    raw = os.environ.get("LLM_LITELLM_CLIENT_ARGS_JSON", "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return dict(parsed)
    return None
