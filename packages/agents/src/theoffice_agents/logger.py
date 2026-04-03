from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from bedrock_agentcore.runtime.app import RequestContextFormatter

_LOGRECORD_RESERVED: frozenset[str] = frozenset(
    logging.LogRecord(
        name="",
        level=logging.NOTSET,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__
) | frozenset({"message", "asctime"})


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    # str() and __str__() are equivalent here; explicit call documents intent for extras.
    return value.__str__()


def _record_extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {
        k: v
        for k, v in record.__dict__.items()
        if k not in _LOGRECORD_RESERVED and not k.startswith("_")
    }


class TheofficeLogFormatter(RequestContextFormatter):
    """AgentCore JSON lines plus any keys passed via ``logger.info(..., extra={...})``."""

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        extras = _record_extra_fields(record)
        if not extras:
            return line
        payload = json.loads(line)
        for key, value in extras.items():
            payload[key] = _json_safe(value)
        return json.dumps(payload, ensure_ascii=False)


class Logger:
    _instance: Logger | None = None

    def __new__(cls) -> Logger:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def init(self) -> None:
        if self._initialized:
            return
        level = getattr(
            logging,
            os.environ.get("LOG_LEVEL", "INFO").upper(),
            logging.INFO,
        )
        logger.setLevel(level)
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setLevel(level)
            handler.setFormatter(TheofficeLogFormatter())
            logger.addHandler(handler)
        logger.propagate = False
        self._initialized = True


logger = logging.getLogger("theoffice_agents")
