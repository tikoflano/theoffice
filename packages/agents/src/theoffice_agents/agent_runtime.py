"""Bedrock AgentCore HTTP runtime with a Strands agent entrypoint."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from bedrock_agentcore import BedrockAgentCoreApp, RequestContext
from strands import Agent
from strands.handlers.callback_handler import null_callback_handler
from theoffice_agents.logger import Logger, logger

from dotenv import find_dotenv, load_dotenv

from theoffice_agents.strands_setup import build_ollama_model


def _extract_prompt(payload: dict[str, Any]) -> str:
    """Resolve user text from an invocation JSON body."""
    for key in ("prompt", "input", "message", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    nested = payload.get("input")
    if isinstance(nested, dict):
        for key in ("text", "prompt", "message"):
            value = nested.get(key)
            if isinstance(value, str) and value.strip():
                return value
    raise ValueError(
        "Request body must include a non-empty string in one of: "
        "prompt, input, message, text (or input.text / input.prompt)."
    )


def _invocation_result(
    agent: Agent, payload: dict[str, Any], context: RequestContext
) -> dict[str, Any]:
    prompt = _extract_prompt(payload)
    logger.info("Invocation prompt received", extra={"prompt": prompt})
    result = agent(prompt)
    out: dict[str, Any] = {
        "response": str(result).strip(),
        "stop_reason": result.stop_reason,
    }
    if context.session_id:
        out["session_id"] = context.session_id
    return out


@asynccontextmanager
async def _lifespan(app: BedrockAgentCoreApp) -> AsyncIterator[None]:
    logger.info("AgentCore startup: loading Strands Ollama model")
    app.state.model = build_ollama_model()
    logger.info("AgentCore startup: model loaded",
                extra={"model": app.state.model})
    yield
    logger.info("AgentCore shutdown")


def create_app() -> BedrockAgentCoreApp:
    """Build the AgentCore Starlette app with Strands and lifecycle hooks."""
    app = BedrockAgentCoreApp(lifespan=_lifespan)

    @app.async_task
    async def run_invocation(
        payload: dict[str, Any], context: RequestContext
    ) -> dict[str, Any]:
        logger.info("Invocation received")
        model = app.state.model
        agent = Agent(
            model=model,
            name="theoffice",
            system_prompt="You are a concise, helpful assistant.",
            callback_handler=null_callback_handler,
        )
        logger.info("Agent created")
        return await asyncio.to_thread(_invocation_result, agent, payload, context)

    @app.entrypoint
    async def invoke(
        payload: dict[str, Any], context: RequestContext
    ) -> dict[str, Any]:
        return await run_invocation(payload, context)

    return app


def run() -> None:
    load_dotenv(find_dotenv(usecwd=False))
    Logger().init()
    port = int(os.environ.get("AGENT_PORT", "8080"))
    host = os.environ.get("AGENT_HOST")
    app = create_app()
    app.run(port=port, host=host)
