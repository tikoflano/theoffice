"""Split model "thinking" from user-visible assistant text.

Some models (e.g. Qwen via Groq) embed chain-of-thought in ``<redacted_thinking>`` …
``</redacted_thinking>`` or ``<thinking>`` … ``</thinking>`` inside the text stream.
Strands may also emit separate reasoning blocks. This module normalizes both into
optional *thinking* plus a clean *response* string.
"""

from __future__ import annotations

from typing import Any

from strands.agent.agent_result import AgentResult

# Open / close pairs (lowercased for matching). Order matters: try longer / more
# specific tags first.
_TAG_PAIRS: tuple[tuple[str, str], ...] = (
    ("<redacted_thinking>", "</redacted_thinking>"),
    ("<thinking>", "</thinking>"),
)

# Max tail of the buffer that might complete an opening tag (for streaming).
_MAX_OPEN_LEN = max(len(o) for o, _ in _TAG_PAIRS)


def split_xml_thinking(text: str) -> tuple[str | None, str]:
    """Remove well-formed thinking XML wrappers from *text*.

    Returns ``(thinking_or_none, visible)``. If multiple segments match, their
    inner content is joined with newlines. Unclosed tags leave the tail in
    *visible* unchanged (safe for incremental buffering).
    """
    if not text:
        return None, ""

    thinking_parts: list[str] = []
    out: list[str] = []
    i = 0
    lower = text.lower()

    while i < len(text):
        start_rel = None
        open_len = 0
        close_open = ""
        close_len = 0
        for open_t, close_t in _TAG_PAIRS:
            olen = len(open_t)
            pos = lower.find(open_t, i)
            if pos >= 0 and (start_rel is None or pos < start_rel):
                start_rel = pos
                open_len = olen
                close_open = close_t
                close_len = len(close_t)

        if start_rel is None:
            out.append(text[i:])
            break

        out.append(text[i:start_rel])
        j = start_rel + open_len
        close_rel = lower.find(close_open, j)
        if close_rel < 0:
            # Incomplete segment: keep from open tag onward in visible tail.
            out.append(text[start_rel:])
            break
        inner = text[j:close_rel]
        if inner.strip():
            thinking_parts.append(inner.strip())
        i = close_rel + close_len

    visible = "".join(out).strip()
    thinking = "\n\n".join(thinking_parts) if thinking_parts else None
    return thinking, visible


def _reasoning_text_from_block(block: dict[str, Any]) -> str | None:
    rc = block.get("reasoningContent")
    if not isinstance(rc, dict):
        return None
    rt = rc.get("reasoningText")
    if not isinstance(rt, dict):
        return None
    t = rt.get("text")
    if isinstance(t, str) and t.strip():
        return t.strip()
    return None


def partition_agent_result(result: AgentResult) -> tuple[str | None, str]:
    """Return ``(thinking, response)`` for HTTP / streaming consumers."""
    if not isinstance(result, AgentResult):
        return None, str(result).strip()

    if result.interrupts:
        return None, str(result)

    if result.structured_output is not None:
        return None, str(result)

    message = result.message
    if not isinstance(message, dict):
        return None, str(result).strip()

    content = message.get("content")
    if not isinstance(content, list):
        return split_xml_thinking(str(result).strip())

    thinking_chunks: list[str] = []
    response_chunks: list[str] = []

    for block in content:
        if not isinstance(block, dict):
            continue
        rt = _reasoning_text_from_block(block)
        if rt is not None:
            thinking_chunks.append(rt)
            continue
        if "text" in block and block["text"]:
            t = str(block["text"])
            xml_think, vis = split_xml_thinking(t)
            if xml_think:
                thinking_chunks.append(xml_think)
            if vis:
                response_chunks.append(vis)
            continue
        cc = block.get("citationsContent")
        if isinstance(cc, dict):
            for item in cc.get("content") or []:
                if isinstance(item, dict) and item.get("text"):
                    response_chunks.append(str(item["text"]))

    thinking_combined = "\n\n".join(thinking_chunks) if thinking_chunks else None
    response = "\n".join(response_chunks).strip()

    # If nothing walked (unexpected shape), fall back to legacy string + split.
    if thinking_combined is None and not response:
        raw = str(result).strip()
        if not raw:
            # Same fallback as text_from_agent_result for empty str case
            for block in content:
                if not isinstance(block, dict):
                    continue
                rt = _reasoning_text_from_block(block)
                if rt:
                    thinking_chunks.append(rt)
            thinking_combined = "\n\n".join(thinking_chunks) if thinking_chunks else None
            return thinking_combined, ""
        return split_xml_thinking(raw)

    return thinking_combined, response


class ThinkingStreamSplitter:
    """Incremental splitter for thinking tags inside a single text delta stream."""

    __slots__ = ("_buf", "_phase", "_open", "_close")

    def __init__(self) -> None:
        self._buf = ""
        self._phase: str = "response"  # "response" | "thinking"
        self._open: str | None = None
        self._close: str | None = None

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        """Return list of ``(phase, delta)`` with phase ``thinking`` or ``response``."""
        if not chunk:
            return []
        self._buf += chunk
        emitted: list[tuple[str, str]] = []

        while self._buf:
            if self._phase == "response":
                low = self._buf.lower()
                earliest: tuple[int, str, str] | None = None
                for open_t, close_t in _TAG_PAIRS:
                    pos = low.find(open_t)
                    if pos >= 0 and (earliest is None or pos < earliest[0]):
                        earliest = (pos, open_t, close_t)

                if earliest is None:
                    # Hold suffix that could be start of an open tag.
                    if len(self._buf) <= _MAX_OPEN_LEN:
                        break
                    emit_len = len(self._buf) - _MAX_OPEN_LEN
                    head, self._buf = self._buf[:emit_len], self._buf[emit_len:]
                    if head:
                        emitted.append(("response", head))
                    continue

                pos, open_t, close_t = earliest
                prefix = self._buf[:pos]
                if prefix:
                    emitted.append(("response", prefix))
                self._buf = self._buf[pos + len(open_t) :]
                self._phase = "thinking"
                self._open = open_t
                self._close = close_t
                continue

            # thinking phase
            assert self._close is not None
            low = self._buf.lower()
            close_t = self._close
            cpos = low.find(close_t)
            if cpos < 0:
                if len(self._buf) <= len(close_t):
                    break
                emit_len = len(self._buf) - len(close_t)
                head, self._buf = self._buf[:emit_len], self._buf[emit_len:]
                if head:
                    emitted.append(("thinking", head))
                continue

            thinking_body = self._buf[:cpos]
            if thinking_body:
                emitted.append(("thinking", thinking_body))
            self._buf = self._buf[cpos + len(close_t) :]
            self._phase = "response"
            self._open = None
            self._close = None

        return emitted

    def flush(self) -> list[tuple[str, str]]:
        """Flush remaining buffer (call when the model stream ends)."""
        if not self._buf:
            return []
        phase = self._phase
        rest = self._buf
        self._buf = ""
        return [(phase, rest)] if rest else []
