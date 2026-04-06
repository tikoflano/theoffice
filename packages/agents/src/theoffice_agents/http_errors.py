"""Structured API error responses (AgentCore /invocations)."""

from __future__ import annotations

from typing import Any

from starlette.responses import JSONResponse


def api_error_response(
    status_code: int,
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "details": details if details is not None else {},
        }
    }
    return JSONResponse(body, status_code=status_code)
