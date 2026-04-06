"""Tests for ``LiteLLMModelFactory``."""

from __future__ import annotations

import pytest
from strands.models import LiteLLMModel
from strands.models.ollama import OllamaModel

from theoffice_agents.model_factory import LiteLLMModelFactory


@pytest.fixture
def ollama_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_API_BASE", "http://ollama:11434")


def test_ollama_uses_native_strands_client(ollama_base: None) -> None:
    f = LiteLLMModelFactory()
    m = f.get("ollama/llama3.2")
    assert isinstance(m, OllamaModel)
    assert m.get_config()["model_id"] == "llama3.2"
    assert m.host == "http://ollama:11434"


def test_non_ollama_uses_litellm() -> None:
    f = LiteLLMModelFactory()
    m = f.get("groq/llama-3.1-8b-instant")
    assert isinstance(m, LiteLLMModel)
