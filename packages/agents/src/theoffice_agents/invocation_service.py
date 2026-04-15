"""Orchestrate registry lookup, model resolution, and Strands invocation."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from litellm.exceptions import APIConnectionError
from starlette.responses import JSONResponse
from strands import Agent
from strands.handlers.callback_handler import null_callback_handler

from theoffice_agents.http_errors import api_error_response
from theoffice_agents.invocation import InvocationParser, InvocationRequest, InvocationValidationError
from theoffice_agents.model_factory import LiteLLMModelFactory
from theoffice_agents.model_resolution import (
    ModelNotConfiguredError,
    ModelResolver,
    UnresolvedModelError,
    UnsupportedProviderError,
)
from theoffice_agents.registry import AgentDefinition, AgentRegistry
from theoffice_agents.thinking_response import ThinkingStreamSplitter, partition_agent_result

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ResolvedInvocation:
    req: InvocationRequest
    agent_def: AgentDefinition
    resolved_model_id: str


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

    def _validate_and_resolve(self, payload: dict[str, Any]) -> tuple[JSONResponse | None, _ResolvedInvocation | None]:
        try:
            req = self._parser.parse(payload)
        except InvocationValidationError as e:
            details: dict[str, Any] = {}
            if e.field:
                details["field"] = e.field
            return (
                api_error_response(
                    422,
                    code="VALIDATION_ERROR",
                    message=str(e),
                    details=details,
                ),
                None,
            )

        agent_def = self._registry.get(req.agent_id)
        if agent_def is None:
            return (
                api_error_response(
                    422,
                    code="VALIDATION_ERROR",
                    message=f"Unknown agent: {req.agent_id!r}",
                    details={"field": "agent"},
                ),
                None,
            )

        try:
            resolved = self._resolver.resolve(
                agent_default_model=agent_def.default_model,
                model_override=req.model_override,
            )
        except UnresolvedModelError as e:
            return (
                api_error_response(
                    422,
                    code="VALIDATION_ERROR",
                    message=str(e),
                    details={"reason": "UNRESOLVED_MODEL"},
                ),
                None,
            )
        except UnsupportedProviderError as e:
            return (
                api_error_response(
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
                ),
                None,
            )
        except ModelNotConfiguredError as e:
            return (
                api_error_response(
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
                ),
                None,
            )

        return None, _ResolvedInvocation(req, agent_def, resolved.model_id)

    def invoke_sync_outcome(
        self,
        payload: dict[str, Any],
        *,
        session_id: str | None,
    ) -> dict[str, Any] | JSONResponse:
        """Return success dict or a Starlette ``JSONResponse`` for API errors."""

        err, ctx = self._validate_and_resolve(payload)
        if err is not None:
            return err
        assert ctx is not None

        try:
            model = self._factory.get(ctx.resolved_model_id)
            agent = Agent(
                model=model,
                name=ctx.req.agent_id,
                system_prompt=ctx.agent_def.system_prompt,
                callback_handler=null_callback_handler,
            )
            logger.info(
                "Invocation running",
                extra={"agent": ctx.req.agent_id, "model": ctx.resolved_model_id},
            )
            result = agent(ctx.req.prompt)
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

        thinking, response = partition_agent_result(result)
        out: dict[str, Any] = {
            "response": response,
            "stop_reason": result.stop_reason,
            "agent": ctx.req.agent_id,
            "model": ctx.resolved_model_id,
        }
        if thinking is not None:
            out["thinking"] = thinking
        if session_id:
            out["session_id"] = session_id
        return out

    async def stream_invocation_events(
        self,
        payload: dict[str, Any],
        *,
        session_id: str | None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield SSE-ready dicts: ``start``, ``delta``, ``done``, or ``error``."""

        err, ctx = self._validate_and_resolve(payload)
        if err is not None:
            yield {
                "type": "error",
                "status_code": err.status_code,
                "body": err.body.decode(),
            }
            return
        assert ctx is not None

        yield {
            "type": "start",
            "agent": ctx.req.agent_id,
            "model": ctx.resolved_model_id,
        }

        splitter = ThinkingStreamSplitter()

        try:
            model = self._factory.get(ctx.resolved_model_id)
            agent = Agent(
                model=model,
                name=ctx.req.agent_id,
                system_prompt=ctx.agent_def.system_prompt,
                callback_handler=null_callback_handler,
            )
            logger.info(
                "Invocation streaming",
                extra={"agent": ctx.req.agent_id, "model": ctx.resolved_model_id},
            )
            saw_done = False
            async for event in agent.stream_async(ctx.req.prompt):
                if isinstance(event, dict) and "result" in event:
                    for phase, delta in splitter.flush():
                        if delta:
                            yield {"type": "delta", "phase": phase, "text": delta}
                    result = event["result"]
                    thinking, response = partition_agent_result(result)
                    done: dict[str, Any] = {
                        "type": "done",
                        "response": response,
                        "stop_reason": result.stop_reason,
                        "agent": ctx.req.agent_id,
                        "model": ctx.resolved_model_id,
                    }
                    if thinking is not None:
                        done["thinking"] = thinking
                    if session_id:
                        done["session_id"] = session_id
                    yield done
                    saw_done = True
                    break

                for phase, fragment in _strands_event_text_fragments(event):
                    if phase == "thinking" and fragment:
                        yield {"type": "delta", "phase": "thinking", "text": fragment}
                    elif phase == "response" and fragment:
                        for p, delta in splitter.feed(fragment):
                            if delta:
                                yield {"type": "delta", "phase": p, "text": delta}

            if not saw_done:
                logger.error("Model stream finished without a final AgentResult event")
                yield {
                    "type": "error",
                    "status_code": 500,
                    "code": "INTERNAL_ERROR",
                    "message": "Stream ended without a final result from the agent.",
                    "details": {},
                }

        except APIConnectionError as e:
            logger.exception("Upstream LLM connection failed (stream)")
            hint = str(e).strip().split("\n", 1)[0]
            hint = re.sub(r"\x1b\[[0-9;]*m", "", hint)[:500]
            yield {
                "type": "error",
                "status_code": 502,
                "code": "UPSTREAM_UNAVAILABLE",
                "message": (
                    "Could not reach the model provider. "
                    "For ollama/ models, check OLLAMA_API_BASE and that Ollama is reachable."
                ),
                "details": {"provider_error": hint},
            }
        except Exception:
            logger.exception("Invocation failed (stream)")
            yield {
                "type": "error",
                "status_code": 500,
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred while running the agent.",
                "details": {},
            }


def _strands_event_text_fragments(event: Any) -> list[tuple[str, str]]:
    """Extract (phase, text) from one Strands ``stream_async`` callback dict."""
    if not isinstance(event, dict):
        return []

    out: list[tuple[str, str]] = []

    if event.get("reasoning") and event.get("reasoningText") is not None:
        rt = event.get("reasoningText")
        if isinstance(rt, str) and rt:
            out.append(("thinking", rt))
        return out

    if "data" in event and isinstance(event["data"], str) and event["data"]:
        out.append(("response", event["data"]))
        return out

    raw = event.get("event")
    if not isinstance(raw, dict):
        return out

    delta_ev = raw.get("contentBlockDelta")
    if not isinstance(delta_ev, dict):
        return out

    delta = delta_ev.get("delta")
    if not isinstance(delta, dict):
        return out

    if "text" in delta and delta["text"]:
        out.append(("response", str(delta["text"])))

    rc = delta.get("reasoningContent")
    if isinstance(rc, dict):
        t = rc.get("text")
        if isinstance(t, str) and t:
            out.append(("thinking", t))

    return out
