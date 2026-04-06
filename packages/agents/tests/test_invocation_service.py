"""Tests for ``InvocationService`` (mocked Strands ``Agent``)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from theoffice_agents.invocation_service import InvocationService
from theoffice_agents.model_factory import LiteLLMModelFactory
from theoffice_agents.model_resolution import ModelResolver
from theoffice_agents.registry import AgentRegistry


class _FakeResult:
    stop_reason = "end_turn"

    def __str__(self) -> str:
        return "Hello there."


class _FakeAgent:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def __call__(self, prompt: str) -> _FakeResult:
        self.last_prompt = prompt
        return _FakeResult()


def _registry_file(tmp_path: Path) -> Path:
    p = tmp_path / "agents.yaml"
    p.write_text(
        """
agents:
  - id: test-agent
    default_model: ollama/llama3.2
    system_prompt: You are a test bot.
""",
        encoding="utf-8",
    )
    return p


def _resolver_env() -> dict[str, str]:
    return {"OLLAMA_API_BASE": "http://ollama:11434"}


@pytest.fixture
def service(tmp_path: Path) -> InvocationService:
    reg = AgentRegistry.load(_registry_file(tmp_path))
    return InvocationService(
        reg,
        ModelResolver(_resolver_env()),
        LiteLLMModelFactory(),
    )


def test_unknown_agent(service: InvocationService) -> None:
    out = service.invoke_sync_outcome(
        {"agent": "nope", "prompt": "hi"},
        session_id=None,
    )
    assert out.status_code == 422
    body = out.body.decode()
    assert "VALIDATION_ERROR" in body
    assert "Unknown agent" in body


def test_validation_error(service: InvocationService) -> None:
    out = service.invoke_sync_outcome({"agent": "test-agent"}, session_id=None)
    assert out.status_code == 422


def test_model_not_configured(tmp_path: Path) -> None:
    reg = AgentRegistry.load(_registry_file(tmp_path))
    svc = InvocationService(
        reg,
        ModelResolver(_resolver_env()),
        LiteLLMModelFactory(),
    )
    out = svc.invoke_sync_outcome(
        {"agent": "test-agent", "prompt": "hi", "model": "groq/x"},
        session_id=None,
    )
    assert out.status_code == 501
    assert b"MODEL_NOT_CONFIGURED" in out.body
    assert b"GROQ_API_KEY" in out.body


@patch("theoffice_agents.invocation_service.Agent", _FakeAgent)
def test_success(tmp_path: Path) -> None:
    reg = AgentRegistry.load(_registry_file(tmp_path))
    svc = InvocationService(
        reg,
        ModelResolver(_resolver_env()),
        LiteLLMModelFactory(),
    )

    fake_model = object()
    with patch.object(svc, "_factory") as mf:
        mf.get = lambda mid: fake_model
        out = svc.invoke_sync_outcome(
            {"agent": "test-agent", "prompt": "Say hi."},
            session_id="sess-1",
        )

    assert isinstance(out, dict)
    assert out["response"] == "Hello there."
    assert out["stop_reason"] == "end_turn"
    assert out["agent"] == "test-agent"
    assert out["model"] == "ollama/llama3.2"
    assert out["session_id"] == "sess-1"
