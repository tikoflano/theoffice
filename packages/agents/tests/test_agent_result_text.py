"""Tests for ``text_from_agent_result``."""

from __future__ import annotations

from strands.agent.agent_result import AgentResult
from strands.telemetry.metrics import EventLoopMetrics

from theoffice_agents.agent_result_text import text_from_agent_result


def test_prefers_str_when_non_empty() -> None:
    r = AgentResult(
        stop_reason="end_turn",
        message={"role": "assistant", "content": [{"text": "Hello."}]},
        metrics=EventLoopMetrics(),
        state={},
    )
    assert text_from_agent_result(r) == "Hello."


def test_fallback_reasoning_content() -> None:
    r = AgentResult(
        stop_reason="end_turn",
        message={
            "role": "assistant",
            "content": [
                {
                    "reasoningContent": {
                        "reasoningText": {"text": "Visible reasoning line."},
                    }
                }
            ],
        },
        metrics=EventLoopMetrics(),
        state={},
    )
    assert "Visible reasoning" in text_from_agent_result(r)
