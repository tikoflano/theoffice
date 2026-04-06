"""Resolve effective LiteLLM model id and validate provider environment."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelResolution:
    """Resolved LiteLLM ``model_id`` string ready for the model factory."""

    model_id: str


class UnresolvedModelError(Exception):
    """No model could be resolved from env, agent, and invocation (HTTP 422)."""


class UnsupportedProviderError(Exception):
    """Model id does not use a supported provider prefix (HTTP 422)."""

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        super().__init__(f"Unsupported provider for model id: {model_id!r}")


class ModelNotConfiguredError(Exception):
    """Resolved model needs env vars that are missing or empty (HTTP 501)."""

    def __init__(
        self,
        resolved_model: str,
        missing_environment_variables: list[str],
    ) -> None:
        self.resolved_model = resolved_model
        self.missing_environment_variables = missing_environment_variables
        super().__init__(
            f"Model {resolved_model!r} is missing: {missing_environment_variables}"
        )


# Longest prefix first so e.g. custom providers can be added without shadowing bugs.
_KNOWN_PREFIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("anthropic/", ("ANTHROPIC_API_KEY",)),
    ("groq/", ("GROQ_API_KEY",)),
    # LiteLLM defaults to http://localhost:11434, which fails in Docker/host setups.
    # Require explicit OLLAMA_API_BASE; see model_factory.
    ("ollama/", ()),
    ("openai/", ("OPENAI_API_KEY",)),
)


class ModelResolver:
    """Apply spec resolution order and provider env preflight."""

    def __init__(self, environ: Mapping[str, str]) -> None:
        self._environ = environ

    def resolve(
        self,
        *,
        agent_default_model: str | None,
        model_override: str | None,
    ) -> ModelResolution:
        m: str | None = None
        if env_default := (self._environ.get("DEFAULT_LLM_MODEL") or "").strip():
            m = env_default
        if agent_default_model and agent_default_model.strip():
            m = agent_default_model.strip()
        if model_override and model_override.strip():
            m = model_override.strip()

        if not m:
            raise UnresolvedModelError(
                "No model resolved from DEFAULT_LLM_MODEL, agent default_model, or request model"
            )

        prefix = _matching_prefix(m)
        if prefix is None:
            raise UnsupportedProviderError(m)

        required = _required_vars_for_prefix(prefix)
        missing = [k for k in required if not (self._environ.get(k) or "").strip()]
        if prefix == "ollama/":
            if not (self._environ.get("OLLAMA_API_BASE") or "").strip():
                missing = ["OLLAMA_API_BASE"]
        if missing:
            raise ModelNotConfiguredError(m, missing)

        return ModelResolution(model_id=m)


def _matching_prefix(model_id: str) -> str | None:
    lower = model_id.lower()
    for prefix, _ in _KNOWN_PREFIXES:
        if lower.startswith(prefix):
            return prefix
    return None


def _required_vars_for_prefix(prefix: str) -> tuple[str, ...]:
    for p, vars_ in _KNOWN_PREFIXES:
        if p == prefix:
            return vars_
    return ()
