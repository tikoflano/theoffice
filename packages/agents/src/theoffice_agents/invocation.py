"""Parse and validate AgentCore invocation JSON bodies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InvocationRequest:
    """Validated invocation input (after JSON parse)."""

    agent_id: str
    prompt: str
    model_override: str | None


class InvocationValidationError(ValueError):
    """Payload fails API validation (maps to HTTP 422)."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class InvocationParser:
    """Extract ``InvocationRequest`` from a decoded JSON object."""

    def parse(self, payload: dict[str, Any]) -> InvocationRequest:
        if not isinstance(payload, dict):
            raise InvocationValidationError("Body must be a JSON object")

        agent = payload.get("agent")
        if not isinstance(agent, str) or not agent.strip():
            raise InvocationValidationError(
                "Field 'agent' is required and must be a non-empty string",
                field="agent",
            )

        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise InvocationValidationError(
                "Field 'prompt' is required and must be a non-empty string",
                field="prompt",
            )

        raw_model = payload.get("model")
        model_override: str | None
        if raw_model is None:
            model_override = None
        elif isinstance(raw_model, str) and raw_model.strip():
            model_override = raw_model.strip()
        elif isinstance(raw_model, str):
            model_override = None
        else:
            raise InvocationValidationError(
                "Field 'model' must be a string when provided",
                field="model",
            )

        return InvocationRequest(
            agent_id=agent.strip(),
            prompt=prompt.strip(),
            model_override=model_override,
        )
