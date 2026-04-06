"""Tests for ``InvocationParser``."""

from __future__ import annotations

import pytest

from theoffice_agents.invocation import InvocationParser, InvocationValidationError


def test_parse_minimal() -> None:
    p = InvocationParser().parse({"agent": "x", "prompt": "hi"})
    assert p.agent_id == "x"
    assert p.prompt == "hi"
    assert p.model_override is None


def test_parse_with_model() -> None:
    p = InvocationParser().parse(
        {"agent": "x", "prompt": "hi", "model": "groq/llama-3.1-8b-instant"}
    )
    assert p.model_override == "groq/llama-3.1-8b-instant"


def test_parse_empty_model_treated_absent() -> None:
    p = InvocationParser().parse({"agent": "x", "prompt": "hi", "model": "  "})
    assert p.model_override is None


def test_missing_agent() -> None:
    with pytest.raises(InvocationValidationError):
        InvocationParser().parse({"prompt": "hi"})


def test_missing_prompt() -> None:
    with pytest.raises(InvocationValidationError):
        InvocationParser().parse({"agent": "x"})
