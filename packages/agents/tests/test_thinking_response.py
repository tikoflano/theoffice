"""Tests for thinking vs visible response splitting."""

from __future__ import annotations

from strands.agent.agent_result import AgentResult
from strands.telemetry.metrics import EventLoopMetrics

from theoffice_agents.thinking_response import (
    ThinkingStreamSplitter,
    partition_agent_result,
    split_xml_thinking,
)


def test_split_xml_redacted() -> None:
    thinking, visible = split_xml_thinking(
        "<redacted_thinking>\nstep one\n</redacted_thinking>\n\nHello, world."
    )
    assert thinking == "step one"
    assert visible == "Hello, world."


def test_split_xml_thinking_short_tag() -> None:
    thinking, visible = split_xml_thinking("<thinking>plan</thinking>Answer.")
    assert thinking == "plan"
    assert visible == "Answer."


def test_stream_splitter_across_chunks() -> None:
    sp = ThinkingStreamSplitter()
    acc: list[tuple[str, str]] = []
    acc += sp.feed("<redacted_th")
    acc += sp.feed("inking>inside</redacted_thinking>")
    acc += sp.feed("\n\nOut.")
    acc += sp.flush()
    assert ("thinking", "inside") in acc
    response_text = "".join(t for ph, t in acc if ph == "response")
    assert "Out." in response_text


def test_partition_reasoning_block() -> None:
    r = AgentResult(
        stop_reason="end_turn",
        message={
            "role": "assistant",
            "content": [
                {
                    "reasoningContent": {
                        "reasoningText": {"text": "internal"},
                    }
                },
                {"text": "Hi."},
            ],
        },
        metrics=EventLoopMetrics(),
        state={},
    )
    thinking, response = partition_agent_result(r)
    assert thinking == "internal"
    assert response == "Hi."


def test_partition_xml_inside_text() -> None:
    r = AgentResult(
        stop_reason="end_turn",
        message={
            "role": "assistant",
            "content": [
                {
                    "text": (
                        "<redacted_thinking>\nreasoning here\n</redacted_thinking>\n\n"
                        "Final answer."
                    ),
                },
            ],
        },
        metrics=EventLoopMetrics(),
        state={},
    )
    thinking, response = partition_agent_result(r)
    assert thinking == "reasoning here"
    assert response == "Final answer."
