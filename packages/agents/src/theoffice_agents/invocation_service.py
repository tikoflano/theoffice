"""Orchestrate registry lookup, model resolution, and Strands invocation."""

from __future__ import annotations

import logging
import re
from typing import Any

from litellm.exceptions import APIConnectionError
from starlette.responses import JSONResponse
from strands import Agent
from strands.handlers.callback_handler import null_callback_handler

from theoffice_agents.agent_result_text import text_from_agent_result
from theoffice_agents.http_errors import api_error_response
from theoffice_agents.invocation import InvocationParser, InvocationValidationError
from theoffice_agents.model_factory import LiteLLMModelFactory
from theoffice_agents.model_resolution import (
    ModelNotConfiguredError,
    ModelResolver,
    UnresolvedModelError,
    UnsupportedProviderError,
)
from theoffice_agents.registry import AgentRegistry

logger = logging.getLogger(__name__)


class InvocationService:
    """Application service for one AgentCore invocation."""

    def __init__(
        self,
        registry: AgentRegistry,
        resolver: ModelResolver,
        factory: LiteLLMModelFactory,
    ) -> None:
        self._registry = registry
        self._resolver = resolver
        self._factory = factory
        self._parser = InvocationParser()

    def invoke_sync_outcome(
        self,
        payload: dict[str, Any],
        *,
        session_id: str | None,
    ) -> dict[str, Any] | JSONResponse:
        """Return success dict or a Starlette ``JSONResponse`` for API errors."""

        try:
            req = self._parser.parse(payload)
        except InvocationValidationError as e:
            details: dict[str, Any] = {}
            if e.field:
                details["field"] = e.field
            return api_error_response(
                422,
                code="VALIDATION_ERROR",
                message=str(e),
                details=details,
            )

        agent_def = self._registry.get(req.agent_id)
        if agent_def is None:
            return api_error_response(
                422,
                code="VALIDATION_ERROR",
                message=f"Unknown agent: {req.agent_id!r}",
                details={"field": "agent"},
            )

        try:
            resolved = self._resolver.resolve(
                agent_default_model=agent_def.default_model,
                model_override=req.model_override,
            )
        except UnresolvedModelError as e:
            return api_error_response(
                422,
                code="VALIDATION_ERROR",
                message=str(e),
                details={"reason": "UNRESOLVED_MODEL"},
            )
        except UnsupportedProviderError as e:
            return api_error_response(
                422,
                code="VALIDATION_ERROR",
                message=(
                    f"Model id {e.model_id!r} uses an unsupported provider prefix "
                    "for this deployment"
                ),
                details={
                    "model_id": e.model_id,
                    "reason": "UNSUPPORTED_PROVIDER",
                },
            )
        except ModelNotConfiguredError as e:
            return api_error_response(
                501,
                code="MODEL_NOT_CONFIGURED",
                message=(
                    "The requested model is not set up properly on this server "
                    "(missing environment variables)."
                ),
                details={
                    "resolved_model": e.resolved_model,
                    "missing_environment_variables": e.missing_environment_variables,
                },
            )

        try:
            model = self._factory.get(resolved.model_id)
            agent = Agent(
                model=model,
                name=req.agent_id,
                system_prompt=agent_def.system_prompt,
                callback_handler=null_callback_handler,
            )
            logger.info(
                "Invocation running",
                extra={"agent": req.agent_id, "model": resolved.model_id},
            )
            result = agent(req.prompt)
        except APIConnectionError as e:
            logger.exception("Upstream LLM connection failed")
            hint = str(e).strip().split("\n", 1)[0]
            hint = re.sub(r"\x1b\[[0-9;]*m", "", hint)[:500]
            return api_error_response(
                502,
                code="UPSTREAM_UNAVAILABLE",
                message=(
                    "Could not reach the model provider. "
                    "For ollama/ models, check OLLAMA_API_BASE and that Ollama is reachable."
                ),
                details={"provider_error": hint},
            )
        except Exception:
            logger.exception("Invocation failed")
            return api_error_response(
                500,
                code="INTERNAL_ERROR",
                message="An unexpected error occurred while running the agent.",
                details={},
            )

        out: dict[str, Any] = {
            "response": text_from_agent_result(result),
            "stop_reason": result.stop_reason,
            "agent": req.agent_id,
            "model": resolved.model_id,
        }
        if session_id:
            out["session_id"] = session_id
        return out
