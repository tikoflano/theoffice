"""Load and query the static agent registry (YAML)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AgentDefinition:
    """One row from the agent registry."""

    id: str
    default_model: str | None
    system_prompt: str


class AgentRegistryError(Exception):
    """Invalid or unreadable registry file."""


class AgentRegistry:
    """In-memory registry keyed by agent id."""

    def __init__(self, agents: dict[str, AgentDefinition]) -> None:
        self._agents = agents

    @classmethod
    def load(cls, path: Path) -> AgentRegistry:
        if not path.is_file():
            raise AgentRegistryError(f"Agent registry file not found: {path}")
        try:
            raw = path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise AgentRegistryError(f"Invalid YAML in registry: {path}") from e
        except OSError as e:
            raise AgentRegistryError(f"Cannot read registry: {path}") from e

        if not isinstance(data, dict) or "agents" not in data:
            raise AgentRegistryError("Registry root must be a mapping with an 'agents' list")
        agents_list = data["agents"]
        if not isinstance(agents_list, list):
            raise AgentRegistryError("'agents' must be a list")

        by_id: dict[str, AgentDefinition] = {}
        for i, row in enumerate(agents_list):
            if not isinstance(row, dict):
                raise AgentRegistryError(f"agents[{i}] must be a mapping")
            agent = _parse_agent_row(row, index=i)
            if agent.id in by_id:
                raise AgentRegistryError(f"Duplicate agent id: {agent.id!r}")
            by_id[agent.id] = agent
        return cls(by_id)

    def get(self, agent_id: str) -> AgentDefinition | None:
        return self._agents.get(agent_id)

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._agents

    def __len__(self) -> int:
        return len(self._agents)


def _parse_agent_row(row: dict[str, Any], *, index: int) -> AgentDefinition:
    aid = row.get("id")
    if not isinstance(aid, str) or not aid.strip():
        raise AgentRegistryError(f"agents[{index}].id must be a non-empty string")

    sp = row.get("system_prompt")
    if not isinstance(sp, str) or not sp.strip():
        raise AgentRegistryError(
            f"agents[{index}].system_prompt must be a non-empty string"
        )

    dm = row.get("default_model")
    default_model: str | None
    if dm is None:
        default_model = None
    elif isinstance(dm, str) and dm.strip():
        default_model = dm.strip()
    elif isinstance(dm, str):
        default_model = None
    else:
        raise AgentRegistryError(
            f"agents[{index}].default_model must be a string or omitted"
        )

    return AgentDefinition(id=aid.strip(), default_model=default_model, system_prompt=sp)


def default_registry_path() -> Path:
    """Path to packaged ``agents.yaml`` next to this module."""
    return Path(__file__).resolve().parent / "agents.yaml"
