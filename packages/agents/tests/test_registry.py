"""Tests for ``AgentRegistry``."""

from __future__ import annotations

from pathlib import Path

import pytest

from theoffice_agents.registry import AgentDefinition, AgentRegistry, AgentRegistryError


def _write(p: Path, text: str) -> Path:
    p.write_text(text, encoding="utf-8")
    return p


def test_load_valid(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "a.yaml",
        """
agents:
  - id: a1
    default_model: ollama/llama3.2
    system_prompt: You are A.
  - id: a2
    system_prompt: You are B.
""",
    )
    reg = AgentRegistry.load(path)
    assert len(reg) == 2
    a1 = reg.get("a1")
    assert a1 == AgentDefinition(
        id="a1",
        default_model="ollama/llama3.2",
        system_prompt="You are A.",
    )
    a2 = reg.get("a2")
    assert a2 is not None
    assert a2.default_model is None


def test_duplicate_id(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "dup.yaml",
        """
agents:
  - id: same
    system_prompt: One
  - id: same
    system_prompt: Two
""",
    )
    with pytest.raises(AgentRegistryError, match="Duplicate"):
        AgentRegistry.load(path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(AgentRegistryError, match="not found"):
        AgentRegistry.load(tmp_path / "nope.yaml")


def test_invalid_yaml(tmp_path: Path) -> None:
    path = _write(tmp_path / "bad.yaml", "{ not yaml")
    with pytest.raises(AgentRegistryError, match="Invalid YAML"):
        AgentRegistry.load(path)
