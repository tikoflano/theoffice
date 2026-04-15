"""Bedrock AgentCore HTTP runtime with multi-agent Strands + LiteLLM."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from bedrock_agentcore import BedrockAgentCoreApp, RequestContext
from starlette.responses import JSONResponse

from theoffice_agents.invocation_service import InvocationService
from theoffice_agents.logger import Logger, logger
from theoffice_agents.model_factory import LiteLLMModelFactory
from theoffice_agents.model_resolution import ModelResolver
from theoffice_agents.registry import AgentRegistry, AgentRegistryError, default_registry_path

from dotenv import find_dotenv, load_dotenv


def _registry_path_from_env() -> Path:
    raw = (os.environ.get("AGENTS_REGISTRY_PATH") or "").strip()
    return Path(raw).expanduser() if raw else default_registry_path()


@asynccontextmanager
async def _lifespan(app: BedrockAgentCoreApp) -> AsyncIterator[None]:
    path = _registry_path_from_env()
    logger.info("AgentCore startup: loading agent registry", extra={"path": str(path)})
    try:
        registry = AgentRegistry.load(path)
    except AgentRegistryError as e:
        logger.exception("Agent registry failed to load")
        raise SystemExit(1) from e

    resolver = ModelResolver(os.environ)
    factory = LiteLLMModelFactory()
    app.state.service = InvocationService(registry, resolver, factory)
    logger.info(
        "AgentCore startup: registry loaded",
        extra={"agent_count": len(registry)},
    )
    yield
    logger.info("AgentCore shutdown")


def _run_invocation_sync(
    app: BedrockAgentCoreApp,
    payload: dict[str, Any],
    context: RequestContext,
) -> dict[str, Any] | JSONResponse:
    service: InvocationService = app.state.service
    return service.invoke_sync_outcome(
        payload,
        session_id=context.session_id,
    )


def create_app() -> BedrockAgentCoreApp:
    """Build the AgentCore Starlette app with Strands and lifecycle hooks."""
    app = BedrockAgentCoreApp(lifespan=_lifespan)

    @app.async_task
    async def run_invocation(
        payload: dict[str, Any], context: RequestContext
    ) -> dict[str, Any] | JSONResponse:
        logger.info("Invocation received")
        return await asyncio.to_thread(_run_invocation_sync, app, payload, context)

    async def streaming_invoke(
        payload: dict[str, Any], context: RequestContext
    ):
        task_id = app.add_async_task("invocation_stream")
        try:
            service: InvocationService = app.state.service
            async for item in service.stream_invocation_events(
                payload,
                session_id=context.session_id,
            ):
                yield item
        finally:
            app.complete_async_task(task_id)

    @app.entrypoint
    async def invoke(
        payload: dict[str, Any], context: RequestContext
    ) -> dict[str, Any] | JSONResponse:
        if isinstance(payload, dict) and payload.get("stream"):
            return streaming_invoke(payload, context)
        return await run_invocation(payload, context)

    return app


def run() -> None:
    load_dotenv(find_dotenv(usecwd=False))
    Logger().init()
    port = int(os.environ.get("AGENT_PORT", "8080"))
    host = os.environ.get("AGENT_HOST")
    app = create_app()
    app.run(port=port, host=host)
