"""Tests for ``ModelResolver``."""

from __future__ import annotations

import pytest

from theoffice_agents.model_resolution import (
    ModelNotConfiguredError,
    ModelResolver,
    UnresolvedModelError,
    UnsupportedProviderError,
)


def test_resolution_order_override_last() -> None:
    env = {
        "DEFAULT_LLM_MODEL": "ollama/from-env",
        "GROQ_API_KEY": "x",
    }
    r = ModelResolver(env)
    out = r.resolve(
        agent_default_model="groq/from-agent",
        model_override="groq/from-body",
    )
    assert out.model_id == "groq/from-body"


def test_agent_overwrites_env() -> None:
    env = {"DEFAULT_LLM_MODEL": "ollama/from-env", "GROQ_API_KEY": "k"}
    r = ModelResolver(env)
    out = r.resolve(
        agent_default_model="groq/from-agent",
        model_override=None,
    )
    assert out.model_id == "groq/from-agent"


def test_env_only() -> None:
    env = {
        "DEFAULT_LLM_MODEL": "ollama/llama3.2",
        "OLLAMA_API_BASE": "http://ollama:11434",
    }
    r = ModelResolver(env)
    out = r.resolve(agent_default_model=None, model_override=None)
    assert out.model_id == "ollama/llama3.2"


def test_unresolved() -> None:
    r = ModelResolver({})
    with pytest.raises(UnresolvedModelError):
        r.resolve(agent_default_model=None, model_override=None)


def test_groq_missing_key() -> None:
    r = ModelResolver({})
    with pytest.raises(ModelNotConfiguredError) as ei:
        r.resolve(
            agent_default_model="groq/llama-3.1-8b-instant",
            model_override=None,
        )
    assert ei.value.missing_environment_variables == ["GROQ_API_KEY"]
    assert "groq/" in ei.value.resolved_model


def test_groq_with_key() -> None:
    r = ModelResolver({"GROQ_API_KEY": "secret"})
    out = r.resolve(
        agent_default_model="groq/llama-3.1-8b-instant",
        model_override=None,
    )
    assert out.model_id == "groq/llama-3.1-8b-instant"


def test_unsupported_provider_prefix() -> None:
    r = ModelResolver({"DEFAULT_LLM_MODEL": "foo/bar-model"})
    with pytest.raises(UnsupportedProviderError):
        r.resolve(agent_default_model=None, model_override=None)


def test_ollama_requires_api_base() -> None:
    r = ModelResolver({})
    with pytest.raises(ModelNotConfiguredError) as ei:
        r.resolve(agent_default_model="ollama/llama3.2", model_override=None)
    assert ei.value.missing_environment_variables == ["OLLAMA_API_BASE"]


def test_ollama_with_api_base() -> None:
    r = ModelResolver({"OLLAMA_API_BASE": "http://ollama:11434"})
    out = r.resolve(agent_default_model="ollama/llama3.2", model_override=None)
    assert out.model_id == "ollama/llama3.2"
